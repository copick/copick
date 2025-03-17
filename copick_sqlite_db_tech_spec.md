# CoPick SQLite DB Layer Technical Specification

## 1. Overview

The SQLite DB layer provides a specialized implementation of the CoPick abstract API defined in `models.py` that functions as an indexing and search service for the entire CoPick system. Rather than directly accessing or storing data, this layer maintains a SQLite database that catalogs metadata about CoPick objects across all layers, enabling rapid discovery, filtering, and access.

This implementation is designed to:
- Maintain a comprehensive index of all CoPick objects across all layers
- Provide high-performance metadata search and filtering capabilities
- Return initialized classes from their source layers with minimal overhead
- Support advanced querying across object types and layers
- Automatically update and maintain the index through periodic scanning

## 2. Core Concepts

### 2.1 Metadata Indexing

The SQLite DB layer creates and maintains an index of metadata for all CoPick objects (runs, tomograms, picks, etc.) across all configured layers. This index allows for rapid discovery of objects without having to scan each layer individually.

### 2.2 Layer Delegation

The layer does not directly implement data access methods. Instead, it uses the database to identify relevant objects and then returns properly initialized instances from their source layers:

```python
def get_tomogram(self, tomo_id: str) -> Optional[CopickTomogram]:
    """Get a tomogram by ID from any layer."""
    # Query the database for the tomogram
    tomo_info = self.db.get_tomogram_info(tomo_id)
    if not tomo_info:
        return None
        
    # Get the source layer
    source_layer = self.layer_manager.get_layer(tomo_info["layer_name"])
    if not source_layer:
        return None
        
    # Return the tomogram from its source layer
    return source_layer.get_tomogram_by_path(tomo_info["path"])
```

### 2.3 Automatic Indexing

The layer periodically scans all configured layers to update its index, ensuring that the database stays current with the actual state of the system. This indexing can be:
- Scheduled at regular intervals
- Triggered explicitly by the user
- Performed incrementally when specific changes are detected

### 2.4 Cross-Layer Querying

A key feature of this layer is providing unified queries that span across all layers in the system, allowing users to discover objects regardless of which layer they reside in:

```python
def find_tomograms(self, voxel_size: float = None, tomo_type: str = None, layer_name: str = None) -> List[CopickTomogram]:
    """Find tomograms matching criteria across all layers."""
    # Build the SQL query based on the criteria
    query = "SELECT id, layer_name, path FROM tomograms WHERE 1=1"
    params = []
    
    if voxel_size is not None:
        query += " AND voxel_size = ?"
        params.append(voxel_size)
        
    if tomo_type is not None:
        query += " AND tomo_type = ?"
        params.append(tomo_type)
        
    if layer_name is not None:
        query += " AND layer_name = ?"
        params.append(layer_name)
    
    # Execute the query
    results = self.db.execute(query, params)
    
    # Return initialized tomograms from their source layers
    tomograms = []
    for row in results:
        source_layer = self.layer_manager.get_layer(row["layer_name"])
        if source_layer:
            tomo = source_layer.get_tomogram_by_path(row["path"])
            if tomo:
                tomograms.append(tomo)
                
    return tomograms
```

## 3. Database Schema

The SQLite database uses a schema that tracks all CoPick object types and their relationships, with tables for each object type:

```sql
-- Runs table
CREATE TABLE runs (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    created TEXT,
    layer_name TEXT NOT NULL,
    path TEXT NOT NULL,
    indexed_at TEXT NOT NULL
);

-- Voxel spacings table
CREATE TABLE voxel_spacings (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    voxel_size REAL NOT NULL,
    layer_name TEXT NOT NULL,
    path TEXT NOT NULL,
    indexed_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(id)
);

-- Tomograms table
CREATE TABLE tomograms (
    id TEXT PRIMARY KEY,
    voxel_spacing_id TEXT NOT NULL,
    tomo_type TEXT NOT NULL,
    layer_name TEXT NOT NULL,
    path TEXT NOT NULL,
    dimensions TEXT,  -- JSON array of dimensions
    indexed_at TEXT NOT NULL,
    FOREIGN KEY (voxel_spacing_id) REFERENCES voxel_spacings(id)
);

-- Features table
CREATE TABLE features (
    id TEXT PRIMARY KEY,
    tomogram_id TEXT NOT NULL,
    feature_type TEXT NOT NULL,
    layer_name TEXT NOT NULL,
    path TEXT NOT NULL,
    indexed_at TEXT NOT NULL,
    FOREIGN KEY (tomogram_id) REFERENCES tomograms(id)
);

-- Picks table
CREATE TABLE picks (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    object_name TEXT NOT NULL,
    point_count INTEGER NOT NULL,
    layer_name TEXT NOT NULL,
    path TEXT NOT NULL,
    indexed_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(id)
);

-- Meshes table
CREATE TABLE meshes (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    object_name TEXT NOT NULL,
    layer_name TEXT NOT NULL,
    path TEXT NOT NULL,
    indexed_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(id)
);

-- Segmentations table
CREATE TABLE segmentations (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    name TEXT NOT NULL,
    voxel_size REAL NOT NULL,
    is_multilabel BOOLEAN NOT NULL,
    layer_name TEXT NOT NULL,
    path TEXT NOT NULL,
    indexed_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(id)
);

-- Objects table
CREATE TABLE objects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    is_particle BOOLEAN NOT NULL,
    identifier TEXT,
    layer_name TEXT NOT NULL,
    path TEXT NOT NULL,
    indexed_at TEXT NOT NULL
);

-- Layer status table
CREATE TABLE layer_status (
    layer_name TEXT PRIMARY KEY,
    last_indexed TEXT NOT NULL,
    indexing_status TEXT NOT NULL
);
```

### 3.1 Database Indices

To optimize query performance, the database includes indices on commonly filtered columns:

```sql
CREATE INDEX ix_runs_name ON runs(name);
CREATE INDEX ix_runs_layer_name ON runs(layer_name);

CREATE INDEX ix_voxel_spacings_run_id ON voxel_spacings(run_id);
CREATE INDEX ix_voxel_spacings_voxel_size ON voxel_spacings(voxel_size);
CREATE INDEX ix_voxel_spacings_layer_name ON voxel_spacings(layer_name);

CREATE INDEX ix_tomograms_voxel_spacing_id ON tomograms(voxel_spacing_id);
CREATE INDEX ix_tomograms_tomo_type ON tomograms(tomo_type);
CREATE INDEX ix_tomograms_layer_name ON tomograms(layer_name);

CREATE INDEX ix_features_tomogram_id ON features(tomogram_id);
CREATE INDEX ix_features_feature_type ON features(feature_type);
CREATE INDEX ix_features_layer_name ON features(layer_name);

CREATE INDEX ix_picks_run_id ON picks(run_id);
CREATE INDEX ix_picks_user_id ON picks(user_id);
CREATE INDEX ix_picks_session_id ON picks(session_id);
CREATE INDEX ix_picks_object_name ON picks(object_name);
CREATE INDEX ix_picks_layer_name ON picks(layer_name);

CREATE INDEX ix_meshes_run_id ON meshes(run_id);
CREATE INDEX ix_meshes_user_id ON meshes(user_id);
CREATE INDEX ix_meshes_session_id ON meshes(session_id);
CREATE INDEX ix_meshes_object_name ON meshes(object_name);
CREATE INDEX ix_meshes_layer_name ON meshes(layer_name);

CREATE INDEX ix_segmentations_run_id ON segmentations(run_id);
CREATE INDEX ix_segmentations_user_id ON segmentations(user_id);
CREATE INDEX ix_segmentations_session_id ON segmentations(session_id);
CREATE INDEX ix_segmentations_name ON segmentations(name);
CREATE INDEX ix_segmentations_voxel_size ON segmentations(voxel_size);
CREATE INDEX ix_segmentations_layer_name ON segmentations(layer_name);

CREATE INDEX ix_objects_name ON objects(name);
CREATE INDEX ix_objects_identifier ON objects(identifier);
CREATE INDEX ix_objects_layer_name ON objects(layer_name);
```

## 4. Key Classes

### 4.1 CopickConfigSQLiteDB

Extends `CopickConfig` with SQLite-specific configuration.

**Attributes:**
- `config_type`: Set to "sqlite_db"
- `db_path`: Path to the SQLite database file
- `auto_index`: Whether to automatically index layers when initialized
- `index_interval`: Time interval in seconds for periodic indexing (0 to disable)
- `layer_name`: Name to identify this layer in the multilayer stack
- `priority`: Integer priority value for the layer in the multilayer stack

