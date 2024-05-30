import json
from typing import Any, Dict, List, Optional, Tuple, Type, Union

import fsspec
import trimesh
import zarr
from cryoet_data_portal import AnnotationFile, Client, Dataset, Run
from fsspec import AbstractFileSystem
from trimesh.parent import Geometry

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
    CopickMeshMeta,
    CopickPicksFile,
    CopickRoot,
    CopickRunMeta,
    CopickSegmentationMeta,
    CopickTomogramMeta,
    CopickVoxelSpacingMeta,
    PickableObject,
    TCopickConfig,
    TCopickFeatures,
    TCopickRoot,
    TCopickRun,
    TCopickVoxelSpacing,
)


class CopickConfigCDP(CopickConfig):
    overlay_root: str
    dataset_id: int

    overlay_fs_args: Optional[Dict[str, Any]] = {}


class CopickPicksCDP(CopickPicksOverlay):
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
            json.dump(self.meta.dict(), f, indent=4)


class CopickMeshCDP(CopickMeshOverlay):
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


class CopickSegmentationCDP(CopickSegmentationOverlay):
    @property
    def filename(self) -> str:
        if self.is_multilabel:
            return f"{self.voxel_size:.3f}_{self.user_id}_{self.session_id}_{self.name}-multilabel.zarr"
        else:
            return f"{self.voxel_size:.3f}_{self.user_id}_{self.session_id}_{self.name}.zarr"

    @property
    def path(self) -> str:
        if self.read_only:
            return f"{self.run.static_path}/Segmentations/{self.filename}"
        else:
            return f"{self.run.overlay_path}/Segmentations/{self.filename}"

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


class CopickFeaturesCDP(CopickFeaturesOverlay):
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


