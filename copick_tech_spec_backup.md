# CoPick Technical Specification

## 1. Abstract API (models.py)

The `models.py` file defines the core data models and interfaces for the CoPick system. These classes form the foundation of the hierarchical data structure used throughout the application.

### 1.1 Base Models

#### PickableObject
A metadata class that represents objects that can be "picked" (selected or annotated) within tomograms.

**Attributes:**
- `name`: String name of the object
- `is_particle`: Boolean flag indicating whether the object should be represented by points (True) or segmentation masks (False)
- `label`: Optional numeric label/id for the object, used in multilabel segmentation masks
- `color`: Optional RGBA color tuple for visualization
- `emdb_id`: Optional EMDB ID for the object
- `pdb_id`: Optional PDB ID for the object
- `identifier`: Optional identifier (e.g., Gene Ontology ID or UniProtKB accession)
- `map_threshold`: Optional threshold for rendering isosurfaces
- `radius`: Optional radius when displaying particles as spheres

The class includes validators for the `label` and `color` fields, as well as properties and setters for backward compatibility with `go_id`.

#### CopickConfig
The configuration for a CoPick project that defines available objects and optional indexes.

**Attributes:**
- `name`: Optional name of the project
- `description`: Optional description of the project
- `version`: Optional version of the CoPick API
- `pickable_objects`: List of `PickableObject` instances
- `user_id`: Optional unique identifier for the user
- `session_id`: Optional unique identifier for the session
- `runs`: Optional index for run names
- `voxel_spacings`: Optional index for available voxel spacings
- `tomograms`: Optional index for available voxel spacings and tomogram types

Includes a `from_file` class method to load configurations from disk.

#### CopickLocation, CopickPoint
Classes that represent 3D spatial information:
- `CopickLocation`: Represents a location in 3D space with x, y, and z coordinates
- `CopickPoint`: Extends location with transformation matrix, instance ID, and score information

### 1.2 Hierarchical Data Structure

#### CopickRoot
The root object that contains configuration information and provides access to runs.

**Key Features:**
- `user_id` and `session_id` properties with setters
- Methods to query and access available runs
- Methods to query and access pickable objects
- Methods to refresh metadata from storage
- Factory methods for creating run and object instances

**Implementation Details:**

1. **Lazy Loading Pattern**
   
   CopickRoot implements a lazy loading pattern throughout the API. This means that data is only loaded when explicitly requested, reducing memory usage and improving performance. The pattern is implemented through several mechanisms:

   - **Query Caching**: The `query()` method retrieves a list of available runs, but this operation can be expensive, especially when accessing remote storage. The results are therefore cached in the `_runs` attribute. Subsequent calls to `runs` property reuse this cached data.

   ```python
   def query(self) -> List["CopickRun"]:
       # Implementation varies by backend, but always returns a list of runs
       pass

   @property
   def runs(self) -> List["CopickRun"]:
       if self._runs is None:
           self._runs = self.query()
       return self._runs
   ```

   - **On-Demand Object Creation**: Objects like runs and pickable objects are only instantiated when explicitly requested via their respective getters.

   ```python
   def get_run(self, name: str, **kwargs) -> Union["CopickRun", None]:
       for run in self.runs:
           if run.name == name:
               return run
       
       # Create a new run if not found and kwargs are provided
       if kwargs:
           return self.new_run(name, **kwargs)
       
       return None
   ```

   - **Factory Methods**: The `_run_factory()` and `_object_factory()` methods allow implementations to customize the creation of run and object instances without loading unnecessary data.

2. **Refresh Mechanism**

   The API provides a `refresh()` method that clears the cached data, forcing a reload on the next access:

   ```python
   def refresh(self) -> None:
       self._runs = None
   ```

   This allows clients to explicitly refresh the data when needed, while maintaining the performance benefits of caching during normal operation.

