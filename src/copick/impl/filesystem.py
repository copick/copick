import json
from typing import Any, Dict, List, Optional, Tuple, Type

import fsspec
import trimesh
import zarr
from fsspec import AbstractFileSystem
from trimesh.parent import Geometry

from copick.impl.overlay import (
    CopickFeaturesOverlay,
    CopickMeshOverlay,
    CopickPicksOverlay,
    CopickRunOverlay,
    CopickSegmentationOverlay,
    CopickTomogramOverlay,
    CopickVoxelSpacingOverlay,
)
from copick.models import (
    CopickConfig,
    CopickFeaturesMeta,
    CopickMeshMeta,
    CopickPicksFile,
    CopickRoot,
    CopickRunMeta,
    CopickSegmentationMeta,
    CopickTomogramMeta,
    CopickVoxelSpacingMeta,
    TCopickFeatures,
    TCopickRun,
    TCopickVoxelSpacing,
)


class CopickConfigFSSpec(CopickConfig):
    overlay_root: str
    static_root: Optional[str]

    overlay_fs_args: Optional[Dict[str, Any]] = {}
    static_fs_args: Optional[Dict[str, Any]] = {}


class CopickPicksFSSpec(CopickPicksOverlay):
    @property
    def path(self) -> str:
        if self.read_only:
            return f"{self.run.static_path}/Picks/{self.user_id}_{self.session_id}_{self.pickable_object_name}.json"
        else:
            return f"{self.run.overlay_path}/Picks/{self.user_id}_{self.session_id}_{self.pickable_object_name}.json"

    @property
    def directory(self) -> str:
        if self.read_only:
            return f"{self.run.static_path}/Picks/"
        else:
            return f"{self.run.overlay_path}/Picks/"

    @property
    def fs(self) -> AbstractFileSystem:
        return self.run.fs_static if self.read_only else self.run.fs_overlay

    def _load(self) -> CopickPicksFile:
        if not self.fs.exists(self.path):
            raise FileNotFoundError(f"File not found: {self.path}")

        with self.fs.open(self.path, "r") as f:
            data = json.load(f)

        return CopickPicksFile(**data)

    def _store(self) -> None:
        if not self.fs.exists(self.directory):
            self.fs.makedirs(self.directory, exist_ok=True)

        with self.fs.open(self.path, "w") as f:
            json.dump(self.meta.dict(), f)


class CopickMeshFSSpec(CopickMeshOverlay):
    @property
    def path(self) -> str:
        if self.read_only:
            return f"{self.run.static_path}/Meshes/{self.user_id}_{self.session_id}_{self.pickable_object_name}.glb"
        else:
            return f"{self.run.overlay_path}/Meshes/{self.user_id}_{self.session_id}_{self.pickable_object_name}.glb"

    @property
    def directory(self) -> str:
        if self.read_only:
            return f"{self.run.static_path}/Meshes/"
        else:
            return f"{self.run.overlay_path}/Meshes/"

    @property
    def fs(self) -> AbstractFileSystem:
        return self.run.fs_static if self.read_only else self.run.fs_overlay

    def _load(self) -> Geometry:
        if not self.fs.exists(self.path):
            raise FileNotFoundError(f"File not found: {self.path}")

        with self.fs.open(self.path, "rb") as f:
            scene = trimesh.load(f, file_type="glb")

        return scene

    def _store(self):
        if not self.fs.exists(self.directory):
            self.fs.makedirs(self.directory, exist_ok=True)

        with self.fs.open(self.path, "wb") as f:
            _ = self._mesh.export(f, file_type="glb")


class CopickSegmentationFSSpec(CopickSegmentationOverlay):
    @property
    def path(self) -> str:
        if self.read_only:
            return f"{self.run.static_path}/Segmentations/{self.user_id}_{self.session_id}.zarr"
        else:
            return f"{self.run.overlay_path}/Segmentations/{self.user_id}_{self.session_id}.zarr"

    @property
    def fs(self) -> AbstractFileSystem:
        return self.run.fs_static if self.read_only else self.run.fs_overlay

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


class CopickFeaturesFSSpec(CopickFeaturesOverlay):
    @property
    def path(self) -> str:
        if self.read_only:
            return f"{self.tomogram.static_stem}_{self.feature_type}_features.zarr"
        else:
            return f"{self.tomogram.overlay_stem}_{self.feature_type}_features.zarr"

    @property
    def fs(self) -> AbstractFileSystem:
        return self.tomogram.fs_static if self.read_only else self.tomogram.fs_overlay

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


