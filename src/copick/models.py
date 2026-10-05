import json
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Literal, Optional, Tuple, Type, Union

import numpy as np
import zarr
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_serializer, model_validator
from zarr.abc.store import Store

from copick.util.escape import sanitize_name
from copick.util.filaments import (
    CURVE_KINDS,
    check_curve,
    control_points_from_polyline,
    curve_anchors,
    curve_is_current,
    evaluate_curve,
    median_spacing,
    reverse_knots,
)
from copick.util.log import get_logger
from copick.util.ome import (
    DEFAULT_SPATIAL_CHUNKS,
    fits_in_memory,
    get_level_path,
    initialize_zarr_v3,
    ome_zarr_axes,
    padded_shard_shape,
    segmentation_pyramid,
    volume_pyramid,
    write_ome_zarr,
    write_ome_zarr_3d,
)
from copick.util.relion import picks_to_df_relion, relion_df_to_picks
from copick.util.segmentation import (
    PANOPTIC_CHANNELS,
    RESERVED_NAME_SUFFIXES,
    check_panoptic_values,
    checked_label_cast,
    label_dtype,
    panoptic_channel_index,
    segmentation_directory,
    segmentation_type,
)

# Don't import Geometry at runtime to keep CLI snappy
if TYPE_CHECKING:
    import pandas as pd
    from trimesh.parent import Geometry

logger = get_logger(__name__)


def _open_zarr_array(loc: Store, zarr_group: Optional[str], mode: Literal["r", "r+"]) -> zarr.Array:
    """Open an explicitly named array or resolve the first OME pyramid level."""
    if mode == "r":
        root_group = zarr.open(loc, mode="r")
    elif mode == "r+":
        root_group = zarr.open(loc, mode="r+")
    else:
        raise ValueError(f"Unsupported Zarr array access mode: {mode}")
    array_path = zarr_group if zarr_group is not None else get_level_path(root_group, 0)
    return root_group[array_path]


#: Key in ``PickableObject.metadata`` reserved for copick's own extensions of the object spec.
COPICK_METADATA_NAMESPACE = "copick"
#: Key in the reserved namespace that declares an object to be a filament (see ``FilamentSpec``).
FILAMENT_METADATA_KEY = "filament"


class FilamentSpec(BaseModel):
    """Declares a pickable object to be a filament: a continuous, typically helical or tubular assembly
    (e.g. microtubules, actin) that is annotated with ordered points along its axis.

    Stored on the object as ``metadata["copick"]["filament"]`` (plain JSON), so clients that do not know
    filaments read the object as an ordinary particle and preserve the declaration when they rewrite a
    configuration. Picks of a filament object follow the filament pick conventions: ``instance_id`` is the
    filament ID (starting at 1, 0 = unassigned), points are grouped by filament and ordered along it, and
    the transform's +Z axis is the local tangent in point order.

    Attributes:
        polar: Whether the structure has a polarity (True for microtubules and actin). None if not stated.
        helical_rise_a: Axial rise per subunit in Angstrom. Descriptive only: it is never used as a default
            sampling distance along the filament.
        helical_twist_deg: Twist per subunit in degrees. Descriptive only.
    """

    model_config = ConfigDict(extra="allow")

    polar: Optional[bool] = None
    helical_rise_a: Optional[float] = Field(None, gt=0)
    helical_twist_deg: Optional[float] = None


def _metadata_with_filament(
    metadata: Optional[Dict[str, Any]],
    filament: Union["FilamentSpec", Dict[str, Any], None],
) -> Dict[str, Any]:
    """Return a copy of ``metadata`` with ``filament`` stored under the reserved key, or removed if None."""
    metadata = dict(metadata or {})
    namespace = metadata.get(COPICK_METADATA_NAMESPACE, {})
    if not isinstance(namespace, dict):
        raise ValueError(
            f"metadata[{COPICK_METADATA_NAMESPACE!r}] holds a non-dict value; copick reserves this key for its own "
            "object spec extensions.",
        )
    namespace = dict(namespace)
    if filament is None:
        namespace.pop(FILAMENT_METADATA_KEY, None)
    else:
        spec = filament if isinstance(filament, FilamentSpec) else FilamentSpec.model_validate(filament)
        namespace[FILAMENT_METADATA_KEY] = spec.model_dump(exclude_none=True)
    if namespace:
        metadata[COPICK_METADATA_NAMESPACE] = namespace
    else:
        metadata.pop(COPICK_METADATA_NAMESPACE, None)
    return metadata


class PickableObject(BaseModel):
    """Metadata for a pickable objects.

    Attributes:
        name: Name of the object.
        is_particle: Whether this object should be represented by points (True) or segmentation masks (False).
        label: Numeric label/id for the object, as used in multilabel segmentation masks. Must be unique.
        color: RGBA color for the object.
        emdb_id: EMDB ID for the object.
        pdb_id: PDB ID for the object.
        identifier: Identifier for the object, drawn from an ontology/database namespace
            (GO, UniProtKB, CHEBI, PDB [dash separator, e.g. ``PDB-1BXN``], UBERON, CL, or CDPO).
            When using the data portal, this must match the annotation ``object_id`` exactly.
        map_threshold: Threshold to apply to the map when rendering the isosurface.
        radius: Radius of the particle, when displaying as a sphere. For a filament, the tube radius.
        metadata: Additional metadata for the object (user-defined contents). The key ``"copick"`` is reserved
            for copick's own extensions of the object spec; ``metadata["copick"]["filament"]`` declares the
            object a filament (see ``FilamentSpec``) and is validated when present.
    """

    name: str
    is_particle: bool
    label: Optional[int] = 1
    color: Optional[Tuple[int, int, int, int]] = (100, 100, 100, 255)
    emdb_id: Optional[str] = None
    pdb_id: Optional[str] = None
    identifier: Optional[str] = Field(None, alias=AliasChoices("go_id", "identifier"))
    map_threshold: Optional[float] = None
    radius: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)

    @property
    def go_id(self):
        return self.identifier

    @go_id.setter
    def go_id(self, value: str) -> None:
        self.identifier = value

    @field_validator("label")
    @classmethod
    def validate_label(cls, v) -> int:
        """Validate the label."""
        assert v != 0, "Label 0 is reserved for background."
        return v

    @field_validator("color")
    @classmethod
    def validate_color(cls, v) -> Tuple[int, int, int, int]:
        """Validate the color."""
        assert len(v) == 4, "Color must be a 4-tuple (RGBA)."
        assert all(0 <= c <= 255 for c in v), "Color values must be in the range [0, 255]."
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v) -> Optional[str]:
        """Validate the name."""
        if v != sanitize_name(v):
            raise ValueError(f"Name '{v}' contains invalid characters. Use copick.escape.sanitize_name() to clean it.")
        return v

    @field_validator("metadata", mode="before")
    @classmethod
    def none_to_empty_dict(cls, v):
        return {} if v is None else v

    @model_validator(mode="after")
    def validate_filament_spec(self) -> "PickableObject":
        """Validate and normalise ``metadata["copick"]["filament"]`` when it is present.

        Only that key is checked: any other content of the metadata, including a non-dict value under
        ``"copick"`` written before the key was reserved, is left as it is.
        """
        namespace = self.metadata.get(COPICK_METADATA_NAMESPACE)
        if not isinstance(namespace, dict) or namespace.get(FILAMENT_METADATA_KEY) is None:
            return self
        spec = FilamentSpec.model_validate(namespace[FILAMENT_METADATA_KEY])
        if not self.is_particle:
            raise ValueError(
                f"Object '{self.name}' is declared a filament but is_particle is False; filaments are annotated "
                "with points, so is_particle must be True.",
            )
        self.metadata = {
            **self.metadata,
            COPICK_METADATA_NAMESPACE: {**namespace, FILAMENT_METADATA_KEY: spec.model_dump(exclude_none=True)},
        }
        return self

    @property
    def filament(self) -> Optional[FilamentSpec]:
        """The filament declaration of this object, or None if it is not a filament."""
        namespace = self.metadata.get(COPICK_METADATA_NAMESPACE)
        if isinstance(namespace, dict) and namespace.get(FILAMENT_METADATA_KEY) is not None:
            return FilamentSpec.model_validate(namespace[FILAMENT_METADATA_KEY])
        return None

    @property
    def is_filament(self) -> bool:
        """Whether this object is declared a filament."""
        return self.filament is not None

    def set_filament(self, filament: Union[FilamentSpec, Dict[str, Any], None]) -> None:
        """Declare this object a filament, update its declaration, or remove it (``filament=None``).

        Args:
            filament: The filament spec, as a ``FilamentSpec`` or a dict of its fields, or None.

        Raises:
            ValueError: If the spec is invalid, the object is not a particle, or ``metadata["copick"]`` holds a
                non-dict value.
        """
        metadata = _metadata_with_filament(self.metadata, filament)
        validated = type(self).model_validate({**self.model_dump(), "metadata": metadata})
        self.metadata = validated.metadata


class CopickConfig(BaseModel):
    """Configuration for a copick project. Defines the available objects, user_id and optionally an index for runs.

    Attributes:
        name: Name of the CoPick project.
        description: Description of the CoPick project.
        version: Version of the CoPick API.
        pickable_objects (List[PickableObject]): Index for available pickable objects.
        user_id: Unique identifier for the user (e.g. when distributing the config file to users).
        session_id: Unique identifier for the session.
        voxel_spacings: Index for available voxel spacings.
        runs: Index for run names.
        tomograms: Index for available voxel spacings and tomogram types.
    """

    name: Optional[str] = "CoPick"
    description: Optional[str] = "Let's CoPick!"
    version: Optional[str] = "0.2.0"
    pickable_objects: List[PickableObject]
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    runs: Optional[List[str]] = None
    voxel_spacings: Optional[List[float]] = None
    tomograms: Optional[Dict[float, List[str]]] = {}

    @classmethod
    def from_file(cls, filename: str) -> "CopickConfig":
        """
        Load a CopickConfig from a file and create a CopickConfig object.

        Args:
            filename: path to the file

        Returns:
            CopickConfig: Initialized CopickConfig object

        """
        with open(filename) as f:
            return cls(**json.load(f))

    @field_validator("user_id")
    @classmethod
    def validate_user_id(cls, v) -> Optional[str]:
        """Validate the user_id."""
        if v is not None and v != sanitize_name(v):
            raise ValueError(
                f"user_id '{v}' contains invalid characters. Use copick.escape.sanitize_name() to clean it.",
            )
        return v

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, v) -> Optional[str]:
        """Validate the session_id."""
        if v is not None and v != sanitize_name(v):
            raise ValueError(
                f"session_id '{v}' contains invalid characters. Use copick.escape.sanitize_name() to clean it.",
            )
        return v


class CopickLocation(BaseModel):
    """Location in 3D space.

    Attributes:
        x: x-coordinate.
        y: y-coordinate.
        z: z-coordinate.
    """

    x: float
    y: float
    z: float


class CopickPoint(BaseModel):
    """Point in 3D space with an associated orientation, score value and instance ID.

    Attributes:
        location (CopickLocation): Location in 3D space, in Angstrom.
        transformation: Transformation matrix from object space to tomogram space. Its translation is a shift in
            Angstrom added to the location: the particle centre is ``location + transformation[:3, 3]``.
        instance_id: Instance ID. For points of a filament object, the filament ID (starting at 1; 0 means
            unassigned).
        score: Score value.
    """

    location: CopickLocation
    transformation_: Optional[List[List[float]]] = [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]
    instance_id: Optional[int] = 0
    score: Optional[float] = 1.0

    model_config = {
        "arbitrary_types_allowed": True,
    }

    @field_validator("transformation_")
    @classmethod
    def validate_transformation(cls, v) -> List[List[float]]:
        """Validate the transformation matrix."""
        arr = np.array(v)
        assert arr.shape == (4, 4), "transformation must be a 4x4 matrix."
        assert arr[3, 3] == 1.0, "Last element of transformation matrix must be 1.0."
        assert np.allclose(arr[3, :], [0.0, 0.0, 0.0, 1.0]), "Last row of transformation matrix must be [0, 0, 0, 1]."
        return v

    @property
    def transformation(self) -> np.ndarray:
        """The transformation necessary to transform coordinates from the object space to the tomogram space.

        Returns:
            np.ndarray: 4x4 transformation matrix.
        """
        return np.array(self.transformation_)

    @transformation.setter
    def transformation(self, value: np.ndarray) -> None:
        """Set the transformation matrix."""
        assert value.shape == (4, 4), "Transformation must be a 4x4 matrix."
        assert value[3, 3] == 1.0, "Last element of transformation matrix must be 1.0."
        assert np.allclose(value[3, :], [0.0, 0.0, 0.0, 1.0]), "Last row of transformation matrix must be [0, 0, 0, 1]."
        self.transformation_ = value.tolist()


class CopickObject:
    """Object that can be picked or segmented in a tomogram.

    Attributes:
        meta (PickableObject): Metadata for this object.
        root (CopickRoot): Reference to the root this object belongs to.
        name: Name of the object.
        is_particle: Whether this object should be represented by points (True) or segmentation masks (False).
        label: Numeric label/id for the object, as used in multilabel segmentation masks. Must be unique.
        color: RGBA color for the object.
        emdb_id: EMDB ID for the object.
        pdb_id: PDB ID for the object.
        map_threshold: Threshold to apply to the map when rendering the isosurface.
        radius: Radius of the particle, when displaying as a sphere.
        metadata: Additional metadata for the object (user-defined contents).
    """

    def __init__(self, root: "CopickRoot", meta: PickableObject):
        """
        Args:
            root(CopickRoot): The copick project root.
            meta: The metadata for this object.
        """

        self.meta = meta
        self.root = root

    def __repr__(self):
        label = self.label if self.label is not None else "None"
        color = self.color if self.color is not None else "None"
        emdb_id = self.emdb_id if self.emdb_id is not None else "None"
        pdb_id = self.pdb_id if self.pdb_id is not None else "None"
        identifier = self.identifier if self.identifier is not None else "None"
        map_threshold = self.map_threshold if self.map_threshold is not None else "None"
        metadata = self.metadata if self.metadata is not None else "None"

        ret = (
            f"CopickObject(name={self.name}, is_particle={self.is_particle}, label={label}, color={color}, "
            f"emdb_id={emdb_id}, pdb_id={pdb_id}, identifier={identifier} threshold={map_threshold}, "
            f"metadata={metadata}) at {hex(id(self))}"
        )
        return ret

    @property
    def name(self) -> str:
        return self.meta.name

    @property
    def is_particle(self) -> bool:
        return self.meta.is_particle

    @property
    def label(self) -> Union[int, None]:
        return self.meta.label

    @property
    def color(self) -> Union[Tuple[int, int, int, int], None]:
        return self.meta.color

    @property
    def emdb_id(self) -> Union[str, None]:
        return self.meta.emdb_id

    @property
    def pdb_id(self) -> Union[str, None]:
        return self.meta.pdb_id

    @property
    def identifier(self) -> Union[str, None]:
        return self.meta.identifier

    @property
    def map_threshold(self) -> Union[float, None]:
        return self.meta.map_threshold

    @property
    def radius(self) -> Union[float, None]:
        return self.meta.radius

    @property
    def metadata(self) -> Dict[str, Any]:
        return self.meta.metadata

    @property
    def filament(self) -> Optional[FilamentSpec]:
        """The filament declaration of this object, or None if it is not a filament."""
        return self.meta.filament

    @property
    def is_filament(self) -> bool:
        """Whether this object is declared a filament."""
        return self.meta.is_filament

    def zarr(self) -> Optional[Store]:
        """Override this method to return a zarr store for this object. Should return None if
        CopickObject.is_particle is False or there is no associated map."""
        if not self.is_particle:
            return None

        raise NotImplementedError("zarr method must be implemented for particle objects.")

    def has_density_map(self) -> bool:
        """Return whether this object has valid Zarr root metadata."""
        if not self.is_particle:
            return False

        raise NotImplementedError("has_density_map must be implemented for particle objects.")

    def numpy(
        self,
        zarr_group: Optional[str] = None,
        x: slice = slice(None, None),
        y: slice = slice(None, None),
        z: slice = slice(None, None),
    ) -> Union[None, np.ndarray]:
        """Returns the content of the Zarr-File for this object as a numpy array. Multiscale group and slices are
        supported.

        Args:
            zarr_group: Explicit Zarr array path. By default, resolve level 0 from OME metadata.
            x: Slice for the x-axis.
            y: Slice for the y-axis.
            z: Slice for the z-axis.

        Returns:
            np.ndarray: The object as a numpy array.
        """

        loc = self.zarr()
        if loc is None:
            return None

        group = _open_zarr_array(loc, zarr_group, mode="r")

        fits, req, avail = fits_in_memory(group, (x, y, z))
        if not fits:
            raise ValueError(f"Requested region does not fit in memory. Requested: {req}, Available: {avail}.")

        return group[z, y, x]

    def from_numpy(
        self,
        data: np.ndarray,
        voxel_size: float,
        dtype: Optional[np.dtype] = np.float32,
    ) -> None:
        """Set the object from a numpy array.

        Args:
            data: The segmentation as a numpy array.
            voxel_size: Voxel size of the object.
            dtype: Data type of the segmentation. Default is `np.float32`.
        """
        loc = self.zarr()
        if loc is None:
            raise ValueError(
                f"Cannot write a density map for object {self.name!r}: no writable Zarr store is available.",
            )

        pyramid = volume_pyramid(data, voxel_size, 1, dtype=dtype)
        write_ome_zarr_3d(loc, pyramid)
        self._on_density_map_written()

    def _on_density_map_written(self) -> None:
        """Hook invoked after a density-map pyramid is written successfully."""

    def set_region(
        self,
        data: np.ndarray,
        zarr_group: Optional[str] = None,
        x: slice = slice(None, None),
        y: slice = slice(None, None),
        z: slice = slice(None, None),
    ) -> None:
        """Set a region of the object from a numpy array.

        Args:
            data: The object's subregion as a numpy array.
            zarr_group: Explicit Zarr array path. By default, resolve level 0 from OME metadata.
            x: Slice for the x-axis.
            y: Slice for the y-axis.
            z: Slice for the z-axis.
        """
        loc = self.zarr()
        if loc is None:
            raise ValueError(
                f"Cannot write a density map for object {self.name!r}: no writable Zarr store is available.",
            )
        _open_zarr_array(loc, zarr_group, mode="r+")[z, y, x] = data

    def delete(self) -> None:
        """Delete the object."""
        self._delete_data()

        # Remove the object from the root
        if self.root._objects is not None:
            self.root._objects.remove(self)

    def _delete_data(self) -> None:
        """Override this method to delete the object data."""
        raise NotImplementedError("_delete_data method must be implemented for CopickObject.")


