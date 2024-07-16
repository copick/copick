"""Read a feature map from a zarr-store into a numpy array."""

import copick
import numpy as np
import zarr

# Initialize the root object from a configuration file
root = copick.from_file("path/to/config.json")

# Get the run named 'TS_001'
run = root.get_run("TS_001")

# Get the voxel spacing with a resolution of 10 angstroms
voxel_spacing = run.get_voxel_spacing(10.000)

# Get the tomogram named 'wbp'
tomogram = voxel_spacing.get_tomogram("wbp")

# Get the feature map named 'sobel'
feature_map = tomogram.get_features("sobel")

# Read the feature map from its zarr-store
zarr_array = zarr.open(feature_map.zarr())["0"]
feature_map_data = np.array(zarr_array)
