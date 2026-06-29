# Logical Operations

The `copick_utils.logical` module performs boolean and distance-based operations
on meshes, segmentations, and picks. These are the functional building blocks
behind the `copick logical ...` CLI commands.

## Mesh boolean operations

::: copick_utils.logical.mesh_operations.mesh_union
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick_utils.logical.mesh_operations.mesh_difference
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick_utils.logical.mesh_operations.mesh_intersection
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick_utils.logical.mesh_operations.mesh_exclusion
    options:
        show_root_heading: true
        show_root_full_path: true

## Segmentation boolean operations

::: copick_utils.logical.segmentation_operations.segmentation_union
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick_utils.logical.segmentation_operations.segmentation_difference
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick_utils.logical.segmentation_operations.segmentation_intersection
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick_utils.logical.segmentation_operations.segmentation_exclusion
    options:
        show_root_heading: true
        show_root_full_path: true

## Distance-based limiting

::: copick_utils.logical.distance_operations.limit_mesh_by_distance
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick_utils.logical.distance_operations.limit_segmentation_by_distance
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick_utils.logical.distance_operations.limit_picks_by_distance
    options:
        show_root_heading: true
        show_root_full_path: true

## Point inclusion / exclusion

::: copick_utils.logical.point_operations.picks_inclusion_by_mesh
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick_utils.logical.point_operations.picks_exclusion_by_mesh
    options:
        show_root_heading: true
        show_root_full_path: true

## Usage Examples

### Keep only picks within a distance of a reference mesh

```python
import copick
from copick_utils.logical.distance_operations import limit_picks_by_distance

root = copick.from_file("config.json")
run = root.get_run("TS_001")

kept, stats = limit_picks_by_distance(
    picks=run.get_picks(object_name="ribosome")[0],
    run=run,
    object_name="ribosome",
    session_id="near-membrane",
    user_id="copick-utils",
    reference_mesh=run.get_meshes(object_name="membrane")[0],
    max_distance=150.0,      # angstroms
)
print(stats)
```

### Union of two meshes

```python
from copick_utils.logical.mesh_operations import mesh_union

merged, stats = mesh_union(
    mesh1=run.get_meshes(object_name="compartment-a")[0],
    mesh2=run.get_meshes(object_name="compartment-b")[0],
    run=run,
    object_name="compartments",
    session_id="0",
    user_id="copick-utils",
)
```
