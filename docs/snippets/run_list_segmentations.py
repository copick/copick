"""Print all segmentations for a run in a copick project."""

import copick

# Initialize the root object from a configuration file
root = copick.from_file("path/to/config.json")

# Get the run named 'TS_001'
run = root.get_run("TS_001")

# List all available segmentations for the run
segmentations = run.segmentations
for segmentation in segmentations:
    print(f"Segmentation: {segmentation.name}")