3. **Extensibility Through Abstract Factory Pattern**

   CopickRoot uses the Abstract Factory pattern to create runs and objects without requiring knowledge of their concrete implementations:

   ```python
   def _run_factory(self) -> Tuple[Type["CopickRun"], Type["CopickRunMeta"]]:
       # Must be implemented by subclasses
       pass

   def _object_factory(self) -> Tuple[Type["CopickObject"], Type["PickableObject"]]:
       # Must be implemented by subclasses
       pass
   ```

   This allows different implementations (filesystem, data portal, etc.) to create appropriate subclasses without changing the core API.

4. **Configuration Management**

   CopickRoot maintains the configuration passed during initialization, making it available to all child objects. This includes:
   
   - User and session IDs
   - Available pickable objects
   - Other metadata needed by the implementation

   Configuration properties use getters and setters to ensure that changes propagate correctly:

   ```python
   @property
   def user_id(self) -> str:
       return self.config.user_id

   @user_id.setter
   def user_id(self, value: str) -> None:
       self.config.user_id = value
   ```

#### CopickRun
Represents a collection of data with a specific name.

**Key Features:**
- Methods to query and access voxel spacings, picks, meshes, and segmentations
- Filter methods for user-generated vs. tool-generated data
- Methods to refresh metadata from storage
- Factory methods for creating child objects
- Methods to ensure run existence

**Implementation Details:**

1. **Hierarchical Lazy Loading**

   CopickRun implements a hierarchical lazy loading pattern, similar to CopickRoot. It maintains separate caches for each type of data it contains:

   ```python
   def __init__(self, root: "CopickRoot", meta: CopickRunMeta, config: Optional["CopickConfig"] = None):
       self.root = root
       self.meta = meta
       self.config = config or root.config
       
       # Initialize caches as None
       self._voxel_spacings = None
       self._picks = None
       self._meshes = None
       self._segmentations = None
   ```

   These caches are populated on-demand when the corresponding properties are accessed:

   ```python
   @property
   def voxel_spacings(self) -> List["CopickVoxelSpacing"]:
       if self._voxel_spacings is None:
           self._voxel_spacings = self.query_voxelspacings()
       return self._voxel_spacings
   ```

   This ensures that potentially expensive I/O operations are only performed when necessary.

2. **Filtering Capabilities**

   CopickRun provides methods to filter data based on various criteria, particularly distinguishing between user-generated and tool-generated data:

   ```python
   def user_picks(self) -> List["CopickPicks"]:
       return [p for p in self.picks if p.from_user]
       
   def tool_picks(self) -> List["CopickPicks"]:
       return [p for p in self.picks if p.from_tool]
   ```

   These methods build on the base properties that use lazy loading, so they maintain efficiency while providing more specific access patterns.

   More complex filtering is supported through parameterized getters:

   ```python
   def get_picks(self, object_name: str = None, user_id: str = None, session_id: str = None) -> List["CopickPicks"]:
       result = self.picks
       
       if object_name is not None:
           result = [p for p in result if p.pickable_object_name == object_name]
           
       if user_id is not None:
           result = [p for p in result if p.user_id == user_id]
           
       if session_id is not None:
           result = [p for p in result if p.session_id == session_id]
           
       return result
   ```

   This enables clients to efficiently query only the specific data they need.

3. **Factory Methods and Creation Patterns**

   CopickRun uses the Abstract Factory pattern to create child objects, allowing concrete implementations to customize the instantiation process:

   ```python
   def _voxel_spacing_factory(self) -> Tuple[Type["CopickVoxelSpacing"], Type["CopickVoxelSpacingMeta"]]:
       # Must be implemented by subclasses
       pass
   ```

   These factory methods are used both for querying existing data and for creating new instances:

   ```python
   def new_voxel_spacing(self, voxel_size: float, **kwargs) -> "CopickVoxelSpacing":
       # Get the appropriate classes from the factory
       voxel_spacing_cls, voxel_spacing_meta_cls = self._voxel_spacing_factory()
       
       # Create the metadata
       meta = voxel_spacing_meta_cls(voxel_size=voxel_size)
       
       # Create and return the instance
       return voxel_spacing_cls(run=self, meta=meta, **kwargs)
   ```

   This approach ensures that the correct implementation-specific classes are used while maintaining a consistent API.