class CopickTomogramFSSpec(CopickTomogramOverlay):
    def _feature_factory(self) -> Tuple[Type[TCopickFeatures], Type["CopickFeaturesMeta"]]:
        return CopickFeaturesFSSpec, CopickFeaturesMeta

    @property
    def static_path(self) -> str:
        return f"{self.voxel_spacing.static_path}/{self.tomo_type}.zarr"

    @property
    def overlay_path(self) -> str:
        return f"{self.voxel_spacing.overlay_path}/{self.tomo_type}.zarr"

    @property
    def static_stem(self) -> str:
        return f"{self.voxel_spacing.static_path}/{self.tomo_type}"

    @property
    def overlay_stem(self) -> str:
        return f"{self.voxel_spacing.overlay_path}/{self.tomo_type}"

    @property
    def fs_static(self) -> AbstractFileSystem:
        return self.voxel_spacing.fs_static

    @property
    def fs_overlay(self) -> AbstractFileSystem:
        return self.voxel_spacing.fs_overlay

    @property
    def static_is_overlay(self) -> bool:
        return self.fs_static == self.fs_overlay and self.static_path == self.overlay_path

    def _query_static_features(self) -> List[CopickFeaturesFSSpec]:
        if self.static_is_overlay:
            return []

        feat_loc = self.static_path.replace(".zarr", "_")
        paths = self.fs_static.glob(feat_loc + "*_features.zarr") + self.fs_static.glob(feat_loc + "*_features.zarr/")
        paths = [p.rstrip("/") for p in paths if self.fs_static.isdir(p)]
        feature_types = [n.replace(feat_loc, "").replace("_features.zarr", "") for n in paths]

        return [
            CopickFeaturesFSSpec(
                tomogram=self,
                meta=CopickFeaturesMeta(
                    tomo_type=self.tomo_type,
                    feature_type=ft,
                ),
                read_only=True,
            )
            for ft in feature_types
        ]

    def _query_overlay_features(self) -> List[CopickFeaturesFSSpec]:
        feat_loc = self.overlay_path.replace(".zarr", "_")
        paths = self.fs_overlay.glob(feat_loc + "*_features.zarr") + self.fs_overlay.glob(feat_loc + "*_features.zarr/")
        paths = [p.rstrip("/") for p in paths if self.fs_overlay.isdir(p)]
        feature_types = [n.replace(feat_loc, "").replace("_features.zarr", "") for n in paths]

        return [
            CopickFeaturesFSSpec(
                tomogram=self,
                meta=CopickFeaturesMeta(
                    tomo_type=self.tomo_type,
                    feature_type=ft,
                ),
                read_only=False,
            )
            for ft in feature_types
        ]

    def zarr(self) -> zarr.storage.FSStore:
        if self.read_only:
            fs = self.fs_static
            path = self.static_path
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


class CopickVoxelSpacingFSSpec(CopickVoxelSpacingOverlay):
    def _tomogram_factory(self) -> Tuple[Type[CopickTomogramFSSpec], Type[CopickTomogramMeta]]:
        return CopickTomogramFSSpec, CopickTomogramMeta

    @property
    def static_path(self):
        return f"{self.run.static_path}/VoxelSpacing{self.voxel_size:.3f}"

    @property
    def overlay_path(self):
        return f"{self.run.overlay_path}/VoxelSpacing{self.voxel_size:.3f}"

    @property
    def fs_static(self):
        return self.run.fs_static

    @property
    def fs_overlay(self):
        return self.run.fs_overlay

    @property
    def static_is_overlay(self):
        return self.fs_static == self.fs_overlay and self.static_path == self.overlay_path

    def _query_static_tomograms(self) -> List[CopickTomogramFSSpec]:
        if self.static_is_overlay:
            return []

        tomo_loc = f"{self.static_path}/"
        paths = self.fs_static.glob(tomo_loc + "*.zarr") + self.fs_static.glob(tomo_loc + "*.zarr/")
        paths = [p.rstrip("/") for p in paths if self.fs_static.isdir(p)]
        tomo_types = [n.replace(tomo_loc, "").replace(".zarr", "") for n in paths]
        tomo_types = [t for t in tomo_types if "features" not in t]

        return [
            CopickTomogramFSSpec(
                voxel_spacing=self,
                meta=CopickTomogramMeta(tomo_type=tt),
                read_only=True,
            )
            for tt in tomo_types
        ]

    def _query_overlay_tomograms(self) -> List[CopickTomogramFSSpec]:
        tomo_loc = f"{self.overlay_path}/"
        paths = self.fs_overlay.glob(tomo_loc + "*.zarr") + self.fs_overlay.glob(tomo_loc + "*.zarr/")
        paths = [p.rstrip("/") for p in paths if self.fs_overlay.isdir(p)]
        tomo_types = [n.replace(tomo_loc, "").replace(".zarr", "") for n in paths]
        tomo_types = [t for t in tomo_types if "features" not in t]

        return [
            CopickTomogramFSSpec(
                voxel_spacing=self,
                meta=CopickTomogramMeta(tomo_type=tt),
                read_only=False,
            )
            for tt in tomo_types
        ]

    def ensure(self) -> None:
        if not self.fs_overlay.exists(self.overlay_path):
            self.fs_overlay.makedirs(self.overlay_path, exist_ok=True)


