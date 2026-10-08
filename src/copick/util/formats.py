"""Format-specific I/O utilities for import/export functionality.

This module provides utilities for reading and writing various file formats used in
cryo-ET data processing, including coordinate transformations between different
conventions.

Supported formats:
- EM files (TOM toolbox motivelists and volumes via emfile package)
- Dynamo tables (.tbl files via dynamotable package)
- STAR files (RELION particle files via starfile package)
- CSV files (copick-native format with full 4x4 matrices)
- TIFF stacks (via tifffile package)
"""

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

from copick.util.log import get_logger

if TYPE_CHECKING:
    import pandas as pd

    from copick.impl.filesystem import CopickRootFSSpec

logger = get_logger(__name__)


# =============================================================================
# Format Extension Detection
# =============================================================================


def get_picks_format_from_extension(path: str) -> Optional[str]:
    """Get the picks format name from a file extension.

    Args:
        path: The file path or name from which to extract the extension.

    Returns:
        The format name corresponding to the extension, or None if unknown.
    """
    formats = {
        "em": "em",
        "star": "star",
        "tbl": "dynamo",
        "csv": "csv",
    }
    ext = path.split(".")[-1].lower()
    return formats.get(ext)


def get_volume_format_from_extension(path: str) -> Optional[str]:
    """Get the volume format name from a file extension.

    Args:
        path: The file path or name from which to extract the extension.

    Returns:
        The format name corresponding to the extension, or None if unknown.
    """
    formats = {
        "mrc": "mrc",
        "zarr": "zarr",
        "map": "mrc",
        "tif": "tiff",
        "tiff": "tiff",
        "em": "em",
    }
    ext = path.split(".")[-1].lower()
    return formats.get(ext)


# =============================================================================
# Tomogram Index Mapping Utilities
# =============================================================================


def read_index_map(path: str) -> Dict[int, str]:
    """Read a tomogram index-to-run name mapping file.

    The file should be a CSV or TSV with two columns:
    - Column 1: Tomogram index (integer)
    - Column 2: Run name (string)

    The delimiter is auto-detected (comma or tab).

    Args:
        path: Path to the mapping file (CSV or TSV).

    Returns:
        Dictionary mapping tomogram index (int) to run name (str).

    Raises:
        ValueError: If file format is invalid or contains duplicate indices.
    """
    import pandas as pd

    # Try to auto-detect delimiter
    with open(path) as f:
        first_line = f.readline()

    delimiter = "\t" if "\t" in first_line else ","

    df = pd.read_csv(path, sep=delimiter, header=None, names=["index", "run_name"])

    if df.shape[1] < 2:
        raise ValueError(
            f"Index map file must have at least 2 columns (index, run_name), got {df.shape[1]} columns",
        )

    # Convert to dict (strip whitespace to handle Windows line endings)
    indices = df["index"].astype(int).tolist()
    run_names = df["run_name"].astype(str).str.strip().tolist()

    # Check for duplicates
    if len(indices) != len(set(indices)):
        duplicates = [i for i in set(indices) if indices.count(i) > 1]
        raise ValueError(f"Duplicate tomogram indices in mapping: {duplicates}")

    return dict(zip(indices, run_names, strict=True))


def read_index_map_inverse(path: str) -> Dict[str, int]:
    """Read a tomogram index map and return run_name to index mapping.

    This is the inverse of read_index_map() for export operations.
    Reads the same file format but returns the mapping in reverse:
    run_name -> tomogram_index.

    Args:
        path: Path to the mapping file (CSV or TSV).

    Returns:
        Dictionary mapping run_name (str) to tomogram index (int).

    Raises:
        ValueError: If file format is invalid or contains duplicate run names.
    """
    index_to_run = read_index_map(path)

    # Invert the mapping
    run_to_index = {run_name: index for index, run_name in index_to_run.items()}

    # Check for duplicate run names (would indicate data issue)
    if len(run_to_index) != len(index_to_run):
        # Find duplicates
        run_names = list(index_to_run.values())
        duplicates = [name for name in set(run_names) if run_names.count(name) > 1]
        raise ValueError(f"Duplicate run names in index map: {duplicates}")

    return run_to_index


def read_dynamo_tomolist(path: str) -> Dict[int, str]:
    """Read a Dynamo tomolist file and extract run names from MRC paths.

    Dynamo tomolists are whitespace-delimited files with two columns:
    - Column 1: Tomogram index (integer)
    - Column 2: Path to MRC/REC file

    Run names are extracted from the filenames (without extension).

    Args:
        path: Path to the Dynamo tomolist file.

    Returns:
        Dictionary mapping tomogram index (int) to run name (str).

    Raises:
        ValueError: If file format is invalid or contains duplicate indices.
    """
    import os

    import pandas as pd

    # Use regex whitespace splitting to handle both tab and space delimiters
    df = pd.read_csv(path, sep=r"\s+", header=None, names=["index", "mrc_path"])

    if df.shape[1] < 2:
        raise ValueError(
            f"Dynamo tomolist must have at least 2 columns (index, path), got {df.shape[1]} columns",
        )

    index_to_run = {}
    for _, row in df.iterrows():
        tomo_idx = int(row["index"])
        mrc_path = str(row["mrc_path"]).strip()  # Strip whitespace to handle Windows line endings

        # Extract filename without extension as run name
        basename = os.path.basename(mrc_path)
        # Handle both .mrc and .rec extensions
        if basename.endswith(".mrc") or basename.endswith(".rec"):
            run_name = basename[:-4]
        else:
            # Strip any extension
            run_name = os.path.splitext(basename)[0]

        if tomo_idx in index_to_run:
            raise ValueError(f"Duplicate tomogram index in tomolist: {tomo_idx}")

        index_to_run[tomo_idx] = run_name

    return index_to_run


# =============================================================================
# Coordinate Transformations
# =============================================================================


def euler_to_matrix(
    angles: np.ndarray,
    convention: str = "ZYZ",
    degrees: bool = True,
) -> np.ndarray:
    """Convert Euler angles to rotation matrices.

    Args:
        angles: Array of shape (N, 3) containing Euler angles.
        convention: Euler angle convention (e.g., "ZYZ", "ZXZ").
        degrees: Whether angles are in degrees (True) or radians (False).

    Returns:
        Array of shape (N, 3, 3) containing rotation matrices.
    """
    from scipy.spatial.transform import Rotation

    rotations = Rotation.from_euler(convention, angles, degrees=degrees)
    return rotations.as_matrix()


def matrix_to_euler(
    matrices: np.ndarray,
    convention: str = "ZYZ",
    degrees: bool = True,
) -> np.ndarray:
    """Convert rotation matrices to Euler angles.

    Args:
        matrices: Array of shape (N, 3, 3) containing rotation matrices.
        convention: Euler angle convention (e.g., "ZYZ", "ZXZ").
        degrees: Whether to return angles in degrees (True) or radians (False).

    Returns:
        Array of shape (N, 3) containing Euler angles.
    """
    from scipy.spatial.transform import Rotation

    N = matrices.shape[0]
    eulers = np.zeros((N, 3), dtype=float)

    for i, Rmat in enumerate(matrices):
        if np.allclose(Rmat, np.eye(3)):
            # Handle identity rotation
            eulers[i] = np.array([0.0, 0.0, 0.0])
        else:
            r = Rotation.from_matrix(Rmat)
            eulers[i] = r.as_euler(convention, degrees=degrees)

    return eulers


def transforms_to_points_and_rotations(
    transforms: np.ndarray,
    eps: float = 1e-8,
) -> Tuple[np.ndarray, np.ndarray]:
    """Extract translation vectors and rotation matrices from 4x4 transforms.

    Args:
        transforms: Array of shape (N, 4, 4) containing affine transforms.
        eps: Tolerance for checking valid transform structure.

    Returns:
        Tuple of (translations [N, 3], rotations [N, 3, 3]).

    Raises:
        ValueError: If transforms have invalid structure.
    """
    if transforms.ndim != 3 or transforms.shape[-2:] != (4, 4):
        raise ValueError("Expected (N, 4, 4) array.")

    # Normalize by bottom-right element if needed
    bottom = transforms[:, 3, :]
    w = bottom[:, 3]

    w_bad_mask = np.abs(w) <= eps
    if np.any(w_bad_mask):
        idx = np.where(w_bad_mask)[0]
        raise ValueError(f"Invalid transform (w≈0) for indices {idx.tolist()}.")

    norm = transforms / w[:, None, None]

    translations = norm[:, :3, 3]
    rotations = norm[:, :3, :3]

    return translations, rotations


def points_and_rotations_to_transforms(
    points: np.ndarray,
    rotations: np.ndarray,
) -> np.ndarray:
    """Create 4x4 affine transforms from points and rotation matrices.

    Args:
        points: Array of shape (N, 3) containing translation vectors.
        rotations: Array of shape (N, 3, 3) containing rotation matrices.

    Returns:
        Array of shape (N, 4, 4) containing affine transforms.
    """
    N = points.shape[0]
    transforms = np.zeros((N, 4, 4), dtype=float)
    transforms[:, :3, :3] = rotations
    transforms[:, :3, 3] = points
    transforms[:, 3, 3] = 1.0
    return transforms


# =============================================================================
# Dynamo Format Utilities
# =============================================================================


def read_dynamo_table(
    path: str,
    include_tomo_index: bool = False,
) -> Union[
    Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray],
    Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray],
]:
    """Read a Dynamo table file.

    Dynamo uses ZXZ intrinsic Euler convention with coordinates in pixels
    (corner-origin). Shifts are stored separately from coordinates.

    Args:
        path: Path to the .tbl file.
        include_tomo_index: If True, also return the tomogram index column.

    Returns:
        If include_tomo_index=False: Tuple of (positions [N, 3] in pixels,
            eulers [N, 3] in degrees, shifts [N, 3] in pixels, scores [N]).
        If include_tomo_index=True: Same as above plus tomo_indices [N] as integers.
    """
    import dynamotable

    df = dynamotable.read(path)

    # Coordinates (columns 24, 25, 26 are x, y, z)
    positions = df[["x", "y", "z"]].to_numpy()

    # Euler angles (columns 7, 8, 9 are tdrot, tilt, narot - ZXZ convention)
    eulers = df[["tdrot", "tilt", "narot"]].to_numpy()

    # Shifts (columns 4, 5, 6 are dx, dy, dz)
    shifts = df[["dx", "dy", "dz"]].to_numpy()

    # Cross-correlation score (column 10)
    scores = df["cc"].to_numpy() if "cc" in df.columns else np.ones(len(df))

    if include_tomo_index:
        # Tomogram index (column 2 - "tomo")
        tomo_indices = df["tomo"].to_numpy().astype(int)
        return positions, eulers, shifts, scores, tomo_indices

    return positions, eulers, shifts, scores


