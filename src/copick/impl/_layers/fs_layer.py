import json
from typing import TYPE_CHECKING, List, Optional, Tuple, Type, Union

import fsspec
import trimesh
import zarr
from fsspec import AbstractFileSystem
from trimesh.parent import Geometry

from copick.impl.multilayer import CopickConfigML
from copick.models import (
    CopickFeatures,
    CopickFeaturesMeta,
    CopickMesh,
    CopickMeshMeta,
    CopickObject,
    CopickPicks,
    CopickPicksFile,
    CopickRoot,
    CopickRun,
    CopickRunMeta,
    CopickSegmentation,
    CopickSegmentationMeta,
    CopickTomogram,
    CopickTomogramMeta,
    CopickVoxelSpacing,
    CopickVoxelSpacingMeta,
    PickableObject,
)

# Type aliases using forward references
if TYPE_CHECKING:
    RunClz = Tuple[Type["CopickRunFSLayer"], Type[CopickRunMeta]]
    ObjectClz = Tuple[Type["CopickObjectFSLayer"], Type[PickableObject]]
    VoxelSpacingClz = Tuple[Type["CopickVoxelSpacingFSLayer"], Type[CopickVoxelSpacingMeta]]
    PicksClz = Tuple[Type["CopickPicksFSLayer"], Type[CopickPicksFile]]
    MeshClz = Tuple[Type["CopickMeshFSLayer"], Type[CopickMeshMeta]]
    SegmenationClz = Tuple[Type["CopickSegmentationFSLayer"], Type[CopickSegmentationMeta]]
    TomogramClz = Tuple[Type["CopickTomogramFSLayer"], Type[CopickTomogramMeta]]
    FeaturesClz = Tuple[Type["CopickFeaturesFSLayer"], Type[CopickFeaturesMeta]]


class CopickPicksFSLayer(CopickPicks):
    """CopickPicks class backed by fsspec storage.

    Attributes:
        path (str): The path to the picks file.
        directory (str): The directory containing the picks file.
        fs (AbstractFileSystem): The filesystem containing the picks file.
    """

    run: "CopickRunFSLayer"

    def __init__(self, run: "CopickRunFSLayer", file: CopickPicksFile, read_only: Union[bool, None] = None):
        super().__init__(run, file)
        self.read_only = read_only if read_only is not None else run.read_only

    @property
    def path(self) -> str:
        return f"{self.run.path}/Picks/{self.user_id}_{self.session_id}_{self.pickable_object_name}.json"

    @property
    def directory(self) -> str:
        return f"{self.run.path}/Picks/"

    @property
    def fs(self) -> AbstractFileSystem:
        return self.run.fs

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


class CopickMeshFSLayer(CopickMesh):
    """CopickMesh class backed by fspec storage.

    Attributes:
        path (str): The path to the mesh file.
        directory (str): The directory containing the mesh file.
        fs (AbstractFileSystem): The filesystem containing the mesh file.
    """

    run: "CopickRunFSLayer"

    def __init__(
        self,
        run: "CopickRunFSLayer",
        meta: CopickMeshMeta,
        mesh: Optional[Geometry] = None,
        read_only: Union[bool, None] = None,
    ):
        super().__init__(run, meta, mesh)
        self.read_only = read_only if read_only is not None else run.read_only

    @property
    def path(self) -> str:
        return f"{self.run.path}/Meshes/{self.user_id}_{self.session_id}_{self.pickable_object_name}.glb"

    @property
    def directory(self) -> str:
        return f"{self.run.path}/Meshes/"

    @property
    def fs(self) -> AbstractFileSystem:
        return self.run.fs

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


class CopickSegmentationFSLayer(CopickSegmentation):
    """CopickSegmentation class backed by fsspec storage.

    Attributes:
        filename (str): The filename of the segmentation file.
        path (str): The path to the segmentation file.
        fs (AbstractFileSystem): The filesystem containing the segmentation file.
    """

    run: "CopickRunFSLayer"

    def __init__(self, run: "CopickRunFSLayer", meta: CopickSegmentationMeta, read_only: Union[bool, None] = None):
        super().__init__(run, meta)
        self.read_only = read_only if read_only is not None else run.read_only

    @property
    def filename(self) -> str:
        if self.is_multilabel:
            return f"{self.voxel_size:.3f}_{self.user_id}_{self.session_id}_{self.name}-multilabel.zarr"
        else:
            return f"{self.voxel_size:.3f}_{self.user_id}_{self.session_id}_{self.name}.zarr"

    @property
    def path(self) -> str:
        return f"{self.run.path}/Segmentations/{self.filename}"

    @property
    def fs(self) -> AbstractFileSystem:
        return self.run.fs

    def zarr(self) -> zarr.storage.FSStore:
        """Get the zarr store for the segmentation object.

        Returns:
            zarr.storage.FSStore: The zarr store for the segmentation object.
        """
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