class CopickRoot:
    """Root of a copick project. Contains references to the runs and pickable objects.

    Attributes:
        config (CopickConfig): Configuration of the copick project.
        user_id: Unique identifier for the user.
        session_id: Unique identifier for the session.
        runs (List[CopickRun]): References to the runs for this project. Lazy loaded upon access.
        pickable_objects (List[CopickObject]): References to the pickable objects for this project.

    """

    def __init__(self, config: CopickConfig):
        """
        Args:
            config (CopickConfig): Configuration of the copick project.
        """
        self.config = config
        self._runs: Optional[List["CopickRun"]] = None
        self._objects: Optional[List[CopickObject]] = None

        # If runs are specified in the config, create them
        if config.runs is not None:
            self._runs = [CopickRun(self, CopickRunMeta(name=run_name)) for run_name in config.runs]

    def __repr__(self):
        lpo = None if self._objects is None else len(self._objects)
        lr = None if self._runs is None else len(self._runs)
        return f"CopickRoot(user_id={self.user_id}, len(pickable_objects)={lpo}, len(runs)={lr}) at {hex(id(self))}"

    @property
    def user_id(self) -> str:
        return self.config.user_id

    @user_id.setter
    def user_id(self, value: str) -> None:
        self.config.user_id = value

    @property
    def session_id(self) -> str:
        return self.config.session_id

    @session_id.setter
    def session_id(self, value: str) -> None:
        self.config.session_id = value

    def query(self) -> List["CopickRun"]:
        """Override this method to query for runs."""
        pass

    @property
    def runs(self) -> List["CopickRun"]:
        if self._runs is None:
            self._runs = self.query()

        return self._runs

    def get_run(self, name: str, **kwargs) -> Union["CopickRun", None]:
        """Get run by name.

        Args:
            name: Name of the run to retrieve.
            **kwargs: Additional keyword arguments for the run metadata.

        Returns:
            CopickRun: The run with the given name, or None if not found.
        """
        # Random access
        if self._runs is None:
            clz, meta_clz = self._run_factory()
            rm = meta_clz(name=name, **kwargs)
            run = clz(self, meta=rm)

            if not run.ensure(create=False):
                return None
            else:
                return run

        # Access through index
        else:
            for run in self.runs:
                if run.name == name:
                    return run

        return None

    def _query_objects(self):
        clz, meta_clz = self._object_factory()
        self._objects = [clz(self, meta=obj) for obj in self.config.pickable_objects]

    @property
    def pickable_objects(self) -> List["CopickObject"]:
        if self._objects is None:
            self._query_objects()

        return self._objects

    def get_object(self, name: str) -> Union["CopickObject", None]:
        """Get object by name.

        Args:
            name: Name of the object to retrieve.

        Returns:
            CopickObject: The object with the given name, or None if not found.
        """
        for obj in self.pickable_objects:
            if obj.name == name:
                return obj

        return None

    def refresh(self) -> None:
        """Refresh the list of runs."""
        self._runs = self.query()
        self._objects = None  # Reset objects to force reloading

    def reconnect(self) -> None:
        """Reconnect to the storage backend and invalidate all caches.

        Override in subclasses that use remote filesystems (e.g. SSH, S3).
        No-op for local filesystem backends.
        """
        pass

    def _invalidate_all_caches(self) -> None:
        """Invalidate all cached child objects, forcing re-query on next access."""
        if self._runs is not None:
            for run in self._runs:
                run._invalidate_caches()
        self._runs = None
        self._objects = None

    def save_config(self, config_path: str) -> None:
        """Save the configuration to a JSON file.

        Args:
            config_path: Path to the configuration file to save.
        """
        with open(config_path, "w") as f:
            json.dump(self.config.model_dump(), f, indent=4)

    def new_run(self, name: str, exist_ok: bool = False, **kwargs) -> "CopickRun":
        """Create a new run.

        Args:
            name: Name of the run to create.
            exist_ok: Whether to raise an error if the run already exists.
            **kwargs: Additional keyword arguments for the run metadata.

        Returns:
            CopickRun: The newly created run.

        Raises:
            ValueError: If a run with the given name already exists.
        """
        if name in [r.name for r in self.runs]:
            if exist_ok:
                run = self.get_run(name)
            else:
                raise ValueError(f"Run name {name} already exists.")
        else:
            clz, meta_clz = self._run_factory()
            rm = meta_clz(name=name, **kwargs)
            run = clz(self, meta=rm)

            # Append the run
            if self._runs is None:
                self._runs = []
            self._runs.append(run)

            # Ensure the run record exists
            run.ensure(create=True)

        return run

    def delete_run(self, name: str) -> None:
        """Delete a run by name.

        Args:
            name: Name of the run to delete.
        """
        run = self.get_run(name)

        if run is None:
            return

        self._runs.remove(run)
        run.delete()
        del run

    def _run_factory(self) -> Tuple[Type["CopickRun"], Type["CopickRunMeta"]]:
        """Override this method to return the run class and run metadata class."""
        return CopickRun, CopickRunMeta

    def new_object(
        self,
        name: str,
        is_particle: bool,
        label: Optional[int] = None,
        color: Optional[Tuple[int, int, int, int]] = None,
        emdb_id: Optional[str] = None,
        pdb_id: Optional[str] = None,
        identifier: Optional[str] = None,
        map_threshold: Optional[float] = None,
        radius: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
        exist_ok: bool = False,
        filament: Union[FilamentSpec, Dict[str, Any], None] = None,
    ) -> "CopickObject":
        """Create a new pickable object and add it to the configuration.

        Args:
            name: Name of the object.
            is_particle: Whether this object should be represented by points (True) or segmentation masks (False).
            label: Numeric label/id for the object. If None, will use the next available label.
            color: RGBA color for the object. If None, will use a default color.
            emdb_id: EMDB ID for the object.
            pdb_id: PDB ID for the object.
            identifier: Identifier for the object, drawn from an ontology/database namespace
            (GO, UniProtKB, CHEBI, PDB [dash separator, e.g. ``PDB-1BXN``], UBERON, CL, or CDPO).
            When using the data portal, this must match the annotation ``object_id`` exactly.
            map_threshold: Threshold to apply to the map when rendering the isosurface.
            radius: Radius of the particle, when displaying as a sphere.
            metadata: Additional metadata for the object (user-defined contents).
            exist_ok: Whether existing objects with the same name should be overwritten..
            filament: Declare the object a filament (see ``FilamentSpec``); stored as
                ``metadata["copick"]["filament"]``. Requires ``is_particle=True``. None leaves the metadata as given.

        Returns:
            CopickObject: The newly created object.

        Raises:
            ValueError: If an object with the given name already exists and exist_ok is False, or if the
                resulting object definition is invalid.
        """
        sane_name = sanitize_name(name)

        if name != sane_name:
            raise ValueError(
                f"Object name '{name}' contains invalid characters. Use copick.escape.sanitize_name() to clean it.",
            )
        name = sane_name
        if name.endswith(RESERVED_NAME_SUFFIXES):
            import logging

            logging.getLogger(__name__).warning(
                f"Object name '{name}' ends in a segmentation type suffix ({', '.join(RESERVED_NAME_SUFFIXES)}); "
                "its segmentation store names will be ambiguous.",
            )

        # Check if the object already exists
        obj = self.get_object(name)
        if obj and not exist_ok:
            raise ValueError(f"Object name {name} already exists.")

        if obj:
            updated_metadata = metadata if metadata else obj.metadata
            if filament is not None:
                updated_metadata = _metadata_with_filament(updated_metadata, filament)
            updated = {
                **obj.meta.model_dump(),
                "is_particle": is_particle,
                "label": label if label else obj.label,
                "color": color if color else obj.color,
                "emdb_id": emdb_id if emdb_id else obj.emdb_id,
                "pdb_id": pdb_id if pdb_id else obj.pdb_id,
                "identifier": identifier if identifier else obj.identifier,
                "map_threshold": map_threshold if map_threshold else obj.map_threshold,
                "radius": radius if radius else obj.radius,
                "metadata": updated_metadata,
            }
            # Validate the updated definition as a whole before changing the object in place, so an invalid
            # update raises instead of leaving a half-updated object in the configuration.
            validated = type(obj.meta).model_validate(updated)
            for field_name in type(obj.meta).model_fields:
                setattr(obj.meta, field_name, getattr(validated, field_name))
        else:
            # Check for duplicate label BEFORE auto-assignment
            if label is not None:
                existing_labels = {obj.label for obj in self.config.pickable_objects if obj.label is not None}

                if label in existing_labels:
                    raise ValueError(f"Object label {label} already exists.")

            # Auto-assign label if not provided
            if label is None:
                existing_labels = [obj.label for obj in self.config.pickable_objects if obj.label is not None]
                label = max(existing_labels) + 1 if existing_labels else 1

            # Use default color if not provided
            if color is None:
                color = (100, 100, 100, 255)

            # Create the pickable object metadata
            pickable_meta = PickableObject(
                name=name,
                is_particle=is_particle,
                label=label,
                color=color,
                emdb_id=emdb_id,
                pdb_id=pdb_id,
                identifier=identifier,
                map_threshold=map_threshold,
                radius=radius,
                metadata=_metadata_with_filament(metadata, filament) if filament is not None else (metadata or {}),
            )

            # Add to configuration
            self.config.pickable_objects.append(pickable_meta)

            # Create the object and add to cache
            clz, _ = self._object_factory()
            obj = clz(self, pickable_meta, read_only=False)

            # Ensure the objects cache is initialized before appending
            if self._objects is None:
                # This will initialize self._objects
                _ = self.pickable_objects
            self._objects.append(obj)

        return obj

    def _object_factory(self) -> Tuple[Type["CopickObject"], Type["PickableObject"]]:
        """Override this method to return the object class and object metadata class."""
        return CopickObject, PickableObject


class CopickRunMeta(BaseModel):
    """Data model for run level metadata.

    Attributes:
        name: Name of the run.
    """

    name: str