4. **Refresh and Persistence**

   CopickRun implements a refresh mechanism that clears all caches, forcing a reload on the next access:

   ```python
   def refresh(self) -> None:
       self.refresh_voxel_spacings()
       self.refresh_picks()
       self.refresh_meshes()
       self.refresh_segmentations()
       
   def refresh_voxel_spacings(self) -> None:
       self._voxel_spacings = None
   ```

   This allows clients to explicitly refresh data when needed, such as after changes have been made to the underlying storage.

   It also provides an `ensure()` method that checks if the run record exists in storage and optionally creates it if it doesn't:

   ```python
   def ensure(self, create: bool = False) -> bool:
       # Implementation varies by backend
       # Returns True if the run exists or was created, False otherwise
       pass
   ```

   This method is typically used to verify or prepare storage before performing operations that require the run to exist.

#### CopickVoxelSpacing
Represents a specific voxel spacing (resolution) within a run.

**Key Features:**
- Methods to query and access tomograms
- Methods to refresh metadata from storage
- Factory methods for creating tomogram instances
- Methods to ensure voxel spacing record existence

**Implementation Details:**

1. **Lazy Loading of Tomograms**

   CopickVoxelSpacing implements lazy loading for tomograms, following the same pattern as its parent classes:

   ```python
   def __init__(self, run: CopickRun, meta: CopickVoxelSpacingMeta, config: Optional[CopickConfig] = None):
       self.run = run
       self.meta = meta
       self.config = config or run.config
       
       # Initialize cache as None
       self._tomograms = None
   ```

   The tomograms are loaded only when requested:

   ```python
   @property
   def tomograms(self) -> List["CopickTomogram"]:
       if self._tomograms is None:
           self._tomograms = self.query_tomograms()
       return self._tomograms
   ```

   This ensures that expensive I/O operations to scan for available tomograms are only performed when necessary.

2. **Tomogram Access Patterns**

   CopickVoxelSpacing provides methods to access tomograms by type, both for single instances and collections:

   ```python
   def get_tomogram(self, tomo_type: str) -> Union["CopickTomogram", None]:
       for tomogram in self.tomograms:
           if tomogram.tomo_type == tomo_type:
               return tomogram
       return None
   ```

   ```python
   def get_tomograms(self, tomo_type: str) -> List["CopickTomogram"]:
       return [t for t in self.tomograms if t.tomo_type == tomo_type]
   ```

   These methods build on the lazy loading property, so they maintain efficiency while providing more targeted access.

3. **Factory Methods for Tomogram Creation**

   CopickVoxelSpacing uses the Abstract Factory pattern to create tomogram instances:

   ```python
   def _tomogram_factory(self) -> Tuple[Type["CopickTomogram"], Type["CopickTomogramMeta"]]:
       # Must be implemented by subclasses
       pass
   ```

   This factory method is used when creating new tomograms:

   ```python
   def new_tomogram(self, tomo_type: str, **kwargs) -> "CopickTomogram":
       # Get the appropriate classes from the factory
       tomogram_cls, tomogram_meta_cls = self._tomogram_factory()
       
       # Create the metadata
       meta = tomogram_meta_cls(tomo_type=tomo_type)
       
       # Create and return the instance
       return tomogram_cls(voxel_spacing=self, meta=meta, **kwargs)
   ```

   This ensures that the correct implementation-specific classes are used while maintaining a consistent API.

