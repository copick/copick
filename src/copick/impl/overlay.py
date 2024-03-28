from typing import List

from copick.models import CopickPicks, CopickRun, CopickVoxelSpacing


class CopickPicksStatic(CopickPicks):
    """A read-only version of CopickPicks."""

    pass

    def store(self):
        """Store picks to a read-only source."""
        raise NotImplementedError("Cannot store picks to a read-only source.")


class CopickRunOverlay(CopickRun):
    def query_picks(self) -> List[CopickPicksStatic]:
        """Query picks from a common source. Reimplement this for querying a read-only source."""
        pass

    def query_picks_overlay(self) -> List[CopickPicks]:
        """Query picks from an overlay source. Reimplement this for querying a writable source."""
        pass

    @property
    def voxel_spacings(self) -> List[CopickVoxelSpacing]:
        """Lazy load voxel spacings via a RESTful interface or filesystem."""
        if self.voxel_spacings_ is None:
            self.voxel_spacings_ = self.query_voxelspacings()

        return self.voxel_spacings_

    @property
    def picks(self) -> List[CopickPicks]:
        """Lazy load picks via a RESTful interface or filesystem."""
        if self.picks_ is None:
            self.picks_ = self.query_picks() + self.query_picks_overlay()

        return self.picks_
