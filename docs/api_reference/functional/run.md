# Run Operations

The `copick.ops.run` module provides utilities for parallel processing across multiple runs in Copick projects. The main function `map_runs` enables efficient execution of operations on multiple runs using thread or process-based parallelism.

## Functions

::: copick.ops.run.map_runs
    options:
        show_root_heading: true
        show_root_full_path: true

## Usage Examples

### Basic Parallel Processing

```python
from copick.ops.run import map_runs
from copick.impl.filesystem import CopickRootFSSpec

# Open a project
root = CopickRootFSSpec.from_file("config.json")

# Define a callback function
def process_run(run, **kwargs):
    """Process a single run - count picks."""
    pick_count = 0
    for picks in run.picks:
        if picks.points:
            pick_count += len(picks.points)
    return pick_count

# Execute on multiple runs
run_names = ["experiment_001", "experiment_002", "experiment_003"]
results = map_runs(
    callback=process_run,
    root=root,
    runs=run_names,
    workers=4,
    parallelism="thread",
    show_progress=True,
    task_desc="Counting picks"
)

# Results is a dictionary: {"experiment_001": 150, "experiment_002": 203, ...}
```

### Processing with Run-Specific Arguments

```python
def segment_tomogram(run, threshold=0.5, model_path=None, **kwargs):
    """Segment tomograms in a run."""
    results = []
    for vs in run.voxel_spacings:
        for tomo in vs.tomograms:
            # Perform segmentation with threshold and model
            segmentation = perform_segmentation(tomo, threshold, model_path)
            results.append(segmentation)
    return results

# Different parameters for each run
run_args = [
    {"threshold": 0.3, "model_path": "model_v1.pth"},
    {"threshold": 0.5, "model_path": "model_v2.pth"},
    {"threshold": 0.7, "model_path": "model_v1.pth"}
]

results = map_runs(
    callback=segment_tomogram,
    root=root,
    runs=run_names,
    run_args=run_args,
    workers=2,
    parallelism="process",  # Use process parallelism for CPU-intensive tasks
    show_progress=True,
    task_desc="Segmenting tomograms"
)
```

### Working with CopickRun Objects

```python
# You can pass CopickRun objects directly instead of names
runs = [root.get_run(name) for name in run_names]

def analyze_run(run, analysis_type="basic", **kwargs):
    """Analyze various aspects of a run."""
    stats = {
        "name": run.name,
        "voxel_spacings": len(run.voxel_spacings),
        "tomograms": sum(len(vs.tomograms) for vs in run.voxel_spacings),
        "picks": len(run.picks),
        "segmentations": len(run.segmentations)
    }
    return stats

results = map_runs(
    callback=analyze_run,
    root=root,
    runs=runs,  # Pass CopickRun objects
    workers=8,
    analysis_type="detailed"  # Additional kwargs
)
```

### Error Handling and Logging

```python
def robust_processing(run, **kwargs):
    """Process with error handling."""
    try:
        # Simulate some processing that might fail
        if run.name == "problematic_run":
            raise ValueError("Simulated error")

        # Normal processing
        return {"status": "success", "data": len(run.picks)}

    except Exception as e:
        # Errors are logged automatically by map_runs
        return {"status": "error", "error": str(e)}

results = map_runs(
    callback=robust_processing,
    root=root,
    runs=run_names,
    workers=4,
    show_progress=True,
    task_desc="Processing with error handling"
)

# Check results
for run_name, result in results.items():
    if result is None:
        print(f"Run {run_name} failed completely")
    elif result.get("status") == "error":
        print(f"Run {run_name} had error: {result['error']}")
    else:
        print(f"Run {run_name} succeeded: {result}")
```


## Callback Function Requirements

Your callback function must follow this signature:

```python
def callback(run: CopickRun, **run_args, **kwargs) -> Any:
    """
    Process a single run.

    Args:
        run: The CopickRun object to process
        **run_args: Run-specific arguments from run_args list
        **kwargs: Global arguments passed to map_runs

    Returns:
        Any: Result data (will be stored in results dict)
    """
    pass
```