4. **Refresh and Storage Management**

   CopickVoxelSpacing provides a refresh mechanism for tomograms:

   ```python
   def refresh_tomograms(self) -> None:
       self._tomograms = None
       
   def refresh(self) -> None:
       self.refresh_tomograms()
   ```

   This allows clients to explicitly refresh the tomogram data when needed.

   It also includes an `ensure()` method to check if the voxel spacing record exists in storage and optionally create it:

   ```python
   def ensure(self, create: bool = False) -> bool:
       # Implementation varies by backend
       # Returns True if the voxel spacing exists or was created, False otherwise
       pass
   ```

   This method is typically used to verify or prepare storage before performing operations that require the voxel spacing to exist.

#### CopickTomogram
Represents a tomographic volume with a specific type and voxel spacing.

**Key Features:**
- Methods to query and access feature maps
- Methods to load and store volume data via zarr
- Methods to convert between zarr and numpy formats
- Methods to set regions of the tomogram

**Implementation Details:**

1. **Lazy Loading of Feature Maps**

   CopickTomogram implements lazy loading for feature maps, following the same pattern as its parent classes:

   ```python
   def __init__(self, voxel_spacing: "CopickVoxelSpacing", meta: CopickTomogramMeta, config: Optional["CopickConfig"] = None):
       self.voxel_spacing = voxel_spacing
       self.meta = meta
       self.config = config or voxel_spacing.config
       
       # Initialize cache as None
       self._features = None
   ```

   Feature maps are loaded only when the features property is accessed:

   ```python
   @property
   def features(self) -> List["CopickFeatures"]:
       if self._features is None:
           self._features = self.query_features()
       return self._features
   ```

   This ensures that potentially expensive I/O operations to scan for available feature maps are only performed when necessary.

2. **Zarr-Based Storage Interface**

   CopickTomogram provides access to tomographic volume data using zarr, a format designed for chunked, compressed N-dimensional arrays:

   ```python
   def zarr(self) -> MutableMapping:
       """Get the zarr store for the tomogram object.

       Returns:
           MutableMapping: The zarr store for the tomogram object.
       """
       # Implementation varies by backend, but always returns a zarr store
       pass
   ```

   This method provides a unified interface to access the underlying storage, regardless of whether it's a local file system, cloud storage, or some other backend.

3. **Numpy Conversion for Data Access**

   CopickTomogram provides methods to convert between zarr and numpy formats, allowing for easy integration with scientific computing libraries:

   ```python
   def numpy(
       self,
       zarr_group: str = "0",
       x: slice = slice(None, None),
       y: slice = slice(None, None),
       z: slice = slice(None, None),
   ) -> np.ndarray:
       """Get the tomogram as a numpy array.

       Args:
           zarr_group: Zarr group to read from.
           x: Slice for x dimension.
           y: Slice for y dimension.
           z: Slice for z dimension.

       Returns:
           np.ndarray: The tomogram as a numpy array.
       """
       store = self.zarr()
       z_array = zarr.open(store, mode="r")
       
       if zarr_group in z_array:
           # Get the requested region of data
           return z_array[zarr_group][x, y, z]
       else:
           # Handle case when zarr_group doesn't exist
           raise KeyError(f"Zarr group '{zarr_group}' not found")
   ```

   This method allows efficient access to regions of the tomogram, which is essential for working with large volumes that might not fit entirely in memory.