class CopickRunFSSpec(CopickRunOverlay):
    def _voxel_spacing_factory(self) -> Tuple[Type[TCopickVoxelSpacing], Type["CopickVoxelSpacingMeta"]]:
        return CopickVoxelSpacingFSSpec, CopickVoxelSpacingMeta

    def _picks_factory(self) -> Type[CopickPicksFSSpec]:
        return CopickPicksFSSpec

    def _mesh_factory(self) -> Tuple[Type[CopickMeshFSSpec], Type[CopickMeshMeta]]:
        return CopickMeshFSSpec, CopickMeshMeta

    def _segmentation_factory(self) -> Tuple[Type[CopickSegmentationFSSpec], Type[CopickSegmentationMeta]]:
        return CopickSegmentationFSSpec, CopickSegmentationMeta

    @property
    def static_path(self):
        return f"{self.root.root_static}/ExperimentRuns/{self.name}"

    @property
    def overlay_path(self):
        return f"{self.root.root_overlay}/ExperimentRuns/{self.name}"

    @property
    def fs_static(self):
        return self.root.fs_static

    @property
    def fs_overlay(self):
        return self.root.fs_overlay

    @property
    def static_is_overlay(self):
        return self.fs_static == self.fs_overlay and self.static_path == self.overlay_path

    def query_voxelspacings(self) -> List[CopickVoxelSpacingFSSpec]:
        static_vs_loc = f"{self.static_path}/VoxelSpacing"
        spaths = self.fs_static.glob(static_vs_loc + "*") + self.fs_static.glob(static_vs_loc + "*/")
        spaths = [p.rstrip("/") for p in spaths]
        sspacings = [float(p.replace(f"{static_vs_loc}", "")) for p in spaths]

        overlay_vs_loc = f"{self.overlay_path}/VoxelSpacing"
        opaths = self.fs_overlay.glob(overlay_vs_loc + "*") + self.fs_overlay.glob(overlay_vs_loc + "*/")
        opaths = [p.rstrip("/") for p in opaths]
        ospacings = [float(p.replace(f"{overlay_vs_loc}", "")) for p in opaths]

        paths = spaths + opaths
        spacings = sspacings + ospacings

        return [
            CopickVoxelSpacingFSSpec(
                meta=CopickVoxelSpacingMeta(voxel_size=s),
                run=self,
            )
            for p, s in zip(paths, spacings, strict=True)
        ]

    def _query_static_picks(self) -> List[CopickPicksFSSpec]:
        if self.static_is_overlay:
            return []

        pick_loc = f"{self.static_path}/Picks/"
        paths = self.fs_static.glob(pick_loc + "*.json")
        names = [n.replace(pick_loc, "").replace(".json", "") for n in paths]

        users = [n.split("_")[0] for n in names]
        sessions = [n.split("_")[1] for n in names]
        objects = [n.split("_")[2] for n in names]

        return [
            CopickPicksFSSpec(
                run=self,
                file=CopickPicksFile(
                    pickable_object_name=o,
                    user_id=u,
                    session_id=s,
                ),
                read_only=True,
            )
            for u, s, o in zip(users, sessions, objects, strict=True)
        ]

    def _query_overlay_picks(self) -> List[CopickPicksFSSpec]:
        pick_loc = f"{self.overlay_path}/Picks/"
        paths = self.fs_overlay.glob(pick_loc + "*.json")
        names = [n.replace(pick_loc, "").replace(".json", "") for n in paths]

        users = [n.split("_")[0] for n in names]
        sessions = [n.split("_")[1] for n in names]
        objects = [n.split("_")[2] for n in names]

        return [
            CopickPicksFSSpec(
                run=self,
                file=CopickPicksFile(
                    pickable_object_name=o,
                    user_id=u,
                    session_id=s,
                ),
                read_only=False,
            )
            for u, s, o in zip(users, sessions, objects, strict=True)
        ]

    def _query_static_meshes(self) -> List[CopickMeshFSSpec]:
        if self.static_is_overlay:
            return []

        mesh_loc = f"{self.static_path}/Meshes/"
        paths = self.fs_static.glob(mesh_loc + "*.glb")
        names = [n.replace(mesh_loc, "").replace(".glb", "") for n in paths]

        users = [n.split("_")[0] for n in names]
        sessions = [n.split("_")[1] for n in names]
        objects = [n.split("_")[2] for n in names]

        return [
            CopickMeshFSSpec(
                run=self,
                meta=CopickMeshMeta(
                    pickable_object_name=o,
                    user_id=u,
                    session_id=s,
                ),
                read_only=True,
            )
            for u, s, o in zip(users, sessions, objects, strict=True)
        ]

    def _query_overlay_meshes(self) -> List[CopickMeshFSSpec]:
        mesh_loc = f"{self.overlay_path}/Meshes/"
        paths = self.fs_overlay.glob(mesh_loc + "*.glb")
        names = [n.replace(mesh_loc, "").replace(".glb", "") for n in paths]

        users = [n.split("_")[0] for n in names]
        sessions = [n.split("_")[1] for n in names]
        objects = [n.split("_")[2] for n in names]

        return [
            CopickMeshFSSpec(
                run=self,
                meta=CopickMeshMeta(
                    pickable_object_name=o,
                    user_id=u,
                    session_id=s,
                ),
                read_only=False,
            )
            for u, s, o in zip(users, sessions, objects, strict=True)
        ]

    def _query_static_segmentations(self) -> List[CopickSegmentationFSSpec]:
        if self.static_is_overlay:
            return []

        seg_loc = f"{self.static_path}/Segmentations/"
        paths = self.fs_static.glob(seg_loc + "*.zarr") + self.fs_static.glob(seg_loc + "*.zarr/")
        paths = [p.rstrip("/") for p in paths if self.fs_static.isdir(p)]
        names = [n.replace(seg_loc, "").replace(".zarr", "") for n in paths]

        users = [n.split("_")[0] for n in names]
        sessions = [n.split("_")[1] for n in names]

        return [
            CopickSegmentationFSSpec(
                run=self,
                meta=CopickSegmentationMeta(
                    user_id=u,
                    session_id=s,
                ),
                read_only=True,
            )
            for u, s in zip(users, sessions, strict=True)
        ]

    def _query_overlay_segmentations(self) -> List[CopickSegmentationFSSpec]:
        seg_loc = f"{self.overlay_path}/Segmentations/"
        paths = self.fs_overlay.glob(seg_loc + "*.zarr") + self.fs_overlay.glob(seg_loc + "*.zarr/")
        paths = [p.rstrip("/") for p in paths if self.fs_overlay.isdir(p)]
        names = [n.replace(seg_loc, "").replace(".zarr", "") for n in paths]

        users = [n.split("_")[0] for n in names]
        sessions = [n.split("_")[1] for n in names]

        return [
            CopickSegmentationFSSpec(
                run=self,
                meta=CopickSegmentationMeta(
                    user_id=u,
                    session_id=s,
                ),
                read_only=False,
            )
            for u, s in zip(users, sessions, strict=True)
        ]

    def ensure(self) -> None:
        if not self.fs_overlay.exists(self.overlay_path):
            self.fs_overlay.makedirs(self.overlay_path, exist_ok=True)


