# Processing

The `copick_utils.process` module provides segmentation-processing utilities:
connected-component analysis, skeletonization, spline fitting, rescaling, label
splitting, valid-box generation, and thickness filtering.

These are the functional building blocks behind the `copick process ...` CLI
commands.

## Connected components

::: copick_utils.process.connected_components.separate_segmentation_components
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick_utils.process.connected_components.separate_connected_components_3d
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick_utils.process.connected_components.extract_individual_components
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick_utils.process.connected_components.print_component_stats
    options:
        show_root_heading: true
        show_root_full_path: true

## Skeletonization

::: copick_utils.process.skeletonize.TubeSkeletonizer3D
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick_utils.process.skeletonize.skeletonize_segmentation
    options:
        show_root_heading: true
        show_root_full_path: true

## Spline fitting

::: copick_utils.process.spline_fitting.SkeletonSplineFitter
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick_utils.process.spline_fitting.fit_spline_to_skeleton
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick_utils.process.spline_fitting.fit_spline_to_segmentation
    options:
        show_root_heading: true
        show_root_full_path: true

## Rescaling

::: copick_utils.process.rescale.rescale_segmentation
    options:
        show_root_heading: true
        show_root_full_path: true

## Label operations

::: copick_utils.process.split_labels.split_multilabel_segmentation
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick_utils.process.split_labels.split_labels_batch
    options:
        show_root_heading: true
        show_root_full_path: true

## Valid-box generation

::: copick_utils.process.validbox.create_validbox_mesh
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick_utils.process.validbox.generate_validbox
    options:
        show_root_heading: true
        show_root_full_path: true

## Thickness filtering

::: copick_utils.process.thickness_filter.thickness_filter_segmentation
    options:
        show_root_heading: true
        show_root_full_path: true

## Usage Examples

### Split a segmentation into connected components

```python
import copick
from copick_utils.process.connected_components import separate_segmentation_components

root = copick.from_file("config.json")
run = root.get_run("TS_001")
seg = run.get_segmentations(name="membrane")[0]

components = separate_segmentation_components(
    segmentation=seg,
    connectivity="all",      # 26-connectivity
    min_size=1000.0,         # drop components smaller than 1000 Å³
    output_user_id="components",
)
print(f"found {len(components)} components")
```

### Rescale a segmentation to a new voxel spacing

```python
from copick_utils.process.rescale import rescale_segmentation

rescaled, stats = rescale_segmentation(
    segmentation=seg,
    run=run,
    object_name="membrane",
    session_id="0",
    user_id="copick-utils",
    target_voxel_spacing=20.0,
    tomo_type="wbp",
)
```