4. **Data Import and Region Setting**

   CopickTomogram provides methods to import data from numpy arrays and set specific regions of the tomogram:

   ```python
   def from_numpy(
       self,
       data: np.ndarray,
       levels: int = 3,
       dtype: Optional[np.dtype] = np.float32,
   ) -> None:
       """Set the tomogram data from a numpy array.

       Args:
           data: The tomogram data as a numpy array.
           levels: Number of resolution levels to create.
           dtype: Data type to use for the zarr array.
       """
       store = self.zarr()
       shape = data.shape
       chunks = calculate_chunks(shape)  # Function to determine optimal chunk size
       
       # Create multi-resolution pyramid
       for i in range(levels):
           level_data = downsample(data, i) if i > 0 else data  # Function to downsample data
           level_shape = level_data.shape
           z_array = zarr.create(
               shape=level_shape,
               chunks=chunks,
               dtype=dtype,
               store=store,
               path=str(i),
               overwrite=True,
           )
           z_array[:] = level_data
   ```

   ```python
   def set_region(
       self,
       data: np.ndarray,
       zarr_group: str = "0",
       x: slice = slice(None, None),
       y: slice = slice(None, None),
       z: slice = slice(None, None),
   ) -> None:
       """Set a region of the tomogram.

       Args:
           data: The tomogram data as a numpy array.
           zarr_group: Zarr group to write to.
           x: Slice for x dimension.
           y: Slice for y dimension.
           z: Slice for z dimension.
       """
       store = self.zarr()
       z_array = zarr.open(store, mode="a")
       
       if zarr_group in z_array:
           # Set the specified region
           z_array[zarr_group][x, y, z] = data
       else:
           # Handle case when zarr_group doesn't exist
           raise KeyError(f"Zarr group '{zarr_group}' not found")
   ```

   These methods support both complete replacement of tomogram data and partial updates to specific regions, which is essential for efficient processing of large volumes.

5. **Feature Map Management**

   CopickTomogram provides methods to create and access feature maps:

   ```python
   def new_features(self, feature_type: str, **kwargs) -> "CopickFeatures":
       # Get the appropriate classes from the factory
       feature_cls, feature_meta_cls = self._feature_factory()
       
       # Create the metadata
       meta = feature_meta_cls(
           tomo_type=self.tomo_type,
           feature_type=feature_type,
       )
       
       # Create and return the instance
       return feature_cls(tomogram=self, meta=meta, **kwargs)
   ```

   This factory method ensures that the correct implementation-specific feature classes are created while maintaining a consistent API.

   ```python
   def get_features(self, feature_type: str) -> Union["CopickFeatures", None]:
       for feature in self.features:
           if feature.feature_type == feature_type:
               return feature
       return None
   ```

   This method provides efficient access to specific feature maps by type.

#### CopickFeatures
Represents feature maps computed on a tomogram.

**Key Features:**
- Methods to load and store feature map data via zarr
- Methods to convert between zarr and numpy formats
- Methods to set regions of the feature map

**Implementation Details:**

1. **Feature Map Storage Interface**

   CopickFeatures provides access to feature map data using zarr, similar to CopickTomogram:

   ```python
   def zarr(self) -> MutableMapping:
       """Get the zarr store for the feature map.

       Returns:
           MutableMapping: The zarr store for the feature map.
       """
       # Implementation varies by backend, but always returns a zarr store
       pass
   ```

   This method provides a unified interface to access the underlying storage, regardless of the backend implementation.

2. **Numpy Conversion with Flexible Slicing**

   CopickFeatures provides methods to convert between zarr and numpy formats with support for flexible slicing:

   ```python
   def numpy(
       self,
       zarr_group: str = "0",
       slices: Tuple[slice, ...] = None,
   ) -> np.ndarray:
       """Get the feature map as a numpy array.

       Args:
           zarr_group: Zarr group to read from.
           slices: Slices for each dimension. If None, all data is returned.

       Returns:
           np.ndarray: The feature map as a numpy array.
       """
       store = self.zarr()
       z_array = zarr.open(store, mode="r")
       
       if zarr_group in z_array:
           if slices is not None:
               # Get the requested region of data
               return z_array[zarr_group][slices]
           else:
               # Get all data
               return z_array[zarr_group][:]
       else:
           # Handle case when zarr_group doesn't exist
           raise KeyError(f"Zarr group '{zarr_group}' not found")
   ```

   This method provides flexibility in accessing feature map data, which can have varying dimensionality depending on the feature type.

