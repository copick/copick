## 2. Multilayer Interface (multilayer.py)

The `multilayer.py` file defines classes that extend the base models from `models.py` by adding the ability to query
copick data artifacts from multiple storage locations, a local database, a local cache, and the cryoET data portal.

### 2.1 Core Concept

The multilayer system is comprised of the following types of layers: 

- At most one cryoET data portal layer
- As many read-only fsspec-based layers as needed
- As many read-write fsspec-based layers as needed
- One optional local cache layer (specialized fsspec-based layer for local cache)
- One optional local database layer (using sqlite for storing metadata and references to data in other layers, as well as loaded copick points)

The layers are combined in a stack, with the following priorities for fetching data:

1. Local database
2. Local cache
3. Read-write fsspec layers
4. Read-only fsspec layers
5. CryoET data portal

Within the groups of read-only and read-write layers, the order of priority is determined by an integer priority value. This priority value is also used to determine the order of layers in the stack for simplicity.

Each layer type implements the full Copick interface, with the following exceptions:

- Read-only layers do not implement the `store()` method
- Read-write layers implement the `store()` method
- The `ensure()` method is implemented by all layers, but raises an error if called on a read-only layer
- The `refresh()` method is implemented by all layers
- The `new()` method is implemented by read-write layers
- The database layer is to be considered read-only, as it only contains metadata and references to data in other layers

The `multilayer.py` file also contains a `CopickXXXML` classes that implement the Copick interface and provides a unified view of the stack of layers (where XXX is the type of the Copick object, e.g. `Root`, `Picks`, `Mesh`, `Segmentation`, etc.).

The `CopickXXXML` classes are implemented as proxies to the actual layer objects, and are used to provide a unified view of the stack of layers. Each method of the `CopickXXXML` class calls the 
corresponding method of the layer objects in order of priority and returns the results. In case of duplicate data, the highest priority layer is chosen. Each method in Multilayer also allows to specify specific layers by name to be used in the method call.

### 2.2 Key Classes

#### CopickRootML

Implements the `CopickRoot` interface and provides a unified view of the stack of layers.

#### CopickRunML

Implements the `CopickRun` interface and provides a unified view of the stack of layers.

#### CopickPicksML

Implements the `CopickPicks` interface and provides a unified view of the stack of layers.

#### CopickMeshML

Implements the `CopickMesh` interface and provides a unified view of the stack of layers.

#### CopickSegmentationML

Implements the `CopickSegmentation` interface and provides a unified view of the stack of layers.

#### CopickFeaturesML

Implements the `CopickFeatures` interface and provides a unified view of the stack of layers.

#### CopickVoxelSpacingML

Implements the `CopickVoxelSpacing` interface and provides a unified view of the stack of layers.

#### CopickTomogramML

Implements the `CopickTomogram` interface and provides a unified view of the stack of layers.

#### CopickObjectML

Implements the `CopickObject` interface and provides a unified view of the stack of layers.

#### CopickConfigML

Implements the `CopickConfig` interface and provides a unified view of the stack of layers.


