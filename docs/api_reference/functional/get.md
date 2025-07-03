# Get Operations

The `copick.ops.get` module provides query functions for retrieving data from Copick projects. These functions offer convenient ways to search, filter, and access runs, tomograms, picks, segmentations, and other data entities.

## Functions

::: copick.ops.get.get_segmentations
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick.ops.get.get_meshes
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick.ops.get.get_picks
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick.ops.get.get_voxelspacings
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick.ops.get.get_tomograms
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick.ops.get.get_features
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick.ops.get.get_runs
    options:
        show_root_heading: true
        show_root_full_path: true

## Usage Examples

### Getting Runs

```python
from copick.ops.get import get_runs
from copick.impl.filesystem import CopickRootFSSpec

# Open a project
root = CopickRootFSSpec.from_file("config.json")

# Get all runs
all_runs = get_runs(root)

# Get runs with specific names
selected_runs = get_runs(root, run_names=["experiment_001", "experiment_002"])

# Get runs with query filtering
filtered_runs = get_runs(root, query={"tilt_series_id": "12345"})
```

### Getting Tomograms

```python
from copick.ops.get import get_tomograms

# Get all tomograms from specific runs
tomograms = get_tomograms(
    root=root,
    run_names=["experiment_001"],
    voxel_spacings=[10.0, 20.0],
    tomo_types=["wbp", "ctf_corrected"]
)

# Get tomograms with user filtering
user_tomograms = get_tomograms(
    root=root,
    user_id="researcher_001",
    session_id="session_123"
)
```

### Getting Picks

```python
from copick.ops.get import get_picks

# Get picks for specific objects
ribosome_picks = get_picks(
    root=root,
    object_names=["ribosome"],
    user_id="annotation_tool",
    run_names=["experiment_001"]
)

# Get picks with confidence filtering
high_confidence_picks = get_picks(
    root=root,
    query={"confidence": {"$gt": 0.8}}
)
```

### Getting Segmentations

```python
from copick.ops.get import get_segmentations

# Get segmentations by type
membrane_segmentations = get_segmentations(
    root=root,
    segmentation_types=["membrane", "organelle"],
    voxel_spacings=[10.0]
)

# Get multilabel segmentations
multilabel_segs = get_segmentations(
    root=root,
    is_multilabel=True,
    user_id="segmentation_model"
)
```
