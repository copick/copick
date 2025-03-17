# CoPick Technical Specification

## 1. Abstract API (models.py)

The `models.py` file defines the core data models and interfaces for the CoPick system. These classes form the
foundation of the hierarchical data structure used throughout the application.

### 1.1 Base Models

#### PickableObject

A metadata class that represents objects that can be "picked" (selected or annotated) within tomograms.

**Attributes:**

- `name`: String name of the object
- `is_particle`: Boolean flag indicating whether the object should be represented by points (True) or segmentation
  masks (False)
- `label`: Optional numeric label/id for the object, used in multilabel segmentation masks
- `color`: Optional RGBA color tuple for visualization
- `emdb_id`: Optional EMDB ID for the object
- `pdb_id`: Optional PDB ID for the object
- `identifier`: Optional identifier (e.g., Gene Ontology ID or UniProtKB accession)
- `map_threshold`: Optional threshold for rendering isosurfaces
- `radius`: Optional radius when displaying particles as spheres

The class includes validators for the `label` and `color` fields, as well as properties and setters for backward
compatibility with `go_id`.

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

### 1.2 Meta Classes

The CoPick abstract API makes extensive use of "meta" classes to manage metadata for each major component in the system. These meta classes are implemented as Pydantic models, providing a robust foundation for data validation, serialization, and documentation.

#### Core Concept

For each major class in the hierarchy (CopickRun, CopickVoxelSpacing, CopickTomogram, etc.), there is a corresponding "meta" class (CopickRunMeta, CopickVoxelSpacingMeta, CopickTomogramMeta, etc.) that stores metadata about the instance. These meta classes are passed to the constructors of their respective main classes:

```python
def __init__(self, root: "CopickRoot", meta: CopickRunMeta, config: Optional["CopickConfig"] = None):
    self.root = root
    self.meta = meta
    self.config = config or root.config
```

#### Structure and Benefits

1. **Separation of Concerns**

   The meta classes separate metadata management from functionality:
   
   ```python
   class CopickRunMeta(BaseModel):
       """Metadata for a CopickRun instance."""
       name: str
       created: Optional[datetime] = None
       modified: Optional[datetime] = None
       description: Optional[str] = None
   ```
   
   This allows the main classes to focus on behavior and operations while the meta classes handle data structure and validation.

2. **Pydantic Integration**

   By implementing meta classes as Pydantic models, CoPick gains:
   
   - **Automatic validation**: Field types are checked and validated at runtime
   - **Schema generation**: OpenAPI/JSON schema can be automatically generated
   - **Default values**: Fields can have sensible defaults
   - **Documentation**: Field descriptions are built into the model
   - **Serialization**: Easy conversion to/from JSON, dict, and other formats

3. **Factory Pattern Integration**

   The meta classes are integral to CoPick's Abstract Factory pattern. Factory methods typically return both the main class and its corresponding meta class:
   
   ```python
   def _run_factory(self) -> Tuple[Type["CopickRun"], Type["CopickRunMeta"]]:
       # Returns appropriate implementation classes
       pass
   ```
   
   This allows implementations to customize both the behavior (main class) and the metadata structure (meta class).

4. **Metadata Persistence**

   The meta classes provide a clean way to persist metadata to storage:
   
   ```python
   # Serializing metadata to JSON
   def _store_metadata(self):
       metadata_json = self.meta.json()
       # Write to storage
   
   # Deserializing metadata from JSON
   @classmethod
   def _load_metadata(cls, data):
       return cls.meta_cls.parse_raw(data)
   ```

#### Key Meta Classes

1. **CopickRunMeta**
   
   Stores metadata about a run, such as:
   - `name`: Unique identifier for the run
   - `created`: Timestamp when the run was created
   - `modified`: Timestamp when the run was last modified
   - `description`: Optional description of the run

2. **CopickVoxelSpacingMeta**
   
   Stores metadata about a voxel spacing, such as:
   - `voxel_size`: Size of voxels in nanometers
   - `created`: Timestamp when the voxel spacing was created
   - `modified`: Timestamp when the voxel spacing was last modified

