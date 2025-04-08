"""Print all objects and runs in a copick project."""

import copick

# Initialize the root object from a configuration file
root = copick.from_file("path/to/config.json")

# List all available objects
obj_info = [(o.name, o.label) for o in root.pickable_objects]

print("Pickable objects in this project:")
for name, label in obj_info:
    print(f"  {name}: {label}")

# Execute a function on each run in the project
runs = root.runs

print("Runs in this project:")
for run in runs:
    print(f"Run: {run.name}")
    # Do something with the run
