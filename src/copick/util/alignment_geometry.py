"""Geometry of tilt-series alignments.

A (rigid) projection alignment maps a point ``p`` of a tomogram to a point ``q`` of a tilt image::

    q = drop_z(R @ p) + t,    R = Rz(in_plane_rotation) @ Ry(tilt_angle) @ Rx(x_tilt)

with active, right-handed rotations in degrees and positions in Angstrom. ``p`` is relative to a centre of the
tomogram and ``q`` to a centre of the image. Tools differ in where these centres are:

=========================  ================  =================
Convention                 Image centre      Volume centre
=========================  ================  =================
CETS, RELION (``floor``)   ``floor(N/2)``    ``floor(N/2)``
AreTomo3, Warp, CryoET     ``N/2``           ``V/2``
Data Portal (``half``)
=========================  ================  =================

with ``N`` sizes in pixels or voxels (centres at ``N/2 * spacing`` from the corner of pixel 0) and ``V`` volume
extents in Angstrom. copick stores alignments in the CETS convention; a shift ``t`` in another convention converts as::

    t_cets = t_native + d_img - (R @ d_vol)[:2]

with ``d_img`` and ``d_vol`` the offsets of the native centres from the CETS centres, in Angstrom.
"""

import math
from dataclasses import dataclass
from typing import Dict, Literal, Optional, Sequence, Tuple

import numpy as np

#: Where a convention puts the centre of an axis of ``N`` samples: at ``N/2`` or at ``floor(N/2)``.
CenterKind = Literal["half", "floor"]


@dataclass(frozen=True)
class FrameConvention:
    """Image and volume centres of a tool's alignments."""

    image_center: CenterKind
    volume_center: CenterKind


#: Frame conventions by source format.
FRAME_CONVENTIONS: Dict[str, FrameConvention] = {
    "CETS": FrameConvention("floor", "floor"),
    "RELION": FrameConvention("floor", "floor"),
    "ARETOMO3": FrameConvention("half", "half"),
    "WARP": FrameConvention("half", "half"),
    "PORTAL": FrameConvention("half", "half"),
}


def rot_x(angle: float) -> np.ndarray:
    """Active right-handed rotation about x by ``angle`` degrees."""
    c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    return np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]])


def rot_y(angle: float) -> np.ndarray:
    """Active right-handed rotation about y by ``angle`` degrees."""
    c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])


def rot_z(angle: float) -> np.ndarray:
    """Active right-handed rotation about z by ``angle`` degrees."""
    c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def rotation(tilt_angle: float, x_tilt: float = 0.0, in_plane_rotation: float = 0.0) -> np.ndarray:
    """The rotation ``Rz(in_plane_rotation) @ Ry(tilt_angle) @ Rx(x_tilt)`` of a projection alignment."""
    return rot_z(in_plane_rotation) @ rot_y(tilt_angle) @ rot_x(x_tilt)


def _check_close(matrix: np.ndarray, expected: np.ndarray, what: str, tolerance: float) -> None:
    deviation = float(np.max(np.abs(np.asarray(matrix, dtype=float) - expected)))
    if deviation > tolerance:
        raise ValueError(f"{what} is not of the expected form (deviation {deviation:.3g}).")


def decompose_tilt(matrix: Sequence[Sequence[float]], tolerance: float = 1e-6) -> Tuple[float, float]:
    """Decompose ``Ry(tilt_angle) @ Rx(x_tilt)`` into its angles in degrees.

    Args:
        matrix: The 3x3 matrix.
        tolerance: Largest deviation of ``matrix`` from the recomposed one.

    Returns:
        ``(tilt_angle, x_tilt)``.

    Raises:
        ValueError: If ``matrix`` is not such a product.
    """
    m = np.asarray(matrix, dtype=float)
    if m.shape != (3, 3):
        raise ValueError(f"Expected a 3x3 matrix, got shape {m.shape}.")
    x_tilt = math.degrees(math.atan2(-m[1, 2], m[1, 1]))
    tilt_angle = math.degrees(math.atan2(-m[2, 0], m[0, 0]))
    _check_close(m, rot_y(tilt_angle) @ rot_x(x_tilt), "The tilt matrix", tolerance)
    # Adding 0.0 turns -0.0 into 0.0
    return tilt_angle + 0.0, x_tilt + 0.0


def decompose_in_plane(matrix: Sequence[Sequence[float]], tolerance: float = 1e-6) -> float:
    """The angle in degrees of a 2x2 rotation matrix ``[[cos, -sin], [sin, cos]]``.

    Raises:
        ValueError: If ``matrix`` is not a rotation.
    """
    m = np.asarray(matrix, dtype=float)
    if m.shape != (2, 2):
        raise ValueError(f"Expected a 2x2 matrix, got shape {m.shape}.")
    angle = math.degrees(math.atan2(m[1, 0], m[0, 0]))
    _check_close(m, rot_z(angle)[:2, :2], "The in-plane rotation", tolerance)
    return angle + 0.0


