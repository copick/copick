# CoPick Filesystem Layer Technical Specification

## 1. Overview

The filesystem layer provides a concrete implementation of the CoPick abstract API defined in `models.py`. It enables storing and retrieving CoPick data using a single filesystem backend through the fsspec library, which supports local and remote file systems with a unified interface.

This implementation is designed to:
- Serve as a standalone implementation of the abstract API
- Function as a layer within the multilayer architecture
- Support both local and remote file systems through fsspec
- Maintain efficient operation with large datasets through lazy loading

## 2. Core Concepts

### 2.1 Single Filesystem Source

Unlike the older overlay-based implementation, this version operates on a single filesystem source. This simplification makes the implementation more focused and allows the multilayer system to handle multiple data sources when needed.

### 2.2 Standardized On-Disk Format

The filesystem layer uses a standardized directory structure and file naming conventions to organize data on disk. This structure mirrors the hierarchical organization of the abstract API, making it intuitive to navigate and maintain.

### 2.3 Lazy Loading Pattern

Following the abstract API's design principles, the filesystem implementation employs lazy loading throughout:
- Metadata is loaded only when accessed
- Data collections are queried only when requested
- Volumetric data is accessed in chunks via zarr

### 2.4 Pydantic-Based Metadata

Metadata is stored as serialized Pydantic models, ensuring validation on both write and read operations. Each component (run, voxel spacing, etc.) has a corresponding `.meta` file containing its serialized metadata.

## 3. On-Disk Structure

The filesystem implementation uses a specific directory structure and file naming conventions:

```
ROOT/
├── ExperimentRuns/
│   ├── [run_name]/
│   │   ├── .meta                       # Run metadata
│   │   ├── VoxelSpacing[voxel_size]/
│   │   │   ├── .meta                   # Voxel spacing metadata
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

### 3.1 File Naming Conventions

- **Metadata Files**: `.meta`
  - JSON files containing serialized Pydantic model data
  - Stored at the root of each component (run, voxel spacing, etc.)

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

### 3.2 Path Generation

Each class in the filesystem implementation provides properties to determine the correct filesystem paths for different types of data:

```python
# Example from CopickRunFS
@property
def path(self) -> str:
    return os.path.join(self.root.config.root, "ExperimentRuns", self.meta.name)
    
@property
def picks_path(self) -> str:
    return os.path.join(self.path, "Picks")
```

## 4. Key Classes

### 4.1 CopickConfigFS

Extends `CopickConfig` with filesystem-specific configuration.

**Attributes:**
- `config_type`: Set to "filesystem"
- `root`: The root URL for the storage
- `fs_args`: Optional arguments for the filesystem
- `layer_name`: Name to identify this layer in the multilayer stack
- `priority`: Integer priority value for the layer in the multilayer stack
- `read_only`: Boolean flag indicating whether this filesystem is read-only

**Methods:**
- `fs()`: Returns an fsspec filesystem instance configured with the appropriate settings

```python
def fs(self) -> fsspec.filesystem:
    """Get the filesystem instance for this configuration."""
    if hasattr(self, '_fs') and self._fs is not None:
        return self._fs
        
    protocol = urlparse(self.root).scheme or 'file'
    self._fs = fsspec.filesystem(protocol, **self.fs_args or {})
    return self._fs
```

### 4.2 CopickRootFS

Implements `CopickRoot` using fsspec storage.

**Attributes:**
- `config`: The filesystem configuration
- `fs`: The fsspec filesystem instance
- `_runs`: Cache for queried runs

**Key Methods:**
- `query()`: Scans for available runs and returns initialized instances
- `_run_factory()` and `_object_factory()`: Return appropriate filesystem-specific implementations
- `ensure()`: Checks if the filesystem root exists and optionally creates it
- `refresh()`: Clears the runs cache

**Example Implementation:**

```python
def query(self) -> List["CopickRunFS"]:
    """Query available runs from the filesystem."""
    runs_path = os.path.join(self.config.root, "ExperimentRuns")
    
    if not self.fs.exists(runs_path):
        return []
        
    run_dirs = [d for d in self.fs.ls(runs_path) 
                if self.fs.isdir(d) and self.fs.exists(os.path.join(d, ".meta"))]
    
    results = []
    for run_dir in run_dirs:
        meta_data = self._load_metadata(run_dir)
        run_cls, run_meta_cls = self._run_factory()
        meta = run_meta_cls(**meta_data)
        results.append(run_cls(root=self, meta=meta))
        
    return results
