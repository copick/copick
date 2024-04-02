# copick
Definitions for a collaborative cryoET annotation tool.

## Data Spec

Shared data is organized as follows:

```
[copick_root]/
|-- copick_config.json (spec: src/models.py:CopickConfig)
|-- ParticleMrcs/
    |-- [object_id]_[object_name].mrc (index: src/models.py:CopickConfig.pickable_objects.object_name)
|-- ExperimentRuns
    |-- [run_name]/ (index: src/io/copick_models.py:CopickPicks.runs)
        |-- VoxelSpacing[xx.yyy]/
        |   |-- [tomotype].zarr/
        |   |   |-- [multiscale subdirectories according to OME-NGFF spec at 100%, 50% and 25% scale]
        |   |-- [tomotype]_[feature_type]_features.zarr/
        |       |-- [multiscale subdirectories according to OME-NGFF spec at 100% scale]
        |-- VoxelSpacing[x2.yy2]/
        |   |-- [tomotype].zarr/
        |   |   |-- [multiscale subdirectories according to OME-NGFF spec at 100%, 50% and 25% scale]
        |   |-- [tomotype]_[feature_type]_features.zarr/
        |       |-- [multiscale subdirectories according to OME-NGFF spec at 100% scale]
        |-- Picks/
        |   |-- [user_id | tool_name]_[session_id | 0]_[object_name].json (spec: src/models.py:CopickPicks)
        |-- Meshes/
        |   |-- [user_id | tool_name]_[session_id | 0]_[object_name].glb (spec: src/models.py:TBD)
        |-- Segmentations/
            |-- [user_id | tool_name]_[session_id | 0].zarr (spec: src/models.py:TBD)
                |-- [multiscale subdirectories according to OME-NGFF spec at 100% scale, 50% and 25% scale]
```

## Sample Data

A test set is hosted on [zenodo](https://doi.org/10.5281/zenodo.10905908).

### Example / Test

```python
from copick.impl.filesystem import CopickRootFSSpec
import zarr

root = CopickRootFSSpec.from_file("/PATH/TO/sample_project/copick_config_filesystem.json")
# List of runs
print(root.runs)

# Points
print(root.runs[0].picks[0].points)

# List of meshes
print(root.runs[0].meshes)

# List of segmentations
print(root.runs[0].segmentations)

# List of voxel spacings
print(root.runs[0].voxel_spacings)

# List of tomograms
print(root.runs[0].voxel_spacings[0].tomograms)

# Get Zarr store for a tomogram
print(zarr.open_group(root.runs[0].voxel_spacings[0].tomograms[0].zarr()).info)

# Get Zarr store for a tomogram feature
print(root.runs[0].voxel_spacings[0].tomograms[1].features)
print(zarr.open_group(root.runs[0].voxel_spacings[0].tomograms[1].features[0].zarr()).info)

# Get a pick file's contents
print(root.runs[0].picks[0].load())

# Get a mesh file's contents
print(root.runs[0].meshes[0].mesh)

# Get a Zarr store for a segmentation
print(root.runs[0].segmentations[0].path)
print(zarr.open_group(root.runs[0].segmentations[0].zarr()).info)

```
