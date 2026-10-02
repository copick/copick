from typing import TYPE_CHECKING, Optional, Tuple, Union

import numpy as np
import zarr

from copick.util.ome import get_level_path

if TYPE_CHECKING:
    import pandas as pd

    from copick.models import CopickPicks


def normalize_transforms(picks: "CopickPicks", eps: float = 1e-8) -> np.ndarray:
    """
    Returns a normalized copy of transforms with bottom rows [0,0,0,1].
    Raises:
    - NotImplementedError if any bottom row has nonzero xyz (perspective terms)
    - ValueError if the homogeneous coordinate w is (approximately) 0
    """
    _, transforms = picks.numpy()
    if transforms.ndim != 3 or transforms.shape[-2:] != (4, 4):
        raise ValueError("Expected (N, 4, 4) array.")

    bottom = transforms[:, 3, :]
    xyz = bottom[:, :3]
    w = bottom[:, 3]

    perspective_mask = np.any(np.abs(xyz) > eps, axis=1)
    if np.any(perspective_mask):
        idx = np.where(perspective_mask)[0]
        raise NotImplementedError(f"Perspective terms present in bottom row for indices {idx.tolist()}.")

    w_bad_mask = np.abs(w) <= eps
    if np.any(w_bad_mask):
        idx = np.where(w_bad_mask)[0]
        raise ValueError(f"Invalid bottom row (w≈0) for indices {idx.tolist()}.")

    norm = transforms / w[:, None, None]
    return norm


def get_tomogram_spacing_and_dimensions(
    picks: "CopickPicks",
    only_voxel_size: bool = False,
) -> Tuple[float, Union[int, None], Union[int, None], Union[int, None]]:
    """
    Get tomogram voxel size and dimensions for the run these picks belong to.
    Returns a tuple of (voxel_size, tomogram_x, tomogram_y, tomogram_z).
    If only_voxel_size is True, only the voxel size will be returned (voxel_size, None, None, None).
    """
    from warnings import warn

    if only_voxel_size:
        if len(picks.run.voxel_spacings) == 0:
            raise ValueError("At least one voxel spacing must defined to import these particles from RELION.")
        elif len(picks.run.voxel_spacings) > 1:
            warn(
                "Multiple voxel spacings found, using the smallest one for converting the coordinates.",
                UserWarning,
                stacklevel=2,
            )
        return min(picks.run.voxel_spacings, key=lambda x: x.voxel_size).voxel_size, None, None, None

    vs_with_tomogram = [v for v in picks.run.voxel_spacings if v.tomograms]
    if len(vs_with_tomogram) == 0:
        raise ValueError(
            "At least one voxel spacing with a tomogram must be defined to import these particles from RELION.",
        )
    voxel_spacing = min(vs_with_tomogram, key=lambda x: x.voxel_size)
    if len(vs_with_tomogram) > 1:
        warn(
            f"Multiple voxel spacings with tomograms found, using the smallest ({voxel_spacing.voxel_size}) for converting the coordinates.",
            UserWarning,
            stacklevel=2,
        )
    tomogram = voxel_spacing.tomograms[0]
    if len(voxel_spacing.tomograms) > 1:
        warn(
            f"Multiple tomograms for voxel spacing {voxel_spacing.voxel_size} found, using ({tomogram.tomo_type}) for converting the coordinates.",
            UserWarning,
            stacklevel=2,
        )
    zarr_group = zarr.open(tomogram.zarr(), mode="r")
    tomogram_z, tomogram_y, tomogram_x = zarr_group[get_level_path(zarr_group, 0)].shape

    return voxel_spacing.voxel_size, tomogram_x, tomogram_y, tomogram_z