3. **CopickTomogramMeta**
   
   Stores metadata about a tomogram, such as:
   - `tomo_type`: Type of the tomogram (e.g., "raw", "denoised", "filtered")
   - `dimensions`: Optional tuple of (width, height, depth)
   - `origin`: Optional tuple of (x, y, z) coordinates of the origin

4. **CopickPicksMeta**
   
   Stores metadata about a collection of picks, such as:
   - `pickable_object_name`: Name of the pickable object
   - `user_id`: ID of the user who created the picks
   - `session_id`: ID of the session in which the picks were created
   - `created`: Timestamp when the picks were created
   - `modified`: Timestamp when the picks were last modified

5. **CopickMeshMeta**
   
   Stores metadata about a mesh, such as:
   - `pickable_object_name`: Name of the pickable object
   - `user_id`: ID of the user who created the mesh
   - `session_id`: ID of the session in which the mesh was created

6. **CopickSegmentationMeta**
   
   Stores metadata about a segmentation, such as:
   - `name`: Name of the segmentation
   - `user_id`: ID of the user who created the segmentation
   - `session_id`: ID of the session in which the segmentation was created
   - `voxel_size`: Size of voxels in nanometers
   - `is_multilabel`: Flag indicating whether the segmentation is multilabel

7. **CopickFeaturesMeta**
   
   Stores metadata about a feature map, such as:
   - `tomo_type`: Type of the source tomogram
   - `feature_type`: Type of the feature map (e.g., "membrane", "density")

#### Cascading Properties

The main classes often provide properties that cascade through metadata and configuration:

```python
@property
def user_id(self) -> str:
    return self.meta.user_id or self.config.user_id

@property
def session_id(self) -> str:
    return self.meta.session_id or self.config.session_id
```

This ensures consistent identification even when metadata is incomplete, falling back to configuration values when necessary.

### 1.3 Hierarchical Data Structure

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

   CopickRoot implements a lazy loading pattern throughout the API. This means that data is only loaded when explicitly
   requested, reducing memory usage and improving performance. The pattern is implemented through several mechanisms:

    - **Query Caching**: The `query()` method retrieves a list of available runs, but this operation can be expensive,
      especially when accessing remote storage. The results are therefore cached in the `_runs` attribute. Subsequent
      calls to `runs` property reuse this cached data.

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

    - **On-Demand Object Creation**: Objects like runs and pickable objects are only instantiated when explicitly
      requested via their respective getters.

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

    - **Factory Methods**: The `_run_factory()` and `_object_factory()` methods allow implementations to customize the
      creation of run and object instances without loading unnecessary data.

2. **Refresh Mechanism**

   The API provides a `refresh()` method that clears the cached data, forcing a reload on the next access:

   ```python
   def refresh(self) -> None:
       self._runs = None
   ```

   This allows clients to explicitly refresh the data when needed, while maintaining the performance benefits of caching
   during normal operation.

3. **Extensibility Through Abstract Factory Pattern**

   CopickRoot uses the Abstract Factory pattern to create runs and objects without requiring knowledge of their concrete
   implementations:

   ```python
   def _run_factory(self) -> Tuple[Type["CopickRun"], Type["CopickRunMeta"]]:
       # Must be implemented by subclasses
       pass

   def _object_factory(self) -> Tuple[Type["CopickObject"], Type["PickableObject"]]:
       # Must be implemented by subclasses
       pass
   ```

   This allows different implementations (filesystem, data portal, etc.) to create appropriate subclasses without
   changing the core API.

