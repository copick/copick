"""Read a mesh from a CopickMesh object and display it."""

import copick

# Initialize the root object from a configuration file
root = copick.from_file("path/to/config.json")

# Get the first run in the project
run = root.runs[0]

# Get a membrane mesh from user 'bob'
mesh = run.get_meshes(object_name="membrane", user_id="bob")[0]

# Show the mesh
mesh.mesh.show()