def relion_rows_to_poses(df: "pd.DataFrame") -> Tuple[np.ndarray, np.ndarray]:
    """Rotations and shifts of RELION tomography particles, in copick's convention.

    RELION composes a particle's orientation as ``A = A_subtomogram @ A_particle`` from ``rlnTomoSubtomogram{Rot,Tilt,
    Psi}`` and ``rlnAngle{Rot,Tilt,Psi}``, and places it at its coordinate minus ``A_subtomogram @ rlnOrigin{X,Y,Z}Angst``
    (RELION's ``ParticleSet::getMatrix3x3`` and ``getPosition``). Each Euler triple is converted with
    ``Rotation.from_euler("ZYZ", angles).inv()``, which equals RELION's Euler-angle matrix. Missing columns count as
    zero angles and zero shifts.

    Args:
        df: RELION particle table.

    Returns:
        Tuple of (rotations, offsets): (N, 3, 3) object-to-tomogram rotations, and (N, 3) shifts in Angstrom in the
        tomogram frame, to be subtracted from the particle coordinates.
    """
    from scipy.spatial.transform import Rotation

    n = len(df)

    sub_orientations = np.tile(np.eye(3), (n, 1, 1))
    if {"rlnTomoSubtomogramRot", "rlnTomoSubtomogramTilt", "rlnTomoSubtomogramPsi"}.issubset(df.columns):
        angles = df[["rlnTomoSubtomogramRot", "rlnTomoSubtomogramTilt", "rlnTomoSubtomogramPsi"]].to_numpy(dtype=float)
        sub_orientations = Rotation.from_euler("ZYZ", angles, degrees=True).inv().as_matrix().reshape(n, 3, 3)

    particle_orientations = np.tile(np.eye(3), (n, 1, 1))
    if {"rlnAngleRot", "rlnAngleTilt", "rlnAnglePsi"}.issubset(df.columns):
        angles = df[["rlnAngleRot", "rlnAngleTilt", "rlnAnglePsi"]].to_numpy(dtype=float)
        particle_orientations = Rotation.from_euler("ZYZ", angles, degrees=True).inv().as_matrix().reshape(n, 3, 3)

    origins = np.zeros((n, 3), dtype=float)
    if {"rlnOriginXAngst", "rlnOriginYAngst", "rlnOriginZAngst"}.issubset(df.columns):
        origins = df[["rlnOriginXAngst", "rlnOriginYAngst", "rlnOriginZAngst"]].to_numpy(dtype=float)

    rotations = np.einsum("nij,njk->nik", sub_orientations, particle_orientations)
    offsets = np.einsum("nij,nj->ni", sub_orientations, origins)
    return rotations, offsets


def copick_tomogram_center(
    picks: "CopickPicks",
    voxel_spacing: Optional[float] = None,
) -> Optional[Tuple[float, float, float]]:
    """Centre in Angstrom of the tomogram of the run these picks belong to (tomogram shape / 2 * voxel size).

    Uses a tomogram at ``voxel_spacing`` if the run has one there, else the tomogram at the smallest voxel spacing
    with a tomogram (as earlier copick versions did). Returns None if the run has no tomogram.
    """
    from copick.util.formats import get_tomogram_centers_from_copick

    run = picks.run
    if voxel_spacing is not None:
        centers = get_tomogram_centers_from_copick(run.root, [run.name], voxel_spacing)
        if run.name in centers:
            return centers[run.name]
    try:
        voxel_size, tomogram_x, tomogram_y, tomogram_z = get_tomogram_spacing_and_dimensions(picks)
    except ValueError:
        return None
    return (tomogram_x / 2 * voxel_size, tomogram_y / 2 * voxel_size, tomogram_z / 2 * voxel_size)


def _smallest_voxel_spacing(picks: "CopickPicks") -> Optional[float]:
    """The run's smallest voxel spacing, or None if it has none."""
    if not picks.run.voxel_spacings:
        return None
    return get_tomogram_spacing_and_dimensions(picks, only_voxel_size=True)[0]