3. **Region-Based Operations**

   CopickFeatures provides methods to set specific regions of the feature map:

   ```python
   def set_region(
       self,
       data: np.ndarray,
       zarr_group: str = "0",
       slices: Tuple[slice, ...] = None,
   ) -> None:
       """Set a region of the feature map.

       Args:
           data: The feature map data as a numpy array.
           zarr_group: Zarr group to write to.
           slices: Slices for each dimension. If None, all data is set.
       """
       store = self.zarr()
       z_array = zarr.open(store, mode="a")
       
       if zarr_group in z_array:
           if slices is not None:
               # Set the specified region
               z_array[zarr_group][slices] = data
           else:
               # Set all data
               z_array[zarr_group][:] = data
       else:
           # Handle case when zarr_group doesn't exist
           raise KeyError(f"Zarr group '{zarr_group}' not found")
   ```

   This method supports partial updates to specific regions of feature maps, allowing for efficient processing of large datasets.

4. **Flexible Feature Type Handling**

   CopickFeatures is designed to accommodate various types of feature maps, which may have different dimensionality, data types, and semantics:

   - **Scalar Features**: Single-value features per voxel (e.g., density, probability)
   - **Vector Features**: Multi-value features per voxel (e.g., orientation, flow)
   - **Tensor Features**: Matrix-valued features per voxel (e.g., structure tensors)

   The implementation doesn't make assumptions about the feature type, allowing applications to define and use custom feature maps as needed.

5. **Memory Efficiency**

   Feature maps can be large, especially for high-resolution tomograms. CopickFeatures is designed to minimize memory usage through:

   - **Chunked Storage**: Zarr's chunked storage allows accessing subsets of data without loading the entire feature map.
   - **On-Demand Loading**: Data is only loaded when explicitly requested.
   - **Region-Based Operations**: Processing can be performed on specific regions rather than the entire volume.

   These design choices ensure that CopickFeatures can handle large datasets efficiently, even on systems with limited memory.

### 1.3 Data Collection Classes

#### CopickPicks
Represents a collection of picked points for a specific object.

**Key Features:**
- Methods to load and store picks
- Properties to check origin (user vs. tool)
- Methods to convert between file format and numpy arrays
- Methods to refresh metadata from storage

#### CopickMesh
Represents a 3D mesh for visualization.

**Key Features:**
- Methods to load and store mesh data
- Properties to check origin (user vs. tool)
- Methods to refresh metadata from storage

#### CopickSegmentation
Represents a segmentation volume.

**Key Features:**
- Properties to check type (multilabel vs. single-label)
- Methods to load and store segmentation data via zarr
- Methods to convert between zarr and numpy formats
- Methods to set regions of the segmentation

### 1.4 User and Session IDs

Two important concepts in CoPick are the User ID and Session ID:

- **User ID**: A unique identifier for the user or tool that created the data. This identifier helps track ownership and provenance of picks, meshes, segmentations, etc. When data is generated by an automated tool rather than a human user, a distinct identifier is still used as the User ID to identify the source.

- **Session ID**: A unique identifier for the session during which data was created. This prevents race conditions when a user is running multiple instances of visualization tools (e.g., napari, ChimeraX) simultaneously. For data generated by automated tools, the Session ID is set to "0" by convention.

The combination of User ID, Session ID, and object type creates a unique identifier for each piece of data in the system, ensuring that data from different sources can coexist without conflicts.

## 2. Overlay Interface (overlay.py)

The `overlay.py` file defines classes that extend the base models from `models.py` by adding read-only functionality. This enables handling data from multiple sources with different access permissions.

### 2.1 Core Concept

The overlay interface adds a `read_only` flag to the base classes and implements functionality to query data from both read-only (static) and writable (overlay) sources. This allows the system to combine data from reference sources (static) with user-generated modifications (overlay).

### 2.2 Key Classes

#### CopickPicksOverlay

