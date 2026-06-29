# Converters

The `copick_utils.converters` module converts between copick data types — picks,
segmentations, and meshes. Each converter reads copick entities (or raw arrays)
and writes a new entity back into the run.

These are the functional building blocks behind the `copick convert ...` CLI
commands; import and call them directly when scripting.

## Picks → Segmentation, Mesh, and geometry

::: copick_utils.converters.segmentation_from_picks.segmentation_from_picks
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick_utils.converters.mesh_from_picks.mesh_from_picks
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick_utils.converters.sphere_from_picks.sphere_from_picks
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick_utils.converters.ellipsoid_from_picks.ellipsoid_from_picks
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick_utils.converters.plane_from_picks.plane_from_picks
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick_utils.converters.surface_from_picks.surface_from_picks
    options:
        show_root_heading: true
        show_root_full_path: true

## Segmentation ↔ Mesh ↔ Picks

::: copick_utils.converters.mesh_from_segmentation.mesh_from_segmentation
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick_utils.converters.segmentation_from_mesh.segmentation_from_mesh
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick_utils.converters.picks_from_segmentation.picks_from_segmentation
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick_utils.converters.picks_from_mesh.picks_from_mesh
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick_utils.converters.caps_from_mesh.caps_from_mesh
    options:
        show_root_heading: true
        show_root_full_path: true

## Usage Examples

### Paint picks into a segmentation volume

```python
import numpy as np

import copick
from copick_utils.converters.segmentation_from_picks import segmentation_from_picks

root = copick.from_file("config.json")
run = root.get_run("TS_001")

# Paint a sphere at every pick into a new multiscale segmentation.
seg, stats = segmentation_from_picks(
    picks=run.get_picks(object_name="ribosome")[0],
    run=run,
    object_name="ribosome",
    session_id="painted-001",
    user_id="copick-utils",
    radius=80.0,            # angstroms
    voxel_spacing=10.0,
    tomo_type="wbp",
)
print(stats)
```

### Extract the caps of a slab mesh

```python
import copick
from copick_utils.converters.caps_from_mesh import caps_from_mesh

root = copick.from_file("config.json")
run = root.get_run("TS_001")

# Keep only the top/bottom faces of a closed slab box, dropping the side walls.
caps, stats = caps_from_mesh(
    mesh=run.get_meshes(object_name="valid-sample")[0],
    run=run,
    object_name="valid-sample-caps",
    session_id="0",
    user_id="copick-utils",
    which="both",
)
```
