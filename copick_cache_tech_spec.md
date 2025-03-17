# CoPick Cache Layer Technical Specification

## 1. Overview

The Cache layer provides a specialized implementation of the CoPick abstract API defined in `models.py`, derived from the filesystem layer. It is designed to efficiently cache data from other layers (particularly remote sources like the CryoET Data Portal) to local storage for improved performance and offline access.

This implementation is designed to:
- Accelerate data access by caching remote content locally
- Function as an intermediate layer within the multilayer architecture
- Integrate transparently with read-only layers to provide a caching proxy
- Maintain efficient operation through smart caching policies

## 2. Core Concepts

### 2.1 Transparent Caching

The cache layer intercepts data requests and transparently caches results locally. When data is requested again, it is served from the cache if available, avoiding expensive remote operations. When changes are written to the cache, they are propagated to the first writable remote layer (this can be turned off if desired).

### 2.2 Filesystem-Based Implementation

The cache layer extends the filesystem layer implementation, leveraging its existing storage mechanisms but adding cache-specific logic for data management, invalidation, and retrieval.

```python
class CopickRootCache(CopickRootFS):
    """Cache implementation of the root class, derived from filesystem implementation."""
    # Cache-specific extensions...
```

### 2.3 Lazy Loading and On-Demand Caching

Following the abstract API's design principles, the cache implementation employs lazy loading and on-demand caching:
- Data is cached only when accessed, not preemptively
- Metadata is cached separately from bulk data
- Cache operations happen in the background where possible

### 2.4 Cache Eviction Policies

The implementation includes configurable policies for cache management:
- Time-based expiration for metadata and data
- Size-based limits with least-recently-used (LRU) eviction
- Prioritization of different data types (metadata vs. volumetric data)

## 3. Cache Structure

The cache implementation uses the filesystem layer's directory structure with additional metadata for cache management:

```
CACHE_ROOT/
├── .cache_metadata/               # Cache management metadata
│   ├── entries.db                 # SQLite database of cache entries
│   ├── stats.json                 # Cache usage statistics
├── ExperimentRuns/                # Standard filesystem layer structure
│   ├── [run_name]/
│   │   ├── .meta                  # Run metadata
│   │   ├── .cache_info            # Cache metadata for this item
│   │   ├── VoxelSpacing[voxel_size]/
│   │   │   ├── .meta              # Voxel spacing metadata
│   │   │   ├── .cache_info        # Cache metadata for this item
│   │   │   ├── [tomo_type].zarr/  # Cached tomogram data
│   │   ├── Picks/
│   │   ├── Meshes/
│   │   ├── Segmentations/
├── Objects/
```

### 3.1 Cache Metadata

Each cached item includes additional metadata to manage the cache:

```python
class CacheInfo:
    """Cache entry metadata."""
    source_layer: str              # Layer that provided the original data
    cached_at: datetime            # When this item was cached
    last_accessed: datetime        # When this item was last accessed
    expires_at: Optional[datetime] # When this item expires
    size_bytes: int                # Size of the cached data
    is_complete: bool              # Whether all data is cached
    etag: Optional[str]            # ETag or version identifier
```

This metadata is stored alongside the cached data as `.cache_info` files.

## 4. Key Classes

### 4.1 CopickConfigCache

Extends `CopickConfigFS` with cache-specific configuration.

**Attributes:**
- `config_type`: Set to "cache"
- `root`: The root path for the cache storage
- `max_size_bytes`: Maximum size of the cache (0 for unlimited)
- `max_age`: Maximum age of cached items (0 for no expiration)
- `parent_layer`: Name of the layer being cached
- `layer_name`: Name to identify this layer in the multilayer stack
- `priority`: Integer priority value for the layer in the multilayer stack

**Example:**

```python
class CopickConfigCache(CopickConfigFS):
    config_type: str = "cache"
    max_size_bytes: int = 10 * 1024 * 1024 * 1024  # 10 GB
    max_age: int = 7 * 24 * 60 * 60  # 1 week in seconds
    parent_layer: str  # Name of the layer being cached
```

### 4.2 CopickRootCache

Implements `CopickRoot` by extending the filesystem implementation.

**Attributes:**
- `config`: The cache configuration
- `parent_root`: The parent layer's root instance
- `cache_manager`: Manager for cache operations

**Key Methods:**
- `query()`: Query available runs, caching results from the parent layer
- `ensure()`: Ensure the cache directory exists
- `clear_cache()`: Clear cached items according to policy
- `get_cache_stats()`: Get statistics about the cache

**Example Implementation:**