Extends `CopickPicks` to handle read-only access control.

**Key Features:**
- `read_only` flag to indicate if picks can be modified
- Override of `store()` method to prevent storing to read-only sources

#### CopickMeshOverlay

Extends `CopickMesh` to handle read-only access control.

**Key Features:**
- `read_only` flag to indicate if mesh can be modified
- Override of `store()` method to prevent storing to read-only sources

#### CopickSegmentationOverlay

Extends `CopickSegmentation` to handle read-only access control.

**Key Features:**
- `read_only` flag to indicate if segmentation can be modified

#### CopickObjectOverlay

Extends `CopickObject` to handle read-only access control.

**Key Features:**
- `read_only` flag to indicate if object can be modified

#### CopickFeaturesOverlay

Extends `CopickFeatures` to handle read-only access control.

**Key Features:**
- `read_only` flag to indicate if features can be modified

#### CopickTomogramOverlay

Extends `CopickTomogram` to handle data from both static and overlay sources.

**Key Features:**
- `read_only` flag to indicate if tomogram can be modified
- Abstract methods `_query_static_features()` and `_query_overlay_features()` to be implemented by subclasses
- Override of `query_features()` to combine results from both sources
- Assertion to ensure static features are marked as read-only

#### CopickVoxelSpacingOverlay

Extends `CopickVoxelSpacing` to handle data from both static and overlay sources.

**Key Features:**
- Abstract methods `_query_static_tomograms()` and `_query_overlay_tomograms()` to be implemented by subclasses
- Override of `query_tomograms()` to combine results from both sources
- Assertion to ensure static tomograms are marked as read-only

#### CopickRunOverlay

Extends `CopickRun` to handle data from both static and overlay sources.

**Key Features:**
- Abstract methods for querying static and overlay voxel spacings, picks, meshes, and segmentations
- Override of query methods to combine results from both sources
- Assertion to ensure static objects are marked as read-only
- Special handling for voxel spacings to prevent duplication

## 3. Filesystem Interface (filesystem.py)

The `filesystem.py` file implements the overlay interface using fsspec as the backend for file system access. It enables storing and retrieving CoPick data using local or remote file systems.

### 3.1 Core Concept

The filesystem interface provides concrete implementations of the abstract overlay classes, using fsspec to interact with file systems. It supports two storage locations:
- A static (read-only) source for reference data
- An overlay (writable) source for user modifications

### 3.2 On-Disk Structure and Naming Conventions

The filesystem implementation uses a specific directory structure and file naming conventions:

```
ROOT/
├── ExperimentRuns/
│   ├── [run_name]/
│   │   ├── .meta                       # Metadata marker file
│   │   ├── VoxelSpacing[voxel_size]/
│   │   │   ├── .meta                   # Metadata marker file
│   │   │   ├── [tomo_type].zarr/       # Tomogram data
│   │   │   ├── [tomo_type]_[feature_type]_features.zarr/  # Feature maps
│   │   ├── Picks/
│   │   │   ├── [user_id]_[session_id]_[pickable_object_name].json  # Pick data
│   │   ├── Meshes/
│   │   │   ├── [user_id]_[session_id]_[pickable_object_name].glb   # Mesh data
│   │   ├── Segmentations/
│   │   │   ├── [voxel_size]_[user_id]_[session_id]_[name].zarr/     # Single-label segmentation
│   │   │   ├── [voxel_size]_[user_id]_[session_id]_[name]-multilabel.zarr/  # Multi-label segmentation
├── Objects/
│   ├── [object_name].zarr/            # Particle data
```

#### File Naming Conventions

- **Picks**: `{user_id}_{session_id}_{pickable_object_name}.json`
  - JSON files containing pick points with metadata
  - Organized by user ID, session ID, and pickable object name

- **Meshes**: `{user_id}_{session_id}_{pickable_object_name}.glb`
  - GLB (binary glTF) files containing 3D mesh data
  - Organized by user ID, session ID, and pickable object name

