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

from typing import TYPE_CHECKING, Dict, Optional, Tuple, Union

import numpy as np

from copick.util.log import get_logger

if TYPE_CHECKING:
    import pandas as pd

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

    return dict(zip(indices, run_names))


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
) -> Union[Tuple[np.ndarray, np.ndarray, np.ndarray], Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]]:
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

    Returns:
        If include_tomo_index=False: Tuple of (positions [N, 3] in pixels 0-indexed,
            eulers [N, 3] in degrees as [phi, theta, psi], scores [N]).
        If include_tomo_index=True: Same as above plus tomo_indices [N] as integers.
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
        return positions, eulers, scores, tomo_indices

    return positions, eulers, scores


def write_em_motivelist(
    path: str,
    positions: np.ndarray,
    eulers: np.ndarray,
    scores: Optional[np.ndarray] = None,
    tomogram_index: int = 1,
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

    # Shifts (columns 10-12) - typically zero
    data[0, :, 10:13] = 0.0

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
    positions_px, eulers_deg, scores, tomo_indices = read_em_motivelist(
        path,
        include_tomo_index=True,
        tomo_index_row=tomo_index_row,
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
        )

        grouped[run_name] = (positions_angstrom, transforms, scores_group)

    return grouped


def write_em_motivelist_grouped(
    path: str,
    grouped_data: Dict[str, Tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]],
    voxel_spacing: float,
    run_to_index: Dict[str, int],
    tomogram_dimensions: Optional[Tuple[int, int, int]] = None,
) -> None:
    """Write a combined TOM toolbox EM motivelist from multiple runs.

    Args:
        path: Output path for the EM file.
        grouped_data: Dict mapping run_name to (positions_angstrom, transforms_4x4, scores).
        voxel_spacing: Voxel spacing in Angstrom for coordinate conversion.
        run_to_index: Mapping from run name to tomogram index.
        tomogram_dimensions: Optional (z, y, x) dimensions for coordinate conversion.

    Raises:
        ValueError: If run_to_index is missing entries for any run.
    """
    import emfile

    all_positions = []
    all_eulers = []
    all_scores = []
    all_tomo_indices = []

    for run_name, (positions, transforms, scores) in grouped_data.items():
        if run_name not in run_to_index:
            raise ValueError(f"Run '{run_name}' not found in run_to_index mapping")

        tomogram_index = run_to_index[run_name]

        # Convert from copick format to EM format
        positions_px, eulers_deg = copick_to_em_transform(
            positions,
            transforms,
            voxel_spacing,
            tomogram_dimensions,
        )

        N = positions_px.shape[0]
        if scores is None:
            scores = np.ones(N)

        all_positions.append(positions_px)
        all_eulers.append(eulers_deg)
        all_scores.append(scores)
        all_tomo_indices.append(np.full(N, tomogram_index))

    # Concatenate all data
    positions_combined = np.vstack(all_positions)
    eulers_combined = np.vstack(all_eulers)
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

    # Shifts (columns 10-12) - typically zero
    data[0, :, 10:13] = 0.0

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


def write_em_volume(path: str, volume: np.ndarray) -> None:
    """Write a TOM toolbox EM volume file.

    Args:
        path: Output path for the EM file.
        volume: 3D numpy array with volume data.
    """
    import emfile

    emfile.write(path, volume.astype(np.float32))


