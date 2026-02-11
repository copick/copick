import json
import re
import warnings
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Type, Union

import cryoet_data_portal as cdp
import fsspec
import numpy as np
import s3fs
import zarr
from fsspec import AbstractFileSystem
from pydantic import BaseModel, create_model, field_validator

from copick.impl.overlay import (
    CopickFeaturesOverlay,
    CopickMeshOverlay,
    CopickObjectOverlay,
    CopickPicksOverlay,
    CopickRunOverlay,
    CopickSegmentationOverlay,
    CopickTomogramOverlay,
    CopickVoxelSpacingOverlay,
)
from copick.models import (
    CopickConfig,
    CopickFeaturesMeta,
    CopickLocation,
    CopickMeshMeta,
    CopickPicksFile,
    CopickPoint,
    CopickRoot,
    CopickRunMeta,
    CopickSegmentationMeta,
    CopickTomogramMeta,
    CopickVoxelSpacingMeta,
    PickableObject,
)
from copick.util.log import get_logger

# Don't import Geometry at runtime to keep CLI snappy
if TYPE_CHECKING:
    from trimesh.parent import Geometry

logger = get_logger(__name__)


def camel(s: str) -> str:
    s = re.sub(r"([_\-])+", " ", s).title().replace(" ", "")
    return "".join([s[0].lower(), s[1:]])


_portal_types = Union[Type[cdp.Annotation], Type[cdp.AnnotationFile], Type[cdp.Tomogram], Type[cdp.AnnotationShape]]


def _portal_to_model(clz: _portal_types, name: str) -> Type[BaseModel]:
    """Automatically create a Pydantic model from a CryoET Data Portal annotation class."""
    vals = clz.__annotations__
    scalars = {k: (Optional[v], None) for k, v in vals.items() if v in ["int", "float", "str", "bool"] and k[0] != "_"}
    return create_model(name, **scalars)


_PortalAnnotation = _portal_to_model(cdp.Annotation, "_PortalAnnotation")
_PortalAnnotationShape = _portal_to_model(cdp.AnnotationShape, "_PortalAnnotationShape")
_PortalAnnotationFile = _portal_to_model(cdp.AnnotationFile, "_PortalAnnotationFile")
_PortalTomogram = _portal_to_model(cdp.Tomogram, "_PortalTomogram")


@dataclass
class PortalCache:
    """Cache for portal annotation data shared across all runs."""

    picks_files_by_run: Dict[int, List[Any]] = field(default_factory=dict)  # Point/OrientedPoint
    seg_files_by_run: Dict[int, List[Any]] = field(default_factory=dict)  # SegmentationMask
    annotation_shapes: Dict[int, Any] = field(default_factory=dict)  # id -> shape
    annotations: Dict[int, Any] = field(default_factory=dict)  # id -> annotation
    author_names: Dict[int, List[str]] = field(default_factory=dict)  # annotation_id -> names
    voxel_spacings: Dict[int, Any] = field(default_factory=dict)  # id -> voxel_spacing

    # Tomogram cache
    tomograms_by_vs: Dict[int, List[Any]] = field(default_factory=dict)  # vs_id -> tomograms
    tomogram_authors: Dict[int, List[str]] = field(default_factory=dict)  # tomogram_id -> authors


class PortalAnnotationMeta(BaseModel):
    """A class to hold the portal anotation file information and the associated annotation file and shape."""

    portal_annotation: Optional[_PortalAnnotation] = _PortalAnnotation()
    portal_annotation_shape: Optional[_PortalAnnotationShape] = _PortalAnnotationShape()
    portal_annotation_file: Optional[_PortalAnnotationFile] = _PortalAnnotationFile()
    voxel_spacing: Optional[float] = None
    portal_author_names: Optional[List[str]] = []

    @field_validator("portal_annotation", mode="before")
    @classmethod
    def check_portal_annotation(cls, v: Union[_PortalAnnotation, cdp.Annotation]) -> _PortalAnnotation:
        if isinstance(v, cdp.Annotation):
            return _PortalAnnotation(**v.to_dict())
        return v

    @field_validator("portal_annotation_shape", mode="before")
    @classmethod
    def check_portal_annotation_shape(
        cls,
        v: Union[_PortalAnnotationShape, cdp.AnnotationShape],
    ) -> _PortalAnnotationShape:
        if isinstance(v, cdp.AnnotationShape):
            return _PortalAnnotationShape(**v.to_dict())
        return v

    @field_validator("portal_annotation_file", mode="before")
    @classmethod
    def check_portal_annotation_file(cls, v: Union[_PortalAnnotationFile, cdp.AnnotationFile]) -> _PortalAnnotationFile:
        if isinstance(v, cdp.AnnotationFile):
            return _PortalAnnotationFile(**v.to_dict())
        return v

    @classmethod
    def from_annotation_file(cls, source: cdp.AnnotationFile):
        return cls(
            portal_annotation_file=_PortalAnnotationFile(**source.to_dict()),
            portal_annotation_shape=_PortalAnnotationShape(**source.annotation_shape.to_dict()),
            portal_annotation=_PortalAnnotation(**source.annotation_shape.annotation.to_dict()),
            voxel_spacing=source.tomogram_voxel_spacing.voxel_spacing,
            portal_author_names=[a.name for a in source.annotation_shape.annotation.authors],
        )

    @property
    def annotation_id(self) -> int:
        return self.portal_annotation.id

    @property
    def annotation_shape_id(self) -> int:
        return self.portal_annotation_shape.id

    @property
    def annotation_file_id(self) -> int:
        return self.portal_annotation_file.id

    @property
    def shape_type(self) -> str:
        return self.portal_annotation_shape.shape_type

    @property
    def object_name(self) -> str:
        return self.portal_annotation.object_name

    @property
    def object_id(self) -> int:
        return self.portal_annotation.object_id

    @property
    def s3_path(self) -> str:
        return self.portal_annotation_file.s3_path

    @property
    def portal_authors(self) -> List[str]:
        return self.portal_author_names

    def compare(self, meta: Dict[str, Any], authors: List[str]) -> bool:
        # To convert to proper format
        qpm = _PortalAnnotation(**meta)
        qa = authors

        # Select fields to compare
        fields = list(qpm.model_fields_set)
        test_fields = [f for f in fields if getattr(qpm, f) is not None]

        # Check if all authors are in the list
        author_condition = all(a in self.portal_authors for a in qa)
        # Check if all fields are equal
        meta_condition = all(getattr(self.portal_annotation, f) == getattr(qpm, f) for f in test_fields)

        return author_condition and meta_condition