def write_dynamo_table(
    path: str,
    positions: np.ndarray,
    eulers: np.ndarray,
    shifts: Optional[np.ndarray] = None,
    scores: Optional[np.ndarray] = None,
    tomogram_index: int = 1,
) -> None:
    """Write a Dynamo table file.

    Args:
        path: Output path for the .tbl file.
        positions: Array of shape (N, 3) with coordinates in pixels.
        eulers: Array of shape (N, 3) with ZXZ Euler angles in degrees.
        shifts: Optional array of shape (N, 3) with shifts in pixels.
        scores: Optional array of shape (N,) with scores.
        tomogram_index: Tomogram index for all particles.
    """
    import dynamotable
    import pandas as pd

    N = positions.shape[0]

    if shifts is None:
        shifts = np.zeros((N, 3))
    if scores is None:
        scores = np.ones(N)

    # Create DataFrame with standard Dynamo columns
    df = pd.DataFrame(
        {
            "tag": np.arange(1, N + 1),
            "aligned": np.ones(N, dtype=int),
            "averaged": np.ones(N, dtype=int),
            "dx": shifts[:, 0],
            "dy": shifts[:, 1],
            "dz": shifts[:, 2],
            "tdrot": eulers[:, 0],
            "tilt": eulers[:, 1],
            "narot": eulers[:, 2],
            "cc": scores,
            "x": positions[:, 0],
            "y": positions[:, 1],
            "z": positions[:, 2],
            "tomo": np.full(N, tomogram_index, dtype=int),
        },
    )

    dynamotable.write(df, path)


def read_dynamo_table_grouped(
    path: str,
    voxel_spacing: float,
    index_to_run: Dict[int, str],
) -> Dict[str, Tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]]:
    """Read a Dynamo table and group particles by tomogram index.

    Reads a Dynamo .tbl file that contains particles from multiple tomograms,
    identified by the 'tomo' column. Groups particles by run name using
    the provided index-to-run mapping.

    Args:
        path: Path to the .tbl file.
        voxel_spacing: Voxel spacing in Angstrom for coordinate conversion.
        index_to_run: Mapping from tomogram index (int) to run name (str).

    Returns:
        Dictionary mapping run_name to (positions_angstrom, transforms_4x4, scores).
        Only includes runs that are present in index_to_run mapping.
    """
    # Read with tomogram indices
    positions_px, eulers_deg, shifts_px, scores, tomo_indices = read_dynamo_table(
        path,
        include_tomo_index=True,
    )

    # Group by tomogram index
    grouped = {}
    unique_indices = np.unique(tomo_indices)

    for tomo_idx in unique_indices:
        if tomo_idx not in index_to_run:
            # Skip particles from unknown tomograms
            continue

        run_name = index_to_run[tomo_idx]
        mask = tomo_indices == tomo_idx

        # Extract particles for this tomogram
        positions_px_group = positions_px[mask]
        eulers_deg_group = eulers_deg[mask]
        shifts_px_group = shifts_px[mask]
        scores_group = scores[mask]

        # Convert to copick format (Angstrom coordinates, 4x4 transforms)
        positions_angstrom, transforms = dynamo_to_copick_transform(
            positions_px_group,
            eulers_deg_group,
            shifts_px_group,
            voxel_spacing,
        )

        grouped[run_name] = (positions_angstrom, transforms, scores_group)

    return grouped


def write_dynamo_table_grouped(
    path: str,
    grouped_data: Dict[str, Tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]],
    voxel_spacing: float,
    run_to_index: Dict[str, int],
) -> None:
    """Write a combined Dynamo table from multiple runs.

    Args:
        path: Output path for the .tbl file.
        grouped_data: Dict mapping run_name to (positions_angstrom, transforms_4x4, scores).
        voxel_spacing: Voxel spacing in Angstrom for coordinate conversion.
        run_to_index: Mapping from run name to tomogram index.

    Raises:
        ValueError: If run_to_index is missing entries for any run.
    """
    import dynamotable
    import pandas as pd

    all_dfs = []
    tag_offset = 0

    for run_name, (positions, transforms, scores) in grouped_data.items():
        if run_name not in run_to_index:
            raise ValueError(f"Run '{run_name}' not found in run_to_index mapping")

        tomogram_index = run_to_index[run_name]

        # Convert from Angstrom to pixels and extract Euler angles
        positions_px, eulers_deg, shifts_px = copick_to_dynamo_transform(
            positions,
            transforms,
            voxel_spacing,
        )

        N = positions_px.shape[0]
        if scores is None:
            scores = np.ones(N)

        # Create DataFrame with standard Dynamo columns
        df = pd.DataFrame(
            {
                "tag": np.arange(tag_offset + 1, tag_offset + N + 1),
                "aligned": np.ones(N, dtype=int),
                "averaged": np.ones(N, dtype=int),
                "dx": shifts_px[:, 0],
                "dy": shifts_px[:, 1],
                "dz": shifts_px[:, 2],
                "tdrot": eulers_deg[:, 0],
                "tilt": eulers_deg[:, 1],
                "narot": eulers_deg[:, 2],
                "cc": scores,
                "x": positions_px[:, 0],
                "y": positions_px[:, 1],
                "z": positions_px[:, 2],
                "tomo": np.full(N, tomogram_index, dtype=int),
            },
        )
        all_dfs.append(df)
        tag_offset += N

    combined_df = pd.concat(all_dfs, ignore_index=True)
    dynamotable.write(combined_df, path)


def dynamo_to_copick_transform(
    positions_px: np.ndarray,
    eulers_deg: np.ndarray,
    shifts_px: np.ndarray,
    voxel_size: float,
) -> Tuple[np.ndarray, np.ndarray]:
    """Convert Dynamo coordinates to copick format.

    Dynamo uses:
    - ZXZ Euler convention (intrinsic, passive)
    - Coordinates in pixels (corner-origin)
    - Separate shifts from coordinates

    Copick uses:
    - 4x4 affine matrices
    - Coordinates in Angstrom (corner-origin)
    - Shifts encoded in the matrix translation

    The conversion uses intrinsic zxz with inversion to match the canonical
    Dynamo → RELION → copick conversion path (verified via eulerangles library).

    Args:
        positions_px: Coordinates in pixels [N, 3].
        eulers_deg: ZXZ Euler angles in degrees [N, 3] as (tdrot, tilt, narot).
        shifts_px: Shifts in pixels [N, 3].
        voxel_size: Voxel size in Angstrom.

    Returns:
        Tuple of (points_angstrom [N, 3], transforms [N, 4, 4]).
    """
    from scipy.spatial.transform import Rotation

    # Convert coordinates to Angstrom
    points_angstrom = positions_px * voxel_size

    # Convert Euler angles to rotation matrices
    # Use intrinsic zxz (lowercase) with inversion to match RELION convention
    rotations = Rotation.from_euler("zxz", eulers_deg, degrees=True).inv().as_matrix()

    # Convert shifts to Angstrom and apply to transform
    shifts_angstrom = shifts_px * voxel_size

    # Create transforms with rotations and shifts
    transforms = points_and_rotations_to_transforms(shifts_angstrom, rotations)

    return points_angstrom, transforms


