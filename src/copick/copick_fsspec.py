from typing import List

from fsspec import AbstractFileSystem

from .copick_models import CopickRoot, CopickRun, CopickTomogram, CopickVoxelSpacing


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


class FSSpecCopickRun(CopickRun):
    fs: AbstractFileSystem
    path: str

    def query_voxelspacings(self) -> List[CopickVoxelSpacing]:
        voxel_loc = f"{self.path.rstrip('/')}/"
        paths = self.fs.glob(voxel_loc + "*")
        spacings = [float(p.replace(f"{voxel_loc}/VoxelSpacing", "")) for p in paths]

        return [
            FSSpecVoxelSpacing(fs=self.fs, path=p, voxel_size=s, run=self) for p, s in zip(paths, spacings, strict=True)
        ]

    def query_annotations(self) -> List[CopickVoxelSpacing]:
        anno_loc = f"{self.path.rstrip('/')}/Annotations/"
        paths = self.fs.glob(anno_loc + "*")
        names = [n.replace(anno_loc, "") for n in paths]

        return [FSSpecCopickRun(fs=self.fs, path=p, name=n, root=self) for p, n in zip(paths, names, strict=True)]


class FSSpecCopickRoot(CopickRoot):
    fs: AbstractFileSystem
    path: str

    @classmethod
    def from_fs(cls, fs: AbstractFileSystem, root_path: str) -> "FSSpecCopickRoot":
        return cls(fs=fs, path=root_path.rstrip("/"))

    def query(self) -> List[CopickRun]:
        run_loc = f"{self.path}/ExperimentRuns/"
        paths = self.fs.glob(run_loc + "*")
        names = [n.replace(run_loc, "") for n in paths]

        return [FSSpecCopickRun(fs=self.fs, path=p, name=n, root=self) for p, n in zip(paths, names, strict=True)]
