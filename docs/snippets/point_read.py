"""Read points from a CopickPicks object."""

import copick
import numpy as np

# Initialize the root object from a configuration file
root = copick.from_file("path/to/config.json")

# Get the first run in the project
run = root.runs[0]

# Get 'proteasome' picks of user 'alice'
picks = run.get_picks(object_name="proteasome", user_id="alice")[0]

# Get the points from the picks
point_arr = np.ndarray((len(picks.points), 3))
for idx, pt in enumerate(picks.points):
    point_arr[idx, :] = [pt.location.x, pt.location.y, pt.location.z]