def copick_to_dynamo_transform(
    points_angstrom: np.ndarray,
    transforms: np.ndarray,
    voxel_size: float,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Convert copick format to Dynamo coordinates.

    This is the inverse of dynamo_to_copick_transform.

    Args:
        points_angstrom: Coordinates in Angstrom [N, 3].
        transforms: 4x4 affine matrices [N, 4, 4].
        voxel_size: Voxel size in Angstrom.

    Returns:
        Tuple of (positions_px [N, 3], eulers_deg [N, 3], shifts_px [N, 3]).
    """
    from scipy.spatial.transform import Rotation

    # Extract translations and rotations from transforms
    translations, rotations = transforms_to_points_and_rotations(transforms)

    # Convert to pixel coordinates
    positions_px = points_angstrom / voxel_size
    shifts_px = translations / voxel_size

    # Convert rotation matrices to ZXZ Euler angles
    # Use intrinsic zxz with inversion (inverse of import conversion)
    N = rotations.shape[0]
    eulers_deg = np.zeros((N, 3), dtype=float)
    for i, Rmat in enumerate(rotations):
        if np.allclose(Rmat, np.eye(3)):
            eulers_deg[i] = np.array([0.0, 0.0, 0.0])
        else:
            r = Rotation.from_matrix(Rmat)
            eulers_deg[i] = r.inv().as_euler("zxz", degrees=True)

    return positions_px, eulers_deg, shifts_px


# =============================================================================
# EM Format Utilities (TOM Toolbox)
# =============================================================================


def read_em_motivelist(
    path: str,
    include_tomo_index: bool = False,
    tomo_index_row: int = 4,
    include_shifts: bool = False,
) -> Tuple[np.ndarray, ...]:
    """Read a TOM toolbox EM motivelist.

    TOM motivelists store particle positions and angles in an array where:
    - Row 0-2: Cross-correlation peak position (unused)
    - Row 3: Score/CCC
    - Row 4: Tomogram index (default location, configurable via tomo_index_row)
    - Row 5: Particle class
    - Row 6: Subtomogram index
    - Row 7-9: Position (x, y, z) in pixels (1-indexed, center-origin convention)
    - Row 10-12: Shifts (dx, dy, dz) in pixels
    - Row 16: Phi (first Z rotation)
    - Row 17: Psi (third Z rotation)
    - Row 18: Theta (second X rotation)

    Note: Euler angles are stored as [phi, psi, theta] in rows 16-18, but the
    ZXZ rotation order is phi-theta-psi. This follows the Artiatomi/ArtiaX convention.

    Note: TOM uses 1-indexed coordinates. This function converts to 0-indexed.

    Args:
        path: Path to the EM file.
        include_tomo_index: If True, also return the tomogram indices.
        tomo_index_row: Row index (0-based) containing tomogram indices (default: 4).
        include_shifts: If True, also return the shifts (rows 10-12) in pixels.

    Returns:
        Tuple of (positions [N, 3] in pixels 0-indexed, eulers [N, 3] in degrees as [phi, theta, psi], scores [N]),
        followed by tomo_indices [N] (integers) if ``include_tomo_index`` and then shifts [N, 3] in pixels if
        ``include_shifts``.
    """
    import emfile

    _header, data = emfile.read(path)

    # Squeeze any leading singleton dimensions
    data = np.squeeze(data)

    # EM files can have different shapes
    # Expected: (20, N) where 20 is rows and N is particles
    # Some files have (N, 20) which needs transposing
    if data.ndim == 1:
        data = data.reshape(-1, 1)
    elif data.ndim == 2:
        # If shape is (N, 20) instead of (20, N), transpose it
        if data.shape[1] == 20 and data.shape[0] != 20:
            data = data.T
        elif data.shape[0] != 20 and data.shape[1] != 20:
            raise ValueError(f"EM motivelist has unexpected shape: {data.shape}, expected (20, N) or (N, 20)")
    else:
        raise ValueError(f"EM motivelist has unexpected shape: {data.shape}")

    if data.shape[0] < 19:
        raise ValueError(f"EM motivelist has unexpected shape: {data.shape}, need at least 19 rows")

    # Positions (rows 7-9, 0-indexed in array)
    # TOM uses 1-indexed coordinates, so subtract 1 to convert to 0-indexed
    positions = data[7:10, :].T - 1  # Shape: (N, 3), now 0-indexed

    # Euler angles: stored as [phi, psi, theta] in rows [16, 17, 18]
    # but ZXZ rotation order is phi-theta-psi, so reorder to [phi, theta, psi]
    # Row 16 = phi, Row 17 = psi, Row 18 = theta
    phi = data[16, :]
    psi = data[17, :]
    theta = data[18, :]
    eulers = np.column_stack([phi, theta, psi])  # Shape: (N, 3) as [phi, theta, psi]

    # Scores (row 3)
    scores = data[3, :]

    if include_tomo_index:
        if tomo_index_row >= data.shape[0]:
            raise ValueError(
                f"tomo_index_row={tomo_index_row} exceeds data shape {data.shape}",
            )
        tomo_indices = data[tomo_index_row, :].astype(int)
        result = (positions, eulers, scores, tomo_indices)
    else:
        result = (positions, eulers, scores)

    if include_shifts:
        result = result + (data[10:13, :].T,)

    return result


def write_em_motivelist(
    path: str,
    positions: np.ndarray,
    eulers: np.ndarray,
    scores: Optional[np.ndarray] = None,
    tomogram_index: int = 1,
    shifts: Optional[np.ndarray] = None,
) -> None:
    """Write a TOM toolbox EM motivelist.

    TOM toolbox uses MATLAB/Fortran ordering, so the output shape is (1, N, 20)
    where N is the number of particles and 20 is the number of data fields.

    Euler angles are expected as [phi, theta, psi] (ZXZ rotation order) but are
    stored as [phi, psi, theta] in columns [16, 17, 18] per Artiatomi convention.

    Note: TOM uses 1-indexed coordinates. This function converts from 0-indexed input.

    Args:
        path: Output path for the EM file.
        positions: Array of shape (N, 3) with coordinates in pixels (0-indexed, center-origin).
        eulers: Array of shape (N, 3) with Euler angles in degrees as [phi, theta, psi].
        scores: Optional array of shape (N,) with scores.
        tomogram_index: Tomogram index for all particles.
        shifts: Optional array of shape (N, 3) with shifts in pixels (rows 10-12); zero if None.
    """
    import emfile

    N = positions.shape[0]

    if scores is None:
        scores = np.ones(N)

    # Create standard TOM motivelist structure
    # Shape: (1, N, 20) for MATLAB/Fortran compatibility
    data = np.zeros((1, N, 20), dtype=np.float32)

    # Cross-correlation peak position (columns 0-2) - typically zero
    data[0, :, 0:3] = 0.0

    # Score (column 3)
    data[0, :, 3] = scores

    # Tomogram index (column 4)
    data[0, :, 4] = tomogram_index

    # Class (column 5) - default to 1
    data[0, :, 5] = 1

    # Particle index (column 6)
    data[0, :, 6] = np.arange(1, N + 1)

    # Positions (columns 7-9)
    # Convert from 0-indexed to 1-indexed by adding 1
    data[0, :, 7:10] = positions + 1

    # Shifts (columns 10-12), in pixels
    data[0, :, 10:13] = 0.0 if shifts is None else shifts

    # Euler angles: input is [phi, theta, psi] but stored as [phi, psi, theta]
    # Column 16 = phi, Column 17 = psi, Column 18 = theta
    data[0, :, 16] = eulers[:, 0]  # phi
    data[0, :, 17] = eulers[:, 2]  # psi (3rd rotation, stored in column 17)
    data[0, :, 18] = eulers[:, 1]  # theta (2nd rotation, stored in column 18)

    emfile.write(path, data)


def read_em_motivelist_grouped(
    path: str,
    voxel_spacing: float,
    index_to_run: Dict[int, str],
    tomo_index_row: int = 4,
) -> Dict[str, Tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]]:
    """Read a TOM toolbox EM motivelist and group particles by tomogram index.

    Reads an EM motivelist file that contains particles from multiple tomograms,
    identified by the tomogram index column. Groups particles by run name using
    the provided index-to-run mapping.

    Args:
        path: Path to the EM file.
        voxel_spacing: Voxel spacing in Angstrom for coordinate conversion.
        index_to_run: Mapping from tomogram index (int) to run name (str).
        tomo_index_row: Row index (0-based) containing tomogram indices (default: 4).

    Returns:
        Dictionary mapping run_name to (positions_angstrom, transforms_4x4, scores).
        Only includes runs that are present in index_to_run mapping.
    """
    # Read with tomogram indices
    positions_px, eulers_deg, scores, tomo_indices, shifts_px = read_em_motivelist(
        path,
        include_tomo_index=True,
        tomo_index_row=tomo_index_row,
        include_shifts=True,
    )

    # Group by tomogram index
    grouped = {}
    unique_indices = np.unique(tomo_indices)

    for tomo_idx in unique_indices:
        if tomo_idx not in index_to_run:
            # Skip particles from unknown tomograms
            continue

        run_name = index_to_run[tomo_idx]
        mask = tomo_indices == tomo_idx

        # Extract particles for this tomogram
        positions_px_group = positions_px[mask]
        eulers_deg_group = eulers_deg[mask]
        scores_group = scores[mask]

        # Convert to copick format (Angstrom coordinates, 4x4 transforms)
        positions_angstrom, transforms = em_to_copick_transform(
            positions_px_group,
            eulers_deg_group,
            voxel_spacing,
            shifts_px=shifts_px[mask],
        )

        grouped[run_name] = (positions_angstrom, transforms, scores_group)

    return grouped


def write_em_motivelist_grouped(
    path: str,
    grouped_data: Dict[str, Tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]],
    voxel_spacing: float,
    run_to_index: Dict[str, int],
) -> None:
    """Write a combined TOM toolbox EM motivelist from multiple runs.

    Args:
        path: Output path for the EM file.
        grouped_data: Dict mapping run_name to (positions_angstrom, transforms_4x4, scores).
        voxel_spacing: Voxel spacing in Angstrom for coordinate conversion.
        run_to_index: Mapping from run name to tomogram index.

    Raises:
        ValueError: If run_to_index is missing entries for any run.
    """
    import emfile

    all_positions = []
    all_eulers = []
    all_shifts = []
    all_scores = []
    all_tomo_indices = []

    for run_name, (positions, transforms, scores) in grouped_data.items():
        if run_name not in run_to_index:
            raise ValueError(f"Run '{run_name}' not found in run_to_index mapping")

        tomogram_index = run_to_index[run_name]

        # Convert from copick format to EM format
        positions_px, eulers_deg, shifts_px = copick_to_em_transform(
            positions,
            transforms,
            voxel_spacing,
            return_shifts=True,
        )

        N = positions_px.shape[0]
        if scores is None:
            scores = np.ones(N)

        all_positions.append(positions_px)
        all_eulers.append(eulers_deg)
        all_shifts.append(shifts_px)
        all_scores.append(scores)
        all_tomo_indices.append(np.full(N, tomogram_index))

    # Concatenate all data
    positions_combined = np.vstack(all_positions)
    eulers_combined = np.vstack(all_eulers)
    shifts_combined = np.vstack(all_shifts)
    scores_combined = np.concatenate(all_scores)
    tomo_indices_combined = np.concatenate(all_tomo_indices)

    N = positions_combined.shape[0]

    # Create standard TOM motivelist structure
    # Shape: (1, N, 20) for MATLAB/Fortran compatibility
    data = np.zeros((1, N, 20), dtype=np.float32)

    # Cross-correlation peak position (columns 0-2) - typically zero
    data[0, :, 0:3] = 0.0

    # Score (column 3)
    data[0, :, 3] = scores_combined

    # Tomogram index (column 4)
    data[0, :, 4] = tomo_indices_combined

    # Class (column 5) - default to 1
    data[0, :, 5] = 1

    # Particle index (column 6)
    data[0, :, 6] = np.arange(1, N + 1)

    # Positions (columns 7-9)
    # Convert from 0-indexed to 1-indexed by adding 1
    data[0, :, 7:10] = positions_combined + 1

    # Shifts (columns 10-12), in pixels
    data[0, :, 10:13] = shifts_combined

    # Euler angles: input is [phi, theta, psi] but stored as [phi, psi, theta]
    # Column 16 = phi, Column 17 = psi, Column 18 = theta
    data[0, :, 16] = eulers_combined[:, 0]  # phi
    data[0, :, 17] = eulers_combined[:, 2]  # psi (3rd rotation, stored in column 17)
    data[0, :, 18] = eulers_combined[:, 1]  # theta (2nd rotation, stored in column 18)

    emfile.write(path, data)


def read_em_volume(path: str) -> np.ndarray:
    """Read a TOM toolbox EM volume file.

    Args:
        path: Path to the EM file.

    Returns:
        3D numpy array with volume data.
    """
    import emfile

    _header, data = emfile.read(path)
    return data


def write_em_volume(path: str, volume: np.ndarray, dtype: np.dtype = np.float32) -> None:
    """Write a TOM toolbox EM volume file.

    Args:
        path: Output path for the EM file.
        volume: 3D numpy array with volume data.
        dtype: Data type written to the file. EM supports int8, int16, int32 and float32.
    """
    import emfile

    data = volume.astype(dtype)
    if data.dtype.kind == "i" and data.dtype.itemsize == 4:
        # emfile looks types up by character code and knows int32 only as "i" (C int); Windows spells it "l".
        data = data.view(np.intc)
    emfile.write(path, data)


def em_to_copick_transform(
    positions_px: np.ndarray,
    eulers_deg: np.ndarray,
    voxel_size: float,
    shifts_px: Optional[np.ndarray] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """Convert TOM/EM coordinates to copick format.

    TOM toolbox uses:
    - Corner-origin coordinates in pixels (already 0-indexed after read_em_motivelist)
    - ZXZ intrinsic Euler convention (Artiatomi/ArtiaX convention)

    Copick uses:
    - Corner-origin coordinates in Angstrom
    - 4x4 affine matrices

    Args:
        positions_px: Coordinates in pixels (0-indexed, corner-origin) [N, 3].
        eulers_deg: ZXZ Euler angles in degrees [N, 3] as [phi, theta, psi].
        voxel_size: Voxel size in Angstrom.
        shifts_px: Optional shifts in pixels [N, 3] (motivelist rows 10-12). They become the transform translation,
            so that the particle centre is ``location + translation``.

    Returns:
        Tuple of (points_angstrom [N, 3], transforms [N, 4, 4]).
    """
    from scipy.spatial.transform import Rotation

    # Convert to Angstrom (coordinates are already corner-origin)
    points_angstrom = positions_px * voxel_size

    # Convert Euler angles to rotation matrices
    # Use intrinsic zxz (lowercase) as per Artiatomi/ArtiaX convention
    rotations = Rotation.from_euler("zxz", eulers_deg, degrees=True).as_matrix()

    # Rotations, with the motivelist shifts (if any) as the translation
    N = positions_px.shape[0]
    transforms = np.zeros((N, 4, 4), dtype=float)
    transforms[:, :3, :3] = rotations
    transforms[:, 3, 3] = 1.0
    if shifts_px is not None:
        transforms[:, :3, 3] = np.asarray(shifts_px, dtype=float) * voxel_size

    return points_angstrom, transforms


def copick_to_em_transform(
    points_angstrom: np.ndarray,
    transforms: np.ndarray,
    voxel_size: float,
    return_shifts: bool = False,
) -> Tuple[np.ndarray, ...]:
    """Convert copick format to TOM/EM coordinates.

    This is the inverse of em_to_copick_transform.

    Args:
        points_angstrom: Coordinates in Angstrom (corner-origin) [N, 3].
        transforms: 4x4 affine matrices [N, 4, 4].
        voxel_size: Voxel size in Angstrom.
        return_shifts: Also return the transform translations as shifts in pixels (motivelist rows 10-12).

    Returns:
        Tuple of (positions_px [N, 3] corner-origin 0-indexed, eulers_deg [N, 3] as [phi, theta, psi]), followed by
        shifts_px [N, 3] if ``return_shifts``.
    """
    from scipy.spatial.transform import Rotation

    # Extract rotations and translations from transforms
    translations, rotations = transforms_to_points_and_rotations(transforms)

    # Convert to pixel coordinates (corner-origin, 0-indexed)
    positions_px = points_angstrom / voxel_size

    # Convert rotation matrices to ZXZ Euler angles
    # Use intrinsic zxz as per Artiatomi/ArtiaX convention
    N = rotations.shape[0]
    eulers_deg = np.zeros((N, 3), dtype=float)
    for i, Rmat in enumerate(rotations):
        if np.allclose(Rmat, np.eye(3)):
            eulers_deg[i] = np.array([0.0, 0.0, 0.0])
        else:
            r = Rotation.from_matrix(Rmat)
            eulers_deg[i] = r.as_euler("zxz", degrees=True)

    if return_shifts:
        return positions_px, eulers_deg, translations / voxel_size
    return positions_px, eulers_deg


# =============================================================================
# STAR File Utilities
# =============================================================================


def read_star_particles_with_optics(path: str) -> Tuple["pd.DataFrame", Optional["pd.DataFrame"]]:
    """Read the particle table of a RELION STAR file and, if present, its optics table.

    Args:
        path: Path to the STAR file.

    Returns:
        Tuple of (particles DataFrame, optics DataFrame or None).
    """
    import starfile

    data = starfile.read(path)

    # starfile returns either a dict (if multiple blocks) or a DataFrame
    if isinstance(data, dict):
        optics = data.get("optics")
        # Look for particles block
        if "particles" in data:
            return data["particles"], optics
        # Fall back to first non-optics block
        for key, value in data.items():
            if key != "optics":
                return value, optics
        raise ValueError("No particle data found in STAR file")

    return data, None


def read_star_particles(path: str) -> "pd.DataFrame":
    """Read a RELION STAR file.

    Args:
        path: Path to the STAR file.

    Returns:
        DataFrame with particle data.
    """
    return read_star_particles_with_optics(path)[0]


def read_star_particles_grouped(path: str) -> Dict[str, "pd.DataFrame"]:
    """Read a RELION STAR file and group particles by tomogram name.

    Reads a RELION particles STAR file and groups the particles by the
    _rlnTomoName column, which identifies which tomogram each particle
    belongs to.

    Args:
        path: Path to the STAR file.

    Returns:
        Dictionary mapping run_name (from rlnTomoName) to DataFrame of particles.

    Raises:
        ValueError: If the STAR file does not contain the rlnTomoName column.
    """
    return group_star_particles_by_tomogram(read_star_particles(path))


def group_star_particles_by_tomogram(df: "pd.DataFrame") -> Dict[str, "pd.DataFrame"]:
    """Group a RELION particle table by its ``rlnTomoName`` column, keeping each tomogram's row order.

    Args:
        df: DataFrame with particle data.

    Returns:
        Dictionary mapping run_name (from rlnTomoName) to DataFrame of particles.

    Raises:
        ValueError: If the table does not contain the rlnTomoName column.
    """
    # Validate that rlnTomoName column exists
    if "rlnTomoName" not in df.columns:
        raise ValueError(
            "STAR file does not contain rlnTomoName column. "
            "Cannot group particles by tomogram. "
            "Use the single-file 'picks' command instead.",
        )

    # Group by tomogram name
    grouped = {}
    for tomo_name, group_df in df.groupby("rlnTomoName"):
        # Reset index for each group
        grouped[str(tomo_name)] = group_df.reset_index(drop=True)

    return grouped


def detect_relion_version(df: "pd.DataFrame") -> str:
    """Auto-detect RELION version from STAR file columns.

    Determines whether a STAR file uses RELION 4.x pixel coordinates
    or RELION 5.0 centered Angstrom coordinates by checking column names.

    Args:
        df: DataFrame with particle data from a STAR file.

    Returns:
        "relion4" if pixel coordinates found (rlnCoordinateX/Y/Z)
        "relion5" if centered Angstrom coordinates found (rlnCenteredCoordinateXAngst/YAngst/ZAngst)

    Raises:
        ValueError: If neither coordinate format is detected.
    """
    relion4_cols = {"rlnCoordinateX", "rlnCoordinateY", "rlnCoordinateZ"}
    relion5_cols = {"rlnCenteredCoordinateXAngst", "rlnCenteredCoordinateYAngst", "rlnCenteredCoordinateZAngst"}

    if relion5_cols.issubset(df.columns):
        return "relion5"
    elif relion4_cols.issubset(df.columns):
        return "relion4"
    else:
        raise ValueError(
            "Cannot detect RELION version. STAR file must contain either:\n"
            "  - rlnCoordinateX/Y/Z (RELION 4.x pixel coordinates), or\n"
            "  - rlnCenteredCoordinateXAngst/YAngst/ZAngst (RELION 5.0 centered coordinates)",
        )


@dataclass
class RelionTomogram:
    """Geometry and optics of one tomogram, read from a RELION tomograms.star file.

    Attributes:
        name: The tomogram's ``rlnTomoName``.
        center_angstrom: Centre of the tomogram in Angstrom, ``rlnTomoSize{X,Y,Z} / 2 * rlnTomoTiltSeriesPixelSize``.
        tilt_series_pixel_size: ``rlnTomoTiltSeriesPixelSize`` in Angstrom: the unit of ``rlnCoordinate{X,Y,Z}``.
        voltage: ``rlnVoltage`` in kV, if present.
        spherical_aberration: ``rlnSphericalAberration`` in mm, if present.
        amplitude_contrast: ``rlnAmplitudeContrast``, if present.
    """

    name: str
    center_angstrom: Tuple[float, float, float]
    tilt_series_pixel_size: float
    voltage: Optional[float] = None
    spherical_aberration: Optional[float] = None
    amplitude_contrast: Optional[float] = None


def read_relion_tomograms(tomograms_star_path: str) -> Dict[str, RelionTomogram]:
    """Read tomogram geometry and optics from a RELION tomograms.star file.

    RELION stores the size of the bin-1 tomogram in tilt-series pixels (``rlnTomoSize{X,Y,Z}``, see RELION's
    ``metadata_label.h``) and places a tomogram's centre at half that size (``tomogram_set.cpp``), so the centre in
    Angstrom is ``rlnTomoSize / 2 * rlnTomoTiltSeriesPixelSize``; the reconstruction binning does not enter it.

    Args:
        tomograms_star_path: Path to a RELION 4/5 tomograms.star file.

    Returns:
        Dict mapping tomo_name to its ``RelionTomogram``.

    Raises:
        ValueError: If required columns are missing from the STAR file.
    """
    import starfile

    data = starfile.read(tomograms_star_path)

    # starfile returns either a dict (if multiple blocks) or a DataFrame
    # Look for "global" block first (RELION5 tomograms.star uses this)
    df = (data["global"] if "global" in data else next(iter(data.values()))) if isinstance(data, dict) else data

    required = [
        "rlnTomoName",
        "rlnTomoSizeX",
        "rlnTomoSizeY",
        "rlnTomoSizeZ",
        "rlnTomoTiltSeriesPixelSize",
    ]
    for col in required:
        if col not in df.columns:
            raise ValueError(
                f"Required column '{col}' not found in tomograms.star for RELION coordinate conversion",
            )

    def optional(row, column) -> Optional[float]:
        return float(row[column]) if column in row.index else None

    tomograms = {}
    for _, row in df.iterrows():
        tomo_name = str(row["rlnTomoName"])
        pixel_size = float(row["rlnTomoTiltSeriesPixelSize"])
        tomograms[tomo_name] = RelionTomogram(
            name=tomo_name,
            center_angstrom=(
                (float(row["rlnTomoSizeX"]) / 2) * pixel_size,
                (float(row["rlnTomoSizeY"]) / 2) * pixel_size,
                (float(row["rlnTomoSizeZ"]) / 2) * pixel_size,
            ),
            tilt_series_pixel_size=pixel_size,
            voltage=optional(row, "rlnVoltage"),
            spherical_aberration=optional(row, "rlnSphericalAberration"),
            amplitude_contrast=optional(row, "rlnAmplitudeContrast"),
        )

    return tomograms


def read_relion5_tomogram_centers(
    tomograms_star_path: str,
) -> Dict[str, Tuple[float, float, float]]:
    """Read tomogram centers in Angstrom from a RELION tomograms.star file.

    The center is ``rlnTomoSize{X,Y,Z} / 2 * rlnTomoTiltSeriesPixelSize`` (see ``read_relion_tomograms``).

    Args:
        tomograms_star_path: Path to RELION 5.0 tomograms.star file.

    Returns:
        Dict mapping tomo_name -> (center_x_angst, center_y_angst, center_z_angst).

    Raises:
        ValueError: If required columns are missing from the STAR file.
    """
    return {name: tomogram.center_angstrom for name, tomogram in read_relion_tomograms(tomograms_star_path).items()}


class RelionPixelSizeError(ValueError):
    """Raised when RELION pixel coordinates cannot be converted because no pixel size is known."""


class RelionTomogramCenterError(ValueError):
    """Raised when RELION centred coordinates must be used but a tomogram's centre is unknown."""


_CENTERED_COLUMNS = ["rlnCenteredCoordinateXAngst", "rlnCenteredCoordinateYAngst", "rlnCenteredCoordinateZAngst"]
_PIXEL_COLUMNS = ["rlnCoordinateX", "rlnCoordinateY", "rlnCoordinateZ"]


def relion_tilt_series_pixel_sizes(df: "pd.DataFrame", optics: Optional["pd.DataFrame"]) -> Optional[np.ndarray]:
    """Per-particle tilt-series pixel size in Angstrom from a STAR file's optics table, or None if it has none.

    RELION 4 and 5 tomography particle files store ``rlnTomoTiltSeriesPixelSize`` in their optics table; particles
    refer to their optics group through ``rlnOpticsGroup`` or ``rlnOpticsGroupName``.

    Raises:
        ValueError: If the optics table has several groups and the particles' groups cannot be resolved.
    """
    if optics is None or len(optics) == 0 or "rlnTomoTiltSeriesPixelSize" not in optics.columns:
        return None
    sizes = optics["rlnTomoTiltSeriesPixelSize"].astype(float)
    if len(optics) == 1:
        return np.full(len(df), float(sizes.iloc[0]))
    for key in ("rlnOpticsGroup", "rlnOpticsGroupName"):
        if key in df.columns and key in optics.columns:
            values = df[key].map(dict(zip(optics[key], sizes, strict=True)))
            if values.isna().any():
                raise ValueError(
                    f"Some particles refer to optics groups ({key}) that are missing from the optics table.",
                )
            return values.to_numpy(dtype=float)
    raise ValueError("The optics table has several groups but the particles do not say which group they belong to.")


def relion_coordinates_to_angstrom(
    df: "pd.DataFrame",
    *,
    voxel_spacing: Optional[float] = None,
    tomogram_centers: Optional[Dict[str, Tuple[float, float, float]]] = None,
    tomogram_center: Optional[Tuple[float, float, float]] = None,
    tomo_name: Optional[str] = None,
    tilt_series_pixel_size: Optional[float] = None,
    optics: Optional["pd.DataFrame"] = None,
    tomograms: Optional[Dict[str, RelionTomogram]] = None,
    relion_version: Optional[str] = None,
) -> np.ndarray:
    """Particle coordinates of a RELION particle table in copick's convention (corner-origin Angstrom).

    Shifts (``rlnOrigin{X,Y,Z}Angst``) are not applied here; see ``copick.util.relion.relion_rows_to_poses``.

    The first rule that applies is used:

    1. ``rlnCenteredCoordinate{X,Y,Z}Angst`` plus the tomogram centre, when the centre of every particle's tomogram is
       known: ``tomogram_center`` for all rows, else ``tomogram_centers`` or ``tomograms`` by ``rlnTomoName`` (or
       ``tomo_name`` when the table has no such column). RELION itself prefers these coordinates.
    2. ``rlnCoordinate{X,Y,Z}`` times the tilt-series pixel size, which is what RELION 4 and 5 mean by these columns.
       The pixel size is ``tilt_series_pixel_size`` if given, else the file's optics table, else the particle's
       tomogram in ``tomograms``.
    3. ``rlnCoordinate{X,Y,Z}`` times ``voxel_spacing``: coordinates in pixels of a tomogram, as older tools and
       earlier copick versions wrote them. A warning is logged.

    ``relion_version="relion5"`` allows only rule 1 and ``"relion4"`` only rules 2 and 3.

    Returns:
        (N, 3) array of positions in Angstrom.

    Raises:
        RelionPixelSizeError: If rule 3 is needed and ``voxel_spacing`` is None.
        RelionTomogramCenterError: If centred coordinates are required (rule 1) but a centre is unknown.
        ValueError: If the table has no usable coordinate columns.
    """
    if relion_version not in (None, "relion4", "relion5"):
        raise ValueError(f"Unknown RELION version '{relion_version}'; expected 'relion4' or 'relion5'.")

    n = len(df)
    if "rlnTomoName" in df.columns:
        names: Optional[List[str]] = df["rlnTomoName"].astype(str).tolist()
    elif tomo_name is not None:
        names = [tomo_name] * n
    else:
        names = None

    has_centered = set(_CENTERED_COLUMNS).issubset(df.columns)
    has_pixels = set(_PIXEL_COLUMNS).issubset(df.columns)

    if has_centered and relion_version != "relion4":
        centers = _row_tomogram_centers(n, names, tomogram_center, tomogram_centers, tomograms)
        if centers is not None:
            return df[_CENTERED_COLUMNS].to_numpy(dtype=float) + centers
        if relion_version == "relion5" or not has_pixels:
            missing = sorted(set(names or []) - set(tomogram_centers or {}) - set(tomograms or {}))
            detail = f" (no centre for tomograms {missing})" if missing else ""
            raise RelionTomogramCenterError(
                "RELION 5.0 coordinates require tomogram dimensions. Provide --tomograms-star "
                f"or ensure tomograms are already imported into the copick project{detail}.",
            )
    elif relion_version == "relion5":
        raise ValueError("STAR file must contain rlnCenteredCoordinateXAngst/YAngst/ZAngst columns for RELION 5.0")

    if not has_pixels:
        raise ValueError("STAR file must contain rlnCoordinateX, rlnCoordinateY, rlnCoordinateZ columns")
    pixels = df[_PIXEL_COLUMNS].to_numpy(dtype=float)

    sizes = None
    if tilt_series_pixel_size is not None:
        sizes = np.full(n, float(tilt_series_pixel_size))
    if sizes is None:
        sizes = relion_tilt_series_pixel_sizes(df, optics)
    if sizes is None and tomograms and names is not None and all(name in tomograms for name in names):
        sizes = np.array([tomograms[name].tilt_series_pixel_size for name in names], dtype=float)
    if sizes is not None:
        return pixels * sizes[:, None]

    if voxel_spacing is None:
        raise RelionPixelSizeError(
            "rlnCoordinateX/Y/Z need a pixel size and the file states none: pass the tilt-series pixel size "
            "(--tilt-series-pixel-size), a tomograms.star (--tomograms-star), or the voxel size the coordinates were "
            "written in (--voxel-size).",
        )
    logger.warning(
        f"Reading rlnCoordinateX/Y/Z as pixels of a tomogram at {voxel_spacing} A: the file states no tilt-series "
        "pixel size. RELION 4/5 tomography files use tilt-series pixels; pass --tilt-series-pixel-size if that is "
        "the case.",
    )
    return pixels * float(voxel_spacing)


def _row_tomogram_centers(
    n: int,
    names: Optional[List[str]],
    tomogram_center: Optional[Tuple[float, float, float]],
    tomogram_centers: Optional[Dict[str, Tuple[float, float, float]]],
    tomograms: Optional[Dict[str, RelionTomogram]],
) -> Optional[np.ndarray]:
    """(N, 3) tomogram centres for each particle, or None if any particle's centre is unknown."""
    if tomogram_center is not None:
        return np.tile(np.asarray(tomogram_center, dtype=float), (n, 1))
    if names is None:
        return None
    centers = []
    for name in names:
        if tomogram_centers and name in tomogram_centers:
            centers.append(tomogram_centers[name])
        elif tomograms and name in tomograms:
            centers.append(tomograms[name].center_angstrom)
        else:
            return None
    return np.asarray(centers, dtype=float).reshape(n, 3)


def _center_tomogram(voxel_spacing, tomo_type: Optional[str]):
    """The tomogram of a voxel spacing whose shape defines the center: the first of ``tomo_type`` if given, else the
    first tomogram; None if there is none."""
    if voxel_spacing is None:
        return None
    tomograms = [t for t in voxel_spacing.tomograms if tomo_type is None or t.tomo_type == tomo_type]
    return tomograms[0] if tomograms else None


def get_tomogram_centers_from_copick(
    root: "CopickRootFSSpec",
    run_names: List[str],
    voxel_spacing: Optional[float],
    tomo_type: Optional[str] = None,
) -> Dict[str, Tuple[float, float, float]]:
    """Get tomogram centers from existing copick project tomograms.

    Uses the zarr shape of existing tomograms to compute centers
    for RELION 5.0 coordinate conversion.

    Args:
        root: Copick root object.
        run_names: List of run names to get centers for.
        voxel_spacing: Voxel spacing in Angstrom. If None, the smallest voxel spacing of each run that has a
            tomogram (of ``tomo_type``, if given) is used.
        tomo_type: Type of the tomogram whose shape defines the center. Default: the voxel spacing's first tomogram.
            A run without a tomogram of this type gets no center; no other type is used instead.

    Returns:
        Dict mapping run_name -> (center_x_angst, center_y_angst, center_z_angst).
        Runs that don't exist or don't have tomograms are silently skipped.
    """
    centers = {}
    for run_name in run_names:
        run = root.get_run(run_name)
        if run is None:
            continue  # Skip missing runs

        if voxel_spacing is None:
            with_tomograms = [v for v in run.voxel_spacings if _center_tomogram(v, tomo_type) is not None]
            vs = min(with_tomograms, key=lambda v: v.voxel_size) if with_tomograms else None
        else:
            vs = run.get_voxel_spacing(voxel_spacing)
        tomo = _center_tomogram(vs, tomo_type)
        if tomo is None:
            continue

        import zarr

        zarr_store = tomo.zarr()
        group = zarr.open(zarr_store, mode="r")
        shape = group["0"].shape  # (z, y, x)

        # Compute center in Angstrom
        center_z = (shape[0] / 2) * vs.voxel_size
        center_y = (shape[1] / 2) * vs.voxel_size
        center_x = (shape[2] / 2) * vs.voxel_size
        centers[run_name] = (center_x, center_y, center_z)

    return centers


def write_star_particles(
    path: str,
    df: "pd.DataFrame",
    optics_group: Union[Dict, "pd.DataFrame", None] = None,
) -> None:
    """Write a RELION STAR file.

    Args:
        path: Output path for the STAR file.
        df: DataFrame with particle data.
        optics_group: Optional optics table: one group as a dict, or a DataFrame with one row per group.
    """
    import pandas as pd
    import starfile

    if optics_group is not None:
        optics_df = optics_group if isinstance(optics_group, pd.DataFrame) else pd.DataFrame([optics_group])
        data = {"optics": optics_df, "particles": df}
    else:
        data = df

    starfile.write(data, path, overwrite=True)


#: Block of a RELION import-coordinates index (see ``write_relion_import_bundle``).
RELION_IMPORT_INDEX_BLOCK = "coordinate_files"


def _check_file_name(name: str) -> None:
    if name in ("", ".", "..") or "/" in name or os.sep in name or "\0" in name:
        raise ValueError(f"Run name {name!r} cannot name a coordinate file.")


def write_relion_import_bundle(
    index_path: str,
    particles: "pd.DataFrame",
    *,
    coordinates_dir: Optional[str] = None,
) -> Tuple[str, Dict[str, str]]:
    """Write particles as the input of RELION's tomography Import Coordinates job (``relion_tomo_import_coordinates``,
    the pipeliner's ``relion.importtomo.coordinates``).

    That program reads one STAR file as an index: a ``data_coordinate_files`` table with ``rlnTomoName`` and
    ``rlnTomoImportParticleFile``, one row per tomogram, each naming a STAR file with that tomogram's particles. It
    reads each of those files whole and appends them, which requires identical columns, so the files are made by
    splitting one table by ``rlnTomoName``. Each holds a single ``data_particles`` table without optics (RELION takes
    the optics from tomograms.star) and without ``rlnOpticsGroup``.

    Args:
        index_path: Path of the index STAR file.
        particles: Particle table with ``rlnTomoName`` (e.g. from ``build_relion_star_tables``).
        coordinates_dir: Directory of the per-tomogram files. Default: ``coordinates`` beside the index. The paths in
            the index are this string joined with ``<rlnTomoName>.star``, as given: a relative directory gives relative
            paths, which RELION resolves from its project directory.

    Returns:
        Tuple of (index path, dict of tomogram name to coordinate file path as written in the index). Tomograms with
        no particles get no file and no index row; an empty table gives an empty index.

    Raises:
        ValueError: If the table has particles but no ``rlnTomoName``, or a tomogram name cannot be a file name.
    """
    import pandas as pd
    import starfile

    if coordinates_dir is None:
        coordinates_dir = os.path.join(os.path.dirname(index_path), "coordinates")
    table = particles.drop(columns=["rlnOpticsGroup"], errors="ignore")
    files: Dict[str, str] = {}
    if len(table):
        if "rlnTomoName" not in table.columns:
            raise ValueError("The particle table has no rlnTomoName, which an import-coordinates index needs.")
        names = table["rlnTomoName"].astype(str)
        unique_names = list(pd.unique(names))
        for name in unique_names:
            _check_file_name(name)
        os.makedirs(coordinates_dir or ".", exist_ok=True)
        for name in unique_names:
            path = os.path.join(coordinates_dir, f"{name}.star")
            starfile.write({"particles": table[names == name].reset_index(drop=True)}, path, overwrite=True)
            files[name] = path
    index = pd.DataFrame({"rlnTomoName": list(files), "rlnTomoImportParticleFile": list(files.values())})
    os.makedirs(os.path.dirname(index_path) or ".", exist_ok=True)
    starfile.write({RELION_IMPORT_INDEX_BLOCK: index}, index_path, overwrite=True)
    return index_path, files


def _relion_eulers(rotations: np.ndarray) -> np.ndarray:
    """RELION Euler angles (rot, tilt, psi) in degrees for object-to-tomogram rotations.

    A matrix that is not a rotation (e.g. a reflection) gets zero angles, and the number of such matrices is logged.
    """
    from scipy.spatial.transform import Rotation

    eulers = np.zeros((rotations.shape[0], 3), dtype=float)
    invalid = 0
    for i, Rmat in enumerate(rotations):
        if np.allclose(Rmat, np.eye(3)):  # skip identities to avoid scipy's gimbal-lock warning
            continue
        try:
            eulers[i] = Rotation.from_matrix(Rmat).inv().as_euler("ZYZ", degrees=True)
        except ValueError:
            invalid += 1
    if invalid:
        logger.warning(
            f"{invalid} of {len(rotations)} transforms are not rotations; their RELION angles are written as 0.",
        )
    return eulers


#: How RELION particle coordinates are written: ``"auto"`` (centered and/or tilt-series pixels, whatever is known) or
#: ``"centered"`` (centered coordinates only, which must be known).
RELION_COORDINATE_MODES = ("auto", "centered")


def _check_coordinates(coordinates: str) -> None:
    if coordinates not in RELION_COORDINATE_MODES:
        raise ValueError(f"coordinates must be one of {RELION_COORDINATE_MODES}, not {coordinates!r}")


def build_relion_particles_df(
    positions: np.ndarray,
    transforms: np.ndarray,
    *,
    tomo_name: Optional[str] = None,
    tomogram_center: Optional[Sequence[float]] = None,
    tilt_series_pixel_size: Optional[float] = None,
    legacy_voxel_spacing: Optional[float] = None,
    instance_ids: Optional[np.ndarray] = None,
    filament: bool = False,
    polarity_known: Union[bool, Sequence[bool], np.ndarray] = False,
    coordinates: str = "auto",
) -> "pd.DataFrame":
    """RELION particle rows for copick picks.

    Each particle's position is its location plus its transform's translation (``geometry.md`` §2.3); its angles
    come from the transform's rotation. With ``coordinates="auto"``, coordinates are written as:

    - ``rlnCenteredCoordinate{X,Y,Z}Angst`` (position minus the tomogram centre) whenever ``tomogram_center`` is
      given; RELION 5 reads these.
    - ``rlnCoordinate{X,Y,Z}`` in tilt-series pixels whenever ``tilt_series_pixel_size`` is given; that is what
      RELION 4 and 5 mean by these columns.
    - With neither, ``rlnCoordinate{X,Y,Z}`` in pixels of ``legacy_voxel_spacing``, as earlier copick versions wrote
      them, with a warning, since RELION would read them as tilt-series pixels.

    With ``coordinates="centered"``, only the centered coordinates are written, and the tomogram center is required.

    Args:
        positions: (N, 3) locations in Angstrom.
        transforms: (N, 4, 4) transforms.
        tomo_name: Written as ``rlnTomoName`` if given.
        tomogram_center: Tomogram centre in Angstrom.
        tilt_series_pixel_size: Tilt-series pixel size in Angstrom.
        legacy_voxel_spacing: Voxel size for the fallback described above.
        instance_ids: (N,) instance IDs; with ``filament``, the filament IDs.
        filament: Write RELION's filament convention (``copick.util.relion.filament_relion_angles``) instead of
            plain angles, plus ``rlnHelicalTubeID`` (the instance ID), ``rlnHelicalTrackLengthAngst`` (Angstrom along
            the filament in point order) and ``rlnAnglePsiFlipRatio`` (see ``polarity_known``). The transforms' +Z
            axis must be the filament axis (copick's filament pick convention).
        polarity_known: For filament columns: whether the point order follows the filament's polarity, for all rows
            (a bool) or per row (an (N,) array). ``rlnAnglePsiFlipRatio`` is 0 where it does (an ordinary psi prior)
            and 0.5 elsewhere (a bimodal prior, so that refinement can flip the direction). The column is always
            written, because RELION reads a missing one as 0.5. Ignored without ``filament``.
        coordinates: ``"auto"`` (as above) or ``"centered"`` (centered coordinates only).

    Raises:
        ValueError: If no coordinates can be written (or, with ``coordinates="centered"``, no center is given),
            filament columns are requested for picks without filament IDs, or ``polarity_known`` is an array of the
            wrong length.
    """
    import pandas as pd

    _check_coordinates(coordinates)
    if coordinates == "centered":
        if tomogram_center is None:
            raise ValueError(
                f"No tomogram center{f' for {tomo_name}' if tomo_name else ''}: centered RELION coordinates need one.",
            )
        tilt_series_pixel_size = None

    positions = np.asarray(positions, dtype=float).reshape(-1, 3)
    transforms = np.asarray(transforms, dtype=float).reshape(-1, 4, 4)
    n = positions.shape[0]
    full_positions = positions + transforms[:, :3, 3]
    known = np.asarray(polarity_known, dtype=bool)
    if known.ndim > 1 or (known.ndim == 1 and known.shape[0] != n):
        raise ValueError(f"polarity_known has shape {known.shape}; expected a bool or one value per pick ({n}).")
    if filament:
        if instance_ids is None or (n and np.min(instance_ids) < 1):
            unassigned = n if instance_ids is None else int(np.sum(np.asarray(instance_ids) < 1))
            raise ValueError(
                f"{unassigned} of {n} picks{f' in {tomo_name}' if tomo_name else ''} have no filament ID "
                "(instance_id < 1); rlnHelicalTubeID starts at 1. Assign filament IDs, or export without filament "
                "columns.",
            )
        from copick.util.relion import filament_relion_angles

        angle_columns = filament_relion_angles(transforms[:, :3, :3])
    else:
        eulers = _relion_eulers(transforms[:, :3, :3])
        angle_columns = {"rlnAngleRot": eulers[:, 0], "rlnAngleTilt": eulers[:, 1], "rlnAnglePsi": eulers[:, 2]}

    data = {}
    if tomo_name is not None:
        data["rlnTomoName"] = [tomo_name] * n
    if tilt_series_pixel_size is not None:
        pixels = full_positions / float(tilt_series_pixel_size)
    elif tomogram_center is None:
        if legacy_voxel_spacing is None:
            raise ValueError(
                "Cannot write RELION coordinates: need the tomogram centre (for centred coordinates) or the "
                "tilt-series pixel size.",
            )
        logger.warning(
            f"Writing rlnCoordinateX/Y/Z in pixels of a tomogram at {legacy_voxel_spacing} A{f' ({tomo_name})' if tomo_name else ''}: "
            "neither the tomogram centre nor the tilt-series pixel size is known. RELION would read these as "
            "tilt-series pixels; pass --tilt-series-pixel-size or --tomograms-star for RELION.",
        )
        pixels = full_positions / float(legacy_voxel_spacing)
    else:
        pixels = None
    if pixels is not None:
        data["rlnCoordinateX"] = pixels[:, 0]
        data["rlnCoordinateY"] = pixels[:, 1]
        data["rlnCoordinateZ"] = pixels[:, 2]
    data.update(angle_columns)
    if filament:
        from copick.util.relion import filament_track_lengths

        ids = np.asarray(instance_ids, dtype=np.int64)
        data["rlnHelicalTubeID"] = ids
        data["rlnHelicalTrackLengthAngst"] = filament_track_lengths(full_positions, ids)
        data["rlnAnglePsiFlipRatio"] = np.where(np.broadcast_to(known, (n,)), 0.0, 0.5)
    if tomogram_center is not None:
        centered = full_positions - np.asarray(tomogram_center, dtype=float)
        data["rlnCenteredCoordinateXAngst"] = centered[:, 0]
        data["rlnCenteredCoordinateYAngst"] = centered[:, 1]
        data["rlnCenteredCoordinateZAngst"] = centered[:, 2]
    return pd.DataFrame(data)


def _relion_optics_row(
    group: int,
    name: str,
    tilt_series_pixel_size: float,
    tomogram: Optional[RelionTomogram] = None,
) -> Dict:
    """One optics group: the tilt-series pixel size RELION requires, and the CTF parameters if they are known."""
    row = {
        "rlnOpticsGroup": group,
        "rlnOpticsGroupName": name,
        "rlnTomoTiltSeriesPixelSize": float(tilt_series_pixel_size),
    }
    if tomogram is not None:
        for column, value in (
            ("rlnVoltage", tomogram.voltage),
            ("rlnSphericalAberration", tomogram.spherical_aberration),
            ("rlnAmplitudeContrast", tomogram.amplitude_contrast),
        ):
            if value is not None:
                row[column] = float(value)
    return row


def build_relion_star_tables(
    runs: Dict[Optional[str], Tuple[np.ndarray, np.ndarray]],
    *,
    voxel_spacing: Optional[float] = None,
    tomogram_centers: Optional[Dict[Optional[str], Tuple[float, float, float]]] = None,
    tilt_series_pixel_size: Union[None, float, Dict[Optional[str], float]] = None,
    tomograms: Optional[Dict[str, RelionTomogram]] = None,
    include_optics: bool = True,
    instance_ids: Optional[Dict[Optional[str], np.ndarray]] = None,
    filament: bool = False,
    polarity_known: Union[bool, Dict[Optional[str], Union[bool, np.ndarray]]] = False,
    coordinates: str = "auto",
) -> Tuple["pd.DataFrame", Optional["pd.DataFrame"]]:
    """Particle and optics tables of a RELION STAR file for picks from one or more runs.

    The same coordinate columns are written for every run: centred coordinates if every run's tomogram centre is
    known, ``rlnCoordinate{X,Y,Z}`` in tilt-series pixels if every run's tilt-series pixel size is known, and the
    legacy tomogram-pixel coordinates (see ``build_relion_particles_df``) only if neither is. With
    ``coordinates="centered"``, only centered coordinates are written, and a run without a center is an error.

    An optics table is written only when the tilt-series pixel size is known (RELION refuses an optics table without
    ``rlnTomoTiltSeriesPixelSize``, and builds one from tomograms.star when the file has none), one group per run.

    Args:
        runs: Dict mapping run name (written as rlnTomoName; None writes no such column) to (positions, transforms).
        voxel_spacing: Voxel size for the legacy fallback.
        tomogram_centers: Tomogram centre in Angstrom per run.
        tilt_series_pixel_size: Tilt-series pixel size in Angstrom, for every run (a float) or per run (a dict; a
            run not in it takes the value from ``tomograms``, if any).
        tomograms: tomograms.star entries per run; they supply centres, tilt-series pixel sizes and CTF parameters.
            A run's entry takes precedence over its ``tomogram_centers`` value.
        include_optics: Write an optics table (when the tilt-series pixel size is known), one group per run.
        instance_ids: Instance IDs per run (filament IDs with ``filament``).
        filament: Write RELION's filament columns (see ``build_relion_particles_df``).
        polarity_known: For filament columns: whether the point order follows the filaments' polarity, for every
            row (a bool) or per run (a dict of run name to a bool or an (N,) array; runs not in it count as unknown).
        coordinates: ``"auto"`` or ``"centered"`` (see above).

    Returns:
        Tuple of (particles DataFrame, optics DataFrame or None).

    Raises:
        ValueError: With ``coordinates="centered"``, if a run has no tomogram center.
    """
    import pandas as pd

    _check_coordinates(coordinates)
    tomograms = tomograms or {}
    tomogram_centers = tomogram_centers or {}
    centers, sizes = {}, {}
    for name in runs:
        tomogram = tomograms.get(name) if name is not None else None
        centers[name] = tomogram.center_angstrom if tomogram is not None else tomogram_centers.get(name)
        size = tilt_series_pixel_size.get(name) if isinstance(tilt_series_pixel_size, dict) else tilt_series_pixel_size
        if size is None and tomogram is not None:
            size = tomogram.tilt_series_pixel_size
        sizes[name] = size
    use_centers = all(center is not None for center in centers.values())
    use_sizes = all(size is not None for size in sizes.values())
    if coordinates == "centered" and not use_centers:
        missing = sorted(str(name) for name, center in centers.items() if center is None)
        raise ValueError(
            f"No tomogram center for {len(missing)} run(s): {', '.join(missing)}. Centered RELION coordinates need the "
            "center of each run's tomogram (from tomograms.star, the caller, or a copick tomogram).",
        )
    if not use_sizes and any(size is not None for size in sizes.values()):
        missing = sorted(str(name) for name, size in sizes.items() if size is None)
        logger.warning(
            f"No tilt-series pixel size for {', '.join(missing)}: writing neither rlnCoordinateX/Y/Z nor an optics "
            "table for any run.",
        )

    particle_tables, optics_rows = [], []
    for group, (name, (positions, transforms)) in enumerate(runs.items(), start=1):
        df = build_relion_particles_df(
            positions,
            transforms,
            tomo_name=name,
            tomogram_center=centers[name] if use_centers else None,
            tilt_series_pixel_size=sizes[name] if use_sizes else None,
            legacy_voxel_spacing=None if (use_centers or use_sizes) else voxel_spacing,
            instance_ids=(instance_ids or {}).get(name),
            filament=filament,
            polarity_known=polarity_known.get(name, False) if isinstance(polarity_known, dict) else polarity_known,
            coordinates=coordinates,
        )
        if include_optics and use_sizes:
            df["rlnOpticsGroup"] = group
            optics_rows.append(_relion_optics_row(group, name or "opticsGroup1", sizes[name], tomograms.get(name)))
        particle_tables.append(df)

    particles = pd.concat(particle_tables, ignore_index=True) if particle_tables else pd.DataFrame()
    optics = pd.DataFrame(optics_rows) if optics_rows else None
    return particles, optics


def write_star_particles_grouped(
    path: str,
    grouped_data: Dict[str, Tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]],
    voxel_spacing: Optional[float] = None,
    optics_group: Optional[Dict] = None,
    *,
    tomogram_centers: Optional[Dict[str, Tuple[float, float, float]]] = None,
    tilt_series_pixel_size: Union[None, float, Dict[str, float]] = None,
    tomograms: Optional[Dict[str, RelionTomogram]] = None,
    include_optics: bool = True,
    instance_ids: Optional[Dict[str, np.ndarray]] = None,
    filament: bool = False,
    polarity_known: Union[bool, Dict[str, Union[bool, np.ndarray]]] = False,
    coordinates: str = "auto",
) -> None:
    """Write a combined RELION STAR file from multiple runs.

    Uses run_name directly as _rlnTomoName column value. Coordinates and optics follow
    ``build_relion_star_tables``.

    Args:
        path: Output path for the STAR file.
        grouped_data: Dict mapping run_name to (positions_angstrom, transforms_4x4, scores).
        voxel_spacing: Voxel spacing in Angstrom, used only when neither tomogram centres nor the tilt-series pixel
            size are known.
        optics_group: Deprecated and ignored: the optics table is derived from the tilt-series pixel size.
        tomogram_centers: Tomogram centre in Angstrom per run.
        tilt_series_pixel_size: Tilt-series pixel size in Angstrom, for every run (a float) or per run (a dict).
        tomograms: tomograms.star entries per run.
        include_optics: Write an optics table when the tilt-series pixel size is known.
        instance_ids: Instance IDs per run (filament IDs with ``filament``).
        filament: Write RELION's filament columns (see ``build_relion_particles_df``).
        polarity_known: For filament columns: whether the point order follows the filaments' polarity, for every
            row (a bool) or per run (a dict of run name to a bool or an (N,) array).
        coordinates: ``"auto"`` or ``"centered"`` (see ``build_relion_star_tables``).
    """
    import warnings

    if optics_group is not None:
        warnings.warn(
            "optics_group is ignored: the optics table is derived from the tilt-series pixel size.",
            DeprecationWarning,
            stacklevel=2,
        )

    particles, optics = build_relion_star_tables(
        {run_name: (positions, transforms) for run_name, (positions, transforms, *_rest) in grouped_data.items()},
        voxel_spacing=voxel_spacing,
        tomogram_centers=tomogram_centers,
        tilt_series_pixel_size=tilt_series_pixel_size,
        tomograms=tomograms,
        include_optics=include_optics,
        instance_ids=instance_ids,
        filament=filament,
        polarity_known=polarity_known,
        coordinates=coordinates,
    )
    write_star_particles(path, particles, optics)