**Example:**

```python
class CopickConfigSQLiteDB(CopickConfig):
    config_type: str = "sqlite_db"
    db_path: str
    auto_index: bool = True
    index_interval: int = 3600  # Index every hour
```

### 4.2 CopickRootSQLiteDB

Implements `CopickRoot` for the SQLite DB layer.

**Attributes:**
- `config`: The SQLite DB configuration
- `db`: The SQLite database manager
- `layer_manager`: The multilayer manager providing access to all layers

**Key Methods:**
- `query()`: Query available runs from the database
- `index_all_layers()`: Scan all layers and update the database
- `index_layer()`: Scan a specific layer and update the database
- `find_objects()`: Search for objects across all layers

**Example Implementation:**

```python
def query(self) -> List[CopickRun]:
    """Query available runs from the database."""
    # Query the database for all runs
    run_records = self.db.execute("SELECT id, layer_name, path FROM runs ORDER BY name")
    
    # Return initialized runs from their source layers
    runs = []
    for record in run_records:
        source_layer = self.layer_manager.get_layer(record["layer_name"])
        if source_layer:
            run = source_layer.get_run_by_path(record["path"])
            if run:
                runs.append(run)
                
    return runs
```

### 4.3 CopickDBManager

A class that manages the SQLite database operations.

**Attributes:**
- `db_path`: Path to the SQLite database file
- `connection`: The SQLite database connection

**Key Methods:**
- `initialize_db()`: Create the database schema if it doesn't exist
- `execute()`: Execute an SQL query
- `get_run_info()`: Get information about a run
- `get_tomogram_info()`: Get information about a tomogram
- `add_run()`: Add or update a run in the database
- `add_tomogram()`: Add or update a tomogram in the database
- `remove_layer_objects()`: Remove all objects from a specific layer

**Example Implementation:**

```python
def add_tomogram(self, tomogram: CopickTomogram, layer_name: str, path: str) -> None:
    """Add or update a tomogram in the database."""
    # Generate a unique ID for the tomogram
    tomo_id = f"{layer_name}:{path}"
    
    # Get the parent voxel spacing
    vs = tomogram.voxel_spacing
    vs_id = f"{layer_name}:{vs.path}"
    
    # Get dimensions if available
    dimensions = json.dumps(tomogram.dimensions) if hasattr(tomogram, "dimensions") else None
    
    # Add or update the tomogram record
    self.execute(
        """
        INSERT OR REPLACE INTO tomograms 
        (id, voxel_spacing_id, tomo_type, layer_name, path, dimensions, indexed_at)
        VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (tomo_id, vs_id, tomogram.tomo_type, layer_name, path, dimensions)
    )
```

### 4.4 CopickIndexer

A class that handles the indexing process for all layers.

**Attributes:**
- `db_manager`: The database manager
- `layer_manager`: The multilayer manager

**Key Methods:**
- `index_all_layers()`: Index all layers in the system
- `index_layer()`: Index a specific layer
- `index_run()`: Index a run and all its contents
- `index_tomogram()`: Index a tomogram
- `update_layer_status()`: Update the indexing status for a layer

**Example Implementation:**

```python
def index_run(self, run: CopickRun, layer_name: str) -> None:
    """Index a run and all its contents."""
    # Add the run to the database
    run_path = run.path if hasattr(run, "path") else f"run:{run.name}"
    self.db_manager.add_run(run, layer_name, run_path)
    
    # Index voxel spacings
    for vs in run.query_voxelspacings():
        vs_path = vs.path if hasattr(vs, "path") else f"vs:{vs.voxel_size}"
        self.db_manager.add_voxel_spacing(vs, layer_name, vs_path)
        
        # Index tomograms for this voxel spacing
        for tomo in vs.query_tomograms():
            self.index_tomogram(tomo, layer_name)
    
    # Index picks
    for pick in run.query_picks():
        pick_path = pick.path if hasattr(pick, "path") else f"picks:{pick.user_id}:{pick.session_id}:{pick.pickable_object_name}"
        self.db_manager.add_picks(pick, layer_name, pick_path)
    
    # Index meshes
    for mesh in run.query_meshes():
        mesh_path = mesh.path if hasattr(mesh, "path") else f"meshes:{mesh.user_id}:{mesh.session_id}:{mesh.pickable_object_name}"
        self.db_manager.add_mesh(mesh, layer_name, mesh_path)
    
    # Index segmentations
    for seg in run.query_segmentations():
        seg_path = seg.path if hasattr(seg, "path") else f"seg:{seg.user_id}:{seg.session_id}:{seg.name}:{seg.voxel_size}"
        self.db_manager.add_segmentation(seg, layer_name, seg_path)
```