class PortalTomogramMeta(BaseModel):
    portal_metadata: Optional[_PortalTomogram] = _PortalTomogram()
    portal_authors: Optional[List[str]] = []

    @classmethod
    def from_tomogram(cls, source: cdp.Tomogram):
        return cls(
            portal_metadata=_PortalTomogram(**source.to_dict()),
            portal_authors=[a.name for a in source.authors],
        )

    @classmethod
    def from_portal_cached(cls, source: cdp.Tomogram, author_names: List[str]):
        """Create metadata from cached portal objects (avoids lazy loading for authors)."""
        return cls(
            portal_metadata=_PortalTomogram(**source.to_dict()),
            portal_authors=author_names,
        )

    def compare(self, meta: Dict[str, Any], authors: List[str]) -> bool:
        # To convert to proper format
        qpm = _PortalTomogram(**meta)
        qa = authors

        # Select fields to compare
        fields = list(qpm.model_fields_set)
        test_fields = [f for f in fields if getattr(qpm, f) is not None]

        # Check if all authors are in the list
        author_condition = all(a in self.portal_authors for a in qa)
        # Check if all fields are equal
        meta_condition = all(getattr(self.portal_metadata, f) == getattr(qpm, f) for f in test_fields)

        return author_condition and meta_condition


class CopickConfigCDP(CopickConfig):
    config_type: str = "cryoet_data_portal"
    overlay_root: str
    dataset_ids: List[int]

    overlay_fs_args: Optional[Dict[str, Any]] = {}


class CopickPicksFileCDP(CopickPicksFile):
    portal_metadata: Optional[PortalAnnotationMeta] = PortalAnnotationMeta()

    @classmethod
    def from_portal_container(cls, source: PortalAnnotationMeta, name: Optional[str] = None):
        """Create a CopickPicksFileCDP from portal metadata WITHOUT loading S3 data.

        Points are loaded lazily when accessed via the points property.
        """
        shape_type = source.shape_type
        user = "data-portal"
        session = str(source.annotation_file_id)
        object_name = f"{name}" if name else f"{camel(source.object_name)}-{source.annotation_file_id}"

        clz = cls(
            pickable_object_name=object_name,
            user_id=user,
            session_id=session,
            portal_metadata=source,
            points=[],  # Empty - will be loaded lazily
        )

        if shape_type == "OrientedPoint":
            clz.trust_orientation = True
        else:
            clz.trust_orientation = False

        return clz

    @staticmethod
    def _load_points_from_s3(portal_meta: PortalAnnotationMeta) -> List[CopickPoint]:
        """Load point data from S3 for a portal annotation.

        This is called lazily when points are first accessed.
        """
        fs = s3fs.S3FileSystem(anon=True)
        vs = portal_meta.voxel_spacing
        shape_type = portal_meta.shape_type
        points = []

        with fs.open(portal_meta.s3_path, "r") as f:
            content = f.read()

        for line in content.strip().split("\n"):
            data = json.loads(line)
            x = data["location"]["x"] * vs
            y = data["location"]["y"] * vs
            z = data["location"]["z"] * vs

            if shape_type == "OrientedPoint":
                mat = np.eye(4, 4)
                mat[:3, :3] = np.array(data["xyz_rotation_matrix"])
                point = CopickPoint(
                    location=CopickLocation(x=x, y=y, z=z),
                    transformation_=mat.tolist(),
                )
            else:
                point = CopickPoint(location=CopickLocation(x=x, y=y, z=z))
            points.append(point)

        return points

    @property
    def portal_annotation_id(self) -> int:
        return self.portal_metadata.annotation_id

    @property
    def portal_annotation_file_id(self) -> int:
        return self.portal_metadata.annotation_file_id

    @property
    def portal_annotation_file_path(self) -> str:
        return self.portal_metadata.s3_path


class CopickPicksCDP(CopickPicksOverlay):
    run: "CopickRunCDP"
    meta: CopickPicksFileCDP

    @property
    def from_tool(self) -> bool:
        return bool(self.read_only or self.session_id == "0")

    @property
    def from_user(self) -> bool:
        return not self.from_tool

    @property
    def path(self) -> str:
        if self.read_only:
            return self.meta.portal_annotation_file_path
        else:
            return f"{self.run.overlay_path}/Picks/{self.user_id}_{self.session_id}_{self.pickable_object_name}.json"

    @property
    def directory(self) -> Union[str, None]:
        if self.read_only:
            return None
        else:
            return f"{self.run.overlay_path}/Picks/"

    @property
    def fs(self) -> AbstractFileSystem:
        return s3fs.S3FileSystem(anon=True) if self.read_only else self.run.fs_overlay

    def _load(self) -> CopickPicksFile:
        # For read-only portal picks, load points from S3
        if self.read_only and self.meta.portal_metadata is not None:
            points = CopickPicksFileCDP._load_points_from_s3(self.meta.portal_metadata)
            # Update the metadata with loaded points
            return CopickPicksFileCDP(
                pickable_object_name=self.meta.pickable_object_name,
                user_id=self.meta.user_id,
                session_id=self.meta.session_id,
                portal_metadata=self.meta.portal_metadata,
                trust_orientation=self.meta.trust_orientation,
                points=points,
            )

        # For overlay picks, load from filesystem
        if not self.fs.exists(self.path):
            logger.critical(f"File not found: {self.path}")
            raise FileNotFoundError(f"File not found: {self.path}")

        with self.fs.open(self.path, "r") as f:
            data = json.load(f)

        return CopickPicksFileCDP(**data)

    def _store(self) -> None:
        if not self.fs.exists(self.directory):
            self.fs.makedirs(self.directory, exist_ok=True)

        with self.fs.open(self.path, "w") as f:
            json.dump(self.meta.model_dump(), f, indent=4)

    def _delete_data(self) -> None:
        if self.fs.exists(self.path):
            self.fs.rm(self.path)
        else:
            raise FileNotFoundError(f"File not found: {self.path}")