def read_relion_tomograms_star(
    path: str,
    half: str = "half1",
    base_dir: Optional[str] = None,
) -> Dict[str, Tuple[str, float]]:
    """Read a RELION tomograms.star file.

    Parses a RELION tomograms.star file and extracts tomogram paths, run names,
    and voxel sizes. The voxel size is the tilt-series pixel size (rlnTomoTiltSeriesPixelSize; for older files
    without it, rlnMicrographOriginalPixelSize) multiplied by the binning factor.

    Args:
        path: Path to the tomograms.star file.
        half: Which reconstruction half to use ("half1" or "half2"). Default: "half1".
        base_dir: RELION project root directory for resolving relative paths in the
            STAR file. Required because RELION stores paths relative to the project
            root, not relative to the STAR file location.

    Returns:
        Dictionary mapping run_name to (mrc_path, voxel_size_angstrom).

    Raises:
        ValueError: If required columns are missing, the half column is not found,
            or base_dir is not provided.

    Example star file format::

        data_global

        loop_
        _rlnTomoName #1
        _rlnMicrographOriginalPixelSize #2
        _rlnTomoTomogramBinning #3
        _rlnTomoReconstructedTomogramHalf1 #4
        _rlnTomoReconstructedTomogramHalf2 #5
        TS_01  0.675  7.407  path/to/half1.mrc  path/to/half2.mrc
    """
    import os

    import starfile

    if base_dir is None:
        raise ValueError(
            "base_dir is required for resolving relative paths in RELION STAR files. "
            "Provide the RELION project root directory.",
        )
    base_dir = os.path.abspath(base_dir)

    data = starfile.read(path)

    # starfile returns either a dict (if multiple blocks) or a DataFrame
    if isinstance(data, dict):  # noqa: SIM108
        # Look for "global" block first (RELION5 tomograms.star uses this), fall back to first block
        df = data["global"] if "global" in data else next(iter(data.values()))
    else:
        df = data

    # Validate required columns
    required_cols = [
        "rlnTomoName",
        "rlnTomoTomogramBinning",
    ]
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Required column '{col}' not found in tomograms.star file")
    # The tomogram's pixel size is the tilt series' times the binning (RELION's reconstruct_tomogram); older files
    # without rlnTomoTiltSeriesPixelSize fall back to the original micrograph pixel size.
    pixel_size_col = next(
        (col for col in ("rlnTomoTiltSeriesPixelSize", "rlnMicrographOriginalPixelSize") if col in df.columns),
        None,
    )
    if pixel_size_col is None:
        raise ValueError(
            "Required column 'rlnTomoTiltSeriesPixelSize' (or 'rlnMicrographOriginalPixelSize') not found in "
            "tomograms.star file",
        )

    # Determine path column based on half
    if half.lower() == "half1":
        path_col = "rlnTomoReconstructedTomogramHalf1"
    elif half.lower() == "half2":
        path_col = "rlnTomoReconstructedTomogramHalf2"
    else:
        raise ValueError(f"Invalid half '{half}'. Must be 'half1' or 'half2'.")

    if path_col not in df.columns:
        raise ValueError(f"Column '{path_col}' not found in tomograms.star file")

    result = {}
    for _, row in df.iterrows():
        run_name = str(row["rlnTomoName"])
        pixel_size = float(row[pixel_size_col])
        binning = float(row["rlnTomoTomogramBinning"])
        mrc_path = str(row[path_col])

        # Compute effective voxel size
        voxel_size = pixel_size * binning

        # Resolve relative paths against base_dir (RELION project root)
        if not os.path.isabs(mrc_path):
            mrc_path = os.path.join(base_dir, mrc_path)

        # Check for duplicate run names
        if run_name in result:
            raise ValueError(f"Duplicate run name '{run_name}' in tomograms.star file")

        result[run_name] = (mrc_path, voxel_size)

    return result