class CopickRun:
    """Encapsulates all data pertaining to a physical location on a sample (i.e. typically one tilt series and the
    associated tomograms). This includes voxel spacings (of the reconstructed tomograms), picks, meshes, and
    segmentations.

    Attributes:
        meta (CopickRunMeta): Metadata for this run.
        root (CopickRoot): Reference to the root project this run belongs to.
        voxel_spacings (List[CopickVoxelSpacing]): Voxel spacings for this run. Either populated from config or lazily
            loaded when CopickRun.voxel_spacings is accessed **for the first time**.
        picks (List[CopickPicks]): Picks for this run. Either populated from config or lazily loaded when
            CopickRun.picks is accessed for **the first time**.
        meshes (List[CopickMesh]): Meshes for this run. Either populated from config or lazily loaded when
            CopickRun.meshes is accessed **for the first time**.
        segmentations (List[CopickSegmentation]): Segmentations for this run. Either populated from config or lazily
            loaded when CopickRun.segmentations is accessed **for the first time**.


    """

    @property
    def split(self) -> Optional[str]:
        """The ML split this run belongs to (train/val/test/custom).

        Supported by the mlcroissant backend (stored in ``runs.csv``).
        Returns ``None`` on backends without a structured place for split
        metadata (filesystem, cryoet_data_portal).
        """
        return None

    def __init__(self, root: "CopickRoot", meta: CopickRunMeta, config: Optional["CopickConfig"] = None):
        self.meta = meta
        self.root = root
        self._voxel_spacings: Optional[List["CopickVoxelSpacing"]] = None
        """Voxel spacings for this run. Either populated from config or lazily loaded when CopickRun.voxel_spacings is
        accessed for the first time."""
        self._picks: Optional[List["CopickPicks"]] = None
        """Picks for this run. Either populated from config or lazily loaded when CopickRun.picks is
        accessed for the first time."""
        self._meshes: Optional[List["CopickMesh"]] = None
        """Meshes for this run. Either populated from config or lazily loaded when CopickRun.picks is
        accessed for the first time."""
        self._filaments: Optional[List["CopickFilaments"]] = None
        """Traced filaments for this run, lazily loaded when CopickRun.filaments is accessed for the first time."""
        self._segmentations: Optional[List["CopickSegmentation"]] = None
        """Segmentations for this run. Either populated from config or lazily loaded when
        CopickRun.segmentations is accessed for the first time."""

        if config is not None:
            voxel_spacings_metas = [
                CopickVoxelSpacingMeta(run=self, voxel_size=vs, config=config) for vs in config.tomograms
            ]
            self._voxel_spacings = [CopickVoxelSpacing(run=self, meta=vs) for vs in voxel_spacings_metas]

            #####################
            # Picks from config #
            #####################
            # Select all available pre-picks for this run
            avail = config.available_pre_picks.keys()
            avail = [a for a in avail if a[0] == self.name]

            # Pre-defined picks
            for av in avail:
                object_name = av[1]
                prepicks = config.available_pre_picks[av]

                for pp in prepicks:
                    pm = CopickPicksFile(
                        pickable_object_name=object_name,
                        user_id=pp,
                        session_id="0",
                        run_name=self.name,
                    )
                    self._picks.append(CopickPicks(run=self, file=pm))

            ######################
            # Meshes from config #
            ######################
            for object_name, tool_names in config.available_pre_meshes.items():
                for mesh_tool in tool_names:
                    mm = CopickMeshMeta(pickable_object_name=object_name, user_id=mesh_tool, session_id="0")
                    com = CopickMesh(run=self, meta=mm)
                    self._meshes.append(com)

            #############################
            # Segmentations from config #
            #############################
            for seg_tool in config.available_pre_segmentations:
                sm = CopickSegmentationMeta(run=self, user_id=seg_tool, session_id="0")
                cos = CopickSegmentation(run=self, meta=sm)
                self._segmentations.append(cos)

    def __repr__(self):
        lvs = None if self._voxel_spacings is None else len(self._voxel_spacings)
        lpck = None if self._picks is None else len(self._picks)
        lmsh = None if self._meshes is None else len(self._meshes)
        lseg = None if self._segmentations is None else len(self._segmentations)
        ret = (
            f"CopickRun(name={self.name}, len(voxel_spacings)={lvs}, len(picks)={lpck}, len(meshes)={lmsh}, "
            f"len(segmentations)={lseg}) at {hex(id(self))}"
        )
        return ret

    @property
    def name(self):
        return self.meta.name

    @name.setter
    def name(self, value: str) -> None:
        self.meta.name = value

    def query_voxelspacings(self) -> List["CopickVoxelSpacing"]:
        """Override this method to query for voxel_spacings.

        Returns:
            List[CopickVoxelSpacing]: List of voxel spacings for this run.
        """
        raise NotImplementedError("query_voxelspacings must be implemented for CopickRun.")

    def query_picks(self) -> List["CopickPicks"]:
        """Override this method to query for picks.

        Returns:
            List[CopickPicks]: List of picks for this run.
        """
        raise NotImplementedError("query_picks must be implemented for CopickRun.")

    def query_filaments(self) -> List["CopickFilaments"]:
        """Override this method to query for filaments. Runs of backends without filaments have none."""
        return []

    def query_meshes(self) -> List["CopickMesh"]:
        """Override this method to query for meshes.

        Returns:
            List[CopickMesh]: List of meshes for this run.
        """
        raise NotImplementedError("query_meshes must be implemented for CopickRun.")

    def query_segmentations(self) -> List["CopickSegmentation"]:
        """Override this method to query for segmentations.

        Returns:
            List[CopickSegmentation]: List of segmentations for this run.
        """
        raise NotImplementedError("query_segmentations must be implemented for CopickRun.")

    @property
    def voxel_spacings(self) -> List["CopickVoxelSpacing"]:
        if self._voxel_spacings is None:
            self._voxel_spacings = self.query_voxelspacings()

        return self._voxel_spacings

    def get_voxel_spacing(self, voxel_size: float, **kwargs) -> Union["CopickVoxelSpacing", None]:
        """Get voxel spacing object by voxel size value.

        Args:
            voxel_size: Voxel size value to search for.
            **kwargs: Additional keyword arguments for the voxel spacing metadata.

        Returns:
            CopickVoxelSpacing: The voxel spacing object with the given voxel size value, or None if not found.
        """
        # Random access
        if self._voxel_spacings is None:
            clz, meta_clz = self._voxel_spacing_factory()
            vm = meta_clz(voxel_size=voxel_size, **kwargs)
            vs = clz(self, meta=vm)

            if not vs.ensure(create=False):
                return None
            else:
                return vs

        # Access through index
        else:
            for vs in self.voxel_spacings:
                if vs.voxel_size == voxel_size:
                    return vs

        return None

    @property
    def picks(self) -> List["CopickPicks"]:
        if self._picks is None:
            self._picks = self.query_picks()

        return self._picks

    def user_picks(self) -> List["CopickPicks"]:
        """Get all user generated picks (i.e. picks that have `CopickPicks.session_id != 0`).

        Returns:
            List[CopickPicks]: List of user-generated picks.
        """
        if self.root.config.user_id is None:
            return [p for p in self.picks if p.from_user]
        else:
            return self.get_picks(user_id=self.root.config.user_id)

    def tool_picks(self) -> List["CopickPicks"]:
        """Get all tool generated picks (i.e. picks that have `CopickPicks.session_id == 0`).

        Returns:
            List[CopickPicks]: List of tool-generated picks.
        """
        return [p for p in self.picks if p.from_tool]

    def get_picks(
        self,
        object_name: Union[str, Iterable[str]] = None,
        user_id: Union[str, Iterable[str]] = None,
        session_id: Union[str, Iterable[str]] = None,
        **kwargs,
    ) -> List["CopickPicks"]:
        """Get picks by name, user_id or session_id (or combinations).

        Args:
            object_name: Name of the object to search for.
            user_id: User ID to search for.
            session_id: Session ID to search for.
            **kwargs: Additional parameters for subclass implementations.

        Returns:
            List[CopickPicks]: List of picks that match the search criteria.
        """
        ret = self.picks

        if object_name is not None:
            object_name = [object_name] if isinstance(object_name, str) else object_name
            ret = [p for p in ret if p.pickable_object_name in object_name]

        if user_id is not None:
            user_id = [user_id] if isinstance(user_id, str) else user_id
            ret = [p for p in ret if p.user_id in user_id]

        if session_id is not None:
            session_id = [session_id] if isinstance(session_id, str) else session_id
            ret = [p for p in ret if p.session_id in session_id]

        return ret

    @property
    def filaments(self) -> List["CopickFilaments"]:
        if self._filaments is None:
            self._filaments = self.query_filaments()

        return self._filaments

    def get_filaments(
        self,
        object_name: Union[str, Iterable[str]] = None,
        user_id: Union[str, Iterable[str]] = None,
        session_id: Union[str, Iterable[str]] = None,
    ) -> List["CopickFilaments"]:
        """Get filaments by object name, user_id or session_id (or combinations).

        Args:
            object_name: Name of the object to search for.
            user_id: User ID to search for.
            session_id: Session ID to search for.

        Returns:
            List[CopickFilaments]: List of filaments that match the search criteria.
        """
        ret = list(self.filaments)

        if object_name is not None:
            object_name = [object_name] if isinstance(object_name, str) else object_name
            ret = [f for f in ret if f.pickable_object_name in object_name]

        if user_id is not None:
            user_id = [user_id] if isinstance(user_id, str) else user_id
            ret = [f for f in ret if f.user_id in user_id]

        if session_id is not None:
            session_id = [session_id] if isinstance(session_id, str) else session_id
            ret = [f for f in ret if f.session_id in session_id]

        return ret

    @property
    def meshes(self) -> List["CopickMesh"]:
        if self._meshes is None:
            self._meshes = self.query_meshes()

        return self._meshes

    def user_meshes(self) -> List["CopickMesh"]:
        """Get all user generated meshes (i.e. meshes that have `CopickMesh.session_id != 0`).

        Returns:
            List[CopickMesh]: List of user-generated meshes.
        """
        if self.root.config.user_id is None:
            return [m for m in self.meshes if m.from_user]
        else:
            return self.get_meshes(user_id=self.root.config.user_id)

    def tool_meshes(self) -> List["CopickMesh"]:
        """Get all tool generated meshes (i.e. meshes that have `CopickMesh.session_id == 0`).

        Returns:
            List[CopickMesh]: List of tool-generated meshes.
        """
        return [m for m in self.meshes if m.from_tool]

    def get_meshes(
        self,
        object_name: Union[str, Iterable[str]] = None,
        user_id: Union[str, Iterable[str]] = None,
        session_id: Union[str, Iterable[str]] = None,
    ) -> List["CopickMesh"]:
        """Get meshes by name, user_id or session_id (or combinations).

        Args:
            object_name: Name of the object to search for.
            user_id: User ID to search for.
            session_id: Session ID to search for.

        Returns:
            List[CopickMesh]: List of meshes that match the search criteria.
        """
        ret = self.meshes

        if object_name is not None:
            object_name = [object_name] if isinstance(object_name, str) else object_name
            ret = [m for m in ret if m.pickable_object_name in object_name]

        if user_id is not None:
            user_id = [user_id] if isinstance(user_id, str) else user_id
            ret = [m for m in ret if m.user_id in user_id]

        if session_id is not None:
            session_id = [session_id] if isinstance(session_id, str) else session_id
            ret = [m for m in ret if m.session_id in session_id]

        return ret

    @property
    def segmentations(self) -> List["CopickSegmentation"]:
        if self._segmentations is None:
            self._segmentations = self.query_segmentations()

        return self._segmentations

    def user_segmentations(self) -> List["CopickSegmentation"]:
        """Get all user generated segmentations (i.e. segmentations that have `CopickSegmentation.session_id != 0`).

        Returns:
            List[CopickSegmentation]: List of user-generated segmentations.
        """
        if self.root.config.user_id is None:
            return [s for s in self.segmentations if s.from_user]
        else:
            return self.get_segmentations(user_id=self.root.config.user_id, is_instance=None, is_panoptic=None)

    def tool_segmentations(self) -> List["CopickSegmentation"]:
        """Get all tool generated segmentations (i.e. segmentations that have `CopickSegmentation.session_id == 0`).

        Returns:
            List[CopickSegmentation]: List of tool-generated segmentations.
        """
        return [s for s in self.segmentations if s.from_tool]

    def get_segmentations(
        self,
        user_id: Union[str, Iterable[str]] = None,
        session_id: Union[str, Iterable[str]] = None,
        is_multilabel: bool = None,
        name: Union[str, Iterable[str]] = None,
        voxel_size: Union[float, Iterable[float]] = None,
        *,
        is_instance: Optional[bool] = False,
        is_panoptic: Optional[bool] = False,
        **kwargs,
    ) -> List["CopickSegmentation"]:
        """Get segmentations by user_id, session_id, name, type or voxel_size (or combinations).

        Without a type, this selects binary and multilabel segmentations, the types every client reads: pass
        ``is_instance=True`` or ``is_panoptic=True`` for the other types, or ``is_instance=None, is_panoptic=None`` for
        any type. ``segmentations`` lists all of them.

        Args:
            user_id: User ID to search for.
            session_id: Session ID to search for.
            is_multilabel: Whether the segmentation is multilabel or not.
            name: Name of the segmentation to search for.
            voxel_size: Voxel size to search for.
            is_instance: Whether to select instance segmentations (True) or not (False, the default); None selects any
                type. Binary segmentations are ``is_multilabel=False, is_instance=False, is_panoptic=False``.
            is_panoptic: Whether to select panoptic segmentations (True) or not (False, the default); None selects any
                type.
            **kwargs: Additional parameters for subclass implementations.

        Returns:
            List[CopickSegmentation]: List of segmentations that match the search criteria.
        """
        ret = self.segmentations

        if user_id is not None:
            user_id = [user_id] if isinstance(user_id, str) else user_id
            ret = [s for s in ret if s.user_id in user_id]

        if session_id is not None:
            session_id = [session_id] if isinstance(session_id, str) else session_id
            ret = [s for s in ret if s.session_id in session_id]

        if is_multilabel is not None:
            ret = [s for s in ret if s.is_multilabel == is_multilabel]

        if is_instance is not None:
            ret = [s for s in ret if s.is_instance == is_instance]

        if is_panoptic is not None:
            ret = [s for s in ret if s.is_panoptic == is_panoptic]

        if name is not None:
            name = [name] if isinstance(name, str) else name
            ret = [s for s in ret if s.name in name]

        if voxel_size is not None:
            voxel_size = [voxel_size] if isinstance(voxel_size, float) else voxel_size
            ret = [s for s in ret if s.voxel_size in voxel_size]

        return ret

    def new_voxel_spacing(self, voxel_size: float, exist_ok: bool = False, **kwargs) -> "CopickVoxelSpacing":
        """Create a new voxel spacing object.

        Args:
            voxel_size: Voxel size value for the contained tomograms.
            exist_ok: Whether to raise an error if the voxel spacing already exists.
            **kwargs: Additional keyword arguments for the voxel spacing metadata.

        Returns:
            CopickVoxelSpacing: The newly created voxel spacing object.

        Raises:
            ValueError: If a voxel spacing with the given voxel size already exists for this run.
        """
        if voxel_size in [vs.voxel_size for vs in self.voxel_spacings]:
            if exist_ok:
                vs = self.get_voxel_spacing(voxel_size)
            else:
                raise ValueError(f"VoxelSpacing {voxel_size} already exists for this run.")
        else:
            clz, meta_clz = self._voxel_spacing_factory()

            vm = meta_clz(voxel_size=voxel_size, **kwargs)
            vs = clz(run=self, meta=vm)

            # Append the voxel spacing
            if self._voxel_spacings is None:
                self._voxel_spacings = []
            self._voxel_spacings.append(vs)

            # Ensure the voxel spacing record exists
            vs.ensure(create=True)

        return vs

    def _voxel_spacing_factory(self) -> Tuple[Type["CopickVoxelSpacing"], Type["CopickVoxelSpacingMeta"]]:
        """Override this method to return the voxel spacing class and voxel spacing metadata class."""
        return CopickVoxelSpacing, CopickVoxelSpacingMeta

    def new_picks(
        self,
        object_name: str,
        session_id: str,
        user_id: Optional[str] = None,
        exist_ok: bool = False,
    ) -> "CopickPicks":
        """Create a new picks object.

        Args:
            object_name: Name of the object to pick.
            session_id: Session ID for the picks.
            user_id: User ID for the picks.
            exist_ok: Whether to raise an error if the picks already exists.

        Returns:
            CopickPicks: The newly created picks object.

        Raises:
            ValueError: If picks for the given object name, session ID and user ID already exist, if the object name
                is not found in the pickable objects, or if the user ID is not set in the root config or supplied.
        """
        object_name = sanitize_name(object_name)
        session_id = sanitize_name(session_id)
        if user_id is not None:
            user_id = sanitize_name(user_id)

        if object_name not in [o.name for o in self.root.config.pickable_objects]:
            raise ValueError(f"Object name {object_name} not found in pickable objects.")

        uid = self.root.config.user_id

        if user_id is not None:
            uid = user_id

        if uid is None:
            raise ValueError("User ID must be set in the root config or supplied to new_picks.")

        if picks := self.get_picks(object_name=object_name, session_id=session_id, user_id=uid):
            if exist_ok:
                picks = picks[0]
            else:
                raise ValueError(f"Picks for {object_name} by user/tool {uid} already exist in session {session_id}.")
        else:
            pm = CopickPicksFile(
                pickable_object_name=object_name,
                user_id=uid,
                session_id=session_id,
                run_name=self.name,
            )

            clz = self._picks_factory()

            picks = clz(run=self, file=pm)

            if self._picks is None:
                self._picks = []
            self._picks.append(picks)

            # Create the picks file
            picks.store()

        return picks

    def _picks_factory(self) -> Type["CopickPicks"]:
        """Override this method to return the picks class."""
        return CopickPicks

    def new_filaments(
        self,
        object_name: str,
        session_id: str,
        user_id: Optional[str] = None,
        exist_ok: bool = False,
    ) -> "CopickFilaments":
        """Create a new, empty set of traced filaments.

        Args:
            object_name: Name of the pickable object the filaments are of. A warning is logged if the object is not
                declared a filament.
            session_id: Session ID for the filaments.
            user_id: User ID for the filaments.
            exist_ok: Whether to return existing filaments instead of raising an error.

        Returns:
            CopickFilaments: The newly created (or existing) filaments.

        Raises:
            ValueError: If the filaments already exist and exist_ok is False, if the object name is not found in the
                pickable objects, or if the user ID is not set in the root config or supplied.
        """
        object_name = sanitize_name(object_name)
        session_id = sanitize_name(session_id)
        if user_id is not None:
            user_id = sanitize_name(user_id)

        obj = self.root.get_object(object_name)
        if obj is None:
            raise ValueError(f"Object name {object_name} not found in pickable objects.")
        if not obj.is_filament:
            import logging

            logging.getLogger(__name__).warning(
                f"Object {object_name} is not declared a filament (see PickableObject.set_filament).",
            )

        uid = user_id if user_id is not None else self.root.config.user_id
        if uid is None:
            raise ValueError("User ID must be set in the root config or supplied to new_filaments.")

        if existing := self.get_filaments(object_name=object_name, session_id=session_id, user_id=uid):
            if exist_ok:
                return existing[0]
            raise ValueError(f"Filaments for {object_name} by user/tool {uid} already exist in session {session_id}.")

        clz = self._filaments_factory()
        filaments = clz(
            run=self,
            file=CopickFilamentsFile(
                pickable_object_name=object_name,
                user_id=uid,
                session_id=session_id,
                run_name=self.name,
            ),
        )
        # Store first, so a backend that cannot store leaves no entry in the cache (get_filaments above has
        # already populated it)
        filaments.store()
        self.filaments.append(filaments)

        return filaments

    def _filaments_factory(self) -> Type["CopickFilaments"]:
        """Override this method to return the filaments class."""
        return CopickFilaments

    def new_mesh(
        self,
        object_name: str,
        session_id: str,
        user_id: Optional[str] = None,
        exist_ok: bool = False,
        **kwargs,
    ) -> "CopickMesh":
        """Create a new mesh object.

        Args:
            object_name: Name of the object to mesh.
            session_id: Session ID for the mesh.
            user_id: User ID for the mesh.
            exist_ok: Whether to raise an error if the mesh already exists.
            **kwargs: Additional keyword arguments for the mesh metadata.

        Returns:
            CopickMesh: The newly created mesh object.

        Raises:
            ValueError: If a mesh for the given object name, session ID and user ID already exist, if the object name
                is not found in the pickable objects, or if the user ID is not set in the root config or supplied.
        """
        object_name = sanitize_name(object_name)
        session_id = sanitize_name(session_id)
        if user_id is not None:
            user_id = sanitize_name(user_id)

        if object_name not in [o.name for o in self.root.config.pickable_objects]:
            raise ValueError(f"Object name {object_name} not found in pickable objects.")

        uid = self.root.config.user_id

        if user_id is not None:
            uid = user_id

        if uid is None:
            raise ValueError("User ID must be set in the root config or supplied to new_mesh.")

        if mesh := self.get_meshes(object_name=object_name, session_id=session_id, user_id=uid):
            if exist_ok:
                mesh = mesh[0]
            else:
                raise ValueError(f"Mesh for {object_name} by user/tool {uid} already exist in session {session_id}.")
        else:
            clz, meta_clz = self._mesh_factory()

            mm = meta_clz(
                pickable_object_name=object_name,
                user_id=uid,
                session_id=session_id,
                **kwargs,
            )

            # Defer trimesh import to keep CLI snappy (trimesh imports scipy)
            import trimesh

            # Need to create an empty trimesh.Trimesh object first, because empty scenes can't be exported.
            tmesh = trimesh.Trimesh()
            scene = tmesh.scene()

            mesh = clz(run=self, meta=mm, mesh=scene)

            if self._meshes is None:
                self._meshes = []
            self._meshes.append(mesh)

            # Create the mesh file
            mesh.store()

        return mesh

    def _mesh_factory(self) -> Tuple[Type["CopickMesh"], Type["CopickMeshMeta"]]:
        """Override this method to return the mesh class and mesh metadata."""
        return CopickMesh, CopickMeshMeta

    def new_segmentation(
        self,
        voxel_size: float,
        name: str,
        session_id: str,
        is_multilabel: bool = False,
        user_id: Optional[str] = None,
        exist_ok: bool = False,
        *,
        is_instance: bool = False,
        is_panoptic: bool = False,
        **kwargs,
    ) -> "CopickSegmentation":
        """Create a new segmentation object.

        Args:
            voxel_size: Voxel size for the segmentation.
            name: Name of the segmentation. For binary and instance segmentations, the name of a pickable object.
            session_id: Session ID for the segmentation.
            is_multilabel: Whether the segmentation is multilabel (several objects, voxel = object label).
            user_id: User ID for the segmentation.
            exist_ok: Whether to raise an error if the segmentation already exists.
            is_instance: Whether the segmentation is an instance segmentation (one object, voxel = instance ID).
            is_panoptic: Whether the segmentation is a panoptic segmentation (channels: object label, instance ID).
            **kwargs: Additional keyword arguments for the segmentation metadata.

        Returns:
            CopickSegmentation: The newly created segmentation object.

        Raises:
            ValueError: If a segmentation for the given name, session ID, user ID, voxel size and type already
                exist, if both ``is_multilabel`` and ``is_instance`` are set, if the object name is not found in the
                pickable objects, if the voxel size is not found in the voxel spacings, or if the user ID is not set
                in the root config or supplied.
        """
        name = sanitize_name(name)
        session_id = sanitize_name(session_id)
        if user_id is not None:
            user_id = sanitize_name(user_id)

        seg_type = segmentation_type(is_multilabel, is_instance, is_panoptic)
        if seg_type in ("binary", "instance") and name not in [o.name for o in self.root.config.pickable_objects]:
            raise ValueError(
                f"Object name {name} not found in pickable objects ({seg_type} segmentations are named after one).",
            )

        uid = self.root.config.user_id

        if user_id is not None:
            uid = user_id

        if uid is None:
            raise ValueError("User ID must be set in the root config or supplied to new_segmentation.")

        if seg := self.get_segmentations(
            session_id=session_id,
            user_id=uid,
            name=name,
            is_multilabel=is_multilabel,
            voxel_size=voxel_size,
            is_instance=is_instance,
            is_panoptic=is_panoptic,
        ):
            if exist_ok:
                seg = seg[0]
            else:
                raise ValueError(
                    f"A {seg_type} segmentation by user/tool {uid} already exists in session {session_id} with name "
                    f"{name} and voxel size of {voxel_size}.",
                )
        else:
            clz, meta_clz = self._segmentation_factory()

            sm = meta_clz(
                is_multilabel=is_multilabel,
                is_instance=is_instance,
                is_panoptic=is_panoptic,
                voxel_size=voxel_size,
                user_id=uid,
                session_id=session_id,
                name=name,
                **kwargs,
            )
            seg = clz(run=self, meta=sm)

            if self._segmentations is None:
                self._segmentations = []

            self._segmentations.append(seg)

            # Materialize the new entity as an explicit Zarr v3 group.
            initialize_zarr_v3(seg.zarr())

        return seg

    def _segmentation_factory(self) -> Tuple[Type["CopickSegmentation"], Type["CopickSegmentationMeta"]]:
        """Override this method to return the segmentation class and segmentation metadata class."""
        return CopickSegmentation, CopickSegmentationMeta

    def refresh_voxel_spacings(self) -> None:
        """Refresh the voxel spacings."""
        self._voxel_spacings = self.query_voxelspacings()

    def refresh_picks(self) -> None:
        """Refresh the picks."""
        self._picks = self.query_picks()

    def refresh_meshes(self) -> None:
        """Refresh the meshes."""
        self._meshes = self.query_meshes()

    def refresh_filaments(self) -> None:
        """Refresh the filaments."""
        self._filaments = self.query_filaments()

    def refresh_segmentations(self) -> None:
        """Refresh the segmentations."""
        self._segmentations = self.query_segmentations()

    def refresh(self) -> None:
        """Refresh all child types."""
        self.refresh_voxel_spacings()
        self.refresh_picks()
        self.refresh_meshes()
        self.refresh_segmentations()
        self.refresh_filaments()

    def _invalidate_caches(self) -> None:
        """Invalidate all cached child data for this run."""
        if self._voxel_spacings is not None:
            for vs in self._voxel_spacings:
                vs._invalidate_caches()
        self._voxel_spacings = None
        self._picks = None
        self._meshes = None
        self._segmentations = None
        self._filaments = None

    def ensure(self, create: bool = False) -> bool:
        """Check if the run record exists, optionally create it if it does not.

        Args:
            create: Whether to create the run record if it does not exist.

        Returns:
            bool: True if the run record exists, False otherwise.
        """
        raise NotImplementedError("ensure must be implemented for CopickRun.")

    def _delete_data(self):
        """Override this method to delete the root data."""
        raise NotImplementedError("_delete_data method must be implemented for CopickRun.")

    def delete(self) -> None:
        """Delete the run record."""
        self.delete_voxel_spacings()
        self.delete_picks()
        self.delete_meshes()
        self.delete_segmentations(is_instance=None, is_panoptic=None)
        self.delete_filaments()
        self._delete_data()

        # Remove the run from the root
        if self in self.root.runs:
            self.root._runs.remove(self)

    def delete_voxel_spacings(self, voxel_size: float = None) -> None:
        """Delete a voxel spacing by voxel size.

        Args:
            voxel_size: Voxel size to delete.
        """
        if voxel_size is not None:
            vs = self.get_voxel_spacing(voxel_size=voxel_size)
            self._voxel_spacings.remove(vs)
            vs.delete()
            del vs
        else:
            for vs in list(self.voxel_spacings):
                self._voxel_spacings.remove(vs)
                vs.delete()
                del vs

    def delete_picks(self, object_name: str = None, user_id: str = None, session_id: str = None) -> None:
        """Delete picks by name, user_id or session_id (or combinations).

        Args:
            object_name: Name of the object to delete.
            user_id: User ID to delete.
            session_id: Session ID to delete.
        """
        for p in list(self.get_picks(object_name=object_name, user_id=user_id, session_id=session_id)):
            self._picks.remove(p)
            p.delete()
            del p

    def delete_meshes(self, object_name: str = None, user_id: str = None, session_id: str = None) -> None:
        """Delete meshes by name, user_id or session_id (or combinations).

        Args:
            object_name: Name of the object to delete.
            user_id: User ID to delete.
            session_id: Session ID to delete.
        """
        for m in list(self.get_meshes(object_name=object_name, user_id=user_id, session_id=session_id)):
            self._meshes.remove(m)
            m.delete()
            del m

    def delete_segmentations(
        self,
        user_id: str = None,
        session_id: str = None,
        is_multilabel: bool = None,
        name: str = None,
        voxel_size: float = None,
        *,
        is_instance: Optional[bool] = False,
        is_panoptic: Optional[bool] = False,
    ) -> None:
        """Delete segmentation by name, user_id or session_id (or combinations). Like ``get_segmentations``, without a
        type this deletes binary and multilabel segmentations only.

        Args:
            user_id: User ID to delete.
            session_id: Session ID to delete.
            is_multilabel: Whether the segmentation is multilabel or not.
            name: Name of the segmentation to delete.
            voxel_size: Voxel size to delete.
            is_instance: Whether to delete instance segmentations (True) or not (False, the default); None deletes any
                type.
            is_panoptic: Whether to delete panoptic segmentations (True) or not (False, the default); None deletes any
                type.
        """
        for s in list(
            self.get_segmentations(
                user_id=user_id,
                session_id=session_id,
                is_multilabel=is_multilabel,
                name=name,
                voxel_size=voxel_size,
                is_instance=is_instance,
                is_panoptic=is_panoptic,
            ),
        ):
            self._segmentations.remove(s)
            s.delete()
            del s

    def delete_filaments(self, object_name: str = None, user_id: str = None, session_id: str = None) -> None:
        """Delete filaments by name, user_id or session_id (or combinations).

        Args:
            object_name: Name of the object to delete.
            user_id: User ID to delete.
            session_id: Session ID to delete.
        """
        for f in self.get_filaments(object_name=object_name, user_id=user_id, session_id=session_id):
            f.delete()