class CopickMeshCDP(CopickMeshOverlay):
    run: "CopickRunCDP"

    @property
    def from_tool(self) -> bool:
        return bool(self.read_only or self.session_id == "0")

    @property
    def from_user(self) -> bool:
        return not self.from_tool

    @property
    def path(self) -> Union[str, None]:
        if self.read_only:
            return None
        else:
            return f"{self.run.overlay_path}/Meshes/{self.user_id}_{self.session_id}_{self.pickable_object_name}.glb"

    @property
    def directory(self) -> Union[str, None]:
        if self.read_only:
            return None
        else:
            return f"{self.run.overlay_path}/Meshes/"

    @property
    def fs(self) -> Union[AbstractFileSystem, None]:
        return None if self.read_only else self.run.fs_overlay

    def _load(self) -> Union["Geometry", None]:
        if not self.fs.exists(self.path):
            logger.critical(f"File not found: {self.path}")
            raise FileNotFoundError(f"File not found: {self.path}")

        with self.fs.open(self.path, "rb") as f:
            # Defer trimesh import to keep CLI snappy (trimesh imports scipy)
            import trimesh

            scene = trimesh.load(f, file_type="glb")

        return scene

    def _store(self):
        if not self.fs.exists(self.directory):
            self.fs.makedirs(self.directory, exist_ok=True)

        with self.fs.open(self.path, "wb") as f:
            _ = self._mesh.export(f, file_type="glb")

    def _delete_data(self):
        if self.fs.exists(self.path):
            self.fs.rm(self.path)
        else:
            raise FileNotFoundError(f"File not found: {self.path}")


class CopickSegmentationMetaCDP(CopickSegmentationMeta):
    portal_metadata: Optional[PortalAnnotationMeta] = PortalAnnotationMeta()

    @classmethod
    def from_portal(cls, source: cdp.AnnotationFile, name: Optional[str] = None):
        object_name = f"{name}" if name else f"{camel(source.annotation_shape.annotation.object_name)}-{source.id}"

        portal_meta = PortalAnnotationMeta.from_annotation_file(source)

        return cls(
            is_multilabel=False,
            voxel_size=source.tomogram_voxel_spacing.voxel_spacing,
            user_id="data-portal",
            session_id=str(source.id),
            name=object_name,
            portal_metadata=portal_meta,
        )

    @property
    def portal_annotation_id(self) -> int:
        return self.portal_metadata.annotation_id

    @property
    def portal_annotation_file_id(self) -> int:
        return self.portal_metadata.annotation_file_id

    @property
    def portal_annotation_file_path(self) -> str:
        return self.portal_metadata.s3_path


class CopickSegmentationCDP(CopickSegmentationOverlay):
    run: "CopickRunCDP"
    meta: CopickSegmentationMetaCDP

    @property
    def from_tool(self) -> bool:
        return bool(self.read_only or self.session_id == "0")

    @property
    def from_user(self) -> bool:
        return not self.from_tool

    @property
    def filename(self) -> str:
        if self.is_multilabel:
            return f"{self.voxel_size:.3f}_{self.user_id}_{self.session_id}_{self.name}-multilabel.zarr"
        else:
            return f"{self.voxel_size:.3f}_{self.user_id}_{self.session_id}_{self.name}.zarr"

    @property
    def path(self) -> str:
        if self.read_only:
            return self.meta.portal_annotation_file_path
        else:
            return f"{self.run.overlay_path}/Segmentations/{self.filename}"

    @property
    def fs(self) -> AbstractFileSystem:
        return s3fs.S3FileSystem(anon=True) if self.read_only else self.run.fs_overlay

    @property
    def portal_segmentation_id(self) -> int:
        return self.meta.portal_annotation_file_id

    def zarr(self) -> zarr.storage.FSStore:
        if self.read_only:
            mode = "r"
            create = False
        else:
            mode = "w"
            create = not self.fs.exists(self.path)

        return zarr.storage.FSStore(
            self.path,
            fs=self.fs,
            mode=mode,
            key_separator="/",
            dimension_separator="/",
            create=create,
        )

    def _delete_data(self) -> None:
        if self.fs.exists(self.path):
            self.fs.rm(self.path, recursive=True)
        else:
            raise FileNotFoundError(f"File not found: {self.path}")


class CopickFeaturesCDP(CopickFeaturesOverlay):
    tomogram: "CopickTomogramCDP"

    @property
    def path(self) -> str:
        if self.read_only:
            logger.critical("Data portal does not support features (yet).")
            raise NotImplementedError("Data portal does not support features (yet).")
        else:
            return f"{self.tomogram.overlay_stem}_{self.feature_type}_features.zarr"

    @property
    def fs(self) -> AbstractFileSystem:
        return self.tomogram.fs_overlay

    def zarr(self) -> zarr.storage.FSStore:
        if self.read_only:
            logger.critical("Data portal does not support features (yet).")
            raise NotImplementedError("Data portal does not support features (yet).")
        else:
            mode = "w"
            create = not self.fs.exists(self.path)

        return zarr.storage.FSStore(
            self.path,
            fs=self.fs,
            mode=mode,
            key_separator="/",
            dimension_separator="/",
            create=create,
        )

    def _delete_data(self) -> None:
        if self.fs.exists(self.path):
            self.fs.rm(self.path, recursive=True)
        else:
            raise FileNotFoundError(f"File not found: {self.path}")


