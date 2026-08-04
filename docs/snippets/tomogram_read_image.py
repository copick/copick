"""Read a tomogram from a zarr-store into a numpy array."""

import numpy as np
import zarr

import copick
from copick.util.ome import get_level_path

# Initialize the root object from a configuration file
root = copick.from_file("path/to/config.json")

# Get the run named 'TS_001'
run = root.get_run("TS_001")

# Get the voxel spacing with a resolution of 10 angstroms
voxel_spacing = run.get_voxel_spacing(10.000)

# Get the tomogram named 'wbp'
tomogram = voxel_spacing.get_tomogram("wbp")

# Read the tomogram from its zarr-store
# Scale 0 is the unbinned tomogram
zarr_group = zarr.open(tomogram.zarr(), mode="r")
zarr_array = zarr_group[get_level_path(zarr_group, 0)]
tomogram_data = np.array(zarr_array)

# Scale 1 is the tomogram binned by 2
zarr_array_bin2 = zarr_group[get_level_path(zarr_group, 1)]
tomogram_data_bin2 = np.array(zarr_array_bin2)