class CopickTomogramCDP(CopickTomogramOverlay):
    def _feature_factory(self) -> Tuple[Type[TCopickFeatures], Type["CopickFeaturesMeta"]]:
        return CopickFeaturesCDP, CopickFeaturesMeta

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

    def _query_static_features(self) -> List[CopickFeaturesCDP]:
        if self.static_is_overlay:
            return []

        feat_loc = self.static_path.replace(".zarr", "_")
        paths = self.fs_static.glob(feat_loc + "*_features.zarr") + self.fs_static.glob(feat_loc + "*_features.zarr/")
        paths = [p.rstrip("/") for p in paths if self.fs_static.isdir(p)]
        feature_types = [n.replace(feat_loc, "").replace("_features.zarr", "") for n in paths]
        # Remove any hidden files?
        feature_types = [ft for ft in feature_types if not ft.startswith(".")]

        feature_types = list(set(feature_types))

        return [
            CopickFeaturesCDP(
                tomogram=self,
                meta=CopickFeaturesMeta(
                    tomo_type=self.tomo_type,
                    feature_type=ft,
                ),
                read_only=True,
            )
            for ft in feature_types
        ]

    def _query_overlay_features(self) -> List[CopickFeaturesCDP]:
        feat_loc = self.overlay_path.replace(".zarr", "_")
        paths = self.fs_overlay.glob(feat_loc + "*_features.zarr") + self.fs_overlay.glob(feat_loc + "*_features.zarr/")
        paths = [p.rstrip("/") for p in paths if self.fs_overlay.isdir(p)]
        feature_types = [n.replace(feat_loc, "").replace("_features.zarr", "") for n in paths]
        # Remove any hidden files?
        feature_types = [ft for ft in feature_types if not ft.startswith(".")]

        feature_types = list(set(feature_types))

        return [
            CopickFeaturesCDP(
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


class CopickVoxelSpacingCDP(CopickVoxelSpacingOverlay):
    def _tomogram_factory(self) -> Tuple[Type[CopickTomogramCDP], Type[CopickTomogramMeta]]:
        return CopickTomogramCDP, CopickTomogramMeta

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

    def _query_static_tomograms(self) -> List[CopickTomogramCDP]:
        if self.static_is_overlay:
            return []

        tomo_loc = f"{self.static_path}/"
        paths = self.fs_static.glob(tomo_loc + "*.zarr") + self.fs_static.glob(tomo_loc + "*.zarr/")
        paths = [p.rstrip("/") for p in paths if self.fs_static.isdir(p)]
        tomo_types = [n.replace(tomo_loc, "").replace(".zarr", "") for n in paths]
        tomo_types = [t for t in tomo_types if "features" not in t]
        # Remove any hidden files?
        tomo_types = [tt for tt in tomo_types if not tt.startswith(".")]

        tomo_types = list(set(tomo_types))

        return [
            CopickTomogramCDP(
                voxel_spacing=self,
                meta=CopickTomogramMeta(tomo_type=tt),
                read_only=True,
            )
            for tt in tomo_types
        ]

    def _query_overlay_tomograms(self) -> List[CopickTomogramCDP]:
        tomo_loc = f"{self.overlay_path}/"
        paths = self.fs_overlay.glob(tomo_loc + "*.zarr") + self.fs_overlay.glob(tomo_loc + "*.zarr/")
        paths = [p.rstrip("/") for p in paths if self.fs_overlay.isdir(p)]
        tomo_types = [n.replace(tomo_loc, "").replace(".zarr", "") for n in paths]
        tomo_types = [t for t in tomo_types if "features" not in t]
        # Remove any hidden files?
        tomo_types = [tt for tt in tomo_types if not tt.startswith(".")]

        tomo_types = list(set(tomo_types))

        return [
            CopickTomogramCDP(
                voxel_spacing=self,
                meta=CopickTomogramMeta(tomo_type=tt),
                read_only=False,
            )
            for tt in tomo_types
        ]

    def ensure(self) -> None:
        if not self.fs_overlay.exists(self.overlay_path):
            self.fs_overlay.makedirs(self.overlay_path, exist_ok=True)


class CopickPicksFileCDP(CopickPicksFile):
    @classmethod
    def from_portal(cls, source: AnnotationFile):
        anno = AnnotationFile.annotation

        user = anno.annotation_software
        session = 0
        obj = anno.object_name

        return cls(
            pickable_object_name=obj,
            user_id=user,
            session_id=session,
        )


class CopickRunCDP(CopickRunOverlay):
    def __init__(self, root: TCopickRoot, meta: CopickRunMeta, portal_run: Run, config: Optional[TCopickConfig] = None):
        CopickRunOverlay.__init__(self, root, meta, config)
        self.portal_run = portal_run

    def _voxel_spacing_factory(self) -> Tuple[Type[TCopickVoxelSpacing], Type["CopickVoxelSpacingMeta"]]:
        return CopickVoxelSpacingCDP, CopickVoxelSpacingMeta

    def _picks_factory(self) -> Type[CopickPicksCDP]:
        return CopickPicksCDP

    def _mesh_factory(self) -> Tuple[Type[CopickMeshCDP], Type[CopickMeshMeta]]:
        return CopickMeshCDP

    def _segmentation_factory(self) -> Tuple[Type[CopickSegmentationCDP], Type[CopickSegmentationMeta]]:
        return CopickSegmentationCDP, CopickSegmentationMeta

    @property
    def overlay_path(self):
        return f"{self.root.root_overlay}/ExperimentRuns/{self.name}"

    @property
    def fs_overlay(self):
        return self.root.fs_overlay

    def query_voxelspacings(self) -> List[CopickVoxelSpacingCDP]:
        portal_vs = self.portal_run.tomogram_voxel_spacings

        return [
            CopickVoxelSpacingCDP(meta=CopickVoxelSpacingMeta(voxel_size=vs.voxel_spacing), run=self, portal_vs=vs)
            for vs in portal_vs
        ]

    def _query_static_picks(self) -> List[CopickPicksCDP]:
        client = Client()
        point_annos = AnnotationFile.find(
            client,
            [
                AnnotationFile.annotation.tomogram_voxel_spacing.run_id == self.portal_run.id,
                AnnotationFile.shape_type._in(["Point", "OrientedPoint"]),
            ],
        )

        # users = [af.annotation.annotation_software for af in point_annos]
        # sessions = [0] * len(point_annos)
        # objects = [af.annotation.object_name for af in point_annos]

        return [
            CopickPicksCDP(
                run=self,
                file=CopickPicksFileCDP.from_portal(af),
                read_only=True,
            )
            for af in point_annos
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

        return [
            CopickPicksCDP(
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

    def _query_static_meshes(self) -> List[CopickMeshCDP]:
        if self.static_is_overlay:
            return []

        mesh_loc = f"{self.static_path}/Meshes/"
        paths = self.fs_static.glob(mesh_loc + "*.glb")
        names = [n.replace(mesh_loc, "").replace(".glb", "") for n in paths]
        # Remove any hidden files?
        names = [n for n in names if not n.startswith(".")]

        users = [n.split("_")[0] for n in names]
        sessions = [n.split("_")[1] for n in names]
        objects = [n.split("_")[2] for n in names]

        return [
            CopickMeshCDP(
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

    def _query_overlay_meshes(self) -> List[CopickMeshCDP]:
        mesh_loc = f"{self.overlay_path}/Meshes/"
        paths = self.fs_overlay.glob(mesh_loc + "*.glb")
        names = [n.replace(mesh_loc, "").replace(".glb", "") for n in paths]
        # Remove any hidden files?
        names = [n for n in names if not n.startswith(".")]

        users = [n.split("_")[0] for n in names]
        sessions = [n.split("_")[1] for n in names]
        objects = [n.split("_")[2] for n in names]

        return [
            CopickMeshCDP(
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

    def _query_static_segmentations(self) -> List[CopickSegmentationCDP]:
        if self.static_is_overlay:
            return []

        seg_loc = f"{self.static_path}/Segmentations/"
        paths = self.fs_static.glob(seg_loc + "*.zarr") + self.fs_static.glob(seg_loc + "*.zarr/")
        paths = [p.rstrip("/") for p in paths if self.fs_static.isdir(p)]
        names = [n.replace(seg_loc, "").replace(".zarr", "") for n in paths]
        # Remove any hidden files?
        names = [n for n in names if not n.startswith(".")]

        # Deduplicate
        names = list(set(names))

        # multilabel vs single label
        metas = []
        for n in names:
            if "multilabel" in n:
                parts = n.split("_")
                metas.append(
                    CopickSegmentationMeta(
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
                    CopickSegmentationMeta(
                        is_multilabel=False,
                        voxel_size=float(parts[0]),
                        user_id=parts[1],
                        session_id=parts[2],
                        name=parts[3],
                    ),
                )

        return [
            CopickSegmentationCDP(
                run=self,
                meta=m,
                read_only=True,
            )
            for m in metas
        ]

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
        for n in names:
            if "multilabel" in n:
                parts = n.split("_")
                metas.append(
                    CopickSegmentationMeta(
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
                    CopickSegmentationMeta(
                        is_multilabel=False,
                        voxel_size=float(parts[0]),
                        user_id=parts[1],
                        session_id=parts[2],
                        name=parts[3],
                    ),
                )

        return [
            CopickSegmentationCDP(
                run=self,
                meta=m,
                read_only=False,
            )
            for m in metas
        ]

    def ensure(self) -> None:
        if not self.fs_overlay.exists(self.overlay_path):
            self.fs_overlay.makedirs(self.overlay_path, exist_ok=True)


class CopickObjectCDP(CopickObjectOverlay):
    @property
    def path(self):
        return f"{self.root.root_static}/Objects/{self.name}.zarr"

    @property
    def fs(self):
        return self.root.fs_static

    def zarr(self) -> Union[None, zarr.storage.FSStore]:
        if not self.is_particle:
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


class CopickRootCDP(CopickRoot):
    def __init__(self, config: CopickConfigCDP):
        super().__init__(config)

        self.fs_overlay: AbstractFileSystem = fsspec.core.url_to_fs(config.overlay_root, **config.overlay_fs_args)[0]

        self.client = Client()
        self.dataset = Dataset.get_by_id(self.client, config.dataset_id)

        self.root_overlay: str = self.fs_overlay._strip_protocol(config.overlay_root)

    @classmethod
    def from_file(cls, path: str) -> "CopickRootCDP":
        with open(path, "r") as f:
            data = json.load(f)

        return cls(CopickConfigCDP(**data))

    def _run_factory(self) -> Tuple[Type[TCopickRun], Type["CopickRunMeta"]]:
        return CopickRunCDP, CopickRunMeta

    def _object_factory(self) -> Tuple[Type[CopickObjectCDP], Type[PickableObject]]:
        return CopickObjectCDP, PickableObject

    def query(self) -> List[CopickRunCDP]:
        portal_runs = self.dataset.runs

        runs = []
        for pr in portal_runs:
            rm = CopickRunMeta(name=pr.name)
            runs.append(CopickRunCDP(root=self, meta=rm, portal_run=pr))

        return runs