```python
def query(self) -> List[CopickRunCache]:
    """Query available runs, with caching."""
    # Try to load from cache first
    cached_runs = super().query()
    
    if cached_runs and not self._is_cache_stale("runs"):
        # Cache hit - update access time
        self.cache_manager.update_access_time("runs")
        return cached_runs
    
    # Cache miss or stale - query from parent
    parent_runs = self.parent_root.query()
    
    # Cache the results
    results = []
    for pr in parent_runs:
        run_cls, run_meta_cls = self._run_factory()
        run = run_cls(root=self, meta=pr.meta, parent_run=pr)
        run.ensure(create=True)
        results.append(run)
    
    # Update cache metadata
    self.cache_manager.set_cache_entry(
        "runs", 
        expires_at=datetime.now() + timedelta(seconds=self.config.max_age)
    )
    
    return results
```

### 4.3 CopickRunCache

Implements `CopickRun` by extending the filesystem implementation.

**Attributes:**
- `root`: The parent CopickRootCache instance
- `meta`: The run metadata
- `parent_run`: The parent layer's run instance

**Key Methods:**
- `query_voxelspacings()`: Query voxel spacings with caching
- `query_picks()`: Query picks with caching
- `ensure()`: Ensure the cache directory exists
- `is_cached()`: Check if this run is fully cached

**Example Implementation:**

```python
def query_voxelspacings(self) -> List[CopickVoxelSpacingCache]:
    """Query voxel spacings with caching."""
    # Try to load from cache first
    cached_spacings = super().query_voxelspacings()
    
    if cached_spacings and not self._is_cache_stale("voxel_spacings"):
        # Cache hit - update access time
        self.root.cache_manager.update_access_time(f"{self.path}/voxel_spacings")
        return cached_spacings
    
    # Cache miss or stale - query from parent
    parent_spacings = self.parent_run.query_voxelspacings()
    
    # Cache the results
    results = []
    for ps in parent_spacings:
        vs_cls, vs_meta_cls = self._voxel_spacing_factory()
        vs = vs_cls(run=self, meta=ps.meta, parent_voxel_spacing=ps)
        vs.ensure(create=True)
        results.append(vs)
    
    # Update cache metadata
    self.root.cache_manager.set_cache_entry(
        f"{self.path}/voxel_spacings", 
        expires_at=datetime.now() + timedelta(seconds=self.root.config.max_age)
    )
    
    return results
```

### 4.4 CopickVoxelSpacingCache

Implements `CopickVoxelSpacing` by extending the filesystem implementation.

**Attributes:**
- `run`: The parent CopickRunCache instance
- `meta`: The voxel spacing metadata
- `parent_voxel_spacing`: The parent layer's voxel spacing instance

**Key Methods:**
- `query_tomograms()`: Query tomograms with caching
- `ensure()`: Ensure the cache directory exists
- `get_tomograms()`: Get tomograms with filtering, using cache

**Example Implementation:**

```python
def query_tomograms(self) -> List[CopickTomogramCache]:
    """Query tomograms with caching."""
    # Try to load from cache first
    cached_tomograms = super().query_tomograms()
    
    if cached_tomograms and not self._is_cache_stale("tomograms"):
        return cached_tomograms
    
    # Cache miss or stale - query from parent
    parent_tomograms = self.parent_voxel_spacing.query_tomograms()
    
    # Cache the results
    results = []
    for pt in parent_tomograms:
        tomo_cls, tomo_meta_cls = self._tomogram_factory()
        tomo = tomo_cls(voxel_spacing=self, meta=pt.meta, parent_tomogram=pt)
        # Note: Tomogram data will be cached on demand, not here
        results.append(tomo)
    
    # Update cache metadata
    self.run.root.cache_manager.set_cache_entry(
        f"{self.path}/tomograms", 
        expires_at=datetime.now() + timedelta(seconds=self.run.root.config.max_age)
    )
    
    return results
```

### 4.5 CopickTomogramCache

Implements `CopickTomogram` by extending the filesystem implementation.

**Attributes:**
- `voxel_spacing`: The parent CopickVoxelSpacingCache instance
- `meta`: The tomogram metadata
- `parent_tomogram`: The parent layer's tomogram instance

**Key Methods:**
- `query_features()`: Query features with caching
- `zarr()`: Get the zarr store, caching data on access
- `numpy()`: Get a region as a numpy array, using cache
- `ensure_region_cached()`: Ensure a specific region is cached

**Example Implementation:**