class CopickFeaturesFSLayer(CopickFeatures):
    """CopickFeatures class backed by fsspec storage.

    Attributes:
        path (str): The path to the features file.
        fs (AbstractFileSystem): The filesystem containing the features file.
    """

    tomogram: "CopickTomogramFSLayer"

    def __init__(
        self,
        tomogram: "CopickTomogramFSLayer",
        meta: CopickFeaturesMeta,
        read_only: Union[bool, None] = None,
    ):
        super().__init__(tomogram, meta)
        self.read_only = read_only if read_only is not None else tomogram.read_only

    @property
    def path(self) -> str:
        return f"{self.tomogram.stem}_{self.feature_type}_features.zarr"

    @property
    def fs(self) -> AbstractFileSystem:
        return self.tomogram.fs

    def zarr(self) -> zarr.storage.FSStore:
        """Get the zarr store for the features object.

        Returns:
            zarr.storage.FSStore: The zarr store for the features object.
        """
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


class CopickTomogramFSLayer(CopickTomogram):
    """CopickTomogram class backed by fsspec storage.

    Attributes:
        static_path (str): The path to the tomogram on the static source.
        overlay_path (str): The path to the tomogram on the overlay source.
        static_stem (str): The stem of the tomogram on the static source.
        overlay_stem (str): The stem of the tomogram on the overlay source.
        fs_static (AbstractFileSystem): The filesystem containing the tomogram on the static source.
        fs_overlay (AbstractFileSystem): The filesystem containing the tomogram on the overlay source.
        static_is_overlay (bool): Whether the static and overlay sources are the same.
    """

    features_clz: "FeaturesClz" = ("CopickFeaturesFSLayer", "CopickFeaturesMeta")
    voxel_spacing: "CopickVoxelSpacingFSLayer"

    def __init__(
        self,
        voxel_spacing: "CopickVoxelSpacingFSLayer",
        meta: CopickTomogramMeta,
        read_only: Union[bool, None] = None,
        **kwargs,
    ):
        super().__init__(voxel_spacing, meta)
        self.read_only = read_only if read_only is not None else voxel_spacing.read_only

    @property
    def path(self) -> str:
        return f"{self.voxel_spacing.path}/{self.tomo_type}.zarr"

    @property
    def stem(self) -> str:
        return f"{self.voxel_spacing.path}/{self.tomo_type}"

    @property
    def fs(self) -> AbstractFileSystem:
        return self.voxel_spacing.fs

    def _query_features(self) -> List[CopickFeaturesFSLayer]:
        feat_loc = self.path.replace(".zarr", "_")
        paths = self.fs.glob(feat_loc + "*_features.zarr") + self.fs.glob(feat_loc + "*_features.zarr/")
        paths = [p.rstrip("/") for p in paths if self.fs.isdir(p)]
        feature_types = [n.replace(feat_loc, "").replace("_features.zarr", "") for n in paths]
        # Remove any hidden files?
        feature_types = [ft for ft in feature_types if not ft.startswith(".")]

        feature_types = list(set(feature_types))

        return [
            CopickFeaturesFSLayer(
                tomogram=self,
                meta=CopickFeaturesMeta(
                    tomo_type=self.tomo_type,
                    feature_type=ft,
                ),
                read_only=self.read_only,
            )
            for ft in feature_types
        ]

    def zarr(self) -> zarr.storage.FSStore:
        """Get the zarr store for the tomogram object.

        Returns:
            zarr.storage.FSStore: The zarr store for the tomogram object.
        """
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