class CopickVoxelSpacingMeta(BaseModel):
    """Data model for voxel spacing metadata.

    Attributes:
        voxel_size: Voxel size in angstrom, rounded to the third decimal.
    """

    voxel_size: float


class CopickVoxelSpacing:
    """Encapsulates all data pertaining to a specific voxel spacing. This includes the tomograms and feature maps at
    this voxel spacing.

    Attributes:
        run (CopickRun): Reference to the run this voxel spacing belongs to.
        meta (CopickVoxelSpacingMeta): Metadata for this voxel spacing.
        tomograms (List[CopickTomogram]): Tomograms for this voxel spacing. Either populated from config or lazily loaded
            when CopickVoxelSpacing.tomograms is accessed **for the first time**.
    """

    def __init__(self, run: CopickRun, meta: CopickVoxelSpacingMeta, config: Optional[CopickConfig] = None):
        """
        Args:
            run: Reference to the run this voxel spacing belongs to.
            meta: Metadata for this voxel spacing.
            config: Configuration of the copick project.
        """
        self.run = run
        self.meta = meta

        self._tomograms: Optional[List["CopickTomogram"]] = None
        """References to the tomograms for this voxel spacing."""

        if config is not None:
            tomo_metas = [CopickTomogramMeta(tomo_type=tt) for tt in config.tomograms[self.voxel_size]]
            self._tomograms = [CopickTomogram(voxel_spacing=self, meta=tm, config=config) for tm in tomo_metas]

    def __repr__(self):
        lts = None if self._tomograms is None else len(self._tomograms)
        return f"CopickVoxelSpacing(voxel_size={self.voxel_size}, len(tomograms)={lts}) at {hex(id(self))}"

    @property
    def voxel_size(self) -> float:
        return self.meta.voxel_size

    def query_tomograms(self) -> List["CopickTomogram"]:
        """Override this method to query for tomograms."""
        raise NotImplementedError("query_tomograms must be implemented for CopickVoxelSpacing.")

    @property
    def tomograms(self) -> List["CopickTomogram"]:
        if self._tomograms is None:
            self._tomograms = self.query_tomograms()

        return self._tomograms

    def get_tomogram(self, tomo_type: str) -> Union["CopickTomogram", None]:
        """Get tomogram by type.

        Args:
            tomo_type: Type of the tomogram to retrieve.

        Returns:
            CopickTomogram: The tomogram with the given type, or `None` if not found.
        """
        from warnings import warn

        warn(
            "get_tomogram is deprecated, use get_tomograms instead. Results may be incomplete",
            DeprecationWarning,
            stacklevel=2,
        )
        for tomo in self.tomograms:
            if tomo.tomo_type == tomo_type:
                return tomo
        return None

    def get_tomograms(self, tomo_type: str = None, **kwargs) -> List["CopickTomogram"]:
        """Get tomograms by type.

        Args:
            tomo_type: Type of the tomograms to retrieve.
            **kwargs: Additional parameters for subclass implementations.

        Returns:
            List[CopickTomogram]: The tomograms with the given type.
        """
        tomos = [tomo for tomo in self.tomograms if tomo.tomo_type == tomo_type]
        return tomos

    def refresh_tomograms(self) -> None:
        """Refresh `CopickVoxelSpacing.tomograms` from storage."""
        self._tomograms = self.query_tomograms()

    def refresh(self) -> None:
        """Refresh `CopickVoxelSpacing.tomograms` from storage."""
        self.refresh_tomograms()

    def _invalidate_caches(self) -> None:
        """Invalidate all cached child data for this voxel spacing."""
        self._tomograms = None

    def new_tomogram(self, tomo_type: str, exist_ok: bool = False, **kwargs) -> "CopickTomogram":
        """Create a new tomogram object, also creates the Zarr-store in the storage backend.

        Args:
            tomo_type: Type of the tomogram to create.
            exist_ok: Whether to raise an error if the tomogram already exists.
            **kwargs: Additional keyword arguments for the tomogram metadata.

        Returns:
            CopickTomogram: The newly created tomogram object.

        Raises:
            ValueError: If a tomogram with the given type already exists for this voxel spacing.
        """
        tomo_type = sanitize_name(tomo_type)

        if tomo := self.get_tomograms(tomo_type):
            if exist_ok:
                tomo = tomo[0]
            else:
                raise ValueError(f"Tomogram type {tomo_type} already exists for this voxel spacing.")
        else:
            clz, meta_clz = self._tomogram_factory()

            tm = meta_clz(tomo_type=tomo_type, **kwargs)
            tomo = clz(voxel_spacing=self, meta=tm)

            # Append the tomogram
            if self._tomograms is None:
                self._tomograms = []
            self._tomograms.append(tomo)

            # Materialize the new entity as an explicit Zarr v3 group.
            initialize_zarr_v3(tomo.zarr())

        return tomo

    def _tomogram_factory(self) -> Tuple[Type["CopickTomogram"], Type["CopickTomogramMeta"]]:
        """Override this method to return the tomogram class."""
        return CopickTomogram, CopickTomogramMeta

    def ensure(self, create: bool = False) -> bool:
        """Override to check if the voxel spacing record exists, optionally create it if it does not.

        Args:
            create: Whether to create the voxel spacing record if it does not exist.

        Returns:
            bool: True if the voxel spacing record exists, False otherwise.
        """
        raise NotImplementedError("ensure must be implemented for CopickVoxelSpacing.")

    def _delete_data(self):
        """Override this method to delete the voxel spacing data."""
        raise NotImplementedError("_delete_data method must be implemented for CopickVoxelSpacing.")

    def delete(self) -> None:
        """Delete the voxel spacing record."""
        self.delete_tomograms()
        self._delete_data()

        # Remove the voxel spacing from the run
        if self in self.run.voxel_spacings:
            self.run._voxel_spacings.remove(self)

    def delete_tomograms(self, tomo_type: str = None) -> None:
        """Delete a tomogram by type.

        Args:
            tomo_type: Type of the tomogram to delete.
        """
        if tomo_type is not None:
            for t in self.get_tomograms(tomo_type=tomo_type):
                self._tomograms.remove(t)
                t.delete()
                del t
        else:
            for t in self.tomograms:
                self._tomograms.remove(t)
                t.delete()
                del t


