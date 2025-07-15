from typing import Tuple, Union

import mrcfile
import numpy as np
import zarr

from copick.util.ome import get_voxel_size_from_zarr


def get_format_from_extension(path: str) -> Union[str, None]:
    """
    Get the format name from a file extension.

    Args:
        path (str): The file path or name from which to extract the extension.

    Returns:
        str: The format name corresponding to the extension.
    """
    formats = {
        "mrc": "mrc",
        "zarr": "zarr",
        "map": "mrc",
    }
    return formats.get(path.split(".")[-1], None)


def get_data_from_file(path: str, file_format: str) -> Tuple[np.ndarray, float]:
    """
    Get the data from a file based on its format.

    Args:
        path (str): The file path or name.
        file_format (str): The format of the file.

    Returns:
        (array, voxel_size): The data read from the file and the voxel size.
    """
    if file_format == "mrc":
        with mrcfile.open(path) as mrc:
            volume_data = mrc.data
            voxel_spacing = float(mrc.voxel_size.y)  # Assuming isotropic voxel size
    elif file_format == "zarr":
        zarr_group = zarr.open(path)
        volume_data = zarr_group["0"][:]
        voxel_spacing = get_voxel_size_from_zarr(zarr_group)
    else:
        raise ValueError(f"Unsupported file format: {file_format}")

    return volume_data, voxel_spacing