class CopickTomogramMetaCDP(CopickTomogramMeta):
    portal_tomo_id: Optional[int] = None
    portal_tomo_path: Optional[str] = None
    portal_metadata: Optional[PortalTomogramMeta] = PortalTomogramMeta()

    @classmethod
    def from_portal(cls, source: cdp.Tomogram, author_names: Optional[List[str]] = None):
        reconstruction_method = camel(source.reconstruction_method)
        processing_method = camel(source.processing)
        processing_tool = camel(source.processing_software) if source.processing_software else ""
        ctf_status = "ctfdeconv" if source.ctf_corrected else ""

        # Only include non-empty processing_tool and ctf_status
        name = f"{reconstruction_method}-{processing_method}"
        if processing_tool:
            name += f"-{processing_tool}"
        if ctf_status:
            name += f"-{ctf_status}"

        # Use cached authors if provided, otherwise trigger lazy load
        if author_names is not None:
            portal_meta = PortalTomogramMeta.from_portal_cached(source, author_names)
        else:
            portal_meta = PortalTomogramMeta.from_tomogram(source)

        return cls(
            tomo_type=name,
            portal_tomo_id=source.id,
            portal_tomo_path=source.s3_omezarr_dir,
            portal_metadata=portal_meta,
        )


class CopickTomogramCDP(CopickTomogramOverlay):
    voxel_spacing: "CopickVoxelSpacingCDP"
    meta: CopickTomogramMetaCDP

    def _feature_factory(self) -> Tuple[Type[CopickFeaturesCDP], Type["CopickFeaturesMeta"]]:
        return CopickFeaturesCDP, CopickFeaturesMeta

    @property
    def tomo_type(self) -> str:
        """The type of tomogram. For data portal tomograms, this is derived as
        `cryoet_data_portal.Tomogram.reconstruction_method + "-" + cryoet_data_portal.Tomogram.processing + ["-" +
        cryoet_data_portal.Tomogram.processing_software + "-" + cryoet_data_portal.Tomogram.ctf_corrected`], where
        `cryoet_data_portal.Tomogram.processing_software` and `cryoet_data_portal.Tomogram.ctf_corrected` are discarded
        if null in the database.
        """
        return self.meta.tomo_type

    @property
    def portal_tomo(self) -> bool:
        """Whether this tomogram is from the portal or not."""
        return self.meta.portal_tomo_id is not None

    @property
    def static_path(self) -> str:
        return self.meta.portal_tomo_path if self.portal_tomo else None

    @property
    def overlay_path(self) -> str:
        return f"{self.voxel_spacing.overlay_path}/{self.tomo_type}.zarr"

    @property
    def overlay_stem(self) -> str:
        return f"{self.voxel_spacing.overlay_path}/{self.tomo_type}"

    @property
    def fs_overlay(self) -> AbstractFileSystem:
        return self.voxel_spacing.fs_overlay

    @property
    def fs_static(self) -> AbstractFileSystem:
        return s3fs.S3FileSystem(anon=True)

    def _query_static_features(self) -> List[CopickFeaturesCDP]:
        # Features are not defined by the portal yet
        return []

    def _query_overlay_features(self) -> List[CopickFeaturesCDP]:
        feat_loc = self.overlay_path.replace(".zarr", "_")
        paths = self.fs_overlay.glob(feat_loc + "*_features.zarr") + self.fs_overlay.glob(feat_loc + "*_features.zarr/")
        paths = [p.rstrip("/") for p in paths if self.fs_overlay.isdir(p)]
        feature_types = [n.replace(feat_loc, "").replace("_features.zarr", "") for n in paths]
        # Remove any hidden files?
        feature_types = [ft for ft in feature_types if not ft.startswith(".")]

        feature_types = list(set(feature_types))
        clz, meta_clz = self._feature_factory()

        return [
            clz(
                tomogram=self,
                meta=meta_clz(
                    tomo_type=self.tomo_type,
                    feature_type=ft,
                ),
                read_only=False,
            )
            for ft in feature_types
        ]

    def zarr(self) -> zarr.storage.FSStore:
        if self.read_only:
            fs = s3fs.S3FileSystem(anon=True)
            path = self.meta.portal_tomo_path
            mode = "r"
            create = False
        else:
            fs = self.fs_overlay
            path = self.overlay_path
            mode = "w"
            create = not fs.exists(path)

        return zarr.storage.FSStore(
            path,
            fs=fs,
            mode=mode,
            key_separator="/",
            dimension_separator="/",
            create=create,
        )

    def _delete_data(self) -> None:
        if self.fs_overlay.exists(self.overlay_path):
            self.fs_overlay.rm(self.overlay_path, recursive=True)
        else:
            raise FileNotFoundError(f"File not found: {self.overlay_path}")


class CopickVoxelSpacingMetaCDP(CopickVoxelSpacingMeta):
    portal_vs_id: Optional[int] = None

    @classmethod
    def from_portal(cls, source: cdp.TomogramVoxelSpacing):
        return cls(voxel_size=source.voxel_spacing, portal_vs_id=source.id)  # , portal_vs=source)