def center(size: Sequence[int], spacing: float, kind: CenterKind) -> np.ndarray:
    """Position in Angstrom, from the corner of sample 0, of the centre of an image or volume of ``size`` samples."""
    size = np.asarray(size, dtype=float)
    if kind == "half":
        return size / 2.0 * spacing
    if kind == "floor":
        return np.floor(size / 2.0) * spacing
    raise ValueError(f"Unknown centre convention {kind!r}.")


def image_delta(width: int, height: int, pixel_size: float, kind: CenterKind) -> np.ndarray:
    """Offset in Angstrom of an image centre in convention ``kind`` from its CETS centre."""
    return center((width, height), pixel_size, kind) - center((width, height), pixel_size, "floor")


def volume_delta(
    size: Sequence[int],
    voxel_size: float,
    kind: CenterKind,
    native_extent: Optional[Sequence[float]] = None,
) -> np.ndarray:
    """Offset in Angstrom of a volume centre in convention ``kind`` from the CETS centre of the reference volume.

    Args:
        size: Size of the reference volume in voxels.
        voxel_size: Voxel size of the reference volume in Angstrom.
        kind: Convention of the native centre.
        native_extent: Extent of the volume in the native tool in Angstrom; for ``half``, its centre is half of it.
            Default: ``size * voxel_size``.

    Returns:
        The offset ``(x, y, z)``.
    """
    if kind == "half" and native_extent is not None:
        native_center = np.asarray(native_extent, dtype=float) / 2.0
    else:
        native_center = center(size, voxel_size, kind)
    return native_center - center(size, voxel_size, "floor")


def native_to_cets_shift(
    shift: Sequence[float],
    matrix: np.ndarray,
    image_offset: Sequence[float],
    volume_offset: Sequence[float],
) -> np.ndarray:
    """Convert a shift in Angstrom from a native frame to the CETS frame.

    Args:
        shift: The native shift ``(x, y)``.
        matrix: The rotation ``R`` of the projection.
        image_offset: ``image_delta`` of the native frame.
        volume_offset: ``volume_delta`` of the native frame.

    Returns:
        The CETS shift ``(x, y)``.
    """
    return (
        np.asarray(shift, dtype=float)
        + np.asarray(image_offset, dtype=float)
        - (np.asarray(matrix) @ np.asarray(volume_offset, dtype=float))[:2]
    )


def cets_to_native_shift(
    shift: Sequence[float],
    matrix: np.ndarray,
    image_offset: Sequence[float],
    volume_offset: Sequence[float],
) -> np.ndarray:
    """Convert a shift in Angstrom from the CETS frame to a native frame (the inverse of ``native_to_cets_shift``)."""
    return (
        np.asarray(shift, dtype=float)
        - np.asarray(image_offset, dtype=float)
        + (np.asarray(matrix) @ np.asarray(volume_offset, dtype=float))[:2]
    )


def default_reference_size(native_extent: Sequence[float], voxel_size: float) -> Tuple[int, int, int]:
    """Size in voxels of the reference volume of an alignment computed for a volume of ``native_extent`` Angstrom."""
    return tuple(max(1, int(round(float(v) / voxel_size))) for v in native_extent)


def tomogram_to_reference(
    points: np.ndarray,
    tomogram_size: Sequence[int],
    tomogram_voxel_size: float,
    reference_size: Sequence[int],
    reference_voxel_size: float,
    volume_center: CenterKind,
    reference_native_extent: Optional[Sequence[float]] = None,
    reference_offset: Optional[Sequence[float]] = None,
) -> np.ndarray:
    """Express points of a tomogram in the CETS frame of an alignment's reference volume.

    Without ``reference_offset``, the tomogram is assumed to share the native rotation centre of the alignment: the
    centre, in the alignment's native convention, of the tomogram and of the reference volume coincide.

    Args:
        points: Points ``(n, 3)`` in Angstrom from the corner of voxel 0 of the tomogram (copick's pick coordinates).
        tomogram_size: Size of the tomogram in voxels ``(x, y, z)``.
        tomogram_voxel_size: Voxel size of the tomogram in Angstrom.
        reference_size: Size of the reference volume in voxels.
        reference_voxel_size: Voxel size of the reference volume in Angstrom.
        volume_center: Native volume centre convention of the alignment.
        reference_native_extent: Native extent of the reference volume in Angstrom.
        reference_offset: Explicit offset in Angstrom from the tomogram's CETS frame to the reference's CETS frame.

    Returns:
        The points ``(n, 3)`` in the reference's CETS frame.
    """
    points = np.atleast_2d(np.asarray(points, dtype=float))
    if reference_offset is not None:
        return points - center(tomogram_size, tomogram_voxel_size, "floor") + np.asarray(reference_offset, dtype=float)
    native = points - center(tomogram_size, tomogram_voxel_size, volume_center)
    return native + volume_delta(reference_size, reference_voxel_size, volume_center, reference_native_extent)


def project(points: np.ndarray, matrix: np.ndarray, shift: Sequence[float]) -> np.ndarray:
    """Project points ``(n, 3)`` of a volume onto a tilt image: ``drop_z(R @ p) + t`` for each point."""
    points = np.atleast_2d(np.asarray(points, dtype=float))
    return (points @ np.asarray(matrix).T)[:, :2] + np.asarray(shift, dtype=float)
