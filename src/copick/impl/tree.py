from typing import Union

from copick.models import (
    CopickRoot,
    CopickRun,
    CopickTomogram,
    CopickVoxelSpacing,
)


class TreeRoot:
    def __init__(self, root: CopickRoot):
        self.root = root
        self.has_children = True

    def child(self, row) -> "TreeRun":
        return TreeRun(run=self.root.runs[row])

    def childCount(self) -> int:
        return len(self.root.runs)

    def childIndex(self) -> Union[int, None]:
        return None

    def data(self, column: int) -> str:
        if column == 0:
            return self.root.config.name
        elif column == 1:
            return ""

    def columnCount(self) -> int:
        return 2


class TreeRun:
    def __init__(self, run: CopickRun):
        self.run = run
        self.has_children = True

    def child(self, row) -> "TreeVoxelSpacing":
        return TreeVoxelSpacing(voxel_spacing=self.run.voxel_spacings[row])

    def childCount(self) -> int:
        return len(self.run.voxel_spacings)

    def childIndex(self) -> Union[int, None]:
        return self.run.root.runs.index(self)

    def data(self, column: int) -> str:
        if column == 0:
            return self.run.name
        elif column == 1:
            return ""

    def columnCount(self) -> int:
        return 2


class TreeVoxelSpacing:
    def __init__(self, voxel_spacing: CopickVoxelSpacing):
        self.voxel_spacing = voxel_spacing
        self.has_children = True

    def child(self, row) -> "TreeTomogram":
        return self.voxel_spacing.tomograms[row]

    def childCount(self) -> int:
        return len(self.voxel_spacing.tomograms)

    def childIndex(self) -> Union[int, None]:
        return self.voxel_spacing.run.voxel_spacings.index(self)

    def data(self, column: int) -> str:
        if column == 0:
            return f"VoxelSpacing{self.voxel_spacing.voxel_size:.3f}"
        elif column == 1:
            return ""

    def columnCount(self) -> int:
        return 2


class TreeTomogram:
    def __init__(self, tomogram: CopickTomogram):
        self.tomogram = tomogram
        self.has_children = False

    def child(self, row) -> None:
        return None

    def childCount(self) -> int:
        return 0

    def childIndex(self) -> Union[int, None]:
        return self.tomogram.voxel_spacing.tomograms.index(self)

    def data(self, column: int) -> str:
        if column == 0:
            return self.tomogram.tomo_type
        elif column == 1:
            return ""

    def columnCount(self) -> int:
        return 2
