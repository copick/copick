from typing import TYPE_CHECKING, Tuple, Union

import numpy as np
import zarr

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
    tomogram_z, tomogram_y, tomogram_x = zarr.open(tomogram.zarr())["0"].shape

    return voxel_spacing.voxel_size, tomogram_x, tomogram_y, tomogram_z


def picks_to_df_relion(picks: "CopickPicks") -> "pd.DataFrame":
    """Returns the points as a pandas DataFrame with RELION columns:
    rlnCoordinateX, rlnCoordinateY, rlnCoordinateZ,
    rlnAngleRot, rlnAngleTilt, rlnAnglePsi,
    rlnCenteredCoordinateXAngst, rlnCenteredCoordinateYAngst, rlnCenteredCoordinateZAngst
    """
    import pandas as pd
    from scipy.spatial.transform import Rotation

    points, _ = picks.numpy()
    transforms = normalize_transforms(picks)
    translations = transforms[:, :3, 3]
    points += translations
    rots = transforms[:, :3, :3]
    eulers = np.zeros((rots.shape[0], 3))
    for i, Rmat in enumerate(rots):
        if np.allclose(Rmat, np.eye(3)):
            # handle identity rotation to prevent excessive scipy UserWarning
            eulers[i] = np.array([0.0, 0.0, 0.0])
        else:
            r = Rotation.from_matrix(Rmat)
            eulers[i] = r.inv().as_euler("ZYZ", degrees=True)
    voxel_size, tomogram_x, tomogram_y, tomogram_z = get_tomogram_spacing_and_dimensions(picks, only_voxel_size=False)
    points_px = points / voxel_size
    centered_points = points.copy()
    centered_points[:, 0] -= tomogram_x / 2 * voxel_size
    centered_points[:, 1] -= tomogram_y / 2 * voxel_size
    centered_points[:, 2] -= tomogram_z / 2 * voxel_size

    df = pd.DataFrame(
        {
            "rlnCoordinateX": points_px[:, 0],
            "rlnCoordinateY": points_px[:, 1],
            "rlnCoordinateZ": points_px[:, 2],
            "rlnAngleRot": eulers[:, 0],
            "rlnAngleTilt": eulers[:, 1],
            "rlnAnglePsi": eulers[:, 2],
            "rlnCenteredCoordinateXAngst": centered_points[:, 0],
            "rlnCenteredCoordinateYAngst": centered_points[:, 1],
            "rlnCenteredCoordinateZAngst": centered_points[:, 2],
        },
    )
    return df


def relion_df_to_picks(picks: "CopickPicks", df: "pd.DataFrame") -> None:
    """Set the points from a pandas DataFrame with RELION columns."""
    from scipy.spatial.transform import Rotation

    if not {"rlnCenteredCoordinateXAngst", "rlnCenteredCoordinateYAngst", "rlnCenteredCoordinateZAngst"}.issubset(
        df.columns,
    ) and not {"rlnCoordinateX", "rlnCoordinateY", "rlnCoordinateZ"}.issubset(df.columns):
        raise ValueError("DataFrame does not contain required RELION columns.")

    N = len(df)
    all_sub_orientations = np.zeros((N, 3, 3), dtype=float)
    aligned_offsets = np.zeros((N, 3), dtype=float)
    all_orientations = np.zeros((N, 3, 3), dtype=float)
    affine_combined_orientations = np.zeros((N, 4, 4), dtype=float)

    # Following RELION convention, offsets are oriented in the direction of the subtomogram orientation and subtracted from the point
    # and the aligned orientation is combined with the subtomogram orientation and converted to a 4x4 affine transformation matrix

    # First do the affine transformation matrix (holds the orientations)
    # Subtomogram orientations
    if {"rlnTomoSubtomogramRot", "rlnTomoSubtomogramTilt", "rlnTomoSubtomogramPsi"}.issubset(df.columns):
        angles = df[["rlnTomoSubtomogramRot", "rlnTomoSubtomogramTilt", "rlnTomoSubtomogramPsi"]].to_numpy()
        all_sub_orientations[:] = Rotation.from_euler("ZYZ", angles, degrees=True).inv().as_matrix()
    else:
        all_sub_orientations[:] = np.eye(3)

    # Refined particle orientations
    if {"rlnAngleRot", "rlnAngleTilt", "rlnAnglePsi"}.issubset(df.columns):
        angles = df[["rlnAngleRot", "rlnAngleTilt", "rlnAnglePsi"]].to_numpy()
        all_orientations[:] = Rotation.from_euler("ZYZ", angles, degrees=True).inv().as_matrix()
    else:
        all_orientations[:] = np.eye(3)

    combined_orientations = np.einsum("nij,njk->nik", all_orientations, all_sub_orientations)

    affine_combined_orientations[:, :3, :3] = combined_orientations
    affine_combined_orientations[:, 3, 3] = 1.0

    # Refined particle offsets
    if {"rlnOriginXAngst", "rlnOriginYAngst", "rlnOriginZAngst"}.issubset(df.columns):
        aligned_offsets = df[["rlnOriginXAngst", "rlnOriginYAngst", "rlnOriginZAngst"]].to_numpy()

    all_sub_oriented_aligned_offsets = np.einsum("nij,nj->ni", all_sub_orientations, aligned_offsets)

    # Convert coordinates to uncentered angstrom copick format
    # Use "rlnCoordinateX", "rlnCoordinateY, and rlnCoordinateZ" if possible because it doesn't require tomogram dimensions for converting to copick format
    if {"rlnCoordinateX", "rlnCoordinateY", "rlnCoordinateZ"}.issubset(df.columns):
        all_coords = df[["rlnCoordinateX", "rlnCoordinateY", "rlnCoordinateZ"]].to_numpy()
        voxel_size, _, _, _ = get_tomogram_spacing_and_dimensions(picks, only_voxel_size=True)
        all_coords *= voxel_size
    else:
        all_coords = df[
            ["rlnCenteredCoordinateXAngst", "rlnCenteredCoordinateYAngst", "rlnCenteredCoordinateZAngst"]
        ].to_numpy()
        voxel_size, tomogram_x, tomogram_y, tomogram_z = get_tomogram_spacing_and_dimensions(
            picks,
            only_voxel_size=False,
        )

        all_coords[:, 0] += tomogram_x / 2 * voxel_size
        all_coords[:, 1] += tomogram_y / 2 * voxel_size
        all_coords[:, 2] += tomogram_z / 2 * voxel_size

    corrected_all_coords = all_coords - all_sub_oriented_aligned_offsets

    picks.from_numpy(corrected_all_coords, affine_combined_orientations)