# =============================================================================
# CSV Utilities (Copick Native Format)
# =============================================================================


def read_picks_csv(path: str) -> "pd.DataFrame":
    """Read a copick CSV picks file.

    The CSV format includes:
    - run_name: Run identifier
    - x, y, z: Coordinates in Angstrom (corner-origin)
    - transform_00 through transform_33: Full 4x4 matrix elements
    - score: Optional confidence score
    - instance_id: Optional instance identifier

    Args:
        path: Path to the CSV file.

    Returns:
        DataFrame with picks data.
    """
    import pandas as pd

    return pd.read_csv(path)


def write_picks_csv(
    path: str,
    run_name: str,
    positions: np.ndarray,
    transforms: np.ndarray,
    scores: Optional[np.ndarray] = None,
    instance_ids: Optional[np.ndarray] = None,
) -> None:
    """Write picks to a copick CSV file.

    Args:
        path: Output path for the CSV file.
        run_name: Run name for all points.
        positions: Array of shape (N, 3) with coordinates in Angstrom.
        transforms: Array of shape (N, 4, 4) with transformation matrices.
        scores: Optional array of shape (N,) with scores.
        instance_ids: Optional array of shape (N,) with instance IDs.
    """
    import pandas as pd

    N = positions.shape[0]

    data = {
        "run_name": [run_name] * N,
        "x": positions[:, 0],
        "y": positions[:, 1],
        "z": positions[:, 2],
    }

    # Add all 16 matrix elements
    for i in range(4):
        for j in range(4):
            data[f"transform_{i}{j}"] = transforms[:, i, j]

    if scores is not None:
        data["score"] = scores
    else:
        data["score"] = np.ones(N)

    if instance_ids is not None:
        data["instance_id"] = instance_ids

    df = pd.DataFrame(data)
    df.to_csv(path, index=False)