4. **Configuration Management**

   CopickRoot maintains the configuration passed during initialization, making it available to all child objects. This
   includes:

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

   CopickRun implements a hierarchical lazy loading pattern, similar to CopickRoot. It maintains separate caches for
   each type of data it contains:

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

   CopickRun provides methods to filter data based on various criteria, particularly distinguishing between
   user-generated and tool-generated data:

   ```python
   def user_picks(self) -> List["CopickPicks"]:
       return [p for p in self.picks if p.from_user]
       
   def tool_picks(self) -> List["CopickPicks"]:
       return [p for p in self.picks if p.from_tool]
   ```

   These methods build on the base properties that use lazy loading, so they maintain efficiency while providing more
   specific access patterns.

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

   CopickRun uses the Abstract Factory pattern to create child objects, allowing concrete implementations to customize
   the instantiation process:

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

   This allows clients to explicitly refresh data when needed, such as after changes have been made to the underlying
   storage.

   It also provides an `ensure()` method that checks if the run record exists in storage and optionally creates it if it
   doesn't:

   ```python
   def ensure(self, create: bool = False) -> bool:
       # Implementation varies by backend
       # Returns True if the run exists or was created, False otherwise
       pass
   ```

   This method is typically used to verify or prepare storage before performing operations that require the run to
   exist.

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

   It also includes an `ensure()` method to check if the voxel spacing record exists in storage and optionally create
   it:

   ```python
   def ensure(self, create: bool = False) -> bool:
       # Implementation varies by backend
       # Returns True if the voxel spacing exists or was created, False otherwise
       pass
   ```

   This method is typically used to verify or prepare storage before performing operations that require the voxel
   spacing to exist.

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

   This ensures that potentially expensive I/O operations to scan for available feature maps are only performed when
   necessary.

2. **Zarr-Based Storage Interface**

   CopickTomogram provides access to tomographic volume data using zarr, a format designed for chunked, compressed
   N-dimensional arrays:

   ```python
   def zarr(self) -> MutableMapping:
       """Get the zarr store for the tomogram object.

       Returns:
           MutableMapping: The zarr store for the tomogram object.
       """
       # Implementation varies by backend, but always returns a zarr store
       pass
   ```

   This method provides a unified interface to access the underlying storage, regardless of whether it's a local file
   system, cloud storage, or some other backend.

3. **Numpy Conversion for Data Access**

   CopickTomogram provides methods to convert between zarr and numpy formats, allowing for easy integration with
   scientific computing libraries:

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

   This method allows efficient access to regions of the tomogram, which is essential for working with large volumes
   that might not fit entirely in memory.

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

   These methods support both complete replacement of tomogram data and partial updates to specific regions, which is
   essential for efficient processing of large volumes.

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

   This factory method ensures that the correct implementation-specific feature classes are created while maintaining a
   consistent API.

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

   This method provides flexibility in accessing feature map data, which can have varying dimensionality depending on
   the feature type.

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

   This method supports partial updates to specific regions of feature maps, allowing for efficient processing of large
   datasets.

4. **Flexible Feature Type Handling**

   CopickFeatures is designed to accommodate various types of feature maps, which may have different dimensionality,
   data types, and semantics:

    - **Scalar Features**: Single-value features per voxel (e.g., density, probability)
    - **Vector Features**: Multi-value features per voxel (e.g., orientation, flow)
    - **Tensor Features**: Matrix-valued features per voxel (e.g., structure tensors)

   The implementation doesn't make assumptions about the feature type, allowing applications to define and use custom
   feature maps as needed.

5. **Memory Efficiency**

   Feature maps can be large, especially for high-resolution tomograms. CopickFeatures is designed to minimize memory
   usage through:

    - **Chunked Storage**: Zarr's chunked storage allows accessing subsets of data without loading the entire feature
      map.
    - **On-Demand Loading**: Data is only loaded when explicitly requested.
    - **Region-Based Operations**: Processing can be performed on specific regions rather than the entire volume.

   These design choices ensure that CopickFeatures can handle large datasets efficiently, even on systems with limited
   memory.

### 1.4 Annotation Classes

#### CopickPicks

Represents a collection of picked points for a specific object.

**Key Features:**

- Methods to load and store picks
- Properties to check origin (user vs. tool)
- Methods to convert between file format and numpy arrays
- Methods to refresh metadata from storage

**Implementation Details:**

