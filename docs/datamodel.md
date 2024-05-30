The on-disk data model of copick is as follows:


```
📁 copick_root
├─ 📄 copick_config.json
├─ 📁 Objects
│  └─ 📄 [pickable_object_name].zarr
└─ 📁 ExperimentRuns
   └─ 📁 [run_name] (index: src/io/copick_models.py:CopickPicks.runs)
      ├─ 📁 VoxelSpacing[xx.yyy]/
      │  ├─ 📁 [tomotype].zarr/
      │  │  └─ [OME-NGFF spec at 100%, 50% and 25% scale]
      │  └─ 📁 [tomotype]_[feature_type]_features.zarr/
      │     └─ [OME-NGFF spec at 100% scale]
      ├─ 📁 VoxelSpacing[x2.yy2]/
      │  ├─ 📁 [tomotype].zarr/
      │  │  └─ [OME-NGFF spec at 100%, 50% and 25% scale]
      │  └─ 📁 [tomotype]_[feature_type]_features.zarr/
      │     └─ [OME-NGFF spec at 100% scale]
      ├─ 📁 Picks/
      │  └─ 📄 [user_id | tool_name]_[session_id | 0]_[object_name].json
      ├─ 📁 Meshes/
      │  └─ 📄 [user_id | tool_name]_[session_id | 0]_[object_name].glb
      └─ 📁 Segmentations/
         ├─ 📁 [xx.yyy]_[user_id | tool_name]_[session_id | 0]_[object_name].zarr
         │   └─ [OME-NGFF spec at 100% scale, 50% and 25% scale]
         └─ 📁 [xx.yyy]_[user_id | tool_name]_[session_id | 0]_[name]-multilabel.zarr
             └─ [OME-NGFF spec at 100% scale, 50% and 25% scale]
```