def write_picks_csv_grouped(
    path: str,
    grouped_data: Dict[str, Tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]],
    instance_ids: Optional[Dict[str, np.ndarray]] = None,
) -> None:
    """Write a combined CSV file from multiple runs.

    Simply concatenates all runs with run_name column identifying each.

    Args:
        path: Output path for the CSV file.
        grouped_data: Dict mapping run_name to (positions_angstrom, transforms_4x4, scores).
        instance_ids: Optional dict mapping run_name to an (N,) array of instance IDs. When given, an
            ``instance_id`` column is written (0 for runs without an entry).
    """
    import pandas as pd

    all_dfs = []

    for run_name, (positions, transforms, scores) in grouped_data.items():
        N = positions.shape[0]

        data = {
            "run_name": [run_name] * N,
            "x": positions[:, 0],
            "y": positions[:, 1],
            "z": positions[:, 2],
        }

        # Add all 16 matrix elements
        for i in range(4):
            for j in range(4):
                data[f"transform_{i}{j}"] = transforms[:, i, j]

        if scores is not None:
            data["score"] = scores
        else:
            data["score"] = np.ones(N)

        if instance_ids is not None:
            ids = instance_ids.get(run_name)
            data["instance_id"] = np.zeros(N, dtype=np.int64) if ids is None else np.asarray(ids, dtype=np.int64)

        all_dfs.append(pd.DataFrame(data))

    combined_df = pd.concat(all_dfs, ignore_index=True)
    combined_df.to_csv(path, index=False)