- **Segmentations**:
  - Single-label: `{voxel_size:.3f}_{user_id}_{session_id}_{name}.zarr`
  - Multi-label: `{voxel_size:.3f}_{user_id}_{session_id}_{name}-multilabel.zarr`
  - Zarr directories containing volumetric segmentation data
  - Organized by voxel size (with 3 decimal places), user ID, session ID, and object name

- **Tomograms**: `{tomo_type}.zarr`
  - Zarr directories containing tomographic volume data
  - Organized by tomogram type within voxel spacing directories

- **Feature Maps**: `{tomo_type}_{feature_type}_features.zarr`
  - Zarr directories containing feature map data
  - Organized by tomogram type and feature type

### 3.3 Key Classes

#### CopickConfigFSSpec

Extends `CopickConfig` with filesystem-specific configuration.

**Attributes:**
- `config_type`: Set to "filesystem"
- `overlay_root`: The root URL for the overlay storage
- `static_root`: Optional root URL for the static storage
- `overlay_fs_args`: Optional arguments for the overlay filesystem
- `static_fs_args`: Optional arguments for the static filesystem

#### CopickPicksFSSpec

Implements `CopickPicksOverlay` using fsspec storage.

**Key Features:**
- Properties to determine appropriate path and filesystem based on read-only status
- Implementation of `_load()` and `_store()` methods using JSON serialization

#### CopickMeshFSSpec

Implements `CopickMeshOverlay` using fsspec storage.

**Key Features:**
- Properties to determine appropriate path and filesystem based on read-only status
- Implementation of `_load()` and `_store()` methods using trimesh serialization with GLB format

#### CopickSegmentationFSSpec

Implements `CopickSegmentationOverlay` using fsspec storage.

**Key Features:**
- Properties to determine appropriate path and filesystem based on read-only status
- Implementation of `zarr()` method to provide Zarr storage access

#### CopickFeaturesFSSpec

Implements `CopickFeaturesOverlay` using fsspec storage.

**Key Features:**
- Properties to determine appropriate path and filesystem based on read-only status
- Implementation of `zarr()` method to provide Zarr storage access

#### CopickTomogramFSSpec

Implements `CopickTomogramOverlay` using fsspec storage.

**Key Features:**
- Properties to determine paths and filesystems for both static and overlay sources
- Implementation of `_query_static_features()` and `_query_overlay_features()` methods
- Implementation of `zarr()` method to provide Zarr storage access
- Special handling for the case when static and overlay sources are the same

#### CopickVoxelSpacingFSSpec

Implements `CopickVoxelSpacingOverlay` using fsspec storage.

**Key Features:**
- Properties to determine paths and filesystems for both static and overlay sources
- Implementation of `_query_static_tomograms()` and `_query_overlay_tomograms()` methods
- Implementation of `ensure()` method to check or create voxel spacing records

#### CopickRunFSSpec

Implements `CopickRunOverlay` using fsspec storage.

**Key Features:**
- Properties to determine paths and filesystems for both static and overlay sources
- Implementation of query methods for voxel spacings, picks, meshes, and segmentations from both sources
- Implementation of `ensure()` method to check or create run records

#### CopickObjectFSSpec

Implements `CopickObjectOverlay` using fsspec storage.

**Key Features:**
- Properties to determine the appropriate path and filesystem
- Implementation of `zarr()` method to provide Zarr storage access

#### CopickRootFSSpec

Implements `CopickRoot` using fsspec storage.

**Key Features:**
- Initialization of fsspec filesystems for both static and overlay sources
- Implementation of query methods to find available runs from both sources
- Implementation of factory methods for creating runs and objects
- Implementation of `from_file()` class method to load from a configuration file

## 4. CryoET Data Portal Interface (cryoet_data_portal.py)

The `cryoet_data_portal.py`