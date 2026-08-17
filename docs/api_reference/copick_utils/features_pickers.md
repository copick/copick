# Features & Pickers

Small helpers for feature extraction and grid picking.

## Features

`copick_utils.features` computes multiscale image features (intensity, edges,
texture) from a tomogram using scikit-image — useful as inputs to pixel
classifiers.

::: copick_utils.features.skimage.compute_skimage_features
    options:
        show_root_heading: true
        show_root_full_path: true

## Pickers

`copick_utils.pickers` provides simple, non-ML pick generators.

::: copick_utils.pickers.grid_picker.grid_picker
    options:
        show_root_heading: true
        show_root_full_path: true

## Usage Examples

### Generate a regular grid of picks

```python
import copick
from copick_utils.pickers.grid_picker import grid_picker

root = copick.from_file("config.json")
run = root.get_run("TS_001")
tomo = run.get_voxel_spacing(10.0).get_tomograms("wbp")[0]

picks = grid_picker(
    pickable_obj=root.get_object("ribosome"),
    run=run,
    tomogram=tomo,
    grid_spacing_factor=1.0,   # spacing as a multiple of the object radius
    session_id="0",
    user_id="gridPicker",
)
```

### Compute scikit-image features for a tomogram

```python
from copick_utils.features.skimage import compute_skimage_features

features = compute_skimage_features(
    tomogram=tomo,
    feature_type="skimage-multiscale",
    copick_root=root,
    intensity=True,
    edges=True,
    texture=True,
)
```

`compute_skimage_features` returns feature-major data shaped `(feature, z, y, x)`. Copick stores that output through
the same centralized OME-Zarr writer used by `CopickFeatures.from_numpy()` and `copick.ops.add_features()`. Existing 3D
feature volumes remain `(z, y, x)`. By default, 4D arrays use one feature per inner chunk and one padded spatial shard
per feature volume; pass a spatial 3-tuple or an explicit 4D tuple through `chunks`, and an explicit dimension-matched
tuple through `shards`, to override the layout.