```python
def zarr(self) -> MutableMapping:
    """Get the zarr store with caching."""
    # Check if tomogram is already cached (at least partially)
    if not self.voxel_spacing.run.root.fs.exists(self.path):
        # Create cache directory
        self._ensure_cache_directory()
        
    # Return zarr store backed by local cache
    # This will use a caching zarr store that fetches missing chunks from parent
    return CachingZarrStore(
        local_path=self.path,
        fs=self.voxel_spacing.run.root.fs,
        parent_store=self.parent_tomogram.zarr() if self.parent_tomogram else None,
        cache_manager=self.voxel_spacing.run.root.cache_manager
    )
```

### 4.6 CachingZarrStore

A specialized zarr store implementation that caches data on access.

**Attributes:**
- `local_path`: Path to the local cache
- `fs`: Filesystem for the cache
- `parent_store`: Parent zarr store to fetch missing data
- `cache_manager`: Cache manager for tracking metadata

**Key Methods:**
- `__getitem__()`: Get an item, caching if needed
- `__setitem__()`: Set an item in the cache
- `__contains__()`: Check if an item is in the cache

**Example Implementation:**

```python
def __getitem__(self, key: str) -> bytes:
    """Get an item, caching if needed."""
    chunk_path = os.path.join(self.local_path, key)
    
    # Check if chunk is cached
    if self.fs.exists(chunk_path):
        # Update access time
        self.cache_manager.update_access_time(chunk_path)
        with self.fs.open(chunk_path, 'rb') as f:
            return f.read()
    
    # Not cached, fetch from parent
    if self.parent_store is None:
        raise KeyError(f"Key {key} not found in cache and no parent store available")
    
    data = self.parent_store[key]
    
    # Cache the chunk
    self._cache_chunk(key, data)
    
    return data
```

### 4.7 CacheManager

A class that manages cache operations and policies.

**Attributes:**
- `cache_root`: Path to the cache root
- `fs`: Filesystem for the cache
- `db_path`: Path to the cache database
- `max_size_bytes`: Maximum size of the cache
- `max_age`: Maximum age of cached items

**Key Methods:**
- `update_access_time()`: Update the last access time for an item
- `set_cache_entry()`: Add or update a cache entry
- `is_stale()`: Check if a cache entry is stale
- `cleanup()`: Clean up the cache according to policy
- `get_stats()`: Get cache statistics

**Example Implementation:**

```python
def cleanup(self) -> int:
    """Clean up the cache according to policy, returning bytes freed."""
    conn = sqlite3.connect(self.db_path)
    cursor = conn.cursor()
    
    # First, remove expired entries
    now = datetime.now()
    cursor.execute(
        "SELECT path, size_bytes FROM cache_entries WHERE expires_at < ?", 
        (now,)
    )
    expired = cursor.fetchall()
    
    bytes_freed = 0
    for path, size in expired:
        if self.fs.exists(path):
            self.fs.rm(path, recursive=True)
        cursor.execute("DELETE FROM cache_entries WHERE path = ?", (path,))
        bytes_freed += size
    
    # If still over size limit, remove by LRU
    if self.max_size_bytes > 0:
        cursor.execute("SELECT SUM(size_bytes) FROM cache_entries")
        total_size = cursor.fetchone()[0] or 0
        
        if total_size > self.max_size_bytes:
            # Get entries ordered by last_accessed
            cursor.execute(
                "SELECT path, size_bytes FROM cache_entries ORDER BY last_accessed ASC"
            )
            lru_entries = cursor.fetchall()
            
            for path, size in lru_entries:
                if self.fs.exists(path):
                    self.fs.rm(path, recursive=True)
                cursor.execute("DELETE FROM cache_entries WHERE path = ?", (path,))
                bytes_freed += size
                
                total_size -= size
                if total_size <= self.max_size_bytes:
                    break
    
    conn.commit()
    conn.close()
    
    return bytes_freed
```

## 5. Cache Management

### 5.1 Cache Initialization

The cache is initialized when the layer is first created:

```python
def __init__(self, config: CopickConfigCache):
    """Initialize the cache layer."""
    super().__init__(config)
    
    # Create cache metadata directory
    cache_meta_dir = os.path.join(self.config.root, ".cache_metadata")
    self.fs.makedirs(cache_meta_dir, exist_ok=True)
    
    # Initialize cache database
    db_path = os.path.join(cache_meta_dir, "entries.db")
    self.cache_manager = CacheManager(
        cache_root=self.config.root,
        fs=self.fs,
        db_path=db_path,
        max_size_bytes=self.config.max_size_bytes,
        max_age=self.config.max_age
    )
    
    # Run initial cleanup to enforce policies
    self.cache_manager.cleanup()
```

### 5.2 Chunk-Based Caching

For large data like tomograms, the cache uses chunk-based storage to avoid caching entire volumes when only portions are needed:

```python
def numpy(
    self,
    zarr_group: str = "0",
    x: slice = slice(None, None),
    y: slice = slice(None, None),
    z: slice = slice(None, None),
) -> np.ndarray:
    """Get a region of the tomogram as a numpy array, using cache."""
    # Get the zarr store with caching
    store = self.zarr()
    z_array = zarr.open(store, mode="r")
    
    if zarr_group in z_array:
        # This will cache any missing chunks through the CachingZarrStore
        return z_array[zarr_group][x, y, z]
    else:
        raise KeyError(f"Zarr group '{zarr_group}' not found")
```

### 5.3 Background Caching

The implementation supports background caching for prefetching data:

```python
def prefetch_region(
    self,
    zarr_group: str = "0",
    x: slice = slice(None, None),
    y: slice = slice(None, None),
    z: slice = slice(None, None),
) -> None:
    """Prefetch a region of the tomogram in the background."""
    # Start a background thread to cache the region
    thread = threading.Thread(
        target=self._prefetch_region_worker,
        args=(zarr_group, x, y, z),
        daemon=True
    )
    thread.start()
    
def _prefetch_region_worker(
    self,
    zarr_group: str,
    x: slice,
    y: slice,
    z: slice,
) -> None:
    """Worker for prefetching a region."""
    try:
        store = self.zarr()
        z_array = zarr.open(store, mode="r")
        
        if zarr_group in z_array:
            # Access the region to trigger caching through CachingZarrStore
            _ = z_array[zarr_group][x, y, z]
    except Exception as e:
        logging.warning(f"Error prefetching region: {e}")
```

### 5.4 Cache Invalidation

The cache implementation includes methods for invalidating stale entries:

```python
def invalidate(self, path: str = None) -> None:
    """Invalidate cache entries at the given path or all if None."""
    if path is None:
        # Invalidate all cache entries
        self.cache_manager.clear_all()
    else:
        # Invalidate specific path and all children
        self.cache_manager.clear_path(path)
```

## 6. Integration with Multilayer System

The cache layer is designed to sit between end users and other layers in the multilayer system:

### 6.1 Layer Configuration

The cache layer is configured with a parent layer to cache:

```python
config = CopickConfigCache(
    root="/path/to/cache",
    max_size_bytes=10 * 1024 * 1024 * 1024,  # 10 GB
    max_age=7 * 24 * 60 * 60,  # 1 week
    parent_layer="portal-public",
    layer_name="cached-portal",
    priority=5  # Higher priority than the parent
)
```

### 6.2 Parent Layer Connection

The cache layer requires a connection to its parent layer:

```python
def connect_parent_layer(self, parent_root: CopickRoot) -> None:
    """Connect the parent layer to this cache layer."""
    self.parent_root = parent_root
```

### 6.3 Method Passthrough

Cache methods follow the same signatures as the abstract API, allowing them to be properly proxied by the multilayer system:

```python
def query_picks(self) -> List[CopickPicksCache]:
    """Query picks with caching."""
    # Try cache first
    cached_picks = super().query_picks()
    
    if cached_picks and not self._is_cache_stale("picks"):
        return cached_picks
    
    # Get from parent
    parent_picks = self.parent_run.query_picks()
    
    # Cache and return
    results = self._cache_picks(parent_picks)
    return results
```

## 7. Cache Utilities

### 7.1 Cache Introspection

The cache layer provides utilities for inspecting the cache state:

```python
def get_cache_info(self, path: str = None) -> Dict:
    """Get information about the cache or a specific path."""
    return self.cache_manager.get_info(path)
```

### 7.2 Cache Prefetching

The layer provides methods for prefetching entire objects:

```python
def prefetch_tomogram(self, tomo_id: str) -> None:
    """Prefetch an entire tomogram in the background."""
    # Get the tomogram
    tomogram = self.get_tomogram(tomo_id)
    if tomogram is None:
        raise ValueError(f"Tomogram {tomo_id} not found")
    
    # Start a background thread to prefetch
    thread = threading.Thread(
        target=self._prefetch_tomogram_worker,
        args=(tomogram,),
        daemon=True
    )
    thread.start()
```


## 8. Conclusion

The Cache layer provides an efficient caching mechanism for the CoPick system, derived from the filesystem layer. It is designed to:

- Accelerate data access by caching remote resources locally
- Manage cache size through configurable policies
- Cache data at both metadata and chunk levels
- Prefetch data in the background for improved performance
- Integrate with the multilayer system to provide a transparent caching layer

This implementation bridges the gap between remote resources and local performance, enabling efficient operation even with large datasets or intermittent connectivity. 