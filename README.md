# copick
Definitions for a collaborative cryoET annotation tool.

## Data Spec

Shared data is organized as follows:

```
[copick_root]/
|-- copick_config.json (spec: src/io/copick_models.py:CopickConfig)
|-- ObjectMrcs/
    |-- [object_name].mrc (index: src/io/copick_models.py:CopickConfig.pickable_objects.object_name)
|-- ExperimentRuns
    |-- [run_name]/ (index: src/io/copick_models.py:CopickPicks.runs)
        |-- VoxelSpacing[xx.yyy]/
            |-- [tomotype].zarr/
                |-- [subdirectories according to OME-NGFF spec at 100%, 50% and 25% scale]
        |-- VoxelSpacing[x2.yy2]/
            |-- [tomotype].zarr/
                |-- [subdirectories according to OME-NGFF spec at 100%, 50% and 25% scale]
        |-- Annotations/
            |-- [user_id | tool_name]_[session_id | 0]_[object_name].json (spec: src/io/copick_models.py:CopickPicks)
```