class CopickVoxelSpacingCDP(CopickVoxelSpacingOverlay):
    run: "CopickRunCDP"
    meta: CopickVoxelSpacingMetaCDP

    def _tomogram_factory(self) -> Tuple[Type[CopickTomogramCDP], Type[CopickTomogramMetaCDP]]:
        return CopickTomogramCDP, CopickTomogramMetaCDP

    @property
    def overlay_path(self):
        return f"{self.run.overlay_path}/VoxelSpacing{self.voxel_size:.3f}"

    @property
    def fs_overlay(self):
        return self.run.fs_overlay

    @property
    def portal_vs_id(self) -> int:
        return self.meta.portal_vs_id

    def _query_static_tomograms(self) -> List[CopickTomogramCDP]:
        if self.portal_vs_id is None:
            return []

        cache = self.run.root._ensure_annotation_cache()
        portal_tomos = cache.tomograms_by_vs.get(self.portal_vs_id, [])

        if not portal_tomos:
            return []

        clz, meta_clz = self._tomogram_factory()
        tomos = []

        for t in portal_tomos:
            author_names = cache.tomogram_authors.get(t.id, [])
            tomo_meta = meta_clz.from_portal(t, author_names=author_names)
            tomo = clz(voxel_spacing=self, meta=tomo_meta, read_only=True)
            tomos.append(tomo)

        return tomos

    def _query_overlay_tomograms(self) -> List[CopickTomogramCDP]:
        tomo_loc = f"{self.overlay_path}/"
        paths = self.fs_overlay.glob(tomo_loc + "*.zarr") + self.fs_overlay.glob(tomo_loc + "*.zarr/")
        paths = [p.rstrip("/") for p in paths if self.fs_overlay.isdir(p)]
        tomo_types = [n.replace(tomo_loc, "").replace(".zarr", "") for n in paths]
        tomo_types = [t for t in tomo_types if "features" not in t]
        # Remove any hidden files?
        tomo_types = [tt for tt in tomo_types if not tt.startswith(".")]

        tomo_types = list(set(tomo_types))
        clz, meta_clz = self._tomogram_factory()

        return [
            clz(
                voxel_spacing=self,
                meta=meta_clz(tomo_type=tt),
                read_only=False,
            )
            for tt in tomo_types
        ]

    def ensure(self, create: bool = False) -> bool:
        """Checks if the voxel spacing record exists in the static or overlay directory, optionally creating it in the
        overlay filesystem if it does not.

        Args:
            create: Whether to create the voxel spacing record if it does not exist.

        Returns:
            bool: True if the voxel spacing record exists, False otherwise.
        """
        client = cdp.Client()
        vs = cdp.TomogramVoxelSpacing.find(
            client,
            [  # noqa
                cdp.TomogramVoxelSpacing.run.id == self.run.portal_run_id,
                cdp.TomogramVoxelSpacing.voxel_spacing == self.meta.voxel_size,
            ],
        )
        exists = len(vs) > 0 or self.fs_overlay.exists(self.overlay_path)

        if len(vs) > 0:
            self.meta.portal_vs_id = vs[0].id

        if not exists and create:
            self.fs_overlay.makedirs(self.overlay_path, exist_ok=True)
            # TODO: Write metadata
            with self.fs_overlay.open(self.overlay_path + "/.meta", "w") as f:
                f.write("meta")  # Touch the file
            return True
        else:
            return exists

    def get_tomograms(
        self,
        tomo_type: str = None,
        portal_meta_query: Dict[str, Any] = None,
        portal_author_query: List[str] = None,
        **kwargs,
    ) -> List["CopickTomogramCDP"]:
        """Get a tomogram by type. Portal metadata are compared for equality. Authors are compared for inclusion.

        Args:
            tomo_type: The type of tomogram to get. For portal tomograms, this is
                `cryoet_data_portal.Tomogram.reconstruction_method.`
            portal_meta_query: Dictionary of values to compare against portal metadata of this tomogram. Allowed keys
                are the scalar fields of [cryoet_data_portal.Tomogram](https://chanzuckerberg.github.io/cryoet-data-portal/api_reference.html#cryoet_data_portal.Tomogram)
            portal_author_query: List of author names. Tomograms are included if this author is in the portal
                annotation's author list.
            **kwargs: Additional parameters passed to parent class.

        Returns:
            List[CopickTomogram]: The list of tomograms that match the query.
        """
        tomos = super().get_tomograms(tomo_type, **kwargs)

        if portal_meta_query is None:
            portal_meta_query = {}
        if portal_author_query is None:
            portal_author_query = []

        # Compare portal metadata and authors
        return [t for t in tomos if t.meta.portal_metadata.compare(portal_meta_query, portal_author_query)]

    def _delete_data(self) -> None:
        if self.fs_overlay.exists(self.overlay_path):
            self.fs_overlay.rm(self.overlay_path, recursive=True)
        else:
            raise FileNotFoundError(f"File not found: {self.overlay_path}")


class CopickRunMetaCDP(CopickRunMeta):
    portal_run_id: Optional[int] = None
    portal_run_name: Optional[str] = None
    portal_dataset_id: Optional[int] = None

    @classmethod
    def from_portal(cls, source: cdp.Run):
        return cls(
            name=f"{source.id}",
            portal_run_id=source.id,
            portal_run_name=source.name,
            portal_dataset_id=source.dataset_id,
        )