class CopickTomogramMeta(BaseModel):
    """Data model for tomogram metadata.

    Attributes:
        tomo_type: Type of the tomogram.
    """

    tomo_type: str


class CopickTomogram:
    """Encapsulates all data pertaining to a specific tomogram. This includes the features for this tomogram and the
    associated Zarr-store.

    Attributes:
        voxel_spacing (CopickVoxelSpacing): Reference to the voxel spacing this tomogram belongs to.
        meta (CopickTomogramMeta): Metadata for this tomogram.
        features (List[CopickFeatures]): Features for this tomogram. Either populated from config or lazily loaded when
            `CopickTomogram.features` is accessed **for the first time**.
        tomo_type (str): Type of the tomogram.
    """

    def __init__(
        self,
        voxel_spacing: "CopickVoxelSpacing",
        meta: CopickTomogramMeta,
        config: Optional["CopickConfig"] = None,
    ):
        self.meta = meta
        self.voxel_spacing = voxel_spacing

        self._features: Optional[List["CopickFeatures"]] = None
        """Features for this tomogram."""

        if config is not None and self.tomo_type in config.features[self.voxel_spacing.voxel_size]:
            feat_metas = [CopickFeaturesMeta(tomo_type=self.tomo_type, feature_type=ft) for ft in config.feature_types]
            self._features = [CopickFeatures(tomogram=self, meta=fm) for fm in feat_metas]

    def __repr__(self):
        lft = None if self._features is None else len(self._features)
        return f"CopickTomogram(tomo_type={self.tomo_type}, len(features)={lft}) at {hex(id(self))}"

    @property
    def tomo_type(self) -> str:
        return self.meta.tomo_type

    @property
    def features(self) -> List["CopickFeatures"]:
        if self._features is None:
            self._features = self.query_features()

        return self._features

    @features.setter
    def features(self, value: List["CopickFeatures"]) -> None:
        """Set the features."""
        self._features = value

    def get_features(self, feature_type: str) -> Union["CopickFeatures", None]:
        """Get feature maps by type.

        Args:
            feature_type: Type of the feature map to retrieve.

        Returns:
            CopickFeatures: The feature map with the given type, or `None` if not found.
        """
        for feat in self.features:
            if feat.feature_type == feature_type:
                return feat
        return None

    def new_features(self, feature_type: str, exist_ok: bool = False, **kwargs) -> "CopickFeatures":
        """Create a new feature map object. Also creates the Zarr-store for the map in the storage backend.

        Args:
            feature_type: Type of the feature map to create.
            exist_ok: Whether to raise an error if the feature map already exists.
            **kwargs: Additional keyword arguments for the feature map metadata.

        Returns:
            CopickFeatures: The newly created feature map object.

        Raises:
            ValueError: If a feature map with the given type already exists for this tomogram.
        """
        feature_type = sanitize_name(feature_type)

        if feat := self.get_features(feature_type):
            if exist_ok:
                return feat
            else:
                raise ValueError(f"Feature type {feature_type} already exists for this tomogram.")
        else:
            clz, meta_clz = self._feature_factory()

            fm = meta_clz(tomo_type=self.tomo_type, feature_type=feature_type, **kwargs)
            feat = clz(tomogram=self, meta=fm)

            # Append the feature set
            if self._features is None:
                self._features = []

            self._features.append(feat)

            # Materialize the new entity as an explicit Zarr v3 group.
            initialize_zarr_v3(feat.zarr())

        return feat

    def _feature_factory(self) -> Tuple[Type["CopickFeatures"], Type["CopickFeaturesMeta"]]:
        """Override this method to return the features class and features metadata class."""
        return CopickFeatures, CopickFeaturesMeta

    def query_features(self) -> List["CopickFeatures"]:
        """Override this method to query for features."""
        raise NotImplementedError("query_features must be implemented for CopickTomogram.")

    def refresh_features(self) -> None:
        """Refresh `CopickTomogram.features` from storage."""
        self._features = self.query_features()

    def refresh(self) -> None:
        """Refresh `CopickTomogram.features` from storage."""
        self.refresh_features()

    def _invalidate_caches(self) -> None:
        """Invalidate all cached features for this tomogram."""
        self._features = None

    def delete(self) -> None:
        """Delete the tomogram record."""
        self.delete_features()
        self._delete_data()

        # Remove the tomogram from the voxel spacing
        if self in self.voxel_spacing.tomograms:
            self.voxel_spacing._tomograms.remove(self)

    def delete_features(self) -> None:
        """Delete all features for this tomogram."""
        for f in self.features:
            self._features.remove(f)
            f.delete()
            del f

    def _delete_data(self) -> None:
        """Delete the tomogram data."""
        raise NotImplementedError("_delete_data must be implemented for CopickTomogram.")

    def zarr(self) -> Store:
        """Override to return the Zarr store for this tomogram. Also needs to handle creating the store if it
        doesn't exist."""
        raise NotImplementedError("zarr must be implemented for CopickTomogram.")

    def numpy(
        self,
        zarr_group: Optional[str] = None,
        x: slice = slice(None, None),
        y: slice = slice(None, None),
        z: slice = slice(None, None),
    ) -> np.ndarray:
        """Returns the content of the Zarr-File for this tomogram as a numpy array. Multiscale group and slices are
        supported.

        Args:
            zarr_group: Explicit Zarr array path. By default, resolve level 0 from OME metadata.
            x: Slice for the x-axis.
            y: Slice for the y-axis.
            z: Slice for the z-axis.

        Returns:
            np.ndarray: The tomogram as a numpy array.
        """

        loc = self.zarr()
        group = _open_zarr_array(loc, zarr_group, mode="r")

        fits, req, avail = fits_in_memory(group, (x, y, z))
        if not fits:
            raise ValueError(f"Requested region does not fit in memory. Requested: {req}, Available: {avail}.")

        return np.array(group[z, y, x])

    def from_numpy(
        self,
        data: np.ndarray,
        levels: int = 3,
        dtype: Optional[np.dtype] = np.float32,
    ) -> None:
        """Set the tomogram from a numpy array and compute multiscale pyramid. By default, three levels of the pyramid
        are computed.

        Args:
            data: The segmentation as a numpy array.
            levels: Number of levels in the multiscale pyramid.
            dtype: Data type of the segmentation. Default is `np.float32`.
        """
        loc = self.zarr()
        pyramid = volume_pyramid(data, self.voxel_spacing.voxel_size, levels, dtype=dtype)
        write_ome_zarr_3d(loc, pyramid)

    def set_region(
        self,
        data: np.ndarray,
        zarr_group: Optional[str] = None,
        x: slice = slice(None, None),
        y: slice = slice(None, None),
        z: slice = slice(None, None),
    ) -> None:
        """Set a region of the tomogram from a numpy array.

        Args:
            data: The tomogram's subregion as a numpy array.
            zarr_group: Explicit Zarr array path. By default, resolve level 0 from OME metadata.
            x: Slice for the x-axis.
            y: Slice for the y-axis.
            z: Slice for the z-axis.
        """
        loc = self.zarr()
        _open_zarr_array(loc, zarr_group, mode="r+")[z, y, x] = data


class CopickFeaturesMeta(BaseModel):
    """Data model for feature map metadata.

    Attributes:
        tomo_type: Type of the tomogram that the features were computed on.
        feature_type: Type of the features contained.
    """

    tomo_type: str
    feature_type: str


class CopickFeatures:
    """Encapsulates all data pertaining to a specific feature map, i.e. the Zarr-store for the feature map.

    Attributes:
        tomogram (CopickTomogram): Reference to the tomogram this feature map belongs to.
        meta (CopickFeaturesMeta): Metadata for this feature map.
        tomo_type (str): Type of the tomogram that the features were computed on.
        feature_type (str): Type of the features contained.
    """

    def __init__(self, tomogram: CopickTomogram, meta: CopickFeaturesMeta):
        """

        Args:
            tomogram: Reference to the tomogram this feature map belongs to.
            meta: Metadata for this feature map.
        """
        self.meta: CopickFeaturesMeta = meta
        self.tomogram: CopickTomogram = tomogram

    def __repr__(self):
        return f"CopickFeatures(tomo_type={self.tomo_type}, feature_type={self.feature_type}) at {hex(id(self))}"

    @property
    def tomo_type(self) -> str:
        return self.meta.tomo_type

    @property
    def feature_type(self) -> str:
        return self.meta.feature_type

    def delete(self):
        """Delete the feature map record."""
        self._delete_data()

        # Remove the feature map from the tomogram
        if self in self.tomogram.features:
            self.tomogram._features.remove(self)

    def _delete_data(self):
        """Delete the feature map data."""
        raise NotImplementedError("_delete_data must be implemented for CopickFeatures.")

    def zarr(self) -> Store:
        """Override to return the Zarr store for this feature set. Also needs to handle creating the store if it
        doesn't exist."""
        raise NotImplementedError("zarr must be implemented for CopickFeatures.")

    def numpy(
        self,
        zarr_group: Optional[str] = None,
        slices: Tuple[slice, ...] = None,
    ) -> np.ndarray:
        """Returns the content of the Zarr-File for this feature map as a numpy array. Multiscale group and slices are
        supported.

        Args:
            zarr_group: Explicit Zarr array path. By default, resolve level 0 from OME metadata.
            slices: Tuple of slices for the axes.

        Returns:
            np.ndarray: The object as a numpy array.
        """

        loc = self.zarr()
        group = _open_zarr_array(loc, zarr_group, mode="r")
        ndim = len(group.shape)

        if slices is None:
            slices = tuple(slice(None, None) for _ in range(ndim))

        fits, req, avail = fits_in_memory(group, slices)
        if not fits:
            raise ValueError(f"Requested region does not fit in memory. Requested: {req}, Available: {avail}.")

        return np.array(group[slices])

    def from_numpy(
        self,
        data: np.ndarray,
        *,
        chunks: Optional[Tuple[int, ...]] = None,
        shards: Optional[Tuple[int, ...]] = None,
        dtype: Optional[np.dtype] = None,
        metadata: Optional[Dict[str, Any]] = None,
        overwrite: bool = True,
    ) -> None:
        """Write a 3D or feature-major 4D feature array.

        Args:
            data: Feature data shaped ``(z, y, x)`` or ``(feature, z, y, x)``.
            chunks: Optional inner chunk shape. A 3-tuple for 4D data is expanded with a leading extent of one.
            shards: Optional dimension-matched shard shape.
            dtype: Optional dtype conversion applied before writing.
            metadata: Optional OME multiscale metadata payload.
            overwrite: Replace an existing feature array. Defaults to True for backward compatibility.
        """
        array = np.asarray(data, dtype=dtype)
        if array.ndim not in (3, 4):
            raise ValueError(f"Feature data must be 3D (z, y, x) or 4D (feature, z, y, x), got shape {array.shape!r}")

        spatial_chunks = DEFAULT_SPATIAL_CHUNKS if chunks is None else chunks
        if array.ndim == 3:
            effective_chunks = spatial_chunks
            effective_shards = shards
        else:
            if len(spatial_chunks) == 3:
                effective_chunks = (1, *spatial_chunks)
            elif len(spatial_chunks) == 4:
                effective_chunks = spatial_chunks
            else:
                raise ValueError(
                    f"chunks must contain 3 spatial dimensions or all 4 dimensions, got {spatial_chunks!r}",
                )
            effective_shards = shards
            if effective_shards is None:
                effective_shards = (1, *padded_shard_shape(array.shape[1:], effective_chunks[1:]))

        write_ome_zarr(
            self.zarr(),
            {self.tomogram.voxel_spacing.voxel_size: array},
            ome_zarr_axes(array.ndim),
            effective_chunks,
            metadata=metadata,
            shard_size=effective_shards,
            overwrite=overwrite,
        )

    def set_region(
        self,
        data: np.ndarray,
        zarr_group: Optional[str] = None,
        slices: Tuple[slice, ...] = None,
    ) -> None:
        """Set the content of the Zarr-File for this feature map from a numpy array. Multiscale group and slices are
        supported.

        Args:
            data: The data to set.
            zarr_group: Explicit Zarr array path. By default, resolve level 0 from OME metadata.
            slices: Tuple of slices for the axes.
        """
        loc = self.zarr()
        if slices is None:
            array = _open_zarr_array(loc, zarr_group, mode="r+")
            slices = tuple(slice(None) for _ in array.shape)
            array[slices] = data
            return
        _open_zarr_array(loc, zarr_group, mode="r+")[slices] = data


class CopickPicksFile(BaseModel):
    """Datamodel for a collection of locations, orientations and other metadata for one pickable object.

    Attributes:
        pickable_object_name: Pickable object name from CopickConfig.pickable_objects[X].name
        user_id: Unique identifier for the user or tool name.
        session_id: Unique identifier for the pick session (prevent race if they run multiple instances of napari,
            ChimeraX, etc.) If it is 0, this pick was generated by a tool.
        run_name: Name of the run this pick belongs to.
        voxel_spacing: Voxel spacing for the tomogram this pick belongs to.
        unit: Unit for the location of the pick.
        points (List[CopickPoint]): References to the points for this pick.
        trust_orientation: Flag to indicate if the angles are known for this pick or should be ignored.

    """

    pickable_object_name: str
    user_id: str
    session_id: Union[str, Literal["0"]]
    run_name: Optional[str] = None
    voxel_spacing: Optional[float] = None
    unit: str = "angstrom"
    points: Optional[List[CopickPoint]] = Field(default_factory=list)
    trust_orientation: Optional[bool] = True


