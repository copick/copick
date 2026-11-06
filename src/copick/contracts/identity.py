"""Which reconstruction, which voxel grid, and which segmentation a document refers to."""

import math
from typing import TYPE_CHECKING, List, Literal, Optional

from pydantic import Field

from copick.contracts._common import Contract, Shape3, Vec3

if TYPE_CHECKING:
    from copick.models import CopickSegmentation, CopickTomogram

SegmentationKind = Literal["binary", "multilabel", "instance", "panoptic"]

_ANGSTROM_PER_UNIT = {"angstrom": 1.0, "nanometer": 10.0, "micrometer": 1e4}


def _multiscale(attrs: dict) -> dict:
    """First multiscale of OME-NGFF 0.4 (``multiscales``) or 0.5 (``ome.multiscales``) attributes."""
    multiscales = attrs.get("multiscales") or (attrs.get("ome") or {}).get("multiscales")
    if not multiscales:
        raise ValueError("No OME-NGFF multiscales metadata.")
    return multiscales[0]


class Geometry(Contract):
    """The level-0 voxel grid of a reconstruction: axes (z, y, x), physical coordinates in angstrom.

    A voxel's physical position is ``index * scale_angstrom + translation_angstrom``. Data on a different grid (a
    feature map, a label volume, a model output) must be resampled by its producer before it can be compared or
    combined, and the resampling recorded.
    """

    shape: Shape3
    scale_angstrom: Vec3
    translation_angstrom: Vec3 = Field(default_factory=lambda: [0.0, 0.0, 0.0])

    def mismatches(self, other: "Geometry", tolerance_angstrom: float = 1e-3) -> List[str]:
        """Differences from another grid, in words; empty if both describe the same voxels."""
        problems = []
        if list(self.shape) != list(other.shape):
            problems.append(f"shape {list(self.shape)} != {list(other.shape)}")
        for name in ("scale_angstrom", "translation_angstrom"):
            mine, theirs = getattr(self, name), getattr(other, name)
            if not all(
                math.isclose(a, b, rel_tol=1e-6, abs_tol=tolerance_angstrom) for a, b in zip(mine, theirs, strict=True)
            ):
                problems.append(f"{name} {list(mine)} != {list(theirs)}")
        return problems

    @classmethod
    def from_ome_attrs(cls, attrs: dict, shape: List[int]) -> "Geometry":
        """Read the first multiscale level of OME-NGFF (0.4 ``multiscales`` or 0.5 ``ome.multiscales``) attributes."""
        level = _multiscale(attrs)
        space = [axis for axis in level.get("axes", []) if axis.get("type", "space") == "space"]
        if [axis.get("name") for axis in space] != ["z", "y", "x"]:
            raise ValueError(f"Expected spatial axes z, y, x; found {[axis.get('name') for axis in space]}.")
        units = {axis.get("unit", "angstrom") for axis in space}
        if len(units) != 1 or next(iter(units)) not in _ANGSTROM_PER_UNIT:
            raise ValueError(f"Unsupported spatial units {sorted(units)}.")
        per_unit = _ANGSTROM_PER_UNIT[next(iter(units))]
        scale, translation = [1.0, 1.0, 1.0], [0.0, 0.0, 0.0]
        for transform in level["datasets"][0].get("coordinateTransformations", []):
            if transform.get("type") == "scale":
                scale = [float(v) for v in transform["scale"][-3:]]
            elif transform.get("type") == "translation":
                translation = [float(v) for v in transform["translation"][-3:]]
        return cls(
            shape=list(shape)[-3:],
            scale_angstrom=[s * per_unit for s in scale],
            translation_angstrom=[t * per_unit for t in translation],
        )


class ReconstructionRef(Contract):
    """A copick tomogram, by its place in a project, together with its voxel grid.

    Two clients show the same reconstruction only if both the key (project, run, voxel size, reconstruction type)
    and the geometry agree; matching names alone are not enough.
    """

    project: str = Field(
        pattern=r"^[^/\\:]+$",
        description="Project identifier chosen by the host (for example a registry ID). Not a path or URL.",
    )
    run: str = Field(min_length=1)
    voxel_size: float = Field(gt=0, description="Copick voxel spacing in angstrom.")
    tomo_type: str = Field(min_length=1)
    geometry: Geometry
    portal_tomogram_id: Optional[int] = Field(
        default=None,
        description="CryoET Data Portal tomogram ID, when the reconstruction comes from the portal.",
    )

    @property
    def key(self) -> str:
        return f"{self.project}/{self.run}/{self.voxel_size:.3f}/{self.tomo_type}"

    def mismatches(self, other: "ReconstructionRef") -> List[str]:
        """Differences from another reference, in words; empty if both name the same reconstruction and grid."""
        problems = [] if self.key == other.key else [f"reconstruction {self.key} != {other.key}"]
        return problems + self.geometry.mismatches(other.geometry)

    @classmethod
    def from_tomogram(cls, tomogram: "CopickTomogram", project: str) -> "ReconstructionRef":
        """Describe an opened copick tomogram; reads OME metadata and the level-0 shape, not voxel data."""
        import zarr

        group = zarr.open_group(tomogram.zarr(), mode="r")
        attrs = dict(group.attrs)
        first = _multiscale(attrs)["datasets"][0]["path"]
        voxel_spacing = tomogram.voxel_spacing
        return cls(
            project=project,
            run=voxel_spacing.run.name,
            voxel_size=voxel_spacing.voxel_size,
            tomo_type=tomogram.tomo_type,
            geometry=Geometry.from_ome_attrs(attrs, list(group[first].shape)),
            portal_tomogram_id=getattr(tomogram.meta, "portal_tomo_id", None),
        )


class SegmentationRef(Contract):
    """A copick segmentation of a run, as copick stores it.

    ``kind`` uses copick's segmentation types: ``multilabel`` (one value per class) and ``binary`` hold semantic
    labels; ``instance`` holds instance IDs of one object; ``panoptic`` holds both in two channels.
    """

    name: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    voxel_size: float = Field(gt=0)
    kind: SegmentationKind

    def same_segmentation(self, other: "SegmentationRef") -> bool:
        return (self.name, self.user_id, self.session_id, round(self.voxel_size, 3), self.kind) == (
            other.name,
            other.user_id,
            other.session_id,
            round(other.voxel_size, 3),
            other.kind,
        )

    @classmethod
    def from_segmentation(cls, segmentation: "CopickSegmentation") -> "SegmentationRef":
        from copick.util.segmentation import segmentation_type

        meta = segmentation.meta
        return cls(
            name=meta.name,
            user_id=meta.user_id,
            session_id=str(meta.session_id),
            voxel_size=meta.voxel_size,
            kind=segmentation_type(meta.is_multilabel, meta.is_instance, meta.is_panoptic),
        )