def _csv_instance_ids(df: "pd.DataFrame") -> Optional[np.ndarray]:
    """The ``instance_id`` column of a copick CSV as an int64 array (missing values become 0), or None."""
    if "instance_id" not in df.columns:
        return None
    return df["instance_id"].fillna(0).to_numpy().astype(np.int64)


def csv_to_copick_arrays(
    df: "pd.DataFrame",
    include_instance_ids: bool = False,
) -> Dict[str, Tuple[np.ndarray, ...]]:
    """Convert CSV DataFrame to copick arrays, grouped by run_name.

    Args:
        df: DataFrame with CSV picks data.
        include_instance_ids: Append the instance IDs to each tuple (zeros if the file has no ``instance_id``
            column).

    Returns:
        Dictionary mapping run_name to (positions, transforms, scores) tuples, or to
        (positions, transforms, scores, instance_ids) tuples if ``include_instance_ids`` is set.
    """
    results = {}

    for run_name, group in df.groupby("run_name"):
        N = len(group)

        positions = group[["x", "y", "z"]].to_numpy()

        # Reconstruct transforms from matrix elements
        transforms = np.zeros((N, 4, 4), dtype=float)
        for i in range(4):
            for j in range(4):
                col = f"transform_{i}{j}"
                if col in group.columns:
                    transforms[:, i, j] = group[col].to_numpy()
                elif i == j:
                    transforms[:, i, j] = 1.0  # Identity diagonal

        scores = group["score"].to_numpy() if "score" in group.columns else np.ones(N)

        if include_instance_ids:
            ids = _csv_instance_ids(group)
            results[run_name] = (positions, transforms, scores, np.zeros(N, dtype=np.int64) if ids is None else ids)
        else:
            results[run_name] = (positions, transforms, scores)

    return results