class CopickPicks:
    """Encapsulates all data pertaining to a specific set of picked points. This includes the locations, orientations,
    and other metadata for the set of points.

    Attributes:
        run (CopickRun): Reference to the run this pick belongs to.
        meta (CopickPicksFile): Metadata for this pick.
        points (List[CopickPoint]): Points for this pick. Either populated from storage or lazily loaded when
            `CopickPicks.points` is accessed **for the first time**.
        from_tool (bool): Flag to indicate if this pick was generated by a tool.
        pickable_object_name (str): Pickable object name from `CopickConfig.pickable_objects[...].name`
        user_id (str): Unique identifier for the user or tool name.
        session_id (str): Unique identifier for the pick session
        trust_orientation (bool): Flag to indicate if the angles are known for this pick or should be ignored.
        color: Color of the pickable object this pick belongs to.
    """

    def __init__(self, run: CopickRun, file: CopickPicksFile):
        """
        Args:
            run: Reference to the run this pick belongs to.
            file: Metadata for this set of points.
        """
        self.meta: CopickPicksFile = file
        self.run: CopickRun = run

    def __repr__(self):
        lpt = None if self.meta.points is None else len(self.meta.points)
        ret = (
            f"CopickPicks(pickable_object_name={self.pickable_object_name}, user_id={self.user_id}, "
            f"session_id={self.session_id}, len(points)={lpt}) at {hex(id(self))}"
        )
        return ret

    def _load(self) -> CopickPicksFile:
        """Override this method to load points from a RESTful interface or filesystem."""
        raise NotImplementedError("load must be implemented for CopickPicks.")

    def _store(self):
        """Override this method to store points with a RESTful interface or filesystem. Also needs to handle creating
        the file if it doesn't exist."""
        raise NotImplementedError("store must be implemented for CopickPicks.")

    def load(self) -> CopickPicksFile:
        """Load the points from storage.

        Returns:
            CopickPicksFile: The loaded points.
        """
        self.meta = self._load()

        return self.meta

    def store(self):
        """Store the points (set using `CopickPicks.points` property)."""
        self._store()

    @property
    def from_tool(self) -> bool:
        return self.session_id == "0"

    @property
    def from_user(self) -> bool:
        return self.session_id != "0"

    @property
    def pickable_object_name(self) -> str:
        return self.meta.pickable_object_name

    @property
    def user_id(self) -> str:
        return self.meta.user_id

    @property
    def session_id(self) -> Union[str, Literal["0"]]:
        return self.meta.session_id

    @property
    def points(self) -> List[CopickPoint]:
        if self.meta.points is None or len(self.meta.points) == 0:
            self.meta = self.load()

        return self.meta.points

    @points.setter
    def points(self, value: List[CopickPoint]) -> None:
        self.meta.points = value

    @property
    def trust_orientation(self) -> bool:
        return self.meta.trust_orientation

    @property
    def color(self) -> Union[Tuple[int, int, int, int], None]:
        if self.run.root.get_object(self.pickable_object_name) is None:
            raise ValueError(f"{self.pickable_object_name} is not a recognized object name (run: {self.run.name}).")

        return self.run.root.get_object(self.pickable_object_name).color

    def refresh(self) -> None:
        """Refresh the points from storage."""
        self.meta = self.load()

    def delete(self) -> None:
        """Delete the pick record."""
        self._delete_data()

        # Remove the pick from the run
        if self in self.run.picks:
            self.run._picks.remove(self)

    def _delete_data(self) -> None:
        """Delete the pick data."""
        raise NotImplementedError("_delete_data must be implemented for CopickPicks.")

    def numpy(self) -> Tuple[np.ndarray, np.ndarray]:
        """Return the points as a [N, 3] numpy array (N, [x, y, z]) and the transforms as a [N, 4, 4] numpy array.
        Format of the transforms is:
                ```
                [[rxx, rxy, rxz, tx],
                 [ryx, ryy, ryz, ty],
                 [rzx, rzy, rzz, tz],
                 [  0,   0,   0,  1]]
                ```

        Returns:
            Tuple[np.ndarray, np.ndarray]: The picks and transforms as numpy arrays.
        """

        points = np.zeros((len(self.points), 3))
        transforms = np.zeros((len(self.points), 4, 4))

        for i, p in enumerate(self.points):
            points[i, :] = np.array([p.location.x, p.location.y, p.location.z])
            transforms[i, :, :] = p.transformation

        return points, transforms

    def instance_ids(self) -> np.ndarray:
        """Return the instance IDs of the points as a [N] integer array.

        For filament objects the instance ID is the filament ID (starting at 1; 0 means unassigned).
        """
        return np.array([0 if p.instance_id is None else p.instance_id for p in self.points], dtype=np.int64)

    def scores(self) -> np.ndarray:
        """Return the scores of the points as a [N] float array (1.0 where a point has no score)."""
        return np.array([1.0 if p.score is None else p.score for p in self.points], dtype=float)

    def full_positions(self) -> np.ndarray:
        """Return the particle centres as a [N, 3] array in Angstrom: each point's location plus the translation
        of its transform, which holds shifts such as those refined during subtomogram averaging.

        Use this, not the locations returned by ``numpy()``, wherever a particle is placed, drawn or extracted.
        """
        points, transforms = self.numpy()
        if len(points) == 0:
            return points
        return points + transforms[:, :3, 3]

    def from_numpy(
        self,
        positions: np.ndarray,
        transforms: Optional[np.ndarray] = None,
        instance_ids: Optional[np.ndarray] = None,
        scores: Optional[np.ndarray] = None,
    ) -> None:
        """Set the points and transforms from numpy arrays, and store them.

        Args:
            positions: [N, 3] numpy array of positions (N, [x, y, z]).
            transforms: [N, 4, 4] numpy array of orientations. If None, transforms will be set to the identity
                matrix. Format of the transforms is:
                ```
                [[rxx, rxy, rxz, tx],
                 [ryx, ryy, ryz, ty],
                 [rzx, rzy, rzz, tz],
                 [  0,   0,   0,  1]]
                ```
            instance_ids: [N] integer array of instance IDs (>= 0). For filament objects, the filament ID of each
                point (starting at 1). If None, every point gets 0.
            scores: [N] array of finite scores. If None, every point gets 1.0.

        Raises:
            ValueError: If the array lengths differ, an instance ID is negative or not an integer, or a score is not
                finite.
        """
        positions = np.asarray(positions)
        n = positions.shape[0]

        if transforms is not None and n != transforms.shape[0]:
            raise ValueError("Number of positions and transforms must be the same.")

        if instance_ids is not None:
            instance_ids = np.asarray(instance_ids)
            if instance_ids.shape != (n,):
                raise ValueError(f"instance_ids must have shape ({n},), got {instance_ids.shape}.")
            if instance_ids.size and (
                not np.all(np.isfinite(instance_ids.astype(float)))
                or not np.all(np.equal(np.mod(instance_ids.astype(float), 1), 0))
            ):
                raise ValueError("instance_ids must be integers.")
            instance_ids = instance_ids.astype(np.int64)
            if instance_ids.size and instance_ids.min() < 0:
                raise ValueError("instance_ids must be >= 0.")

        if scores is not None:
            scores = np.asarray(scores, dtype=float)
            if scores.shape != (n,):
                raise ValueError(f"scores must have shape ({n},), got {scores.shape}.")
            if not np.all(np.isfinite(scores)):
                raise ValueError("scores must be finite.")

        points = []

        for i in range(n):
            p = CopickPoint(location=CopickLocation(x=positions[i, 0], y=positions[i, 1], z=positions[i, 2]))
            if transforms is not None:
                p.transformation = transforms[i, :, :]
            if instance_ids is not None:
                p.instance_id = int(instance_ids[i])
            if scores is not None:
                p.score = float(scores[i])
            points.append(p)

        self.points = points
        self.store()

    def df(self, format: str = "relion", **kwargs) -> "pd.DataFrame":
        """Returns the points as a pandas DataFrame with columns based on the format.

        For ``format="relion"``, keyword arguments go to ``copick.util.relion.picks_to_df_relion``
        (``voxel_spacing``, ``tilt_series_pixel_size``, ``tomogram_center``).
        """
        if format == "relion":
            return picks_to_df_relion(self, **kwargs)
        else:
            raise ValueError(f"Format {format} is not supported.")

    def from_df(self, df: "pd.DataFrame", format: str = "relion", **kwargs) -> None:
        """Set the points from a pandas DataFrame with columns based on the format.

        For ``format="relion"``, keyword arguments go to ``copick.util.relion.relion_df_to_picks`` (``optics``,
        ``tilt_series_pixel_size``, ``tomogram_center``, ``relion_version``).
        """
        if format == "relion":
            relion_df_to_picks(self, df, **kwargs)
        else:
            raise ValueError(f"Format {format} is not supported.")


class CopickFilamentCurve(BaseModel):
    """The editable or fitted representation of a filament's centreline, from which its ``points`` are regenerated.

    The curve is optional; ``points`` stay the canonical centreline. See ``docs/datamodel.md`` (Filaments, Editable
    curves) for the specification, and ``copick.util.filaments`` for the reference implementation.

    Attributes:
        kind: ``"catmull-rom"`` (passes through its control points; interactive tracing), ``"linear"``, or
            ``"bspline"`` (a fitted B-spline, stored exactly). Other kinds are kept as they are but never evaluated.
        control_points: ``[[x, y, z], ...]`` in Angstrom, in the direction of ``points``; the B-spline coefficients
            for ``"bspline"``.
        step: Arc-length spacing of the regenerated ``points``, in Angstrom.
        alpha: Catmull-Rom parameterisation; 0.5 (centripetal) when not given.
        degree: B-spline degree (1-5).
        knots: B-spline knots, clamped.
        smoothing: The fit's smoothing factor (scipy's ``s``). Descriptive only.
    """

    model_config = ConfigDict(extra="allow")

    kind: str = Field(min_length=1)
    control_points: List[Tuple[float, float, float]]
    step: float = Field(gt=0)
    alpha: Optional[float] = None
    degree: Optional[int] = None
    knots: Optional[List[float]] = None
    smoothing: Optional[float] = Field(None, ge=0)

    @model_validator(mode="after")
    def validate_curve(self) -> "CopickFilamentCurve":
        """Check a curve of a known kind against its kind's rules."""
        if self.kind == "catmull-rom" and self.alpha is None:
            self.alpha = 0.5
        if self.kind in CURVE_KINDS:
            check_curve(
                self.kind,
                self.control_points,
                self.step,
                alpha=self.alpha,
                degree=self.degree,
                knots=self.knots,
            )
        return self

    @model_serializer(mode="wrap")
    def _omit_unset(self, handler):
        """Leave out the fields that do not apply to the curve's kind."""
        return {key: value for key, value in handler(self).items() if value is not None}

    @property
    def is_known(self) -> bool:
        """Whether this copick evaluates the curve's kind."""
        return self.kind in CURVE_KINDS

    @property
    def passes_through_control_points(self) -> bool:
        """Whether the curve passes through every control point (all but ``bspline``)."""
        return self.kind in ("catmull-rom", "linear")

    def evaluate(self) -> np.ndarray:
        """The (N, 3) centreline points regenerated from this curve."""
        if not self.is_known:
            raise ValueError(f"Cannot evaluate a curve of unknown kind {self.kind!r}.")
        return evaluate_curve(
            self.control_points,
            self.step,
            kind=self.kind,
            alpha=self.alpha,
            degree=self.degree,
            knots=self.knots,
        )

    def anchors(self) -> np.ndarray:
        """The points the curve passes through: its control points, or a B-spline at its knots."""
        return curve_anchors(self.control_points, kind=self.kind, degree=self.degree, knots=self.knots)

    def is_current_for(self, points) -> bool:
        """Whether this curve still describes ``points`` (never, for an unknown kind)."""
        return curve_is_current(
            points,
            self.control_points,
            self.step,
            kind=self.kind,
            degree=self.degree,
            knots=self.knots,
        )

    def reversed(self) -> "CopickFilamentCurve":
        """The same curve traversed backwards."""
        update = {"control_points": list(reversed(self.control_points))}
        if self.knots is not None:
            update["knots"] = [float(u) for u in reverse_knots(self.knots)]
        return CopickFilamentCurve.model_validate({**self.model_dump(), **update})

    @classmethod
    def from_tck(
        cls,
        tck,
        step: float,
        smoothing: Optional[float] = None,
        scale: float = 1.0,
    ) -> "CopickFilamentCurve":
        """A ``bspline`` curve from scipy's ``splprep`` output.

        Args:
            tck: ``(knots, [cx, cy, cz], degree)``, with the coefficients of the x, y and z coordinates.
            step: Arc-length spacing of the regenerated points, in Angstrom.
            smoothing: The fit's smoothing factor, recorded on the curve.
            scale: Factor from the fit's coordinates to Angstrom (the voxel spacing for a fit in voxels).

        Returns:
            The curve.
        """
        knots, coefficients, degree = tck
        coefficients = np.asarray([np.asarray(c, dtype=float) for c in coefficients])
        if coefficients.ndim != 2 or coefficients.shape[0] != 3:
            raise ValueError("tck must hold three coefficient arrays, for x, y and z.")
        count = len(knots) - int(degree) - 1
        control_points = coefficients[:, :count].T * float(scale)
        return cls(
            kind="bspline",
            degree=int(degree),
            knots=[float(u) for u in knots],
            control_points=[tuple(map(float, c)) for c in control_points],
            step=step,
            smoothing=smoothing,
        )


class CopickFilament(BaseModel):
    """One traced filament: an ordered centreline polyline in tomogram coordinates.

    Attributes:
        instance_id: Filament ID (>= 1), unique within its file. Picks sampled from this filament use it as their
            instance ID.
        points: Ordered vertices ``[[x, y, z], ...]`` in Angstrom, at least two. Consecutive vertices should be no
            further apart than the trace's voxel spacing, so that linear interpolation follows the centreline.
        polarity_known: Whether the point order follows the structure's polarity (meaningful for objects whose
            filament spec has ``polar: true``).
        score: Confidence score.
        radius: Tube radius in Angstrom, if measured.
        metadata: Additional metadata (user-defined contents).
        curve: The editable or fitted curve ``points`` were regenerated from, if any (see ``CopickFilamentCurve``).
    """

    instance_id: int = Field(ge=1)
    points: List[Tuple[float, float, float]]
    polarity_known: bool = False
    score: float = 1.0
    radius: Optional[float] = Field(None, gt=0)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    curve: Optional[CopickFilamentCurve] = None

    @field_validator("points")
    @classmethod
    def validate_points(cls, v) -> List[Tuple[float, float, float]]:
        """At least two finite vertices."""
        if len(v) < 2:
            raise ValueError("A filament needs at least two points.")
        if not np.all(np.isfinite(np.asarray(v, dtype=float))):
            raise ValueError("Filament points must be finite.")
        return v

    @field_validator("metadata", mode="before")
    @classmethod
    def none_to_empty_dict(cls, v):
        return {} if v is None else v

    @classmethod
    def from_curve(cls, instance_id: int, curve: CopickFilamentCurve, **fields) -> "CopickFilament":
        """A filament whose ``points`` are regenerated from ``curve``.

        Args:
            instance_id: Filament ID (>= 1).
            curve: The curve (a known kind).
            **fields: Other ``CopickFilament`` fields (``polarity_known``, ``score``, ``radius``, ``metadata``).
        """
        curve = CopickFilamentCurve.model_validate(curve)
        return cls(instance_id=instance_id, points=_point_list(curve.evaluate()), curve=curve, **fields)

    @classmethod
    def from_control_points(
        cls,
        instance_id: int,
        control_points,
        step: float,
        kind: str = "catmull-rom",
        alpha: float = 0.5,
        **fields,
    ) -> "CopickFilament":
        """A filament traced through ``control_points`` (``catmull-rom`` or ``linear``), with regenerated ``points``.

        Args:
            instance_id: Filament ID (>= 1).
            control_points: (n, 3) control points in Angstrom, n >= 2, in order along the filament.
            step: Arc-length spacing of the regenerated points, in Angstrom (usually the voxel spacing).
            kind: ``"catmull-rom"`` or ``"linear"``; a ``bspline`` is made with ``from_curve``.
            alpha: Catmull-Rom parameterisation.
            **fields: Other ``CopickFilament`` fields.
        """
        if kind not in ("catmull-rom", "linear"):
            raise ValueError(f"from_control_points makes catmull-rom or linear curves, not {kind!r}; use from_curve.")
        curve = CopickFilamentCurve(
            kind=kind,
            control_points=_point_list(control_points),
            step=step,
            alpha=alpha if kind == "catmull-rom" else None,
        )
        return cls.from_curve(instance_id, curve, **fields)

    def curve_is_current(self) -> bool:
        """Whether the filament has a curve of a known kind that still describes its ``points``."""
        return self.curve is not None and self.curve.is_current_for(self.points)

    def with_control_points(self, control_points, step: Optional[float] = None) -> "CopickFilament":
        """A copy with moved or new control points and regenerated ``points``, keeping the curve's kind.

        A ``bspline`` keeps its degree and knots, so it needs as many control points as before. A filament without a
        current curve of a known kind gets a ``catmull-rom`` curve.

        Args:
            control_points: The new (n, 3) control points in Angstrom.
            step: Arc-length spacing of the regenerated points; default the curve's (or, without a curve, the median
                spacing of ``points``).
        """
        control_points = _point_list(control_points)
        if self.curve_is_current():
            data = self.curve.model_dump()
            if self.curve.kind == "bspline" and len(control_points) != len(self.curve.control_points):
                raise ValueError(
                    f"A bspline keeps its knots, so it needs {len(self.curve.control_points)} control points, got "
                    f"{len(control_points)}. Convert it with editable_curve(kinds=('catmull-rom',)) to add or remove "
                    "points.",
                )
            curve = {**data, "control_points": control_points, "step": step or self.curve.step}
        else:
            curve = {
                "kind": "catmull-rom",
                "alpha": 0.5,
                "control_points": control_points,
                "step": step or _default_step(self.points),
            }
        fields = self.model_dump(exclude={"instance_id", "points", "curve"})
        return CopickFilament.from_curve(self.instance_id, CopickFilamentCurve.model_validate(curve), **fields)

    def editable_curve(
        self,
        tolerance: Optional[float] = None,
        step: Optional[float] = None,
        kinds: Iterable[str] = CURVE_KINDS,
    ) -> CopickFilamentCurve:
        """The curve an editor should show: the filament's own if it is current and of one of ``kinds``, otherwise a
        ``catmull-rom`` curve derived from ``points`` (``copick.util.filaments.control_points_from_polyline``).

        Args:
            tolerance: Largest distance of the derived curve from ``points``, in Angstrom; default half ``step``.
            step: Spacing of the derived curve's points; default the median spacing of ``points``.
            kinds: The curve kinds the editor supports.
        """
        if self.curve_is_current() and self.curve.kind in tuple(kinds):
            return self.curve
        step = step or _default_step(self.points)
        control_points = control_points_from_polyline(self.points, tolerance or step / 2)
        return CopickFilamentCurve(kind="catmull-rom", alpha=0.5, control_points=_point_list(control_points), step=step)

    def editable_control_points(
        self,
        tolerance: Optional[float] = None,
        step: Optional[float] = None,
        kinds: Iterable[str] = CURVE_KINDS,
    ) -> np.ndarray:
        """The (n, 3) control points of ``editable_curve(...)``."""
        return np.asarray(self.editable_curve(tolerance=tolerance, step=step, kinds=kinds).control_points, dtype=float)

    def reversed(self) -> "CopickFilament":
        """The filament traversed backwards: ``points`` and the curve both reversed."""
        return CopickFilament.model_validate(
            {
                **self.model_dump(exclude={"curve"}),
                "points": list(reversed(self.points)),
                "curve": None if self.curve is None else self.curve.reversed(),
            },
        )


