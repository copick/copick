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
    tomo_index_row: int = 3,
) -> Union[Tuple[np.ndarray, np.ndarray, np.ndarray], Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]]:
    """Read a TOM toolbox EM motivelist.

    TOM motivelists store particle positions and angles in a 2D array where:
    - Row 0-2: Position shifts (dx, dy, dz) - usually applied during alignment
    - Row 3: Tomogram index (default location, configurable via tomo_index_row)
    - Row 4: Particle class
    - Row 5: Subtomogram filename (unused here, just index)
    - Row 6: Score/CCC
    - Row 7-9: Position (x, y, z) in pixels (center-origin convention)
    - Row 16-18: Euler angles (phi, psi, theta) - typically ZXZ

    Args:
        path: Path to the EM file.
        include_tomo_index: If True, also return the tomogram indices.
        tomo_index_row: Row index (0-based) containing tomogram indices (default: 3).

    Returns:
        If include_tomo_index=False: Tuple of (positions [N, 3] in pixels,
            eulers [N, 3] in degrees, scores [N]).
        If include_tomo_index=True: Same as above plus tomo_indices [N] as integers.
    """
    import emfile

    _header, data = emfile.read(path)

    # EM files can have different shapes, typically (20, N) or similar
    if data.ndim == 1:
        data = data.reshape(-1, 1)

    if data.shape[0] < 19:
        raise ValueError(f"EM motivelist has unexpected shape: {data.shape}")

    # Positions (rows 7-9, 0-indexed)
    positions = data[7:10, :].T  # Shape: (N, 3)

    # Euler angles (rows 16-18, 0-indexed)
    eulers = data[16:19, :].T  # Shape: (N, 3)

    # Scores (row 6)
    scores = data[6, :]

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

    Args:
        path: Output path for the EM file.
        positions: Array of shape (N, 3) with coordinates in pixels.
        eulers: Array of shape (N, 3) with Euler angles in degrees.
        scores: Optional array of shape (N,) with scores.
        tomogram_index: Tomogram index for all particles.
    """
    import emfile

    N = positions.shape[0]

    if scores is None:
        scores = np.ones(N)

    # Create standard TOM motivelist structure (20 rows x N columns)
    data = np.zeros((20, N), dtype=np.float32)

    # Position shifts (rows 0-2) - typically zero for initial list
    data[0:3, :] = 0.0

    # Tomogram index (row 3)
    data[3, :] = tomogram_index

    # Class (row 4) - default to 1
    data[4, :] = 1

    # Particle index (row 5)
    data[5, :] = np.arange(1, N + 1)

    # Score (row 6)
    data[6, :] = scores

    # Positions (rows 7-9)
    data[7:10, :] = positions.T

    # Euler angles (rows 16-18)
    data[16:19, :] = eulers.T

    emfile.write(path, data)


def read_em_volume(path: str) -> np.ndarray:
    """Read a TOM toolbox EM volume file.

    Args:
        path: Path to the EM file.

    Returns:
        3D numpy array with volume data.
    """
    import emfile

    return emfile.read(path)


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
    tomogram_dimensions: Tuple[int, int, int],
) -> Tuple[np.ndarray, np.ndarray]:
    """Convert TOM/EM coordinates to copick format.

    TOM toolbox uses:
    - Center-origin coordinates in pixels
    - ZXZ Euler convention (typically)

    Copick uses:
    - Corner-origin coordinates in Angstrom
    - 4x4 affine matrices

    Args:
        positions_px: Coordinates in pixels (center-origin) [N, 3].
        eulers_deg: ZXZ Euler angles in degrees [N, 3].
        voxel_size: Voxel size in Angstrom.
        tomogram_dimensions: (X, Y, Z) dimensions of tomogram in voxels.

    Returns:
        Tuple of (points_angstrom [N, 3], transforms [N, 4, 4]).
    """
    # Convert from center-origin to corner-origin
    center_offset = np.array(tomogram_dimensions) / 2.0
    positions_corner = positions_px + center_offset

    # Convert to Angstrom
    points_angstrom = positions_corner * voxel_size

    # Convert Euler angles to rotation matrices (ZXZ convention)
    rotations = euler_to_matrix(eulers_deg, convention="ZXZ", degrees=True)

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
    tomogram_dimensions: Tuple[int, int, int],
) -> Tuple[np.ndarray, np.ndarray]:
    """Convert copick format to TOM/EM coordinates.

    Args:
        points_angstrom: Coordinates in Angstrom (corner-origin) [N, 3].
        transforms: 4x4 affine matrices [N, 4, 4].
        voxel_size: Voxel size in Angstrom.
        tomogram_dimensions: (X, Y, Z) dimensions of tomogram in voxels.

    Returns:
        Tuple of (positions_px [N, 3] center-origin, eulers_deg [N, 3]).
    """
    # Extract rotations from transforms
    _, rotations = transforms_to_points_and_rotations(transforms)

    # Convert to pixel coordinates (corner-origin)
    positions_corner_px = points_angstrom / voxel_size

    # Convert from corner-origin to center-origin
    center_offset = np.array(tomogram_dimensions) / 2.0
    positions_px = positions_corner_px - center_offset

    # Convert rotation matrices to ZXZ Euler angles
    eulers_deg = matrix_to_euler(rotations, convention="ZXZ", degrees=True)

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
