# Stats Operations

The `copick.ops.stats` module provides statistical analysis functions for Copick projects. These functions generate comprehensive statistics about picks, meshes, and segmentations including counts, distributions, and frequency analysis.

## Functions

::: copick.ops.stats.picks_stats
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick.ops.stats.meshes_stats
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick.ops.stats.segmentations_stats
    options:
        show_root_heading: true
        show_root_full_path: true

## Usage Examples

### Picks Statistics

```python
from copick.ops.stats import picks_stats
from copick.impl.filesystem import CopickRootFSSpec

# Open a project
root = CopickRootFSSpec.from_file("config.json")

# Get comprehensive picks statistics
all_picks_stats = picks_stats(root)
print(f"Total picks: {all_picks_stats['total_picks']}")
print(f"Distribution by run: {all_picks_stats['distribution_by_run']}")

# Get statistics for specific runs and objects
filtered_stats = picks_stats(
    root=root,
    runs=["experiment_001", "experiment_002"],
    object_name=["ribosome", "proteasome"],
    user_id=["annotator_1"]
)

# Enable parallel processing for large projects
parallel_stats = picks_stats(
    root=root,
    parallel=True,
    workers=12,
    show_progress=True
)
```

### Meshes Statistics

```python
from copick.ops.stats import meshes_stats

# Get mesh statistics with filtering
mesh_stats = meshes_stats(
    root=root,
    runs=["experiment_001"],
    user_id=["modeler_1", "modeler_2"],
    object_name=["ribosome"]
)

print(f"Total meshes: {mesh_stats['total_meshes']}")
print(f"Distribution by user: {mesh_stats['distribution_by_user']}")
print(f"Frequent combinations: {mesh_stats['session_user_object_combinations']}")

# Get statistics for all meshes with parallel processing
all_mesh_stats = meshes_stats(root, parallel=True)
```

### Segmentations Statistics

```python
from copick.ops.stats import segmentations_stats

# Get segmentation statistics with comprehensive filtering
seg_stats = segmentations_stats(
    root=root,
    runs=["experiment_001"],
    user_id=["segmentation_model"],
    name=["membrane", "organelle"],
    voxel_size=[10.0, 20.0],
    is_multilabel=True
)

print(f"Total segmentations: {seg_stats['total_segmentations']}")
print(f"Distribution by name: {seg_stats['distribution_by_name']}")
print(f"Distribution by voxel size: {seg_stats['distribution_by_voxel_size']}")
print(f"Distribution by multilabel: {seg_stats['distribution_by_multilabel']}")

# Analyze combination frequencies
combinations = seg_stats['session_user_voxelspacing_multilabel_combinations']
most_frequent = max(combinations.items(), key=lambda x: x[1])
print(f"Most frequent combination: {most_frequent[0]} ({most_frequent[1]} occurrences)")
```

## Return Value Structure

### Picks Statistics

```python
{
    "total_picks": int,                    # Total number of individual pick points
    "total_pick_files": int,               # Total number of pick files
    "distribution_by_run": {               # Pick count per run
        "run_name": pick_count
    },
    "distribution_by_user": {              # Pick count per user
        "user_id": pick_count
    },
    "distribution_by_session": {           # Pick count per session
        "session_id": pick_count
    },
    "distribution_by_object": {            # Pick count per object
        "object_name": pick_count
    }
}
```

### Meshes Statistics

```python
{
    "total_meshes": int,                   # Total number of mesh files
    "distribution_by_user": {              # Mesh count per user
        "user_id": mesh_count
    },
    "distribution_by_session": {           # Mesh count per session
        "session_id": mesh_count
    },
    "distribution_by_object": {            # Mesh count per object
        "object_name": mesh_count
    },
    "session_user_object_combinations": {  # Frequency of specific combinations
        "session_user_object": frequency
    }
}
```

### Segmentations Statistics

```python
{
    "total_segmentations": int,            # Total number of segmentation files
    "distribution_by_user": {              # Segmentation count per user
        "user_id": segmentation_count
    },
    "distribution_by_session": {           # Segmentation count per session
        "session_id": segmentation_count
    },
    "distribution_by_name": {              # Segmentation count per name
        "name": segmentation_count
    },
    "distribution_by_voxel_size": {        # Segmentation count per voxel size
        "voxel_size": segmentation_count
    },
    "distribution_by_multilabel": {        # Segmentation count by multilabel status
        "True/False": segmentation_count
    },
    "session_user_voxelspacing_multilabel_combinations": {  # Frequency of specific combinations
        "session_user_name_voxelsize_multilabel": frequency
    }
}
```

## Performance Considerations

### Parallel Processing

All stats functions support parallel processing for improved performance with large projects:

```python
# Enable parallel processing with custom worker count
stats = picks_stats(
    root=root,
    parallel=True,
    workers=16,  # Adjust based on your system
    show_progress=True
)
```