class CopickVoxelSpacingFSLayer(CopickVoxelSpacing):
    """CopickVoxelSpacing class backed by fsspec storage.

    Attributes:
        static_path (str): The path to the voxel spacing on the static source.
        overlay_path (str): The path to the voxel spacing on the overlay source.
        fs_static (AbstractFileSystem): The filesystem containing the voxel spacing on the static source.
        fs_overlay (AbstractFileSystem): The filesystem containing the voxel spacing on the overlay source.
        static_is_overlay (bool): Whether the static and overlay sources are the same.

    """

    tomogram_clz: "TomogramClz" = ("CopickTomogramFSLayer", "CopickTomogramMeta")
    run: "CopickRunFSLayer"

    @property
    def path(self) -> str:
        return f"{self.run.path}/VoxelSpacing{self.voxel_size:.3f}"

    @property
    def fs(self) -> AbstractFileSystem:
        return self.run.fs

    @property
    def read_only(self) -> bool:
        return self.run.read_only

    def _query_tomograms(self) -> List[CopickTomogramFSLayer]:
        tomo_loc = f"{self.path}/"
        paths = self.fs.glob(tomo_loc + "*.zarr") + self.fs.glob(tomo_loc + "*.zarr/")
        paths = [p.rstrip("/") for p in paths if self.fs.isdir(p)]
        tomo_types = [n.replace(tomo_loc, "").replace(".zarr", "") for n in paths]
        tomo_types = [t for t in tomo_types if "features" not in t]
        # Remove any hidden files?
        tomo_types = [tt for tt in tomo_types if not tt.startswith(".")]

        tomo_types = list(set(tomo_types))

        return [
            CopickTomogramFSLayer(
                voxel_spacing=self,
                meta=CopickTomogramMeta(tomo_type=tt),
                read_only=self.read_only,
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
        exists = self.fs.exists(self.path)

        if not exists and create and not self.read_only:
            self.fs.makedirs(self.path, exist_ok=True)
            # TODO: Write metadata
            with self.fs.open(self.path + "/.meta", "w") as f:
                f.write("meta")  # Touch the file
            return True
        else:
            return exists


class CopickRunFSLayer(CopickRun):
    """CopickRun class backed by fsspec storage.

    Attributes:
        path (str): The path to the run in storage.
        fs (AbstractFileSystem): The filesystem containing the run.
    """

    voxel_spacing_clz: "VoxelSpacingClz" = ("CopickVoxelSpacingFSLayer", "CopickVoxelSpacingMeta")
    picks_clz: "PicksClz" = ("CopickPicksFSLayer", "CopickPicksFile")
    mesh_clz: "MeshClz" = ("CopickMeshFSLayer", "CopickMeshMeta")
    segmentation_clz: "SegmenationClz" = ("CopickSegmentationFSLayer", "CopickSegmentationMeta")

    root: "CopickRootFSLayer"

    @property
    def path(self) -> str:
        return f"{self.root.url}/ExperimentRuns/{self.name}"

    @property
    def fs(self) -> AbstractFileSystem:
        return self.root.fs

    @property
    def read_only(self) -> bool:
        return self.root.read_only

    def _query_voxel_spacings(self) -> List[CopickVoxelSpacingFSLayer]:
        vs_loc = f"{self.path}/VoxelSpacing"
        paths = set(self.fs.glob(vs_loc + "*") + self.fs.glob(vs_loc + "*/"))
        paths = [p.rstrip("/") for p in paths]
        spacings = [float(p.replace(f"{vs_loc}", "")) for p in paths]

        return [
            CopickVoxelSpacingFSLayer(
                meta=CopickVoxelSpacingMeta(voxel_size=s),
                run=self,
            )
            for s in spacings
        ]

    def _query_picks(self) -> List[CopickPicksFSLayer]:
        pick_loc = f"{self.path}/Picks/"
        paths = self.fs.glob(pick_loc + "*.json")
        names = [n.replace(pick_loc, "").replace(".json", "") for n in paths]
        # Remove any hidden files?
        names = [n for n in names if not n.startswith(".")]

        users = [n.split("_")[0] for n in names]
        sessions = [n.split("_")[1] for n in names]
        objects = [n.split("_")[2] for n in names]

        # zip(strict=True) (replace once python 3.9 is EOL)
        assert len(users) == len(sessions) == len(objects)

        return [
            CopickPicksFSLayer(
                run=self,
                file=CopickPicksFile(
                    pickable_object_name=o,
                    user_id=u,
                    session_id=s,
                ),
                read_only=self.read_only,
            )
            for u, s, o in zip(users, sessions, objects)  # , strict=True)
        ]

    def _query_meshes(self) -> List[CopickMeshFSLayer]:
        mesh_loc = f"{self.path}/Meshes/"
        paths = self.fs.glob(mesh_loc + "*.glb")
        names = [n.replace(mesh_loc, "").replace(".glb", "") for n in paths]
        # Remove any hidden files?
        names = [n for n in names if not n.startswith(".")]

        users = [n.split("_")[0] for n in names]
        sessions = [n.split("_")[1] for n in names]
        objects = [n.split("_")[2] for n in names]

        # zip(strict=True) (replace once python 3.9 is EOL)
        assert len(users) == len(sessions) == len(objects)

        return [
            CopickMeshFSLayer(
                run=self,
                meta=CopickMeshMeta(
                    pickable_object_name=o,
                    user_id=u,
                    session_id=s,
                ),
                read_only=self.read_only,
            )
            for u, s, o in zip(users, sessions, objects)  # , strict=True)
        ]

    def _query_segmentations(self) -> List[CopickSegmentationFSLayer]:
        seg_loc = f"{self.path}/Segmentations/"
        paths = self.fs.glob(seg_loc + "*.zarr") + self.fs.glob(seg_loc + "*.zarr/")
        paths = [p.rstrip("/") for p in paths if self.fs.isdir(p)]
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
            CopickSegmentationFSLayer(
                run=self,
                meta=m,
                read_only=self.read_only,
            )
            for m in metas
        ]

    def ensure(self, create: bool = False) -> bool:
        """Checks if the run record exists in the static or overlay directory, optionally creating it in the overlay
        filesystem if it does not.

        Args:
            create: Whether to create the run record if it does not exist.

        Returns:
            bool: True if the run record exists, False otherwise.
        """

        exists = self.fs.exists(self.path)

        if not exists and create and not self.read_only:
            self.fs.makedirs(self.path, exist_ok=True)
            # TODO: Write metadata
            with self.fs.open(self.path + "/.meta", "w") as f:
                f.write("meta")  # Touch the file
            return True
        else:
            return exists


class CopickObjectFSLayer(CopickObject):
    """CopickObject class backed by fsspec storage.

    Attributes:
        path (str): The path to the object file.
        fs (AbstractFileSystem): The filesystem containing the object file.
    """

    root: "CopickRootFSLayer"

    def __init__(self, root: "CopickRootFSLayer", meta: PickableObject, read_only: Union[bool, None] = None):
        super().__init__(root, meta)
        self.read_only = read_only if read_only is not None else root.read_only

    @property
    def path(self) -> str:
        return f"{self.root.path}/Objects/{self.name}.zarr"

    @property
    def fs(self) -> AbstractFileSystem:
        return self.root.fs

    def zarr(self) -> Union[None, zarr.storage.FSStore]:
        """Get the zarr store for the object.

        Returns:
            Union[None, zarr.storage.FSStore]: The zarr store for the object, or None if the object is not a particle.
        """
        if not self.is_particle:
            return None

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


class CopickRootFSLayer(CopickRoot):
    """CopickRoot class backed by fspec storage.

    Attributes:
        fs (AbstractFileSystem): The storage filesystem.
        root (str): The root path for the storage.
    """

    run_clz: "RunClz" = ("CopickRunFSLayer", "CopickRunMeta")
    object_clz: "ObjectClz" = ("CopickObjectFSLayer", "PickableObject")

    def __init__(self, config: CopickConfigML, name: str):
        """
        Args:
            config: Copick configuration for fsspec-based storage.
            layer: The name of the storage layer to use.
        """
        super().__init__(config)

        self.layer_config = config.layers[name]
        self.read_only = self.layer_config.read_only
        self.fs: AbstractFileSystem = fsspec.core.url_to_fs(self.layer_config.url, **self.layer_config.fs_args)[0]
        self.path: str = self.fs._strip_protocol(self.layer_config.url).rstrip("/")

    def _query_names(self) -> List[str]:
        # Query location
        run_dir = f"{self.path}/ExperimentRuns/"
        paths = self.fs.glob(run_dir + "**", maxdepth=1, detail=True)
        names = [
            p.rstrip("/").replace(run_dir, "")
            for p, details in paths.items()
            if (details.get("type", "") == "directory")
            or (details.get("type", "") == "other" and details.get("islink", False))
            or (details.get("type", "") == "link")
        ]

        # Remove any hidden files
        names = [n for n in names if not n.startswith(".") and n != f"{self.path}/ExperimentRuns"]
        return names

    def query(self) -> List[CopickRunFSLayer]:
        # Query filesystem
        names = self._query_names()

        # Deduplicate
        names = sorted(set(names))

        # Create objects
        clz, meta_clz = self.run_clz
        runs = []
        for n in names:
            rm = meta_clz(name=n)
            runs.append(clz(root=self, meta=rm))

        return runs


# Resolve forward references
CopickRootFSLayer.run_clz = (CopickRunFSLayer, CopickRunMeta)
CopickRootFSLayer.object_clz = (CopickObjectFSLayer, PickableObject)
CopickRunFSLayer.voxel_spacing_clz = (CopickVoxelSpacingFSLayer, CopickVoxelSpacingMeta)
CopickRunFSLayer.picks_clz = (CopickPicksFSLayer, CopickPicksFile)
CopickRunFSLayer.mesh_clz = (CopickMeshFSLayer, CopickMeshMeta)
CopickRunFSLayer.segmentation_clz = (CopickSegmentationFSLayer, CopickSegmentationMeta)
CopickVoxelSpacingFSLayer.tomogram_clz = (CopickTomogramFSLayer, CopickTomogramMeta)
CopickTomogramFSLayer.features_clz = (CopickFeaturesFSLayer, CopickFeaturesMeta)
