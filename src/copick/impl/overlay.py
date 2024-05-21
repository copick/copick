from typing import List, Optional

from trimesh.parent import Geometry

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
    CopickSegmentation,
    CopickSegmentationMeta,
    CopickTomogram,
    CopickTomogramMeta,
    CopickVoxelSpacing,
    PickableObject,
)


class CopickPicksOverlay(CopickPicks):
    def __init__(self, run: CopickRun, file: CopickPicksFile, read_only: bool = False):
        super().__init__(run, file)
        self.read_only = read_only

    def store(self):
        """Store the picks, making sure the source is writable."""
        if self.read_only:
            raise PermissionError("Cannot store picks in a read-only source.")
        self._store()


class CopickMeshOverlay(CopickMesh):
    def __init__(self, run: CopickRun, meta: CopickMeshMeta, mesh: Optional[Geometry] = None, read_only: bool = False):
        super().__init__(run, meta, mesh)
        self.read_only = read_only

    def store(self):
        """Store the mesh, making sure the source is writable."""
        if self.read_only:
            raise PermissionError("Cannot store mesh in a read-only source.")
        self._store()


class CopickSegmentationOverlay(CopickSegmentation):
    def __init__(self, run: CopickRun, meta: CopickSegmentationMeta, read_only: bool = False):
        super().__init__(run, meta)
        self.read_only = read_only


class CopickObjectOverlay(CopickObject):
    def __init__(self, root: CopickRoot, meta: PickableObject, read_only: bool = True):
        super().__init__(root, meta)
        self.read_only = read_only


class CopickRunOverlay(CopickRun):
    def _query_static_picks(self) -> List[CopickPicksOverlay]:
        """Override to query the static source for the picks. All returned picks must be read-only."""
        pass

    def _query_overlay_picks(self) -> List[CopickPicksOverlay]:
        """Override to query the overlay source for the picks."""
        pass

    def query_picks(self) -> List[CopickPicksOverlay]:
        """Query all picks."""
        static = self._query_static_picks()
        overlay = self._query_overlay_picks()

        for p in static:
            assert p.read_only, "Picks from static source must be read-only."

        return static + overlay

    def _query_static_meshes(self) -> List[CopickMeshOverlay]:
        """Override to query the static source for the meshes. All returned meshes must be read-only."""
        pass

    def _query_overlay_meshes(self) -> List[CopickMeshOverlay]:
        """Override to query the overlay source for the meshes."""
        pass

    def query_meshes(self) -> List[CopickMeshOverlay]:
        """Query all meshes."""
        static = self._query_static_meshes()
        overlay = self._query_overlay_meshes()

        for m in static:
            assert m.read_only, "Meshes from static source must be read-only."

        return static + overlay

    def _query_static_segmentations(self) -> List[CopickSegmentationOverlay]:
        """Override to query the static source for the segmentations. All returned segmentations must be read-only."""
        pass

    def _query_overlay_segmentations(self) -> List[CopickSegmentationOverlay]:
        """Override to query the overlay source for the segmentations."""
        pass

    def query_segmentations(self) -> List[CopickSegmentationOverlay]:
        """Query all segmentations."""
        static = self._query_static_segmentations()
        overlay = self._query_overlay_segmentations()

        for s in static:
            assert s.read_only, "Segmentations from static source must be read-only."

        return static + overlay


class CopickFeaturesOverlay(CopickFeatures):
    def __init__(self, tomogram: CopickTomogram, meta: CopickFeaturesMeta, read_only: bool = False):
        super().__init__(tomogram, meta)
        self.read_only = read_only


class CopickTomogramOverlay(CopickTomogram):
    def __init__(self, voxel_spacing: CopickVoxelSpacing, meta: CopickTomogramMeta, read_only: bool = False, **kwargs):
        super().__init__(voxel_spacing, meta, **kwargs)
        self.read_only = read_only

    def _query_static_features(self) -> List[CopickFeaturesOverlay]:
        """Override to query the static source for the features. All returned features must be read-only."""
        pass

    def _query_overlay_features(self) -> List[CopickFeaturesOverlay]:
        """Override to query the overlay source for the features."""
        pass

    def query_features(self) -> List[CopickFeaturesOverlay]:
        """Query all features."""
        static = self._query_static_features()
        overlay = self._query_overlay_features()

        for f in static:
            assert f.read_only, "Features from static source must be read-only."

        return static + overlay


class CopickVoxelSpacingOverlay(CopickVoxelSpacing):
    def _query_static_tomograms(self) -> List[CopickTomogramOverlay]:
        """Override to query the static source for the tomograms. All returned tomograms must be read-only."""
        pass

    def _query_overlay_tomograms(self) -> List[CopickTomogramOverlay]:
        """Override to query the overlay source for the tomograms."""
        pass

    def query_tomograms(self) -> List[CopickTomogramOverlay]:
        """Query all tomograms."""
        static = self._query_static_tomograms()
        overlay = self._query_overlay_tomograms()

        for t in static:
            assert t.read_only, "Tomograms from static source must be read-only."

        return static + overlay
