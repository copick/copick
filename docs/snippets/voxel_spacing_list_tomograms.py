"""Print the list of tomograms for a given voxel spacing."""

import copick

# Initialize the root object from a configuration file
root = copick.from_file("path/to/config.json")

# Get the run named 'TS_001'
run = root.get_run("TS_001")

# Get the voxel spacing with a resolution of 10 angstroms
voxel_spacing = run.get_voxel_spacing(10.000)

# List all available tomograms for the voxel spacing
tomograms = voxel_spacing.tomograms
for tomogram in tomograms:
    print(f"Tomogram: {tomogram.name}")