1. **Efficient Storage of Point Collections**

   CopickPicks implements an efficient storage mechanism for collections of 3D points with metadata:

   ```python
   def __init__(self, run: "CopickRun", meta: CopickPicksMeta, config: Optional["CopickConfig"] = None):
       self.run = run
       self.meta = meta
       self.config = config or run.config
       
       # Initialize data cache as None
       self._data = None
   ```

   The actual point data is loaded only when requested, minimizing memory usage for projects with many pick collections:

   ```python
   @property
   def data(self) -> Union[List[CopickPoint], None]:
       if self._data is None:
           self._data = self._load()
       return self._data
       
   @data.setter
   def data(self, value: List[CopickPoint]) -> None:
       self._data = value
       self._is_loaded = True
   ```

   This lazy loading pattern ensures that potentially large collections of pick points are only loaded into memory when
   actively used.

2. **Origin Tracking with User and Session IDs**

   CopickPicks provides properties to identify the origin of the picks, distinguishing between user-generated and
   tool-generated data:

   ```python
   @property
   def from_user(self) -> bool:
       """Check if the picks are from a user."""
       return self.user_id != "0" and self.session_id != "0"
       
   @property
   def from_tool(self) -> bool:
       """Check if the picks are from a tool."""
       return self.user_id == "0" or self.session_id == "0"
   ```

   These properties make it easy to filter and handle different types of pick data based on their origin.

   Additionally, CopickPicks provides direct access to the user and session IDs:

   ```python
   @property
   def user_id(self) -> str:
       return self.meta.user_id or self.config.user_id
       
   @property
   def session_id(self) -> str:
       return self.meta.session_id or self.config.session_id
   ```

   These properties cascade through metadata and configuration, ensuring consistent identification even when metadata is
   incomplete.

3. **Data Serialization and Persistence**

   CopickPicks implements methods to load from and store to persistent storage:

   ```python
   def _load(self) -> List[CopickPoint]:
       """Load the picks from storage.
       
       Returns:
           List[CopickPoint]: The loaded picks.
       """
       # Implementation varies by backend
       # Typically involves reading from a JSON file and parsing the contents
       pass
       
   def _store(self) -> None:
       """Store the picks to storage."""
       # Implementation varies by backend
       # Typically involves serializing to JSON and writing to a file
       pass
       
   def store(self) -> None:
       """Store the picks to storage."""
       if self._data is not None:
           self._store()
   ```

   The `store()` method checks if data has been loaded before attempting to store it, preventing accidental deletion of
   data that hasn't been loaded.

4. **Conversion Between File Format and Numpy Arrays**

   CopickPicks provides methods to convert between its internal representation and numpy arrays, which are commonly used
   in scientific computing:

   ```python
   def to_numpy(self) -> Tuple[np.ndarray, Optional[np.ndarray]]:
       """Convert picks to numpy arrays of points and scores.
       
       Returns:
           Tuple[np.ndarray, Optional[np.ndarray]]: Points array (Nx3) and scores array (Nx1) if available.
       """
       if not self.data:
           return np.empty((0, 3), dtype=np.float32), np.empty((0, 1), dtype=np.float32)
           
       points = np.array([[p.x, p.y, p.z] for p in self.data], dtype=np.float32)
       
       # Extract scores if available
       scores = np.array([[p.score] for p in self.data if p.score is not None], dtype=np.float32)
       scores = scores if len(scores) == len(points) else None
       
       return points, scores
       
   def from_numpy(self, points: np.ndarray, scores: Optional[np.ndarray] = None) -> None:
       """Set picks from numpy arrays of points and optional scores.
       
       Args:
           points: Points array (Nx3).
           scores: Optional scores array (Nx1).
       """
       self._data = []
       
       for i, (x, y, z) in enumerate(points):
           score = scores[i][0] if scores is not None else None
           self._data.append(CopickPoint(x=float(x), y=float(y), z=float(z), score=score))
   ```

   These methods enable seamless integration with numerical algorithms and machine learning pipelines that operate on
   numpy arrays.

5. **Refresh Mechanism**

   CopickPicks provides a refresh method to reload data from storage, which is useful when the underlying data might
   have changed:

   ```python
   def refresh(self) -> None:
       """Refresh the picks from storage."""
       self._data = None
   ```

   This allows clients to explicitly refresh the data when needed, while maintaining the performance benefits of caching
   during normal operation.