class CopickRootFSSpec(CopickRoot):
    def __init__(self, config: CopickConfigFSSpec):
        super().__init__(config)

        self.fs_overlay: AbstractFileSystem = fsspec.core.url_to_fs(config.overlay_root, **config.overlay_fs_args)[0]
        self.fs_static: Optional[AbstractFileSystem] = None

        self.root_overlay: str = self.fs_overlay._strip_protocol(config.overlay_root)
        self.root_static: Optional[str] = None

        if config.static_root is None:
            self.fs_static = self.fs_overlay
            self.root_static = self.fs_static._strip_protocol(config.overlay_root)
        else:
            self.fs_static = fsspec.core.url_to_fs(config.static_root, **config.static_fs_args)[0]
            self.root_static = self.fs_static._strip_protocol(config.static_root)

    @classmethod
    def from_file(cls, path: str) -> "CopickRootFSSpec":
        with open(path, "r") as f:
            data = json.load(f)

        return cls(CopickConfigFSSpec(**data))

    def _run_factory(self) -> Tuple[Type[TCopickRun], Type["CopickRunMeta"]]:
        return CopickRunFSSpec, CopickRunMeta

    def query(self) -> List[CopickRunFSSpec]:
        static_run_dir = f"{self.root_static}/ExperimentRuns/"
        paths = self.fs_static.glob(static_run_dir + "*") + self.fs_static.glob(static_run_dir + "*/")
        paths = [p.rstrip("/") for p in paths if self.fs_static.isdir(p)]
        names = [n.replace(static_run_dir, "") for n in paths]

        runs = []
        for n in names:
            rm = CopickRunMeta(name=n)
            runs.append(CopickRunFSSpec(root=self, meta=rm))

        return runs