## 5. Advanced Query Capabilities

The SQLite DB layer provides several advanced querying capabilities that would be complex or inefficient to implement across individual layers:

### 5.1 Cross-Layer Object Discovery

Find objects across all layers with a single query:

```python
def find_runs(self, name: str = None, description: str = None, layer_name: str = None) -> List[CopickRun]:
    """Find runs matching criteria across all layers."""
    # Build query conditions
    conditions = []
    params = []
    
    if name is not None:
        conditions.append("name LIKE ?")
        params.append(f"%{name}%")
        
    if description is not None:
        conditions.append("description LIKE ?")
        params.append(f"%{description}%")
        
    if layer_name is not None:
        conditions.append("layer_name = ?")
        params.append(layer_name)
    
    # Construct the query
    query = "SELECT id, layer_name, path FROM runs"
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    
    # Execute the query
    results = self.db.execute(query, params)
    
    # Return initialized runs
    runs = []
    for row in results:
        source_layer = self.layer_manager.get_layer(row["layer_name"])
        if source_layer:
            run = source_layer.get_run_by_path(row["path"])
            if run:
                runs.append(run)
                
    return runs
```

### 5.2 Relationship-Based Queries

Find objects based on their relationships to other objects:

```python
def find_tomograms_for_pick(self, pick_id: str) -> List[CopickTomogram]:
    """Find tomograms associated with a specific pick."""
    # Get the pick's run
    pick_info = self.db.get_pick_info(pick_id)
    if not pick_info:
        return []
    
    # Find tomograms in the same run
    query = """
    SELECT t.id, t.layer_name, t.path
    FROM tomograms t
    JOIN voxel_spacings vs ON t.voxel_spacing_id = vs.id
    WHERE vs.run_id = ?
    """
    
    results = self.db.execute(query, [pick_info["run_id"]])
    
    # Return initialized tomograms
    tomograms = []
    for row in results:
        source_layer = self.layer_manager.get_layer(row["layer_name"])
        if source_layer:
            tomo = source_layer.get_tomogram_by_path(row["path"])
            if tomo:
                tomograms.append(tomo)
                
    return tomograms
```

### 5.3 Full-Text Search

Support for text-based searches across object metadata:

```python
def search(self, query: str) -> Dict[str, List[Any]]:
    """Search for objects matching the text query across all tables."""
    results = {
        "runs": [],
        "tomograms": [],
        "picks": [],
        "meshes": [],
        "segmentations": [],
        "objects": []
    }
    
    # Search runs
    run_rows = self.db.execute(
        "SELECT id, layer_name, path FROM runs WHERE name LIKE ? OR description LIKE ?",
        [f"%{query}%", f"%{query}%"]
    )
    
    for row in run_rows:
        source_layer = self.layer_manager.get_layer(row["layer_name"])
        if source_layer:
            run = source_layer.get_run_by_path(row["path"])
            if run:
                results["runs"].append(run)
    
    # Similar searches for other object types...
    
    return results
```

### 5.4 Aggregation Queries

Provide summary statistics and aggregations across the database:

```python
def get_summary_statistics(self) -> Dict[str, Dict[str, int]]:
    """Get summary statistics for objects across all layers."""
    stats = {}
    
    # Get counts by layer
    layer_stats = self.db.execute("""
    SELECT layer_name,
           (SELECT COUNT(*) FROM runs WHERE layer_name = l.layer_name) AS run_count,
           (SELECT COUNT(*) FROM tomograms WHERE layer_name = l.layer_name) AS tomogram_count,
           (SELECT COUNT(*) FROM picks WHERE layer_name = l.layer_name) AS pick_count,
           (SELECT COUNT(*) FROM meshes WHERE layer_name = l.layer_name) AS mesh_count,
           (SELECT COUNT(*) FROM segmentations WHERE layer_name = l.layer_name) AS segmentation_count,
           (SELECT COUNT(*) FROM objects WHERE layer_name = l.layer_name) AS object_count
    FROM (SELECT DISTINCT layer_name FROM layer_status) l
    """)
    
    for row in layer_stats:
        stats[row["layer_name"]] = {
            "runs": row["run_count"],
            "tomograms": row["tomogram_count"],
            "picks": row["pick_count"],
            "meshes": row["mesh_count"],
            "segmentations": row["segmentation_count"],
            "objects": row["object_count"]
        }
    
    return stats
```