```

### 4.3 CopickRunFS

Implements `CopickRun` using fsspec storage.

**Attributes:**
- `root`: The parent CopickRootFS instance
- `meta`: The run metadata
- `config`: The configuration, inherited from root
- `_voxel_spacings`, `_picks`, `_meshes`, `_segmentations`: Caches for queried data

**Key Methods:**
- `query_voxelspacings()`, `query_picks()`, etc.: Scan for available data
- `_voxel_spacing_factory()`, etc.: Return appropriate filesystem-specific implementations
- `ensure()`: Checks if the run directory exists and optionally creates it
- `refresh_voxel_spacings()`, etc.: Clear specific caches

**Example Implementation:**

```python
def query_picks(self) -> List["CopickPicksFS"]:
    """Query available picks for this run."""
    picks_path = self.picks_path
    
    if not self.root.fs.exists(picks_path):
        return []
        
    pick_files = [f for f in self.root.fs.ls(picks_path) 
                 if f.endswith('.json')]
    
    results = []
    for pick_file in pick_files:
        # Parse filename to extract user_id, session_id, and pickable_object_name
        filename = os.path.basename(pick_file)
        parts = filename.split('_')
        if len(parts) < 3:
            continue
            
        user_id = parts[0]
        session_id = parts[1]
        pickable_object_name = '_'.join(parts[2:]).replace('.json', '')
        
        picks_cls, picks_meta_cls = self._picks_factory()
        meta = picks_meta_cls(
            pickable_object_name=pickable_object_name,
            user_id=user_id,
            session_id=session_id
        )
        results.append(picks_cls(run=self, meta=meta))
        
    return results
```

### 4.4 CopickVoxelSpacingFS

Implements `CopickVoxelSpacing` using fsspec storage.

**Attributes:**
- `run`: The parent CopickRunFS instance
- `meta`: The voxel spacing metadata
- `config`: The configuration, inherited from run
- `_tomograms`: Cache for queried tomograms

**Key Methods:**
- `query_tomograms()`: Scans for available tomograms
- `_tomogram_factory()`: Returns appropriate filesystem-specific implementations
- `ensure()`: Checks if the voxel spacing directory exists and optionally creates it
- `refresh_tomograms()`: Clears the tomograms cache

**Example Implementation:**

```python
def query_tomograms(self) -> List["CopickTomogramFS"]:
    """Query available tomograms for this voxel spacing."""
    if not self.run.root.fs.exists(self.path):
        return []
        
    tomo_dirs = [d for d in self.run.root.fs.ls(self.path) 
                if self.run.root.fs.isdir(d) and d.endswith('.zarr')]
    
    results = []
    for tomo_dir in tomo_dirs:
        tomo_type = os.path.basename(tomo_dir).replace('.zarr', '')
        
        # Filter out feature maps, which also end with .zarr
        if '_features.zarr' in tomo_dir:
            continue
            
        tomogram_cls, tomogram_meta_cls = self._tomogram_factory()
        meta = tomogram_meta_cls(tomo_type=tomo_type)
        results.append(tomogram_cls(voxel_spacing=self, meta=meta))
        
    return results
```

### 4.5 CopickTomogramFS

Implements `CopickTomogram` using fsspec storage.

**Attributes:**
- `voxel_spacing`: The parent CopickVoxelSpacingFS instance
- `meta`: The tomogram metadata
- `config`: The configuration, inherited from voxel_spacing
- `_features`: Cache for queried feature maps

**Key Methods:**
- `query_features()`: Scans for available feature maps
- `_feature_factory()`: Returns appropriate filesystem-specific implementations
- `zarr()`: Returns a zarr store for the tomogram
- `numpy()`: Converts a region of the tomogram to a numpy array
- `set_region()`: Sets a region of the tomogram from a numpy array
- `from_numpy()`: Imports a complete tomogram from a numpy array

**Example Implementation:**

```python
def zarr(self) -> MutableMapping:
    """Get the zarr store for this tomogram."""
    import zarr
    from fsspec.implementations.mapped import MappedFile
    
    return MappedFile({
        'zarr_path': self.path,
        'fs': self.voxel_spacing.run.root.fs
    })
    
def numpy(
    self,
    zarr_group: str = "0",
    x: slice = slice(None, None),
    y: slice = slice(None, None),
    z: slice = slice(None, None),
) -> np.ndarray:
    """Get a region of the tomogram as a numpy array."""
    store = self.zarr()
    z_array = zarr.open(store, mode="r")
    
    if zarr_group in z_array:
        return z_array[zarr_group][x, y, z]
    else:
        raise KeyError(f"Zarr group '{zarr_group}' not found")
