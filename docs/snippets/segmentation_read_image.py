"""Read a segmentation from a CopickSegmentation object."""

import copick
import numpy as np
import zarr

# Initialize the root object from a configuration file
root = copick.from_file("path/to/config.json")

# Get the first run in the project
run = root.runs[0]

# Get 'proteasome' segmentation of user 'alice'
segmentation = run.get_segmentations(object_name="proteasome", user_id="alice")[0]

# Get the segmentation array from the segmentation
seg_zarr = zarr.open(segmentation.zarr())["0"]
seg = np.array(seg_zarr)
