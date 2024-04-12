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
            |-- [xx.yyy]_[user_id | tool_name]_[session_id | 0]_[object_name].zarr (spec: src/models.py:TBD)
            |   |-- [multiscale subdirectories according to OME-NGFF spec at 100% scale, 50% and 25% scale]
            |-- [xx.yyy]_[user_id | tool_name]_[session_id | 0]_[name]_multilabel.zarr (spec: src/models.py:TBD)
                |-- [multiscale subdirectories according to OME-NGFF spec at 100% scale, 50% and 25% scale]
```

## Sample Data

A test set is hosted on [zenodo](https://doi.org/10.5281/zenodo.10905908).

The fsspec implementation allows the dataset to be split into a static and an overlay part. The static part is read-only
and contains the original data. The overlay part is read-write and contains the user-specific annotations.

### Config for identical location

```json
{
    "name": "test",
    "description": "A test project.",
    "version": "1.0.0",

    "pickable_objects": [
        {
            "name": "proteasome",
            "is_particle": true,
            "pdb_id": "3J9I",
            "label": 1,
            "color": [255, 0, 0, 255]
        },
        {
            "name": "ribosome",
            "is_particle": true,
            "pdb_id": "7P6Z",
            "label": 2,
            "color": [0, 255, 0, 255]
        },
        {
            "name": "membrane",
            "is_particle": false,
            "label": 3,
            "color": [0, 0, 0, 255]
        }
    ],

    "overlay_root": "local:///PATH/TO/sample_project",
    "static_root": "local:///PATH/TO/sample_project",

    "overlay_fs_args": {
        "auto_mkdir": true
    }
}
```

### Config for static remote and mutable local dataset

This has the additional `s3fs` requirement.

```json
{
    "name": "test",
    "description": "A test project.",
    "version": "1.0.0",

    "pickable_objects": [
        {
            "name": "proteasome",
            "is_particle": true,
            "pdb_id": "3J9I",
            "label": 1,
            "color": [255, 0, 0, 255]
        },
        {
            "name": "ribosome",
            "is_particle": true,
            "pdb_id": "7P6Z",
            "label": 2,
            "color": [0, 255, 0, 255]
        },
        {
            "name": "membrane",
            "is_particle": false,
            "label": 3,
            "color": [0, 0, 0, 255]
        }
    ],

    "overlay_root": "local:///PATH/TO/sample_project",
    "static_root": "s3://bucket/path/to/sample_project",

    "overlay_fs_args": {
        "auto_mkdir": true
    }
}
```

### API overview
```python
from copick.impl.filesystem import CopickRootFSSpec
import zarr

# Project root
root = CopickRootFSSpec.from_file("/PATH/TO/sample_project/copick_config_filesystem.json")

## Root API
root.config # CopickConfig object
root.runs # List of run objects (lazy loading from filesystem location(s))
root.get_run("run_name") # Get a run by name
run = root.new_run("run_name") # Create a new run (appends to the list of runs and creates directory in overlay fs location)
root.refresh() # Refresh the list of runs from filesystem location(s)

## Run API
# Hierarchical objects (lazy loading from filesystem location(s))
run.picks # List of pick objects
run.meshes # List of mesh objects
run.segmentations # List of segmentation objects
run.voxel_spacings # List of voxel spacing objects

# Create new objects
run.new_pick("user_id", "session_id", "object_name") # Create a new pick object (appends to the list of picks and creates file in overlay fs location)
run.new_mesh("user_id", "session_id", "object_name") # Create a new mesh object (appends to the list of meshes and creates file in overlay fs location)
run.new_segmentation("user_id", "session_id") # Create a new segmentation object (appends to the list of segmentations and creates zarr file in overlay fs location)
run.new_voxel_spacing(10.000) # Create a new voxel spacing object (appends to the list of voxel spacings and creates directory in overlay fs location)

# Get objects by name
run.get_picks(object_name="object_name") # Get all picks (list) for this run with a given object name
# ... similar for meshes, segmentations, voxel spacings

## Pick API
pick = run.picks[0] # Get a pick object
pick.points # List of CopickPoint objects

## Mesh API
mesh = run.meshes[0] # Get a mesh object
mesh.mesh # Trimesh scene object

## Segmentation API
segmentation = run.segmentations[0] # Get a segmentation object
segmentation.zarr() # zarr.storage.FSStore object

## VoxelSpacing API
voxel_spacing = run.voxel_spacings[0] # Get a voxel spacing object
voxel_spacing.tomograms # List of CopickTomogram objects

## Tomogram API
tomogram = voxel_spacing.tomograms[0] # Get a tomogram object
tomogram.zarr() # zarr.storage.FSStore object
tomogram.features # List of CopickTomogramFeature objects


# Example usage
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