def _point_list(points) -> List[Tuple[float, float, float]]:
    return [tuple(map(float, p)) for p in np.asarray(points, dtype=float).reshape(-1, 3)]


def _default_step(points) -> float:
    spacing = median_spacing(points)
    if spacing <= 0:
        raise ValueError("Cannot derive a step from coincident points; pass step.")
    return spacing


class CopickFilamentsFile(BaseModel):
    """Datamodel for the traced filaments of one pickable object in one run, by one user or tool and session.

    Stored as ``{run}/Filaments/{user_id}_{session_id}_{pickable_object_name}.json``.

    Attributes:
        pickable_object_name: Pickable object name from CopickConfig.pickable_objects[X].name
        user_id: Unique identifier for the user or tool name.
        session_id: Unique identifier for the session. If it is 0, the filaments were generated by a tool.
        run_name: Name of the run the filaments belong to.
        voxel_spacing: Voxel spacing of the data the filaments were traced in, if any.
        unit: Unit of the point coordinates.
        version: Version of this file format.
        filaments (List[CopickFilament]): The filaments.
    """

    pickable_object_name: str
    user_id: str
    session_id: Union[str, Literal["0"]]
    run_name: Optional[str] = None
    voxel_spacing: Optional[float] = None
    unit: str = "angstrom"
    version: int = 1
    filaments: List[CopickFilament] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> "CopickFilamentsFile":
        """Filament IDs are unique within a file."""
        ids = [f.instance_id for f in self.filaments]
        if len(ids) != len(set(ids)):
            raise ValueError("Filament instance IDs must be unique within a file.")
        return self


class CopickFilaments:
    """The traced filaments (ordered centrelines) of one pickable object in one run.

    Attributes:
        run (CopickRun): Reference to the run these filaments belong to.
        meta (CopickFilamentsFile): The filaments and their metadata. Loaded from storage when
            ``CopickFilaments.filaments`` is first accessed.
    """

    def __init__(self, run: CopickRun, file: CopickFilamentsFile):
        """
        Args:
            run: Reference to the run these filaments belong to.
            file: Metadata for this set of filaments.
        """
        self.meta: CopickFilamentsFile = file
        self.run: CopickRun = run
        self._loaded = False

    def __repr__(self):
        count = len(self.meta.filaments) if self._loaded else None
        return (
            f"CopickFilaments(pickable_object_name={self.pickable_object_name}, user_id={self.user_id}, "
            f"session_id={self.session_id}, len(filaments)={count}) at {hex(id(self))}"
        )

    def _load(self) -> CopickFilamentsFile:
        """Override this method to load the filaments from storage."""
        raise NotImplementedError("_load must be implemented for CopickFilaments.")

    def _store(self) -> None:
        """Override this method to store the filaments, creating the file if it doesn't exist."""
        raise NotImplementedError("_store must be implemented for CopickFilaments.")

    def _delete_data(self) -> None:
        """Override this method to delete the filaments from storage."""
        raise NotImplementedError("_delete_data must be implemented for CopickFilaments.")

    def load(self) -> CopickFilamentsFile:
        """Load the filaments from storage."""
        self.meta = self._load()
        self._loaded = True
        return self.meta

    def store(self) -> None:
        """Store the filaments. A curve of a known kind that no longer describes its filament's ``points`` is dropped,
        with a warning, rather than stored."""
        self._drop_stale_curves()
        self._store()
        self._loaded = True

    def _drop_stale_curves(self) -> None:
        stale = [
            f.instance_id
            for f in self.meta.filaments
            if f.curve is not None and f.curve.is_known and not f.curve_is_current()
        ]
        if not stale:
            return
        logger.warning(
            f"Dropping the curves of filaments {stale} of {self.pickable_object_name} ({self.user_id}/{self.session_id}): "
            "their points were changed without regenerating them from the curve.",
        )
        self.meta = CopickFilamentsFile.model_validate(
            {
                **self.meta.model_dump(),
                "filaments": [
                    f.model_copy(update={"curve": None}) if f.instance_id in stale else f for f in self.meta.filaments
                ],
            },
        )

    def refresh(self) -> None:
        """Reload the filaments from storage."""
        self.load()

    def delete(self) -> None:
        """Delete the filaments."""
        self._delete_data()
        if self.run._filaments is not None and self in self.run._filaments:
            self.run._filaments.remove(self)

    @property
    def from_tool(self) -> bool:
        return self.session_id == "0"

    @property
    def from_user(self) -> bool:
        return self.session_id != "0"

    @property
    def pickable_object_name(self) -> str:
        return self.meta.pickable_object_name

    @property
    def user_id(self) -> str:
        return self.meta.user_id

    @property
    def session_id(self) -> Union[str, Literal["0"]]:
        return self.meta.session_id

    @property
    def voxel_spacing(self) -> Optional[float]:
        return self.meta.voxel_spacing

    @property
    def filaments(self) -> List[CopickFilament]:
        if not self._loaded:
            self.load()
        return self.meta.filaments

    @filaments.setter
    def filaments(self, value: List[CopickFilament]) -> None:
        self.meta = CopickFilamentsFile.model_validate({**self.meta.model_dump(), "filaments": value})
        self._loaded = True

    def get(self, instance_id: int) -> Optional[CopickFilament]:
        """The filament with this instance ID, or None."""
        for filament in self.filaments:
            if filament.instance_id == instance_id:
                return filament
        return None

    def instance_ids(self) -> np.ndarray:
        """The filaments' instance IDs, in file order."""
        return np.array([f.instance_id for f in self.filaments], dtype=np.int64)

    def numpy(self) -> List[np.ndarray]:
        """The centrelines as a list of (M, 3) arrays of [x, y, z] in Angstrom, in file order."""
        return [np.asarray(f.points, dtype=float).reshape(-1, 3) for f in self.filaments]

    def from_numpy(
        self,
        polylines: List[np.ndarray],
        instance_ids: Optional[List[int]] = None,
        polarity_known: Optional[List[bool]] = None,
        scores: Optional[List[float]] = None,
        radii: Optional[List[Optional[float]]] = None,
        voxel_spacing: Optional[float] = None,
        metadata: Optional[List[Optional[Dict[str, Any]]]] = None,
    ) -> None:
        """Set the filaments from (M, 3) arrays of ordered points in Angstrom, and store them. The filaments have no
        curves; use ``from_control_points`` or ``from_curves`` for editable ones.

        Args:
            polylines: One (M, 3) array per filament, M >= 2, in order along the filament.
            instance_ids: Filament IDs (>= 1, unique). Default 1..K.
            polarity_known: Per filament, whether the point order follows the polarity. Default False.
            scores: Per filament score. Default 1.0.
            radii: Per filament tube radius in Angstrom, or None.
            voxel_spacing: Voxel spacing the filaments were traced in, recorded in the file.
            metadata: Per filament metadata, or None.

        Raises:
            ValueError: If the arguments' lengths differ or a filament is invalid.
        """
        fields = _per_filament_fields(len(polylines), instance_ids, polarity_known, scores, radii, metadata)
        filaments = [CopickFilament(points=_point_list(line), **f) for line, f in zip(polylines, fields, strict=True)]
        self._set(filaments, voxel_spacing)

    def from_curves(
        self,
        curves: List[CopickFilamentCurve],
        instance_ids: Optional[List[int]] = None,
        polarity_known: Optional[List[bool]] = None,
        scores: Optional[List[float]] = None,
        radii: Optional[List[Optional[float]]] = None,
        voxel_spacing: Optional[float] = None,
        metadata: Optional[List[Optional[Dict[str, Any]]]] = None,
    ) -> None:
        """Set the filaments from curves, regenerating their ``points``, and store them.

        Args:
            curves: One ``CopickFilamentCurve`` (or dict of its fields) per filament, of a known kind; for example
                ``CopickFilamentCurve.from_tck(...)`` for a scipy spline fit.
            instance_ids, polarity_known, scores, radii, voxel_spacing, metadata: As for ``from_numpy``.
        """
        fields = _per_filament_fields(len(curves), instance_ids, polarity_known, scores, radii, metadata)
        filaments = [CopickFilament.from_curve(curve=curve, **f) for curve, f in zip(curves, fields, strict=True)]
        self._set(filaments, voxel_spacing)

    def from_control_points(
        self,
        control_points: List[np.ndarray],
        instance_ids: Optional[List[int]] = None,
        step: Optional[float] = None,
        kind: str = "catmull-rom",
        alpha: float = 0.5,
        polarity_known: Optional[List[bool]] = None,
        scores: Optional[List[float]] = None,
        radii: Optional[List[Optional[float]]] = None,
        voxel_spacing: Optional[float] = None,
        metadata: Optional[List[Optional[Dict[str, Any]]]] = None,
    ) -> None:
        """Set the filaments from traced control points (``catmull-rom`` or ``linear`` curves), regenerating their
        ``points``, and store them.

        Args:
            control_points: One (n, 3) array per filament, n >= 2, in order along the filament, in Angstrom.
            instance_ids: Filament IDs (>= 1, unique). Default 1..K.
            step: Arc-length spacing of the regenerated points; default ``voxel_spacing`` (or the file's).
            kind: ``"catmull-rom"`` or ``"linear"``.
            alpha: Catmull-Rom parameterisation.
            polarity_known, scores, radii, voxel_spacing, metadata: As for ``from_numpy``.
        """
        step = step or voxel_spacing or self.meta.voxel_spacing
        if not step:
            raise ValueError("Pass step or voxel_spacing: the spacing of the regenerated points.")
        fields = _per_filament_fields(len(control_points), instance_ids, polarity_known, scores, radii, metadata)
        filaments = [
            CopickFilament.from_control_points(control_points=cps, step=step, kind=kind, alpha=alpha, **f)
            for cps, f in zip(control_points, fields, strict=True)
        ]
        self._set(filaments, voxel_spacing)

    def _set(self, filaments: List[CopickFilament], voxel_spacing: Optional[float]) -> None:
        self.meta = CopickFilamentsFile.model_validate(
            {
                **self.meta.model_dump(),
                "filaments": filaments,
                "voxel_spacing": voxel_spacing if voxel_spacing is not None else self.meta.voxel_spacing,
            },
        )
        self._loaded = True
        self.store()

    def control_points(self) -> List[Optional[np.ndarray]]:
        """Per filament, in file order, the (n, 3) control points of its current curve, or None."""
        return [
            np.asarray(f.curve.control_points, dtype=float) if f.curve_is_current() else None for f in self.filaments
        ]

    def editable_curve(
        self,
        instance_id: int,
        tolerance: Optional[float] = None,
        kinds: Iterable[str] = CURVE_KINDS,
    ) -> CopickFilamentCurve:
        """``CopickFilament.editable_curve`` for one filament, deriving a curve at the file's voxel spacing: points
        ``voxel_spacing`` apart, within half of it of the stored points.

        Raises:
            KeyError: If no filament has this ID.
        """
        filament = self.get(instance_id)
        if filament is None:
            raise KeyError(f"No filament with instance ID {instance_id}.")
        step = self.voxel_spacing or None
        return filament.editable_curve(tolerance=tolerance or (step / 2 if step else None), step=step, kinds=kinds)


def _per_filament_fields(
    k: int,
    instance_ids: Optional[List[int]],
    polarity_known: Optional[List[bool]],
    scores: Optional[List[float]],
    radii: Optional[List[Optional[float]]],
    metadata: Optional[List[Optional[Dict[str, Any]]]],
) -> List[Dict[str, Any]]:
    """The per-filament fields of the ``CopickFilaments.from_*`` setters, checking each list has ``k`` entries."""
    for name, values in (
        ("instance_ids", instance_ids),
        ("polarity_known", polarity_known),
        ("scores", scores),
        ("radii", radii),
        ("metadata", metadata),
    ):
        if values is not None and len(values) != k:
            raise ValueError(f"{name} must have one entry per filament ({k}), got {len(values)}.")
    return [
        {
            "instance_id": int(instance_ids[i]) if instance_ids is not None else i + 1,
            "polarity_known": bool(polarity_known[i]) if polarity_known is not None else False,
            "score": float(scores[i]) if scores is not None else 1.0,
            "radius": None if radii is None or radii[i] is None else float(radii[i]),
            "metadata": {} if metadata is None or metadata[i] is None else dict(metadata[i]),
        }
        for i in range(k)
    ]


class CopickMeshMeta(BaseModel):
    """Data model for mesh metadata.

    Attributes:
        pickable_object_name: Pickable object name from `CopickConfig.pickable_objects[...].name`
        user_id: Unique identifier for the user or tool name.
        session_id: Unique identifier for the pick session. If it is 0, this pick was generated by a tool.
    """

    pickable_object_name: str
    user_id: str
    session_id: Union[str, Literal["0"]]


class CopickMesh:
    """Encapsulates all data pertaining to a specific mesh. This includes the mesh (`trimesh.parent.Geometry`) and other
    metadata.

    Attributes:
        run (CopickRun): Reference to the run this mesh belongs to.
        meta (CopickMeshMeta): Metadata for this mesh.
        mesh (trimesh.parent.Geometry): Mesh for this pick. Either populated from storage or lazily loaded when
            `CopickMesh.mesh` is accessed **for the first time**.
        from_tool (bool): Flag to indicate if this pick was generated by a tool.
        from_user (bool): Flag to indicate if this pick was generated by a user.
        pickable_object_name (str): Pickable object name from `CopickConfig.pickable_objects[...].name`
        user_id (str): Unique identifier for the user or tool name.
        session_id (str): Unique identifier for the pick session
        color: Color of the pickable object this pick belongs to.
    """

    def __init__(self, run: CopickRun, meta: CopickMeshMeta, mesh: Optional["Geometry"] = None):
        self.meta: CopickMeshMeta = meta
        self.run: CopickRun = run

        if mesh is not None:
            self._mesh = mesh
        else:
            self._mesh = None

    def __repr__(self):
        ret = (
            f"CopickMesh(pickable_object_name={self.pickable_object_name}, user_id={self.user_id}, "
            f"session_id={self.session_id}) at {hex(id(self))}"
        )
        return ret

    @property
    def pickable_object_name(self) -> str:
        return self.meta.pickable_object_name

    @property
    def user_id(self) -> str:
        return self.meta.user_id

    @property
    def session_id(self) -> Union[str, Literal["0"]]:
        return self.meta.session_id

    @property
    def color(self):
        return self.run.root.get_object(self.pickable_object_name).color

    def _load(self) -> "Geometry":
        """Override this method to load mesh from a RESTful interface or filesystem."""
        raise NotImplementedError("load must be implemented for CopickMesh.")

    def _store(self):
        """Override this method to store mesh with a RESTful interface or filesystem. Also needs to handle creating
        the file if it doesn't exist."""
        raise NotImplementedError("store must be implemented for CopickMesh.")

    def load(self) -> "Geometry":
        """Load the mesh from storage.

        Returns:
            trimesh.parent.Geometry: The loaded mesh.
        """
        self._mesh = self._load()

        return self._mesh

    def store(self):
        """Store the mesh."""
        self._store()

    @property
    def mesh(self) -> "Geometry":
        if self._mesh is None:
            self._mesh = self.load()

        return self._mesh

    @mesh.setter
    def mesh(self, value: "Geometry") -> None:
        self._mesh = value

    @property
    def from_user(self) -> bool:
        return self.session_id != "0"

    @property
    def from_tool(self) -> bool:
        return self.session_id == "0"

    def refresh(self) -> None:
        """Refresh `CopickMesh.mesh` from storage."""
        self._mesh = self.load()

    def delete(self) -> None:
        """Delete the mesh record."""
        self._delete_data()

        # Remove the mesh from the run
        if self in self.run.meshes:
            self.run._meshes.remove(self)

    def _delete_data(self) -> None:
        """Delete the mesh data."""
        raise NotImplementedError("_delete_data must be implemented for CopickMesh.")


