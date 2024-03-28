from typing import Union

from copick.models import CopickRun, CopickTomogram, CopickVoxelSpacing


class TreeRootMixin:
    def child(self, row) -> CopickRun:
        return self.runs[row]

    def childCount(self) -> int:
        return len(self.runs)

    def childIndex(self) -> Union[int, None]:
        return None

    def data(self, column: int) -> str:
        if column == 0:
            return self.config.name
        elif column == 1:
            return ""

    def columnCount(self) -> int:
        return 2


class TreeRunMixin:
    def child(self, row) -> CopickVoxelSpacing:
        return self.voxel_spacings[row]

    def childCount(self) -> int:
        return len(self.voxel_spacings)

    def childIndex(self) -> Union[int, None]:
        return self.root.runs.index(self)

    def data(self, column: int) -> str:
        if column == 0:
            return self.name
        elif column == 1:
            return ""

    def columnCount(self) -> int:
        return 2


class TreeVoxelSpacingMixin:
    def child(self, row) -> CopickTomogram:
        return self.tomograms[row]

    def childCount(self) -> int:
        return len(self.tomograms)

    def childIndex(self) -> Union[int, None]:
        return self.run.voxel_spacings.index(self)

    def data(self, column: int) -> str:
        if column == 0:
            return f"VoxelSpacing{self.voxel_size:.3f}"
        elif column == 1:
            return ""

    def columnCount(self) -> int:
        return 2


class TreeTomogramMixin:
    def child(self, row) -> None:
        return None

    def childCount(self) -> int:
        return 0

    def childIndex(self) -> Union[int, None]:
        return self.run.voxel_spacings.index(self)

    def data(self, column: int) -> str:
        if column == 0:
            return self.tomotype
        elif column == 1:
            return ""

    def columnCount(self) -> int:
        return 2