def em_to_copick_transform(
    positions_px: np.ndarray,
    eulers_deg: np.ndarray,
    voxel_size: float,
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

    Returns:
        Tuple of (points_angstrom [N, 3], transforms [N, 4, 4]).
    """
    from scipy.spatial.transform import Rotation

    # Convert to Angstrom (coordinates are already corner-origin)
    points_angstrom = positions_px * voxel_size

    # Convert Euler angles to rotation matrices
    # Use intrinsic zxz (lowercase) as per Artiatomi/ArtiaX convention
    rotations = Rotation.from_euler("zxz", eulers_deg, degrees=True).as_matrix()

    # Create identity transforms (no additional translation beyond point location)
    N = positions_px.shape[0]
    transforms = np.zeros((N, 4, 4), dtype=float)
    transforms[:, :3, :3] = rotations
    transforms[:, 3, 3] = 1.0

    return points_angstrom, transforms


def copick_to_em_transform(
    points_angstrom: np.ndarray,
    transforms: np.ndarray,
    voxel_size: float,
) -> Tuple[np.ndarray, np.ndarray]:
    """Convert copick format to TOM/EM coordinates.

    This is the inverse of em_to_copick_transform.

    Args:
        points_angstrom: Coordinates in Angstrom (corner-origin) [N, 3].
        transforms: 4x4 affine matrices [N, 4, 4].
        voxel_size: Voxel size in Angstrom.

    Returns:
        Tuple of (positions_px [N, 3] corner-origin 0-indexed, eulers_deg [N, 3] as [phi, theta, psi]).
    """
    from scipy.spatial.transform import Rotation

    # Extract rotations from transforms
    _, rotations = transforms_to_points_and_rotations(transforms)

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

    return positions_px, eulers_deg


# =============================================================================
# STAR File Utilities
# =============================================================================


def read_star_particles(path: str) -> "pd.DataFrame":
    """Read a RELION STAR file.

    Args:
        path: Path to the STAR file.

    Returns:
        DataFrame with particle data.
    """
    import starfile

    data = starfile.read(path)

    # starfile returns either a dict (if multiple blocks) or a DataFrame
    if isinstance(data, dict):
        # Look for particles block
        if "particles" in data:
            return data["particles"]
        # Fall back to first non-optics block
        for key, value in data.items():
            if key != "optics":
                return value
        raise ValueError("No particle data found in STAR file")

    return data


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
    df = read_star_particles(path)

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


def write_star_particles(
    path: str,
    df: "pd.DataFrame",
    optics_group: Optional[Dict] = None,
) -> None:
    """Write a RELION STAR file.

    Args:
        path: Output path for the STAR file.
        df: DataFrame with particle data.
        optics_group: Optional optics group metadata.
    """
    import pandas as pd
    import starfile

    if optics_group is not None:
        optics_df = pd.DataFrame([optics_group])
        data = {"optics": optics_df, "particles": df}
    else:
        data = df

    starfile.write(data, path, overwrite=True)


def write_star_particles_grouped(
    path: str,
    grouped_data: Dict[str, Tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]],
    voxel_spacing: float,
    optics_group: Optional[Dict] = None,
) -> None:
    """Write a combined RELION STAR file from multiple runs.

    Uses run_name directly as _rlnTomoName column value.

    Args:
        path: Output path for the STAR file.
        grouped_data: Dict mapping run_name to (positions_angstrom, transforms_4x4, scores).
        voxel_spacing: Voxel spacing in Angstrom for coordinate conversion.
        optics_group: Optional optics group metadata.
    """
    import pandas as pd
    import starfile
    from scipy.spatial.transform import Rotation

    all_dfs = []

    for run_name, (positions, transforms, _scores) in grouped_data.items():
        N = positions.shape[0]

        # Convert positions from Angstrom to pixels
        positions_px = positions / voxel_spacing

        # Extract Euler angles from transforms
        rotation_matrices = transforms[:, :3, :3]
        # Invert rotation for RELION convention
        rotations = Rotation.from_matrix(rotation_matrices).inv()
        euler_angles = rotations.as_euler("ZYZ", degrees=True)

        df = pd.DataFrame(
            {
                "rlnTomoName": [run_name] * N,
                "rlnCoordinateX": positions_px[:, 0],
                "rlnCoordinateY": positions_px[:, 1],
                "rlnCoordinateZ": positions_px[:, 2],
                "rlnAngleRot": euler_angles[:, 0],
                "rlnAngleTilt": euler_angles[:, 1],
                "rlnAnglePsi": euler_angles[:, 2],
            },
        )

        if optics_group is not None:
            df["rlnOpticsGroup"] = 1

        all_dfs.append(df)

    combined_df = pd.concat(all_dfs, ignore_index=True)

    if optics_group is not None:
        optics_df = pd.DataFrame([optics_group])
        data = {"optics": optics_df, "particles": combined_df}
    else:
        data = combined_df

    starfile.write(data, path, overwrite=True)


def read_relion_tomograms_star(
    path: str,
    half: str = "half1",
) -> Dict[str, Tuple[str, float]]:
    """Read a RELION tomograms.star file.

    Parses a RELION tomograms.star file and extracts tomogram paths, run names,
    and voxel sizes. The voxel size is computed from the original pixel size
    multiplied by the binning factor.

    Args:
        path: Path to the tomograms.star file.
        half: Which reconstruction half to use ("half1" or "half2"). Default: "half1".

    Returns:
        Dictionary mapping run_name to (mrc_path, voxel_size_angstrom).

    Raises:
        ValueError: If required columns are missing or the half column is not found.

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
        "rlnMicrographOriginalPixelSize",
        "rlnTomoTomogramBinning",
    ]
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Required column '{col}' not found in tomograms.star file")

    # Determine path column based on half
    if half.lower() == "half1":
        path_col = "rlnTomoReconstructedTomogramHalf1"
    elif half.lower() == "half2":
        path_col = "rlnTomoReconstructedTomogramHalf2"
    else:
        raise ValueError(f"Invalid half '{half}'. Must be 'half1' or 'half2'.")

    if path_col not in df.columns:
        raise ValueError(f"Column '{path_col}' not found in tomograms.star file")

    # Get directory of star file for resolving relative paths
    star_dir = os.path.dirname(os.path.abspath(path))

    result = {}
    for _, row in df.iterrows():
        run_name = str(row["rlnTomoName"])
        pixel_size = float(row["rlnMicrographOriginalPixelSize"])
        binning = float(row["rlnTomoTomogramBinning"])
        mrc_path = str(row[path_col])

        # Compute effective voxel size
        voxel_size = pixel_size * binning

        # Resolve relative paths
        if not os.path.isabs(mrc_path):
            mrc_path = os.path.join(star_dir, mrc_path)

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
) -> None:
    """Write a combined CSV file from multiple runs.

    Simply concatenates all runs with run_name column identifying each.

    Args:
        path: Output path for the CSV file.
        grouped_data: Dict mapping run_name to (positions_angstrom, transforms_4x4, scores).
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

        all_dfs.append(pd.DataFrame(data))

    combined_df = pd.concat(all_dfs, ignore_index=True)
    combined_df.to_csv(path, index=False)


def csv_to_copick_arrays(df: "pd.DataFrame") -> Dict[str, Tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """Convert CSV DataFrame to copick arrays, grouped by run_name.

    Args:
        df: DataFrame with CSV picks data.

    Returns:
        Dictionary mapping run_name to (positions, transforms, scores) tuples.
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

    df = pd.read_csv(path)

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

    return positions, transforms, scores, run_names


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