def picks_to_df_relion(
    picks: "CopickPicks",
    *,
    voxel_spacing: Optional[float] = None,
    tilt_series_pixel_size: Optional[float] = None,
    tomogram_center: Optional[Tuple[float, float, float]] = None,
) -> "pd.DataFrame":
    """Returns the points as a pandas DataFrame with RELION columns.

    Columns are rlnTomoName, rlnAngleRot/Tilt/Psi and, following ``copick.util.formats.build_relion_particles_df``,
    rlnCenteredCoordinateX/Y/ZAngst whenever the tomogram centre is known and rlnCoordinateX/Y/Z in tilt-series pixels
    whenever ``tilt_series_pixel_size`` is given. Positions include the transforms' translations.

    Args:
        picks: The picks to convert.
        voxel_spacing: Voxel spacing whose tomogram defines the centre (see ``copick_tomogram_center``).
        tilt_series_pixel_size: Tilt-series pixel size in Angstrom; enables rlnCoordinateX/Y/Z.
        tomogram_center: Tomogram centre in Angstrom; overrides the copick tomogram.
    """
    from copick.util.formats import build_relion_particles_df

    points, _ = picks.numpy()
    transforms = normalize_transforms(picks)
    if tomogram_center is None:
        tomogram_center = copick_tomogram_center(picks, voxel_spacing)
    legacy_voxel_spacing = None
    if tomogram_center is None and tilt_series_pixel_size is None:
        legacy_voxel_spacing = voxel_spacing if voxel_spacing is not None else _smallest_voxel_spacing(picks)

    return build_relion_particles_df(
        points,
        transforms,
        tomo_name=picks.run.name,
        tomogram_center=tomogram_center,
        tilt_series_pixel_size=tilt_series_pixel_size,
        legacy_voxel_spacing=legacy_voxel_spacing,
    )


def relion_df_to_picks(
    picks: "CopickPicks",
    df: "pd.DataFrame",
    *,
    optics: Optional["pd.DataFrame"] = None,
    tilt_series_pixel_size: Optional[float] = None,
    tomogram_center: Optional[Tuple[float, float, float]] = None,
    relion_version: Optional[str] = None,
) -> None:
    """Set the points from a pandas DataFrame with RELION columns.

    Coordinates are resolved by ``copick.util.formats.relion_coordinates_to_angstrom`` (centred coordinates with the
    copick tomogram's centre first, then rlnCoordinateX/Y/Z in tilt-series pixels, then in pixels of the run's smallest
    voxel spacing), and orientations and shifts by ``relion_rows_to_poses``: each pick's location is its coordinate
    minus its shift, and its transform holds the rotation with zero translation.

    Args:
        picks: The picks to set.
        df: RELION particle table; every row belongs to this run.
        optics: The STAR file's optics table, for its tilt-series pixel size.
        tilt_series_pixel_size: Tilt-series pixel size in Angstrom, overriding the optics table.
        tomogram_center: Tomogram centre in Angstrom; overrides the copick tomogram.
        relion_version: Force centred ("relion5") or pixel ("relion4") coordinates.
    """
    from copick.util.formats import relion_coordinates_to_angstrom

    if not {"rlnCenteredCoordinateXAngst", "rlnCenteredCoordinateYAngst", "rlnCenteredCoordinateZAngst"}.issubset(
        df.columns,
    ) and not {"rlnCoordinateX", "rlnCoordinateY", "rlnCoordinateZ"}.issubset(df.columns):
        raise ValueError("DataFrame does not contain required RELION columns.")

    has_centered = {
        "rlnCenteredCoordinateXAngst",
        "rlnCenteredCoordinateYAngst",
        "rlnCenteredCoordinateZAngst",
    }.issubset(
        df.columns,
    )
    if tomogram_center is None and has_centered:
        tomogram_center = copick_tomogram_center(picks)

    coordinates = relion_coordinates_to_angstrom(
        df.drop(columns=["rlnTomoName"], errors="ignore"),
        voxel_spacing=_smallest_voxel_spacing(picks),
        tomogram_center=tomogram_center,
        tilt_series_pixel_size=tilt_series_pixel_size,
        optics=optics,
        relion_version=relion_version,
    )
    rotations, offsets = relion_rows_to_poses(df)

    transforms = np.zeros((len(df), 4, 4), dtype=float)
    transforms[:, :3, :3] = rotations
    transforms[:, 3, 3] = 1.0

    picks.from_numpy(coordinates - offsets, transforms)