```

### 4.6 CopickFeaturesFS

Implements `CopickFeatures` using fsspec storage.

**Attributes:**
- `tomogram`: The parent CopickTomogramFS instance
- `meta`: The feature map metadata
- `config`: The configuration, inherited from tomogram

**Key Methods:**
- `zarr()`: Returns a zarr store for the feature map
- `numpy()`: Converts a region of the feature map to a numpy array
- `set_region()`: Sets a region of the feature map from a numpy array

**Example Implementation:**

```python
@property
def path(self) -> str:
    return os.path.join(
        self.tomogram.voxel_spacing.path, 
        f"{self.meta.tomo_type}_{self.meta.feature_type}_features.zarr"
    )
    
def zarr(self) -> MutableMapping:
    """Get the zarr store for this feature map."""
    import zarr
    from fsspec.implementations.mapped import MappedFile
    
    return MappedFile({
        'zarr_path': self.path,
        'fs': self.tomogram.voxel_spacing.run.root.fs
    })
```

### 4.7 CopickPicksFS

Implements `CopickPicks` using fsspec storage.

**Attributes:**
- `run`: The parent CopickRunFS instance
- `meta`: The picks metadata
- `config`: The configuration, inherited from run
- `_data`: Cache for loaded picks

**Key Methods:**
- `_load()`: Loads pick data from storage
- `_store()`: Stores pick data to storage
- `to_numpy()`: Converts picks to numpy arrays
- `from_numpy()`: Sets picks from numpy arrays

**Example Implementation:**

```python
def _load(self) -> List[CopickPoint]:
    """Load the picks from storage."""
    if not self.run.root.fs.exists(self.path):
        return []
        
    with self.run.root.fs.open(self.path, 'r') as f:
        data = json.load(f)
        
    return [CopickPoint(**point) for point in data]
    
def _store(self) -> None:
    """Store the picks to storage."""
    directory = os.path.dirname(self.path)
    self.run.root.fs.makedirs(directory, exist_ok=True)
    
    data = [point.dict() for point in self.data]
    
    with self.run.root.fs.open(self.path, 'w') as f:
        json.dump(data, f)
```

### 4.8 CopickMeshFS

Implements `CopickMesh` using fsspec storage.

**Attributes:**
- `run`: The parent CopickRunFS instance
- `meta`: The mesh metadata
- `config`: The configuration, inherited from run
- `_mesh`: Cache for loaded mesh

**Key Methods:**
- `_load()`: Loads mesh data from storage
- `_store()`: Stores mesh data to storage
- `to_napari()`: Converts mesh to napari format
- `from_napari()`: Sets mesh from napari format

**Example Implementation:**

```python
def _load(self) -> trimesh.Trimesh:
    """Load the mesh from storage."""
    if not self.run.root.fs.exists(self.path):
        return trimesh.Trimesh()
        
    with self.run.root.fs.open(self.path, 'rb') as f:
        mesh_data = f.read()
        
    return trimesh.load(BytesIO(mesh_data), file_type='glb')
    
def _store(self) -> None:
    """Store the mesh to storage."""
    directory = os.path.dirname(self.path)
    self.run.root.fs.makedirs(directory, exist_ok=True)
    
    mesh_bytes = trimesh.exchange.gltf.export_glb(self.mesh)
    
    with self.run.root.fs.open(self.path, 'wb') as f:
        f.write(mesh_bytes)
```

### 4.9 CopickSegmentationFS

Implements `CopickSegmentation` using fsspec storage.

**Attributes:**
- `run`: The parent CopickRunFS instance
- `meta`: The segmentation metadata
- `config`: The configuration, inherited from run

**Key Methods:**
- `zarr()`: Returns a zarr store for the segmentation
- `numpy()`: Converts a region of the segmentation to a numpy array
- `set_region()`: Sets a region of the segmentation from a numpy array

**Example Implementation:**

```python
@property
def path(self) -> str:
    base = os.path.join(
        self.run.segmentations_path,
        f"{self.meta.voxel_size:.3f}_{self.user_id}_{self.session_id}_{self.meta.name}"
    )
    
    if self.meta.is_multilabel:
        return f"{base}-multilabel.zarr"
    else:
        return f"{base}.zarr"
        
def zarr(self) -> MutableMapping:
    """Get the zarr store for this segmentation."""
    import zarr
    from fsspec.implementations.mapped import MappedFile
    
    return MappedFile({
        'zarr_path': self.path,
        'fs': self.run.root.fs
    })