def read_copick_csv(
    path: str,
) -> Tuple[np.ndarray, np.ndarray, Optional[np.ndarray], np.ndarray]:
    """Read a copick CSV picks file and return arrays.

    Convenience function that reads CSV and returns arrays directly.

    Args:
        path: Path to the CSV file.

    Returns:
        Tuple of (positions, transforms, scores, run_names) where:
        - positions: (N, 3) array of coordinates in Angstrom
        - transforms: (N, 4, 4) array of transformation matrices
        - scores: (N,) array of scores (or None if not present)
        - run_names: (N,) array of run name strings
    """
    import pandas as pd

    positions, transforms, scores, run_names, _ = copick_csv_df_to_arrays(pd.read_csv(path))
    return positions, transforms, scores, run_names


def copick_csv_df_to_arrays(
    df: "pd.DataFrame",
) -> Tuple[np.ndarray, np.ndarray, Optional[np.ndarray], np.ndarray, Optional[np.ndarray]]:
    """Convert a copick CSV DataFrame to arrays.

    Args:
        df: DataFrame with CSV picks data.

    Returns:
        Tuple of (positions, transforms, scores, run_names, instance_ids); ``scores`` and ``instance_ids`` are
        None when the file has no such column.
    """
    N = len(df)
    positions = df[["x", "y", "z"]].to_numpy()

    # Reconstruct transforms from matrix elements
    transforms = np.zeros((N, 4, 4), dtype=float)
    for i in range(4):
        for j in range(4):
            col = f"transform_{i}{j}"
            if col in df.columns:
                transforms[:, i, j] = df[col].to_numpy()
            elif i == j:
                transforms[:, i, j] = 1.0  # Identity diagonal

    scores = df["score"].to_numpy() if "score" in df.columns else None
    run_names = df["run_name"].to_numpy() if "run_name" in df.columns else np.array([""] * N)

    return positions, transforms, scores, run_names, _csv_instance_ids(df)


def write_copick_csv(
    path: str,
    positions: np.ndarray,
    transforms: np.ndarray,
    run_name: str = "",
    scores: Optional[np.ndarray] = None,
    instance_ids: Optional[np.ndarray] = None,
) -> None:
    """Write picks to a copick CSV file.

    Wrapper for write_picks_csv with argument order matching handler expectations.

    Args:
        path: Output path for the CSV file.
        positions: Array of shape (N, 3) with coordinates in Angstrom.
        transforms: Array of shape (N, 4, 4) with transformation matrices.
        run_name: Run name for all points.
        scores: Optional array of shape (N,) with scores.
        instance_ids: Optional array of shape (N,) with instance IDs.
    """
    write_picks_csv(path, run_name, positions, transforms, scores, instance_ids)


def read_copick_csv_grouped(
    path: str,
) -> Dict[str, Tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]]:
    """Read a copick CSV file and return data grouped by run_name.

    Convenience function that reads CSV and returns grouped arrays.

    Args:
        path: Path to the CSV file.

    Returns:
        Dict mapping run_name to (positions, transforms, scores) tuples.
    """
    import pandas as pd

    df = pd.read_csv(path)
    return csv_to_copick_arrays(df)


# =============================================================================
# TIFF Utilities
# =============================================================================


def read_tiff_volume(path: str) -> np.ndarray:
    """Read a TIFF stack as a 3D volume.

    Args:
        path: Path to the TIFF file.

    Returns:
        3D numpy array with volume data.
    """
    import tifffile

    return tifffile.imread(path)


def write_tiff_volume(
    path: str,
    volume: np.ndarray,
    compression: Optional[str] = None,
) -> None:
    """Write a 3D volume as a TIFF stack.

    Args:
        path: Output path for the TIFF file.
        volume: 3D numpy array with volume data.
        compression: Optional compression method ('lzw', 'zlib', 'jpeg', etc.).
    """
    import tifffile

    tifffile.imwrite(path, volume, compression=compression)
