import os
import re
from typing import Dict, List, Tuple, Union

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


def prepare_runs_from_paths(
    root,
    paths: List[str],
    input_run: str,
    run_regex: str = r"(.*)",
    create: bool = True,
    logger=None,
) -> Dict[str, str]:
    """
    Prepare runs from file paths, creating runs if necessary.
    Each run gets exactly one file.

    Args:
        root: Copick root
        paths: List of file paths
        input_run: Run name (empty string means derive from filename)
        run_regex: Regex to match run names in filenames. First group is used as run name.
        create: Whether to create runs if they don't exist
        logger: Logger instance

    Returns:
        Dictionary mapping run names to single file paths
    """
    run_to_file = {}  # Changed variable name to reflect single file per run

    # Map each file to a run name
    for path in paths:
        if input_run == "":
            filename = os.path.basename(path)
            current_run = filename.rsplit(".", 1)[0]
        else:
            current_run = input_run

        # Check if this run already has a file assigned
        if current_run in run_to_file:
            if logger:
                logger.warning(
                    f"Run {current_run} already has a file assigned ({run_to_file[current_run]}). Skipping {path}.",
                )
            continue

        # Match run name with regex
        match = re.search(run_regex, current_run)
        if match:
            current_run = match.group(1)
        else:
            if logger:
                logger.warning(f"Run name {current_run} does not match regex {run_regex}. Skipping {path}.")
            continue

        run_to_file[current_run] = path

    # Create runs if they don't exist
    for run_name in run_to_file:
        if not root.get_run(run_name):
            if create:
                root.new_run(run_name)
                if logger:
                    logger.info(f"Created run: {run_name}")
            else:
                if logger:
                    logger.warning(f"Run {run_name} does not exist and create=False")

    return run_to_file