```

### 4.10 CopickObjectFS

Implements `CopickObject` using fsspec storage.

**Attributes:**
- `root`: The parent CopickRootFS instance
- `meta`: The object metadata
- `config`: The configuration, inherited from root

**Key Methods:**
- `zarr()`: Returns a zarr store for the object
- `numpy()`: Converts a region of the object to a numpy array
- `set_region()`: Sets a region of the object from a numpy array

**Example Implementation:**

```python
@property
def path(self) -> str:
    return os.path.join(self.root.config.root, "Objects", f"{self.meta.name}.zarr")
    
def zarr(self) -> MutableMapping:
    """Get the zarr store for this object."""
    import zarr
    from fsspec.implementations.mapped import MappedFile
    
    return MappedFile({
        'zarr_path': self.path,
        'fs': self.root.fs
    })
```

## 5. Metadata Management

Each component in the filesystem implementation stores and loads metadata using standardized methods:

```python
def _store_metadata(self) -> None:
    """Store metadata to the filesystem."""
    meta_path = os.path.join(self.path, ".meta")
    directory = os.path.dirname(meta_path)
    self.run.root.fs.makedirs(directory, exist_ok=True)
    
    with self.run.root.fs.open(meta_path, 'w') as f:
        f.write(self.meta.json())
        
@staticmethod
def _load_metadata(path: str, fs: fsspec.filesystem) -> Dict:
    """Load metadata from the filesystem."""
    meta_path = os.path.join(path, ".meta")
    
    if not fs.exists(meta_path):
        return {}
        
    with fs.open(meta_path, 'r') as f:
        return json.loads(f.read())
```

This standardized approach ensures consistent handling of metadata across all components.

## 6. Integration with Multilayer System

The filesystem implementation is designed to integrate smoothly with the multilayer system:

### 6.1 Layer Configuration

Each filesystem instance is configured with a layer name and priority to determine its position in the layer stack:

```python
config = CopickConfigFS(
    root="s3://my-bucket/copick-data",
    fs_args={"key": "access_key", "secret": "secret_key"},
    layer_name="s3-data",
    priority=10,
    read_only=True
)
```

### 6.2 Method Compatibility

All methods in the filesystem implementation follow the signatures defined in the abstract API, ensuring they can be correctly proxied by the multilayer classes:

```python
# Abstract API definition
def query_picks(self) -> List["CopickPicks"]:
    """Query available picks for this run."""
    pass

# Filesystem implementation
def query_picks(self) -> List["CopickPicksFS"]:
    """Query available picks for this run."""
    # Implementation details...
```

### 6.3 Read-Only Support

The filesystem implementation respects the `read_only` flag in its configuration:

```python
def store(self) -> None:
    """Store the picks to storage."""
    if self.run.root.config.read_only:
        raise ValueError("Cannot store to a read-only filesystem")
        
    if self._data is not None:
        self._store()
```

This allows the multilayer system to include both read-only and read-write filesystem layers.

## 7. Fsspec Integration

The filesystem implementation leverages fsspec to support a wide range of filesystem types:

### 7.1 Supported Protocols

- `file://` - Local filesystem
- `s3://` - Amazon S3
- `gs://` - Google Cloud Storage
- `azure://` - Azure Blob Storage
- `http://` and `https://` - HTTP/HTTPS
- Many others supported by fsspec

### 7.2 Remote Filesystem Configuration

For remote filesystems, additional configuration is provided through the `fs_args` parameter:

```python
config = CopickConfigFS(
    root="s3://my-bucket/copick-data",
    fs_args={
        "key": "access_key",
        "secret": "secret_key",
        "client_kwargs": {
            "region_name": "us-west-2"
        }
    }
)
```

### 7.3 Zarr Integration

The implementation uses fsspec's `MappedFile` to create zarr stores that work with any filesystem:

```python
def zarr(self) -> MutableMapping:
    """Get the zarr store for this tomogram."""
    import zarr
    from fsspec.implementations.mapped import MappedFile
    
    return MappedFile({
        'zarr_path': self.path,
        'fs': self.voxel_spacing.run.root.fs
    })
```

This allows seamless access to zarr-based data (tomograms, feature maps, segmentations) across local and remote filesystems.

## 8. Conclusion

The filesystem layer provides a complete implementation of the CoPick abstract API using a single filesystem as the storage backend. It is designed to:

- Maintain the same lazy loading patterns as the abstract API
- Support both local and remote filesystems through fsspec
- Store data in a standardized directory structure with clear naming conventions
- Integrate with the multilayer system as either a read-only or read-write layer

This implementation serves as both a standalone CoPick API implementation and a building block for more complex data access patterns in the multilayer architecture. 