#### CopickMesh

Represents a 3D mesh for visualization.

**Key Features:**

- Methods to load and store mesh data
- Properties to check origin (user vs. tool)
- Methods to refresh metadata from storage

**Implementation Details:**

1. **Efficient 3D Mesh Representation**

   CopickMesh uses the trimesh library to represent 3D meshes, which provides efficient storage and operations:

   ```python
   def __init__(self, run: "CopickRun", meta: CopickMeshMeta, config: Optional["CopickConfig"] = None):
       self.run = run
       self.meta = meta
       self.config = config or run.config
       
       # Initialize mesh cache as None
       self._mesh = None
   ```

   The actual mesh data is loaded only when requested, minimizing memory usage for projects with many meshes:

   ```python
   @property
   def mesh(self) -> Union[trimesh.Trimesh, None]:
       if self._mesh is None:
           self._mesh = self._load()
       return self._mesh
       
   @mesh.setter
   def mesh(self, value: trimesh.Trimesh) -> None:
       self._mesh = value
       self._is_loaded = True
   ```

   This lazy loading pattern ensures that potentially large mesh data is only loaded into memory when actively used.

2. **Origin Tracking with User and Session IDs**

   Similar to CopickPicks, CopickMesh provides properties to identify the origin of the mesh data:

   ```python
   @property
   def from_user(self) -> bool:
       """Check if the mesh is from a user."""
       return self.user_id != "0" and self.session_id != "0"
       
   @property
   def from_tool(self) -> bool:
       """Check if the mesh is from a tool."""
       return self.user_id == "0" or self.session_id == "0"
   ```

   These properties make it easy to filter and handle different types of mesh data based on their origin.

   The user and session ID properties cascade through metadata and configuration:

   ```python
   @property
   def user_id(self) -> str:
       return self.meta.user_id or self.config.user_id
       
   @property
   def session_id(self) -> str:
       return self.meta.session_id or self.config.session_id
   ```

3. **Data Serialization and Persistence**

   CopickMesh implements methods to load from and store to persistent storage:

   ```python
   def _load(self) -> trimesh.Trimesh:
       """Load the mesh from storage.
       
       Returns:
           trimesh.Trimesh: The loaded mesh.
       """
       # Implementation varies by backend
       # Typically involves reading from a GLB file and parsing with trimesh
       pass
       
   def _store(self) -> None:
       """Store the mesh to storage."""
       # Implementation varies by backend
       # Typically involves serializing with trimesh and writing to a GLB file
       pass
       
   def store(self) -> None:
       """Store the mesh to storage."""
       if self._mesh is not None:
           self._store()
   ```

   The `store()` method checks if mesh data has been loaded before attempting to store it, preventing accidental
   deletion of data that hasn't been loaded.

4. **Integration with Visualization Tools**

   CopickMesh provides methods to facilitate integration with common visualization tools:

   ```python
   def to_napari(self) -> Dict:
       """Convert the mesh to a format suitable for napari visualization.
       
       Returns:
           Dict: Dictionary containing vertices and faces.
       """
       if self.mesh is None:
           return {"vertices": np.empty((0, 3)), "faces": np.empty((0, 3))}
           
       return {
           "vertices": self.mesh.vertices.astype(np.float32),
           "faces": self.mesh.faces.astype(np.uint32),
       }
       
   def from_napari(self, vertices: np.ndarray, faces: np.ndarray) -> None:
       """Set the mesh from napari format.
       
       Args:
           vertices: Vertices array (Nx3).
           faces: Faces array (Mx3).
       """
       self._mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
   ```

   These methods enable seamless integration with napari, a popular tool for multi-dimensional data visualization in the
   scientific Python ecosystem.

5. **Refresh Mechanism**

   CopickMesh provides a refresh method to reload data from storage:

   ```python
   def refresh(self) -> None:
       """Refresh the mesh from storage."""
       self._mesh = None
   ```

   This allows clients to explicitly refresh the data when needed, while maintaining the performance benefits of caching
   during normal operation.

