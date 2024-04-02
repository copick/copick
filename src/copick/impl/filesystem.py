import json
from collections import namedtuple
from typing import Any, Dict, List, Optional, Union

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
)


class CopickConfigFSSpec(CopickConfig):
    overlay_root: str
    static_root: Optional[str]

    overlay_fs_args: Optional[Dict[str, Any]] = None
    static_fs_args: Optional[Dict[str, Any]] = None


FSArgs = namedtuple("FSArgs", ["fs"])
FSOArgs = namedtuple("FSOArgs", ["fs_overlay", "fs_static"])


class CopickPicksFSSpec(CopickPicksOverlay):
    @property
    def path(self) -> str:
        if self.read_only:
            return f"{self.run.static_path}/Picks/{self.user_id}_{self.session_id}_{self.pickable_object_name}.json"
        else:
            return f"{self.run.overlay_path}/Picks/{self.user_id}_{self.session_id}_{self.pickable_object_name}.json"

    @property
    def fs(self) -> AbstractFileSystem:
        return self.run.fs_static if self.read_only else self.run.fs_overlay

    def _load(self) -> CopickPicksFile:
        with self.fs.open(self.path, "r") as f:
            data = json.load(f)

        return CopickPicksFile(**data)

    def _store(self) -> None:
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
    def fs(self) -> AbstractFileSystem:
        return self.run.fs_static if self.read_only else self.run.fs_overlay

    def _load(self) -> Union[Geometry, None]:
        if not self.fs.exists(self.path):
            return None

        with self.fs.open(self.path, "rb") as f:
            scene = trimesh.load(f, file_type="glb")

        return scene

    def _store(self):
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
            return zarr.storage.FSStore(
                self.path,
                fs=self.fs,
                mode="r",
                key_separator="/",
                dimension_separator="/",
            )
        else:
            return zarr.storage.FSStore(
                self.path,
                fs=self.fs,
                mode="w",
                key_separator="/",
                dimension_separator="/",
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
            return zarr.storage.FSStore(
                self.path,
                fs=self.fs,
                mode="r",
                key_separator="/",
                dimension_separator="/",
            )
        else:
            return zarr.storage.FSStore(
                self.path,
                fs=self.fs,
                mode="w",
                key_separator="/",
                dimension_separator="/",
            )


class CopickTomogramFSSpec(CopickTomogramOverlay):
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

    def _query_static_features(self) -> List[CopickFeaturesFSSpec]:
        if self.fs_static == self.fs_overlay:
            return []

        feat_loc = self.static_path.replace(".zarr", "_")
        paths = self.fs_static.glob(feat_loc + "*_features.zarr")
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
        paths = self.fs_overlay.glob(feat_loc + "*_features.zarr")
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
            return zarr.storage.FSStore(
                self.static_path,
                fs=self.fs_static,
                mode="r",
                key_separator="/",
                dimension_separator="/",
            )
        else:
            return zarr.storage.FSStore(
                self.overlay_path,
                fs=self.fs_overlay,
                mode="w",
                key_separator="/",
                dimension_separator="/",
            )


class CopickVoxelSpacingFSSpec(CopickVoxelSpacingOverlay):
    @property
    def static_path(self):
        return f"{self.run.static_path}/VoxelSpacing{self.voxel_size:.3f}"

    @property
    def overlay_path(self):
        return f"{self.run.static_path}/VoxelSpacing{self.voxel_size:.3f}"

    @property
    def fs_static(self):
        return self.run.fs_static

    @property
    def fs_overlay(self):
        return self.run.fs_overlay

    def _query_static_tomograms(self) -> List[CopickTomogramFSSpec]:
        if self.fs_static == self.fs_overlay:
            return []
        tomo_loc = f"{self.static_path}/"
        paths = self.fs_static.glob(tomo_loc + "*.zarr")
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
        paths = self.fs_overlay.glob(tomo_loc + "*.zarr")
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


class CopickRunFSSpec(CopickRunOverlay):
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

    def query_voxelspacings(self) -> List[CopickVoxelSpacingFSSpec]:
        static_vs_loc = f"{self.static_path}/VoxelSpacing"
        paths = self.fs_static.glob(static_vs_loc + "*")
        spacings = [float(p.replace(f"{static_vs_loc}", "")) for p in paths]

        return [
            CopickVoxelSpacingFSSpec(
                meta=CopickVoxelSpacingMeta(voxel_size=s),
                run=self,
            )
            for p, s in zip(paths, spacings, strict=True)
        ]

    def _query_static_picks(self) -> List[CopickPicksFSSpec]:
        if self.fs_overlay == self.fs_static:
            return []

        pick_loc = f"{self.static_path}/Picks/"
        paths = self.fs_static.glob(pick_loc + "*")
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
        if self.fs_overlay == self.fs_static:
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
        if self.fs_overlay == self.fs_static:
            return []

        seg_loc = f"{self.static_path}/Segmentations/"
        paths = self.fs_static.glob(seg_loc + "*.zarr")
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
        paths = self.fs_overlay.glob(seg_loc + "*.zarr")
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


class CopickRootFSSpec(CopickRoot):
    def __init__(self, config: CopickConfigFSSpec):
        super().__init__(config)

        self.fs_overlay: AbstractFileSystem = fsspec.url_to_fs(config.overlay_root)[0]
        self.fs_static: Optional[AbstractFileSystem] = None

        self.root_overlay: str = self.fs_overlay._strip_protocol(config.overlay_root)
        self.root_static: Optional[str] = None

        if config.static_root is None:
            self.fs_static = self.fs_overlay
            self.root_static = self.fs_overlay._strip_protocol(config.overlay_root)
        else:
            self.fs_static = fsspec.url_to_fs(config.static_root)[0]
            self.root_static = self.fs_overlay._strip_protocol(config.static_root)

    @classmethod
    def from_file(cls, path: str) -> "CopickRootFSSpec":
        with open(path, "r") as f:
            data = json.load(f)

        return cls(CopickConfigFSSpec(**data))

    def query(self) -> List[CopickRunFSSpec]:
        static_run_dir = f"{self.root_static}/ExperimentRuns/"
        paths = self.fs_static.glob(static_run_dir + "*")
        paths = [p for p in paths if self.fs_static.isdir(p)]
        names = [n.replace(static_run_dir, "") for n in paths]

        runs = []
        for n in names:
            rm = CopickRunMeta(name=n)
            runs.append(CopickRunFSSpec(root=self, meta=rm))

        return runs