class CopickRunCDP(CopickRunOverlay):
    root: "CopickRootCDP"
    meta: CopickRunMetaCDP

    def _voxel_spacing_factory(self) -> Tuple[Type[CopickVoxelSpacingCDP], Type[CopickVoxelSpacingMetaCDP]]:
        return CopickVoxelSpacingCDP, CopickVoxelSpacingMetaCDP

    def _picks_factory(self) -> Type[CopickPicksCDP]:
        return CopickPicksCDP

    def _mesh_factory(self) -> Tuple[Type[CopickMeshCDP], Type[CopickMeshMeta]]:
        return CopickMeshCDP, CopickMeshMeta

    def _segmentation_factory(self) -> Tuple[Type[CopickSegmentationCDP], Type[CopickSegmentationMetaCDP]]:
        return CopickSegmentationCDP, CopickSegmentationMetaCDP

    @property
    def overlay_path(self) -> str:
        return f"{self.root.root_overlay}/ExperimentRuns/{self.name}"

    @property
    def fs_overlay(self) -> AbstractFileSystem:
        return self.root.fs_overlay

    @property
    def portal_run_id(self) -> int:
        return self.meta.portal_run_id

    @property
    def portal_run_name(self) -> str:
        return self.meta.name

    @property
    def portal_dataset_id(self) -> int:
        return self.meta.portal_dataset_id

    def _query_static_voxel_spacings(self) -> List[CopickVoxelSpacingCDP]:
        # VoxelSpacings only added on overlay
        if self.portal_run_id is None:
            return []

        client = cdp.Client()
        portal_vs = cdp.TomogramVoxelSpacing.find(
            client,
            [cdp.TomogramVoxelSpacing.run_id == self.portal_run_id],  # noqa
        )

        # portal_vs = self.portal_run.tomogram_voxel_spacings
        clz, meta_clz = self._voxel_spacing_factory()

        return [clz(meta=meta_clz.from_portal(vs), run=self) for vs in portal_vs]

    def _query_overlay_voxel_spacings(self) -> List[CopickVoxelSpacingCDP]:
        overlay_vs_loc = f"{self.overlay_path}/VoxelSpacing"
        opaths = set(self.fs_overlay.glob(overlay_vs_loc + "*") + self.fs_overlay.glob(overlay_vs_loc + "*/"))
        opaths = [p.rstrip("/") for p in opaths]
        spacings = [float(p.replace(f"{overlay_vs_loc}", "")) for p in opaths]

        clz, meta_clz = self._voxel_spacing_factory()

        return [
            clz(
                meta=meta_clz(voxel_size=s),
                run=self,
            )
            for s in spacings
        ]

    def _query_static_picks(self) -> List[CopickPicksCDP]:
        # Run only added on overlay
        if self.portal_run_id is None:
            return []

        # Get cached data from root (fetches once for all runs)
        cache = self.root._ensure_annotation_cache()
        go_map = self.root.go_map

        # Filter annotation files for this run from cache
        point_anno_files = cache.picks_files_by_run.get(self.portal_run_id, [])
        if not point_anno_files:
            return []

        # Create picks using cached lookups
        portal_meta = [
            PortalAnnotationMeta(
                portal_annotation_file=af,
                portal_annotation_shape=cache.annotation_shapes[af.annotation_shape_id],
                portal_annotation=cache.annotations[cache.annotation_shapes[af.annotation_shape_id].annotation_id],
                voxel_spacing=cache.voxel_spacings[af.tomogram_voxel_spacing_id].voxel_spacing,
                portal_author_names=cache.author_names.get(
                    cache.annotation_shapes[af.annotation_shape_id].annotation_id,
                    [],
                ),
            )
            for af in point_anno_files
        ]

        return [
            CopickPicksCDP(
                run=self,
                file=CopickPicksFileCDP.from_portal_container(pm, name=go_map[pm.object_id]),
                read_only=True,
            )
            for pm in portal_meta
        ]

    def _query_overlay_picks(self) -> List[CopickPicksCDP]:
        pick_loc = f"{self.overlay_path}/Picks/"
        paths = self.fs_overlay.glob(pick_loc + "*.json")
        names = [n.replace(pick_loc, "").replace(".json", "") for n in paths]
        # Remove any hidden files?
        names = [n for n in names if not n.startswith(".")]

        users = [n.split("_")[0] for n in names]
        sessions = [n.split("_")[1] for n in names]
        objects = [n.split("_")[2] for n in names]

        assert len(users) == len(sessions) == len(objects)

        return [
            CopickPicksCDP(
                run=self,
                file=CopickPicksFileCDP(
                    pickable_object_name=o,
                    user_id=u,
                    session_id=s,
                ),
                read_only=False,
            )
            for u, s, o in zip(users, sessions, objects, strict=True)
        ]

    def get_picks(
        self,
        object_name: str = None,
        user_id: str = None,
        session_id: str = None,
        portal_meta_query: Dict[str, Any] = None,
        portal_author_query: List[str] = None,
        **kwargs,
    ) -> List["CopickPicksCDP"]:
        """Get picks by name, user_id or session_id (or combinations). Portal metadata are compared for equality. Portal
        authors are checked for inclusion in the full author list.

        Args:
            object_name: Name of the object to search for.
            user_id: User ID to search for.
            session_id: Session ID to search for.
            portal_meta_query: Dictionary of values to compare against portal metadata of this annotation. Allowed keys
                are the scalar fields of [cryoet_data_portal.Annotation](https://chanzuckerberg.github.io/cryoet-data-portal/api_reference.html#cryoet_data_portal.Annotation)
            portal_author_query: List of author names. Segmentations are included if this author is in the portal
                annotation's author list.
            **kwargs: Additional parameters passed to parent class.

        Returns:
            List[CopickPicks]: List of picks that match the search criteria.
        """
        picks = super().get_picks(object_name, user_id, session_id, **kwargs)

        # Just return the regular output if no additional conditions
        if portal_meta_query is None and portal_author_query is None:
            return picks

        if portal_meta_query is None:
            portal_meta_query = {}

        if portal_author_query is None:
            portal_author_query = []

        # Compare the metadata
        picks = [p for p in picks if p.meta.portal_metadata.compare(portal_meta_query, portal_author_query)]

        return picks

    def _query_static_meshes(self) -> List[CopickMeshCDP]:
        # Not defined by the portal yet
        return []

    def _query_overlay_meshes(self) -> List[CopickMeshCDP]:
        mesh_loc = f"{self.overlay_path}/Meshes/"
        paths = self.fs_overlay.glob(mesh_loc + "*.glb")
        names = [n.replace(mesh_loc, "").replace(".glb", "") for n in paths]
        # Remove any hidden files?
        names = [n for n in names if not n.startswith(".")]

        users = [n.split("_")[0] for n in names]
        sessions = [n.split("_")[1] for n in names]
        objects = [n.split("_")[2] for n in names]

        clz, meta_clz = self._mesh_factory()

        return [
            clz(
                run=self,
                meta=meta_clz(
                    pickable_object_name=o,
                    user_id=u,
                    session_id=s,
                ),
                read_only=False,
            )
            for u, s, o in zip(users, sessions, objects, strict=True)
        ]

    def _query_static_segmentations(self) -> List[CopickSegmentationCDP]:
        # Run only added on overlay
        if self.portal_run_id is None:
            return []

        # Get cached data from root (fetches once for all runs)
        cache = self.root._ensure_annotation_cache()
        go_map = self.root.go_map

        # Filter annotation files for this run from cache
        seg_anno_files = cache.seg_files_by_run.get(self.portal_run_id, [])
        if not seg_anno_files:
            return []

        segmentations = []
        clz, meta_clz = self._segmentation_factory()

        for af in seg_anno_files:
            shape = cache.annotation_shapes[af.annotation_shape_id]
            annotation = cache.annotations[shape.annotation_id]
            vs = cache.voxel_spacings.get(af.tomogram_voxel_spacing_id)
            author_names = cache.author_names.get(annotation.id, [])

            object_name = go_map.get(annotation.object_id, f"{camel(annotation.object_name)}-{af.id}")

            # Build metadata directly using cached objects (avoid lazy loading in from_portal)
            portal_meta = PortalAnnotationMeta(
                portal_annotation_file=af,
                portal_annotation_shape=shape,
                portal_annotation=annotation,
                voxel_spacing=vs.voxel_spacing if vs else None,
                portal_author_names=author_names,
            )

            seg_meta = meta_clz(
                is_multilabel=False,
                voxel_size=vs.voxel_spacing if vs else 0.0,
                user_id="data-portal",
                session_id=str(af.id),
                name=object_name,
                portal_metadata=portal_meta,
            )
            seg = clz(run=self, meta=seg_meta, read_only=True)
            segmentations.append(seg)

        return segmentations

    def _query_overlay_segmentations(self) -> List[CopickSegmentationCDP]:
        seg_loc = f"{self.overlay_path}/Segmentations/"
        paths = self.fs_overlay.glob(seg_loc + "*.zarr") + self.fs_overlay.glob(seg_loc + "*.zarr/")
        paths = [p.rstrip("/") for p in paths if self.fs_overlay.isdir(p)]
        names = [n.replace(seg_loc, "").replace(".zarr", "") for n in paths]
        # Remove any hidden files?
        names = [n for n in names if not n.startswith(".")]

        # Deduplicate
        names = list(set(names))

        # multilabel vs single label
        metas = []
        clz, meta_clz = self._segmentation_factory()
        for n in names:
            if "multilabel" in n:
                parts = n.split("_")
                metas.append(
                    meta_clz(
                        is_multilabel=True,
                        voxel_size=float(parts[0]),
                        user_id=parts[1],
                        session_id=parts[2],
                        name=parts[3].replace("-multilabel", ""),
                    ),
                )
            else:
                parts = n.split("_")
                metas.append(
                    meta_clz(
                        is_multilabel=False,
                        voxel_size=float(parts[0]),
                        user_id=parts[1],
                        session_id=parts[2],
                        name=parts[3],
                    ),
                )

        return [
            clz(
                run=self,
                meta=m,
                read_only=False,
            )
            for m in metas
        ]

    def get_segmentations(
        self,
        user_id: str = None,
        session_id: str = None,
        is_multilabel: bool = None,
        name: str = None,
        voxel_size: float = None,
        portal_meta_query: Dict[str, Any] = None,
        portal_author_query: List[str] = None,
        **kwargs,
    ) -> List["CopickSegmentationCDP"]:
        """Get segmentations by user_id, session_id, name, type or voxel_size (or combinations) and portal metadata and
        authors. Portal metadata are compared for equality. Portal authors are checked for inclusion in the full author
        list.

        Args:
            user_id: User ID to search for.
            session_id: Session ID to search for.
            is_multilabel: Whether the segmentation is multilabel or not.
            name: Name of the segmentation to search for.
            voxel_size: Voxel size to search for.
            portal_meta_query: Dictionary of values to compare against portal metadata of this annotation. Allowed keys
                are the scalar fields of [cryoet_data_portal.Annotation](https://chanzuckerberg.github.io/cryoet-data-portal/python-api.html#annotation)
            portal_author_query: List of author names. Segmentations are included if this author is in the portal
                annotation's author list.
            **kwargs: Additional parameters passed to parent class.

        Returns:
            List[CopickSegmentation]: List of segmentations that match the search criteria.
        """
        segmentations = super().get_segmentations(user_id, session_id, is_multilabel, name, voxel_size, **kwargs)

        # Just return the regular output if no additional conditions
        if portal_meta_query is None and portal_author_query is None:
            return segmentations

        if portal_meta_query is None:
            portal_meta_query = {}

        if portal_author_query is None:
            portal_author_query = []

        # Compare the metadata
        segmentations = [
            s
            for s in segmentations
            if s.meta.portal_metadata.compare(
                portal_meta_query,
                portal_author_query,
            )
        ]

        return segmentations

    def ensure(self, create: bool = False) -> bool:
        """Checks if the run record exists in the static or overlay directory, optionally creating it in the overlay
        filesystem if it does not.

        Args:
            create: Whether to create the run record if it does not exist.

        Returns:
            bool: True if the run record exists, False otherwise.
        """
        client = cdp.Client()
        try:
            id_from_name = int(self.name)
            run = cdp.Run.get_by_id(client, id_from_name)
        except ValueError:
            run = None

        exists = run is not None or self.fs_overlay.exists(self.overlay_path)

        if run:
            self.meta.portal_run_id = run.id

        if not exists and create:
            self.fs_overlay.makedirs(self.overlay_path, exist_ok=True)
            # TODO: Write metadata
            with self.fs_overlay.open(self.overlay_path + "/.meta", "w") as f:
                f.write("meta")  # Touch the file
            return True
        else:
            return exists

    def _delete_data(self) -> None:
        if self.fs_overlay.exists(self.overlay_path):
            self.fs_overlay.rm(self.overlay_path, recursive=True)
        else:
            raise FileNotFoundError(f"File not found: {self.overlay_path}")


