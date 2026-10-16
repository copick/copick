"""Read a tilt series and its per-image metadata."""

import copick
import zarr
from copick.util.ome import get_level_path

# Initialize the root object from a configuration file
root = copick.from_file("path/to/config.json")

# Get the tilt series of type 'raw' of the run named 'TS_001'
run = root.get_run("TS_001")
tilt_series = run.get_tilt_series("raw")

# All images (section, y, x) at full size, and one image binned by 4 (the third level)
images = tilt_series.numpy()
group = zarr.open_group(tilt_series.zarr(), mode="r")
image_bin4 = tilt_series.section(0, zarr_group=get_level_path(group, 2))

# Per-image metadata: stage angle, acquisition order, pre-exposure dose and CTF
metadata = tilt_series.metadata
print(metadata.pixel_size, metadata.ctf_status)
for image in metadata.images:
    print(image.section, image.nominal_tilt_angle, image.acquisition_order, image.accumulated_dose, image.ctf)
