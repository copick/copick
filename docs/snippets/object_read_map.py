"""Read a density map from an object's zarr-store into a numpy array."""

import copick

# Initialize the root object from a configuration file
root = copick.from_file("path/to/config.json")

# Get the object named 'proteasome'
proteasome = root.get_object("proteasome")

# Read the density map for the object from its zarr-store
density_map = proteasome.numpy()