class CopickObjectCDP(CopickObjectOverlay):
    root: "CopickRootCDP"

    @property
    def path(self) -> str:
        return f"{self.root.root_overlay}/Objects/{self.name}.zarr"

    @property
    def fs(self) -> AbstractFileSystem:
        return self.root.fs_overlay

    def zarr(self) -> Union[None, zarr.storage.FSStore]:
        if not self.is_particle:
            return None

        # Return none if there is no density map
        if not self.fs.exists(self.path):
            return None

        if self.read_only:
            mode = "r"
            create = False
        else:
            mode = "w"
            create = not self.fs.exists(self.path)

        return zarr.storage.FSStore(
            self.path,
            fs=self.fs,
            mode=mode,
            key_separator="/",
            dimension_separator="/",
            create=create,
        )

    def _delete_data(self) -> None:
        if self.fs.exists(self.path):
            self.fs.rm(self.path, recursive=True)
        else:
            raise FileNotFoundError(f"File not found: {self.path}")


class CopickRootCDP(CopickRoot):
    config: CopickConfigCDP

    def __init__(self, config: CopickConfigCDP):
        super().__init__(config)

        self.fs_overlay: AbstractFileSystem = fsspec.core.url_to_fs(config.overlay_root, **config.overlay_fs_args)[0]
        self.root_overlay: str = self.fs_overlay._strip_protocol(config.overlay_root)  # noqa
        self._portal_cache: Optional[PortalCache] = None

        # Eagerly build annotation cache for all datasets
        self._ensure_annotation_cache()

    @property
    def go_map(self) -> Dict[str, str]:
        return {po.identifier: po.name for po in self.pickable_objects if po.identifier is not None}

    def _ensure_annotation_cache(self) -> PortalCache:
        """Lazily fetch and cache all portal annotation data for picks, segmentations, and tomograms."""
        if self._portal_cache is not None:
            return self._portal_cache

        client = cdp.Client()
        go_map = self.go_map

        # 1. Fetch ALL annotation files for all datasets (picks + segmentations)
        all_anno_files = cdp.AnnotationFile.find(
            client,
            [
                cdp.AnnotationFile.annotation_shape.annotation.run.dataset_id._in(self.dataset_ids),  # noqa
                cdp.AnnotationFile.annotation_shape.shape_type._in(
                    ["Point", "OrientedPoint", "SegmentationMask"],
                ),  # noqa
                cdp.AnnotationFile.annotation_shape.annotation.object_id._in(list(go_map.keys())),  # noqa
            ],
        )

        # 2. Fetch ALL annotation shapes
        all_shapes = cdp.AnnotationShape.find(
            client,
            [
                cdp.AnnotationShape.annotation_files.id._in([af.id for af in all_anno_files]),  # noqa
            ],
        )

        # 3. Fetch ALL annotations
        all_annotations = cdp.Annotation.find(
            client,
            [
                cdp.Annotation.id._in([s.annotation_id for s in all_shapes]),  # noqa
            ],
        )

        # 4. Fetch ALL annotation authors
        all_authors = cdp.AnnotationAuthor.find(
            client,
            [
                cdp.AnnotationAuthor.annotation_id._in([a.id for a in all_annotations]),  # noqa
            ],
        )

        # 5. Fetch ALL voxel spacings
        all_voxel_spacings = cdp.TomogramVoxelSpacing.find(
            client,
            [
                cdp.TomogramVoxelSpacing.run.dataset_id._in(self.dataset_ids),  # noqa
            ],
        )

        # 6. Fetch ALL tomograms for all datasets
        all_tomograms = cdp.Tomogram.find(
            client,
            [
                cdp.Tomogram.tomogram_voxel_spacing.run.dataset_id._in(self.dataset_ids),  # noqa
            ],
        )

        # 7. Fetch ALL tomogram authors
        all_tomogram_authors = cdp.TomogramAuthor.find(
            client,
            [
                cdp.TomogramAuthor.tomogram_id._in([t.id for t in all_tomograms]),  # noqa
            ],
        )

        # Build cache
        cache = PortalCache()

        # Index by id
        cache.annotation_shapes = {s.id: s for s in all_shapes}
        cache.annotations = {a.id: a for a in all_annotations}
        cache.voxel_spacings = {vs.id: vs for vs in all_voxel_spacings}

        # Group annotation files by run_id and shape_type
        for af in all_anno_files:
            shape = cache.annotation_shapes[af.annotation_shape_id]
            annotation = cache.annotations[shape.annotation_id]
            run_id = annotation.run_id

            if shape.shape_type in ["Point", "OrientedPoint"]:
                if run_id not in cache.picks_files_by_run:
                    cache.picks_files_by_run[run_id] = []
                cache.picks_files_by_run[run_id].append(af)
            elif shape.shape_type == "SegmentationMask" and af.format == "zarr":
                if run_id not in cache.seg_files_by_run:
                    cache.seg_files_by_run[run_id] = []
                cache.seg_files_by_run[run_id].append(af)

        # Build annotation author names lookup
        for author in all_authors:
            if author.annotation_id not in cache.author_names:
                cache.author_names[author.annotation_id] = []
            cache.author_names[author.annotation_id].append(author.name)

        # Group tomograms by voxel spacing
        for tomo in all_tomograms:
            vs_id = tomo.tomogram_voxel_spacing_id
            if vs_id not in cache.tomograms_by_vs:
                cache.tomograms_by_vs[vs_id] = []
            cache.tomograms_by_vs[vs_id].append(tomo)

        # Build tomogram author lookup
        for author in all_tomogram_authors:
            if author.tomogram_id not in cache.tomogram_authors:
                cache.tomogram_authors[author.tomogram_id] = []
            cache.tomogram_authors[author.tomogram_id].append(author.name)

        self._portal_cache = cache
        return cache

    @property
    def datasets(self) -> List[cdp.Dataset]:
        warnings.warn(
            "CopickRootCDP.datasets will be deprecated in the next major release. Use "
            "CopickRootCDP.dataset_ids instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        client = cdp.Client()
        datasets = cdp.Dataset.find(client, [cdp.Dataset.id._in(self.dataset_ids)])
        return datasets

    @property
    def dataset_ids(self) -> List[int]:
        return self.config.dataset_ids

    @classmethod
    def from_file(cls, path: str) -> "CopickRootCDP":
        with open(path, "r") as f:
            data = json.load(f)

        return cls(CopickConfigCDP(**data))

    def _run_factory(self) -> Tuple[Type[CopickRunCDP], Type[CopickRunMetaCDP]]:
        return CopickRunCDP, CopickRunMetaCDP

    def _object_factory(self) -> Tuple[Type[CopickObjectCDP], Type[PickableObject]]:
        return CopickObjectCDP, PickableObject

    def query(self) -> List[CopickRunCDP]:
        client = cdp.Client()
        portal_runs = cdp.Run.find(client, [cdp.Run.dataset_id._in(self.dataset_ids)])  # noqa

        runs = []
        for pr in portal_runs:
            rm = CopickRunMetaCDP.from_portal(pr)
            runs.append(CopickRunCDP(root=self, meta=rm))

        return runs

    def _query_objects(self):
        """Override to create objects from config. For CryoET Data Portal, objects are always writable since they only exist in overlay."""
        clz, meta_clz = self._object_factory()
        objects = []

        for obj_meta in self.config.pickable_objects:
            # For CryoET Data Portal, objects are always writable (read_only=False)
            # since they only exist in the overlay filesystem
            obj = clz(self, obj_meta, read_only=False)
            objects.append(obj)

        self._objects = objects