class CopickSegmentationMeta(BaseModel):
    """Datamodel for segmentation metadata.

    Attributes:
        user_id: Unique identifier for the user or tool name.
        session_id: Unique identifier for the segmentation session. If it is 0, this segmentation was generated by a
            tool.
        name: Pickable Object name or multilabel name of the segmentation.
        is_multilabel: Flag to indicate if this is a multilabel segmentation: several objects, each voxel holding
            an object's ``label``.
        is_instance: Flag to indicate if this is an instance segmentation: one object (``name``), each voxel
            holding the ID of the instance it belongs to, 0 for background.
        is_panoptic: Flag to indicate if this is a panoptic segmentation: two channels, each voxel's object
            ``label`` (channel 0) and its instance ID within that object (channel 1).
        voxel_size: Voxel size in angstrom of the tomogram this segmentation belongs to. Rounded to the third decimal.

    A segmentation with no flag is binary: one object (``name``), 1 inside, 0 outside. At most one flag is set.
    """

    user_id: str
    session_id: Union[str, Literal["0"]]
    name: str
    is_multilabel: bool
    is_instance: bool = False
    is_panoptic: bool = False
    voxel_size: float

    @model_validator(mode="after")
    def _one_type(self) -> "CopickSegmentationMeta":
        segmentation_type(self.is_multilabel, self.is_instance, self.is_panoptic)
        return self


class CopickSegmentation:
    """Encapsulates all data pertaining to a specific segmentation. This includes the Zarr-store for the segmentation
    and other metadata.

    Attributes:
        run (CopickRun): Reference to the run this segmentation belongs to.
        meta (CopickSegmentationMeta): Metadata for this segmentation.
        zarr (Store): Zarr store for this segmentation. Either populated from storage or lazily loaded when
            `CopickSegmentation.zarr` is accessed **for the first time**.
        from_tool (bool): Flag to indicate if this segmentation was generated by a tool.
        from_user (bool): Flag to indicate if this segmentation was generated by a user.
        user_id (str): Unique identifier for the user or tool name.
        session_id (str): Unique identifier for the segmentation session
        is_multilabel (bool): Flag to indicate if this is a multilabel segmentation.
        is_instance (bool): Flag to indicate if this is an instance segmentation: voxel values are instance IDs of
            the object ``name``, 0 for background.
        is_panoptic (bool): Flag to indicate if this is a panoptic segmentation: a ``(2, Z, Y, X)`` volume holding
            each voxel's object ``label`` and its instance ID within that object.
        segmentation_type (str): ``"binary"``, ``"multilabel"``, ``"instance"`` or ``"panoptic"``.
        directory (str): The run-level directory holding the store.
        voxel_size (float): Voxel size of the tomogram this segmentation belongs to.
        name (str): Pickable Object name or multilabel name of the segmentation.
        color: Color of the pickable object this segmentation belongs to.
    """

    def __init__(self, run: CopickRun, meta: CopickSegmentationMeta):
        """

        Args:
            run: Reference to the run this segmentation belongs to.
            meta: Metadata for this segmentation.
        """
        self.meta: CopickSegmentationMeta = meta
        self.run: CopickRun = run

    def __repr__(self):
        ret = (
            f"CopickSegmentation(user_id={self.user_id}, session_id={self.session_id}, name={self.name}, "
            f"segmentation_type={self.segmentation_type}, voxel_size={self.voxel_size}) at {hex(id(self))}"
        )
        return ret

    @property
    def user_id(self) -> str:
        return self.meta.user_id

    @property
    def session_id(self) -> Union[str, Literal["0"]]:
        return self.meta.session_id

    @property
    def from_tool(self) -> bool:
        return self.session_id == "0"

    @property
    def from_user(self) -> bool:
        return self.session_id != "0"

    @property
    def is_multilabel(self) -> bool:
        return self.meta.is_multilabel

    @property
    def is_instance(self) -> bool:
        return self.meta.is_instance

    @property
    def is_panoptic(self) -> bool:
        return self.meta.is_panoptic

    @property
    def segmentation_type(self) -> Literal["binary", "multilabel", "instance", "panoptic"]:
        return segmentation_type(self.is_multilabel, self.is_instance, self.is_panoptic)

    @property
    def directory(self) -> str:
        """The run-level directory holding this segmentation's store (``Segmentations`` for binary and multilabel,
        ``InstanceSegmentations`` and ``PanopticSegmentations`` for the newer types)."""
        return segmentation_directory(self.is_multilabel, self.is_instance, self.is_panoptic)

    @property
    def voxel_size(self) -> float:
        return self.meta.voxel_size

    @property
    def name(self) -> str:
        return self.meta.name

    @property
    def color(self):
        if self.is_multilabel or self.is_panoptic:
            return [128, 128, 128, 0]
        obj = self.run.root.get_object(self.name)
        # A store whose name is not (or no longer) a pickable object still lists; it just has no colour of its own.
        return obj.color if obj is not None else [128, 128, 128, 0]

    def delete(self) -> None:
        """Delete the segmentation record."""
        self._delete_data()

        # Remove the segmentation from the run
        if self in self.run.segmentations:
            self.run._segmentations.remove(self)

    def _delete_data(self) -> None:
        """Delete the segmentation data."""
        raise NotImplementedError("_delete_data must be implemented for CopickSegmentation.")

    def zarr(self) -> Store:
        """Override to return the Zarr store for this segmentation. Also needs to handle creating the store if it
        doesn't exist."""
        raise NotImplementedError("zarr must be implemented for CopickSegmentation.")

    def numpy(
        self,
        zarr_group: Optional[str] = None,
        x: slice = slice(None, None),
        y: slice = slice(None, None),
        z: slice = slice(None, None),
        channel: Optional[Union[str, int]] = None,
    ) -> np.ndarray:
        """Returns the content of the Zarr-File for this segmentation as a numpy array. Multiscale group and slices are
        supported.

        Args:
            zarr_group: Explicit Zarr array path. By default, resolve level 0 from OME metadata.
            x: Slice for the x-axis.
            y: Slice for the y-axis.
            z: Slice for the z-axis.
            channel: Panoptic segmentations only: ``"label"`` (0) or ``"instance"`` (1) returns that channel as a
                ``(Z, Y, X)`` array; ``None`` returns both, ``(2, Z, Y, X)``.

        Returns:
            np.ndarray: The segmentation as a numpy array.
        """

        loc = self.zarr()
        group = _open_zarr_array(loc, zarr_group, mode="r")

        if self.is_panoptic:
            c = slice(None) if channel is None else panoptic_channel_index(channel)
            fits, req, avail = fits_in_memory(group, (c if isinstance(c, slice) else slice(c, c + 1), z, y, x))
            if not fits:
                raise ValueError(f"Requested region does not fit in memory. Requested: {req}, Available: {avail}.")
            return np.array(group[c, z, y, x])
        if channel is not None:
            raise ValueError(f"{self} is a {self.segmentation_type} segmentation; only panoptic ones have channels.")

        fits, req, avail = fits_in_memory(group, (x, y, z))
        if not fits:
            raise ValueError(f"Requested region does not fit in memory. Requested: {req}, Available: {avail}.")

        return np.array(group[z, y, x])

    def from_numpy(
        self,
        data: np.ndarray,
        levels: int = 1,
        dtype: Optional[np.dtype] = None,
    ) -> None:
        """Set the segmentation from a numpy array and compute multiscale pyramid. By default, no pyramid is computed
        for segmentations.

        Args:
            data: The segmentation as a numpy array: ``(Z, Y, X)``, or ``(2, Z, Y, X)`` for a panoptic segmentation
                (``np.stack([labels, instance_ids])``).
            levels: Number of levels in the multiscale pyramid.
            dtype: Data type of the segmentation. ``None`` (the default) chooses the smallest unsigned integer type
                that holds every value, starting at ``np.uint8`` (``np.uint16`` for instance and panoptic
                segmentations). A value that would not survive the cast raises ``ValueError``; nothing is wrapped or
                truncated.

        Raises:
            ValueError: For a panoptic segmentation, also if the shape is not ``(2, Z, Y, X)``, a label is neither 0
                nor a pickable object's label, or a background voxel carries an instance ID.
        """
        multichannel = self.is_panoptic
        if multichannel:
            data = np.asarray(data)
            if data.ndim != 4 or data.shape[0] != 2:
                raise ValueError(
                    f"A panoptic segmentation is a (2, Z, Y, X) array (channels {PANOPTIC_CHANNELS}), not {data.shape}.",
                )
        if dtype is None:
            dtype = label_dtype(data, floor=np.uint16 if (self.is_instance or multichannel) else np.uint8)
        if multichannel:
            data = checked_label_cast(data, dtype)
            check_panoptic_values(data[0], data[1], self._object_labels())
        loc = self.zarr()
        pyramid = segmentation_pyramid(data, self.voxel_size, levels, dtype=dtype)
        if multichannel:
            # A leading channel axis, one channel per inner chunk; the scale defaults to [1, vs, vs, vs].
            write_ome_zarr(
                loc,
                pyramid,
                [{"name": "c", "type": "channel"}, *ome_zarr_axes()],
                (1, *DEFAULT_SPATIAL_CHUNKS),
                metadata={"copick": {"segmentation_type": "panoptic", "channels": list(PANOPTIC_CHANNELS)}},
            )
        else:
            write_ome_zarr_3d(loc, pyramid)

    def set_region(
        self,
        data: np.ndarray,
        zarr_group: Optional[str] = None,
        x: slice = slice(None, None),
        y: slice = slice(None, None),
        z: slice = slice(None, None),
        channel: Optional[Union[str, int]] = None,
    ) -> None:
        """Set a region of the segmentation from a numpy array.

        Args:
            data: The segmentation's subregion as a numpy array. Values that do not fit the stored dtype raise
                ``ValueError`` instead of wrapping.
            zarr_group: Explicit Zarr array path. By default, resolve level 0 from OME metadata.
            x: Slice for the x-axis.
            y: Slice for the y-axis.
            z: Slice for the z-axis.
            channel: Panoptic segmentations only: write just this channel (``"label"`` or ``"instance"``); ``None``
                writes both from a ``(2, z, y, x)`` array. The result is checked like ``from_numpy``'s.
        """
        loc = self.zarr()
        array = _open_zarr_array(loc, zarr_group, mode="r+")
        if self.is_panoptic:
            if channel is None:
                data = checked_label_cast(data, array.dtype)
                if data.ndim != 4 or data.shape[0] != 2:
                    raise ValueError(f"A panoptic region is a (2, z, y, x) array, not {data.shape}.")
                check_panoptic_values(data[0], data[1], self._object_labels())
                array[:, z, y, x] = data
                return
            index = panoptic_channel_index(channel)
            other = np.asarray(array[1 - index, z, y, x])
            data = np.broadcast_to(checked_label_cast(data, array.dtype), other.shape)
            labels, instances = (data, other) if index == 0 else (other, data)
            check_panoptic_values(labels, instances, self._object_labels())
            array[index, z, y, x] = data
            return
        if channel is not None:
            raise ValueError(f"{self} is a {self.segmentation_type} segmentation; only panoptic ones have channels.")
        array[z, y, x] = checked_label_cast(data, array.dtype)

    def _object_labels(self) -> List[int]:
        return [o.label for o in self.run.root.config.pickable_objects]

    def _object_label(self, object_name: str) -> int:
        obj = self.run.root.get_object(object_name)
        if obj is None:
            raise ValueError(f"Object name {object_name} not found in pickable objects.")
        return obj.label

    def instance_ids(self, zarr_group: Optional[str] = None, object_name: Optional[str] = None) -> np.ndarray:
        """The instance IDs present: the unique non-zero values of an instance segmentation, or of a panoptic
        segmentation's instance channel where the label is ``object_name``'s.

        The volume is read one chunk at a time, so memory stays bounded by the chunk size.

        Args:
            zarr_group: Explicit Zarr array path. By default, resolve level 0 (which holds every instance) from OME
                metadata.
            object_name: Required for a panoptic segmentation, whose instance IDs are per object.

        Returns:
            Sorted ``int64`` array of instance IDs.

        Raises:
            ValueError: If this is neither an instance nor a panoptic segmentation, or ``object_name`` is missing
                (panoptic) or another object than this instance segmentation's.
        """
        array = _open_zarr_array(self.zarr(), zarr_group, mode="r")
        found = np.zeros(0, dtype=array.dtype)
        if self.is_instance:
            if object_name not in (None, self.name):
                raise ValueError(f"{self} holds instances of {self.name}, not {object_name}.")
            for block in _spatial_blocks(array):
                found = np.union1d(found, np.unique(array[block]))
        elif self.is_panoptic:
            if object_name is None:
                raise ValueError("Instance IDs of a panoptic segmentation are per object; pass object_name.")
            label = self._object_label(object_name)
            for block in _spatial_blocks(array):
                labels, instances = array[(slice(None), *block)]
                found = np.union1d(found, np.unique(instances[labels == label]))
        else:
            raise ValueError(
                f"{self} is a {self.segmentation_type} segmentation; instance_ids() needs an instance or panoptic one.",
            )
        return found[found != 0].astype(np.int64)

    def segments(self, zarr_group: Optional[str] = None) -> List[Tuple[str, int]]:
        """The segments of a panoptic segmentation: each ``(object_name, instance_id)`` present, where instance 0
        is a region of that object not split into instances.

        Args:
            zarr_group: Explicit Zarr array path. By default, resolve level 0 from OME metadata.

        Raises:
            ValueError: If this is not a panoptic segmentation.
        """
        if not self.is_panoptic:
            raise ValueError(f"{self} is a {self.segmentation_type} segmentation; segments() needs a panoptic one.")
        array = _open_zarr_array(self.zarr(), zarr_group, mode="r")
        pairs = set()
        for block in _spatial_blocks(array):
            labels, instances = array[(slice(None), *block)]
            inside = labels != 0
            if inside.any():
                rows = np.unique(np.stack([labels[inside], instances[inside]], axis=1), axis=0)
                pairs.update((int(label), int(instance)) for label, instance in rows)
        names = {o.label: o.name for o in self.run.root.config.pickable_objects}
        return sorted((names.get(label, str(label)), instance) for label, instance in pairs)

    def label_volume(self, zarr_group: Optional[str] = None) -> np.ndarray:
        """A panoptic segmentation's label channel: the multilabel segmentation it contains."""
        return self.numpy(zarr_group=zarr_group, channel="label")

    def instance_volume(self, object_name: str, zarr_group: Optional[str] = None) -> np.ndarray:
        """A panoptic segmentation's instances of one object: the instance segmentation it contains for
        ``object_name`` (instance IDs where the label is that object's, 0 elsewhere)."""
        labels, instances = self.numpy(zarr_group=zarr_group)
        return np.where(labels == self._object_label(object_name), instances, 0)


def _spatial_blocks(array: zarr.Array) -> Iterable[Tuple[slice, slice, slice]]:
    """The ``(z, y, x)`` slices of an array's chunk grid over its trailing three (spatial) axes."""
    cz, cy, cx = array.chunks[-3:]
    nz, ny, nx = array.shape[-3:]
    for z0 in range(0, nz, cz):
        for y0 in range(0, ny, cy):
            for x0 in range(0, nx, cx):
                yield slice(z0, z0 + cz), slice(y0, y0 + cy), slice(x0, x0 + cx)


COPICK_TYPES = (
    CopickRoot,
    CopickRun,
    CopickVoxelSpacing,
    CopickTomogram,
    CopickFeatures,
    CopickPicks,
    CopickMesh,
    CopickSegmentation,
    CopickObject,
    CopickFilaments,
)
