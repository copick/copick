# Sync Operations

The `copick.ops.sync` module provides functions for synchronizing data between Copick projects, including picks, meshes, segmentations, and tomograms. These functions enable efficient copying and migration of annotations and volume data between different Copick projects with support for parallel processing, name mapping, and user filtering.

## Core Features

- **Parallel Processing**: Multi-threaded synchronization for improved performance
- **Name Mapping**: Flexible mapping of source names to target names for runs, objects, and users
- **User Filtering**: Selective synchronization based on user IDs
- **Object Validation**: Automatic creation of missing pickable objects in target projects
- **Progress Tracking**: Optional logging and progress reporting
- **Error Handling**: Comprehensive error reporting with detailed failure information

## Functions

::: copick.ops.sync.sync_picks
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick.ops.sync.sync_meshes
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick.ops.sync.sync_segmentations
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick.ops.sync.sync_tomograms
    options:
        show_root_heading: true
        show_root_full_path: true

## Usage Examples

### Basic Synchronization

```python
import copick
from copick.ops.sync import sync_picks

# Load source and target projects
source_root = copick.from_file("source_config.json")
target_root = copick.from_file("target_config.json")

# Sync all picks from all runs
sync_picks(
    source_root=source_root,
    target_root=target_root,
    log=True
)
```

### Selective Synchronization with Name Mapping

```python
# Sync specific runs with name mapping
sync_picks(
    source_root=source_root,
    target_root=target_root,
    source_runs=["run1", "run2"],
    target_runs={"run1": "experiment_A", "run2": "experiment_B"},
    source_objects=["ribosome", "membrane"],
    target_objects={"ribosome": "ribo", "membrane": "mem"},
    log=True
)
```

### User-Specific Synchronization

```python
# Sync picks from specific users with user ID mapping
sync_picks(
    source_root=source_root,
    target_root=target_root,
    source_users=["user123", "user456"],
    target_users={"user123": "analyst1", "user456": "analyst2"},
    exist_ok=True,  # Allow overwriting existing picks
    max_workers=8,  # Use more threads for faster processing
    log=True
)
```

### Synchronizing Segmentations with Voxel Spacing Filtering

```python
from copick.ops.sync import sync_segmentations

# Sync segmentations for specific voxel spacings
sync_segmentations(
    source_root=source_root,
    target_root=target_root,
    voxel_spacings=[10.0, 20.0],  # Only sync these voxel spacings
    source_names=["membrane", "organelle"],
    target_names={"membrane": "cell_membrane", "organelle": "mitochondria"},
    log=True
)
```

### Synchronizing Tomograms with Type Mapping

```python
from copick.ops.sync import sync_tomograms

# Sync tomograms with type mapping
sync_tomograms(
    source_root=source_root,
    target_root=target_root,
    voxel_spacings=[10.0],
    source_tomo_types=["wbp", "raw"],
    target_tomo_types={"wbp": "filtered", "raw": "original"},
    exist_ok=True,
    log=True
)
```

### Complete Multi-Data Type Synchronization

```python
from copick.ops.sync import sync_picks, sync_meshes, sync_segmentations

# Sync multiple data types in sequence
data_types = [
    (sync_picks, {}),
    (sync_meshes, {}),
    (sync_segmentations, {"voxel_spacings": [10.0, 20.0]})
]

common_args = {
    "source_root": source_root,
    "target_root": target_root,
    "source_runs": ["run1", "run2"],
    "target_runs": {"run1": "exp1", "run2": "exp2"},
    "max_workers": 6,
    "log": True
}

for sync_func, extra_args in data_types:
    print(f"Synchronizing {sync_func.__name__}...")
    sync_func(**common_args, **extra_args)
    print(f"Completed {sync_func.__name__}")
```

## Common Patterns

### Name Mapping Syntax

All synchronization functions support flexible name mapping using dictionaries:

```python
# Run name mapping
target_runs = {
    "source_run1": "target_run1",
    "source_run2": "target_run2"
}

# Object name mapping
target_objects = {
    "ribosome": "large_ribosomal_subunit",
    "membrane": "plasma_membrane",
    "vesicle": "transport_vesicle"
}

# User ID mapping
target_users = {
    "original_user": "new_user_id",
    "temp_user": "permanent_user"
}
```

### Error Handling and Logging

```python
import logging

# Configure logging for detailed output
logging.basicConfig(level=logging.INFO)

try:
    sync_picks(
        source_root=source_root,
        target_root=target_root,
        log=True  # Enable verbose logging
    )
except Exception as e:
    print(f"Synchronization failed: {e}")
    # Check logs for detailed error information
```

### Performance Optimization

```python
# Optimize for large datasets
sync_picks(
    source_root=source_root,
    target_root=target_root,
    max_workers=12,  # Increase parallelism
    exist_ok=True,   # Skip duplicate checks
    log=False        # Reduce logging overhead
)
```

## Integration with CLI

The sync operations are also available through the CLI interface:

```bash
# Basic synchronization
copick sync picks -c source_config.json --target-config target_config.json

# With name mapping and user filtering
copick sync picks -c source_config.json --target-config target_config.json \
    --source-runs "run1,run2" \
    --target-runs "run1:exp1,run2:exp2" \
    --source-users "user1,user2" \
    --target-users "user1:analyst1,user2:analyst2" \
    --log

# From CryoET Data Portal
copick sync picks \
    --source-dataset-ids "12345,67890" \
    --target-config target_config.json \
    --log
```