#### CopickSegmentation

Represents a segmentation volume.

**Key Features:**

- Properties to check type (multilabel vs. single-label)
- Methods to load and store segmentation data via zarr
- Methods to convert between zarr and numpy formats
- Methods to set regions of the segmentation

**Implementation Details:**

1. **Volumetric Segmentation Representation**

   CopickSegmentation provides access to volumetric segmentation data using zarr, a format designed for chunked,
   compressed N-dimensional arrays:

   ```python
   def __init__(self, run: "CopickRun", meta: CopickSegmentationMeta, config: Optional["CopickConfig"] = None):
       self.run = run
       self.meta = meta
       self.config = config or run.config
   ```

   Unlike CopickPicks and CopickMesh, CopickSegmentation does not maintain a full in-memory cache of the segmentation
   data, as segmentation volumes can be extremely large. Instead, it provides methods to access and manipulate the data
   directly in zarr storage.

2. **Segmentation Type Detection**

   CopickSegmentation provides properties to identify the type of segmentation:

   ```python
   @property
   def is_multilabel(self) -> bool:
       """Check if the segmentation is multilabel."""
       return self.meta.is_multilabel
       
   @property
   def is_singlelabel(self) -> bool:
       """Check if the segmentation is single-label."""
       return not self.meta.is_multilabel
   ```

   These properties make it easy to handle different types of segmentation data appropriately. Multilabel segmentations
   use a single volume where each voxel contains a label ID, while single-label segmentations use a binary volume for
   each object.

3. **Zarr-Based Storage Interface**

   CopickSegmentation provides methods to access segmentation data using zarr:

   ```python
   def zarr(self) -> MutableMapping:
       """Get the zarr store for the segmentation.
       
       Returns:
           MutableMapping: The zarr store for the segmentation.
       """
       # Implementation varies by backend
       # Typically involves accessing a zarr directory in the file system
       pass
   ```

   This method provides a unified interface to access the underlying storage, regardless of whether it's a local file
   system, cloud storage, or some other backend.

4. **Numpy Conversion for Data Access**

   CopickSegmentation provides methods to convert between zarr and numpy formats, allowing for easy integration with
   scientific computing libraries:

   ```python
   def numpy(
       self,
       zarr_group: str = "0",
       x: slice = slice(None, None),
       y: slice = slice(None, None),
       z: slice = slice(None, None),
   ) -> np.ndarray:
       """Get the segmentation as a numpy array.
       
       Args:
           zarr_group: Zarr group to read from.
           x: Slice for x dimension.
           y: Slice for y dimension.
           z: Slice for z dimension.
       
       Returns:
           np.ndarray: The segmentation as a numpy array.
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

   This method allows efficient access to regions of the segmentation, which is essential for working with large volumes
   that might not fit entirely in memory.

5. **Region-Based Operations**

   CopickSegmentation provides methods to set specific regions of the segmentation:

   ```python
   def set_region(
       self,
       data: np.ndarray,
       zarr_group: str = "0",
       x: slice = slice(None, None),
       y: slice = slice(None, None),
       z: slice = slice(None, None),
   ) -> None:
       """Set a region of the segmentation.
       
       Args:
           data: The segmentation data as a numpy array.
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

   This method supports partial updates to specific regions of the segmentation, which is essential for efficient
   processing of large volumes.

### 1.5 User and Session IDs

Two important concepts in CoPick are the User ID and Session ID:

- **User ID**: A unique identifier for the user or tool that created the data. This identifier helps track ownership and
  provenance of picks, meshes, segmentations, etc. When data is generated by an automated tool rather than a human user,
  a distinct identifier is still used as the User ID to identify the source.

- **Session ID**: A unique identifier for the session during which data was created. This prevents race conditions when
  a user is running multiple instances of visualization tools (e.g., napari, ChimeraX) simultaneously. For data
  generated by automated tools, the Session ID is set to "0" by convention.

The combination of User ID, Session ID, and object type creates a unique identifier for each piece of data in the
system, ensuring that data from different sources can coexist without conflicts.

