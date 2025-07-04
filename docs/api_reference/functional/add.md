# Add Operations

The `copick.ops.add` module provides functions for adding data to Copick projects, including runs, voxel spacings, tomograms, and features. These functions handle the creation and storage of data entities with proper validation and metadata management.

## Functions

::: copick.ops.add.add_run
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick.ops.add.get_or_create_run
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick.ops.add.add_voxelspacing
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick.ops.add.get_or_create_voxelspacing
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick.ops.add.add_tomogram
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick.ops.add.add_features
    options:
        show_root_heading: true
        show_root_full_path: true

## Usage Examples

### Adding a Run

```python
from copick.ops.add import add_run
from copick.impl.filesystem import CopickRootFSSpec

# Open a project
root = CopickRootFSSpec.from_file("config.json")

# Add a new run
run = add_run(root, "experiment_001", exist_ok=True, log=True)
```

### Adding a Tomogram

```python
import numpy as np
from copick.ops.add import add_tomogram

# Create sample volume data
volume = np.random.rand(512, 512, 512).astype(np.float32)

# Add tomogram with pyramid generation
tomogram = add_tomogram(
    root=root,
    run="experiment_001",
    tomo_type="wbp",
    volume=volume,
    voxel_spacing=10.0,
    create_pyramid=True,
    pyramid_levels=4,
    log=True
)
```

### Adding Features

```python
# Add computed features to a tomogram
features = add_features(
    root=root,
    run="experiment_001",
    voxel_spacing=10.0,
    tomo_type="wbp",
    feature_type="membrane_segmentation",
    features_vol=segmentation_volume,
    log=True
)
```
