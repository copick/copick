from typing import List

from fsspec import AbstractFileSystem

from copick.impl.overlay import CopickRunOverlay
from copick.models import CopickPicks, CopickPoint, CopickRoot, CopickRun, CopickTomogram, CopickVoxelSpacing


class FSSpecCopickPicks(CopickPicks):
    fs: AbstractFileSystem
    path: str

    def load(self) -> List[CopickPoint]:
        pass

    def store(self):
        pass


class FSSpecTomogram(CopickTomogram):
    fs: AbstractFileSystem
    path: str


class FSSpecVoxelSpacing(CopickVoxelSpacing):
    fs: AbstractFileSystem
    path: str

    def query(self) -> List[CopickTomogram]:
        tomo_loc = f"{self.path.rstrip('/')}/"
        paths = self.fs.glob(tomo_loc + "*")
        tomotypes = [n.replace(tomo_loc, "").replace(".zarr", "") for n in paths]

        return [
            FSSpecTomogram(fs=self.fs, path=p, tomotype=t, voxel_spacing=self)
            for p, t in zip(paths, tomotypes, strict=True)
        ]


class CopickRunFSSpec(CopickRunOverlay):
    fs_static: AbstractFileSystem
    fs_overlay: AbstractFileSystem
    path_static: str
    path_overlay: str

    def query_voxelspacings(self) -> List[CopickVoxelSpacing]:
        voxel_loc = f"{self.path.rstrip('/')}/"
        paths = self.fs.glob(voxel_loc + "*")
        spacings = [float(p.replace(f"{voxel_loc}/VoxelSpacing", "")) for p in paths]

        return [
            FSSpecVoxelSpacing(fs=self.fs, path=p, voxel_size=s, run=self) for p, s in zip(paths, spacings, strict=True)
        ]

    def query_picks(self) -> List[CopickPicks]:
        anno_loc = f"{self.path.rstrip('/')}/Annotations/"
        paths = self.fs.glob(anno_loc + "*")
        names = [n.replace(anno_loc, "") for n in paths]

        return [FSSpecCopickPicks(fs=self.fs, path=p, name=n, root=self) for p, n in zip(paths, names, strict=True)]


class FSSpecCopickRoot(CopickRoot):
    fs_static: AbstractFileSystem
    fs_overlay: AbstractFileSystem
    root_static: str
    root_overlay: str

    @property
    def static_run_dir(self) -> str:
        return f"{self.root_static}/ExperimentRuns/"

    @property
    def overlay_run_dir(self) -> str:
        return f"{self.root_overlay}/ExperimentRuns/"

    @classmethod
    def from_fs(
        cls,
        fs: AbstractFileSystem,
        root_path: str,
        fs_overlay: AbstractFileSystem = None,
        root_overlay: str = None,
    ) -> "FSSpecCopickRoot":
        root_path = root_path.rstrip("/")

        if fs_overlay is None:
            fs_overlay = fs
            root_overlay = root_path

        return cls(fs_static=fs, root_static=root_path, fs_overlay=fs_overlay, root_overlay=root_overlay)

    def query(self) -> List[CopickRun]:
        paths = self.fs_static.glob(self.static_run_dir + "*")
        names = [n.replace(self.static_run_dir, "") for n in paths]

        return [
            CopickRunFSSpec(fs_static=self.fs_static, path=p, name=n, root=self)
            for p, n in zip(paths, names, strict=True)
        ]