## 6. Indexing Process

The SQLite DB layer maintains its database through a structured indexing process:

### 6.1 Initial Indexing

When the layer is first initialized, it performs an initial indexing of all layers (if `auto_index` is enabled):

```python
def __init__(self, config: CopickConfigSQLiteDB):
    """Initialize the SQLite DB layer."""
    super().__init__(config)
    
    # Initialize the database
    self.db = CopickDBManager(config.db_path)
    self.db.initialize_db()
    
    # Create the indexer
    self.indexer = CopickIndexer(self.db, self.layer_manager)
    
    # Perform initial indexing if enabled
    if config.auto_index:
        self.index_all_layers()
    
    # Start periodic indexing if enabled
    if config.index_interval > 0:
        self._start_periodic_indexing(config.index_interval)
```

### 6.2 Periodic Indexing

The layer can automatically update its index at regular intervals:

```python
def _start_periodic_indexing(self, interval: int) -> None:
    """Start periodic indexing."""
    import threading
    
    def _indexing_thread():
        while True:
            try:
                self.index_all_layers()
            except Exception as e:
                logging.error(f"Error during periodic indexing: {e}")
            
            time.sleep(interval)
    
    # Start the indexing thread
    thread = threading.Thread(target=_indexing_thread, daemon=True)
    thread.start()
```

### 6.3 Layer-Specific Indexing

Individual layers can be indexed separately:

```python
def index_layer(self, layer_name: str) -> None:
    """Index a specific layer."""
    layer = self.layer_manager.get_layer(layer_name)
    if not layer:
        raise ValueError(f"Layer '{layer_name}' not found")
    
    # Update indexing status
    self.db.update_layer_status(layer_name, "indexing")
    
    try:
        # Clear existing objects for this layer
        self.db.remove_layer_objects(layer_name)
        
        # Index runs from this layer
        for run in layer.query():
            self.indexer.index_run(run, layer_name)
        
        # Index objects from this layer
        for obj in layer.query_objects():
            obj_path = obj.path if hasattr(obj, "path") else f"object:{obj.name}"
            self.db.add_object(obj, layer_name, obj_path)
        
        # Update indexing status
        self.db.update_layer_status(layer_name, "complete")
    except Exception as e:
        # Update indexing status on error
        self.db.update_layer_status(layer_name, f"error: {str(e)}")
        raise
```

### 6.4 Incremental Indexing

To optimize performance, the layer supports incremental indexing that only updates changed objects:

```python
def incremental_index_layer(self, layer_name: str) -> None:
    """Incrementally index a layer by checking for changes."""
    layer = self.layer_manager.get_layer(layer_name)
    if not layer:
        raise ValueError(f"Layer '{layer_name}' not found")
    
    # Get last indexed time for this layer
    last_indexed = self.db.get_layer_last_indexed(layer_name)
    
    # Update indexing status
    self.db.update_layer_status(layer_name, "indexing")
    
    try:
        # For each run, check if it's been modified since last indexing
        for run in layer.query():
            if hasattr(run, "last_modified") and run.last_modified > last_indexed:
                # Remove existing run data
                self.db.remove_run_objects(layer_name, run.name)
                
                # Re-index the run
                self.indexer.index_run(run, layer_name)
        
        # Similar checks for objects
        
        # Update indexing status
        self.db.update_layer_status(layer_name, "complete")
    except Exception as e:
        # Update indexing status on error
        self.db.update_layer_status(layer_name, f"error: {str(e)}")
        raise
```

## 7. Integration with Multilayer System

The SQLite DB layer is designed to work with the multilayer system as a query layer that spans across all other layers:

### 7.1 Layer Configuration

The SQLite DB layer is configured with access to the layer manager:

```python
config = CopickConfigSQLiteDB(
    db_path="/path/to/copick_index.db",
    auto_index=True,
    index_interval=3600,  # 1 hour
    layer_name="db-index",
    priority=1000  # Very high priority to be first in the stack
)
```

### 7.2 Layer Manager Access

The SQLite DB layer requires access to the layer manager to retrieve objects from their source layers:

```python
def set_layer_manager(self, layer_manager: LayerManager) -> None:
    """Set the layer manager for this layer."""
    self.layer_manager = layer_manager
    
    # Update the indexer
    self.indexer.layer_manager = layer_manager
```

### 7.3 Method Delegation

SQLite DB layer methods query the database but delegate actual data access to the source layers:

```python
def get_segmentation(self, seg_id: str) -> Optional[CopickSegmentation]:
    """Get a segmentation by ID from any layer."""
    # Query the database
    seg_info = self.db.get_segmentation_info(seg_id)
    if not seg_info:
        return None
    
    # Get the source layer
    source_layer = self.layer_manager.get_layer(seg_info["layer_name"])
    if not source_layer:
        return None
    
    # Return the segmentation from its source layer
    return source_layer.get_segmentation_by_path(seg_info["path"])
```

## 8. Performance Optimization

The SQLite DB layer includes several optimizations for performance:

### 8.1 Connection Pooling

For multi-threaded access, the layer uses connection pooling:

```python
class ConnectionPool:
    """SQLite connection pool."""
    def __init__(self, db_path: str, max_connections: int = 5):
        self.db_path = db_path
        self.max_connections = max_connections
        self.connections = queue.Queue(maxsize=max_connections)
        self.active_count = 0
        
    def get_connection(self) -> sqlite3.Connection:
        """Get a connection from the pool."""
        try:
            # Try to get an existing connection
            return self.connections.get_nowait()
        except queue.Empty:
            # Create a new connection if under the limit
            if self.active_count < self.max_connections:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                self.active_count += 1
                return conn
            
            # Otherwise wait for a connection
            return self.connections.get()
    
    def release_connection(self, conn: sqlite3.Connection) -> None:
        """Return a connection to the pool."""
        self.connections.put(conn)
```

### 8.2 Query Caching

Frequently used queries are cached to improve performance:

```python
class QueryCache:
    """Cache for frequently used queries."""
    def __init__(self, max_size: int = 100):
        self.cache = {}
        self.max_size = max_size
        self.lock = threading.Lock()
    
    def get(self, query: str, params: tuple) -> Optional[List[sqlite3.Row]]:
        """Get a cached query result."""
        key = (query, str(params))
        with self.lock:
            if key in self.cache:
                return self.cache[key]["result"]
        return None
    
    def set(self, query: str, params: tuple, result: List[sqlite3.Row]) -> None:
        """Cache a query result."""
        key = (query, str(params))
        with self.lock:
            # Evict entries if over size
            if len(self.cache) >= self.max_size:
                # Remove least recently used entry
                lru_key = min(self.cache.items(), key=lambda x: x[1]["accessed"])
                del self.cache[lru_key[0]]
            
            # Add to cache
            self.cache[key] = {
                "result": result,
                "accessed": time.time()
            }
```

### 8.3 Database Optimizations

The SQLite database is optimized for performance:

```python
def optimize_database(self) -> None:
    """Optimize the database for performance."""
    self.execute("PRAGMA journal_mode=WAL")  # Use WAL mode for better concurrency
    self.execute("PRAGMA synchronous=NORMAL")  # Reduce synchronous writes
    self.execute("PRAGMA cache_size=10000")  # Increase cache size
    self.execute("PRAGMA temp_store=MEMORY")  # Store temp tables in memory
    self.execute("ANALYZE")  # Analyze the database for query optimization
```

## 9. Conclusion

The SQLite DB layer provides a powerful indexing and search capability for the CoPick system. It is designed to:

- Maintain a comprehensive index of all CoPick objects across all layers
- Enable high-performance metadata queries and filtering
- Return properly initialized objects from their source layers
- Support advanced cross-layer queries and aggregations
- Automatically maintain the index through periodic scanning

This implementation enhances the CoPick system by providing a unified search and discovery mechanism that spans across all data sources and storage layers, enabling users to quickly find and access the objects they need regardless of where or how they are stored. 