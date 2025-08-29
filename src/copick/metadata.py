"""Pydantic metadata models for the Copick data model."""

import json
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

import numpy as np
from pydantic import AliasChoices, BaseModel, Field, field_validator

from copick.util.escape import sanitize_name


class PickableObject(BaseModel):
    """Metadata for a pickable objects.

    Attributes:
        name: Name of the object.
        is_particle: Whether this object should be represented by points (True) or segmentation masks (False).
        label: Numeric label/id for the object, as used in multilabel segmentation masks. Must be unique.
        color: RGBA color for the object.
        emdb_id: EMDB ID for the object.
        pdb_id: PDB ID for the object.
        identifier: Identifier for the object (e.g. Gene Ontology ID or UniProtKB accession).
        map_threshold: Threshold to apply to the map when rendering the isosurface.
        radius: Radius of the particle, when displaying as a sphere.
        metadata: Additional metadata for the object (user-defined contents).
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


class CopickConfig(BaseModel):
    """Configuration for a copick project. Defines the available objects, user_id and optionally an index for runs.

    Attributes:
        name: Name of the CoPick project.
        description: Description of the CoPick project.
        version: Version of the CoPick API.
        pickable_objects (List[PickableObject]): Index for available pickable objects.
        user_id: Unique identifier for the user (e.g. when distributing the config file to users).
        session_id: Unique identifier for the session.
    """

    name: Optional[str] = "CoPick"
    description: Optional[str] = "Let's CoPick!"
    version: Optional[str] = "0.2.0"
    pickable_objects: List[PickableObject]
    user_id: Optional[str] = None
    session_id: Optional[str] = None

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
        location (CopickLocation): Location in 3D space.
        transformation: Transformation matrix.
        instance_id: Instance ID.
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


class CopickRunMeta(BaseModel):
    """Data model for run level metadata.

    Attributes:
        name: Name of the run.
    """

    name: str


class CopickVoxelSpacingMeta(BaseModel):
    """Data model for voxel spacing metadata.

    Attributes:
        voxel_size: Voxel size in angstrom, rounded to the third decimal.
    """

    voxel_size: float


class CopickTomogramMeta(BaseModel):
    """Data model for tomogram metadata.

    Attributes:
        tomo_type: Type of the tomogram.
    """

    tomo_type: str


class CopickFeaturesMeta(BaseModel):
    """Data model for feature map metadata.

    Attributes:
        tomo_type: Type of the tomogram that the features were computed on.
        feature_type: Type of the features contained.
    """

    tomo_type: str
    feature_type: str


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


class CopickSegmentationMeta(BaseModel):
    """Datamodel for segmentation metadata.

    Attributes:
        user_id: Unique identifier for the user or tool name.
        session_id: Unique identifier for the segmentation session. If it is 0, this segmentation was generated by a
            tool.
        name: Pickable Object name or multilabel name of the segmentation.
        is_multilabel: Flag to indicate if this is a multilabel segmentation. If False, it is a single label
            segmentation.
        voxel_size: Voxel size in angstrom of the tomogram this segmentation belongs to. Rounded to the third decimal.
    """

    user_id: str
    session_id: Union[str, Literal["0"]]
    name: str
    is_multilabel: bool
    voxel_size: float
