# I/O Helpers

The `copick_utils.io` module provides convenience wrappers for reading and
writing copick data as NumPy arrays, handling availability checks and OME-Zarr
plumbing for you.

## Readers

::: copick_utils.io.readers.tomogram
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick_utils.io.readers.segmentation
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick_utils.io.readers.coordinates
    options:
        show_root_heading: true
        show_root_full_path: true

## Writers

::: copick_utils.io.writers.tomogram
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick_utils.io.writers.segmentation
    options:
        show_root_heading: true
        show_root_full_path: true

## Usage Examples

### Read a tomogram and pick coordinates

```python
import copick
from copick_utils.io import readers

root = copick.from_file("config.json")
run = root.get_run("TS_001")

# Tomogram as a NumPy array (Z, Y, X).
volume = readers.tomogram(run, voxel_size=10.0, algorithm="wbp")

# Pick coordinates as an (N, 3) array.
coords = readers.coordinates(run, name="ribosome", user_id="alice", session_id="1")
```

### Write a segmentation back into the run

```python
from copick_utils.io import writers

writers.segmentation(
    run,
    seg_vol,                 # NumPy label volume (Z, Y, X)
    user_id="copick-utils",
    name="membrane",
    session_id="0",
    voxel_size=10.0,
    multilabel=True,
)
```
