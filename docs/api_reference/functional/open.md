# Open Operations

The `copick.ops.open` module provides functions for opening and creating Copick projects from various sources, including configuration files and CryoET Data Portal datasets.

## Functions

::: copick.ops.open.from_string
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick.ops.open.from_file
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick.ops.open.from_czcdp_datasets
    options:
        show_root_heading: true
        show_root_full_path: true

## Usage Examples

### Opening from Configuration File

```python
from copick.ops.open import from_file

# Open project from configuration file
root = from_file("path/to/config.json")

# Access project data
runs = root.runs
tomograms = root.runs[0].voxel_spacings[0].tomograms
```

### Opening from String Configuration

```python
from copick.ops.open import from_string
import json

# Create configuration as string
config = {
    "name": "My Project",
    "description": "Example project",
    "version": "1.0.0",
    "config_type": "filesystem",
    "static_root": "/path/to/static",
    "overlay_root": "/path/to/overlay",
    "pickable_objects": []
}

# Open project from string
root = from_string(json.dumps(config))
```

### Opening from CryoET Data Portal

```python
from copick.ops.open import from_czcdp_datasets

# Create project from Data Portal dataset
root = from_czcdp_datasets(
    dataset_ids=[10001, 10002],
    overlay_root="/path/to/local/storage",
    config_name="My CryoET Project"
)

# Access portal data with local overlay
runs = root.runs
tomograms = root.runs[0].voxel_spacings[0].tomograms
```
