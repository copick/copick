## Abstract Data Entities

The **copick** API allows object-oriented access to cryoET data entities. Each data entity has a corresponding metadata
model defined in pydantic. There is a set of abstract base classes that define the common interface for all
data entities and the associated metadata models. The data entities are organized in a hierarchy that reflects the
on-disk data model of **copick** and the structure of a typical cryoET dataset.

The abstract data entities are defined in the `copick.models` module and given in the table below.

| Data Entity         | Class                          | Metadata Class                   |
|---------------------|--------------------------------|----------------------------------|
| Project Root        | [CopickRoot][CopickRoot]       | [CopickConfig][CopickConfig]     |
| ... Copick Object   | [CopickObject][CopickObject]   | [PickableObject][PickableObject] |
| ... Run             | [CopickRun][CopickRun]         | [CopickRunMeta][CopickRunMeta]   |
| ...... Picks        | [CopickPicks][CopickPicks]     | [CopickPicksFile][CopickPicksFile] |
| ...... Mesh         | [CopickMesh][CopickMesh]       | [CopickMeshMeta][CopickMeshMeta] |
| ...... Segmentation | [CopickSegmentation][CopickSegmentation] | [CopickSegmentationMeta][CopickSegmentationMeta] |
| ...... Voxel Spacing | [CopickVoxelSpacing][CopickVoxelSpacing] | [CopickVoxelSpacingMeta][CopickVoxelSpacingMeta] |
| ......... Tomogram  | [CopickTomogram][CopickTomogram] | [CopickTomogramMeta][CopickTomogramMeta] |
| ......... Features  | [CopickFeatures][CopickFeatures] | [CopickFeaturesMeta][CopickFeaturesMeta] |


## Implementations

There are concrete implementations of the abstract data entities that are used to access data in a **copick** dataset.

* **Overlay:** An extenstion to the abstract **copick** API implementation that adds methods to seamlessly overlay data from different sources.
* **Filesystem:** A concrete implementation that reads and writes data to any storage supported by `fsspec`.
