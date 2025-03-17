# CoPick CryoET Data Portal Layer Technical Specification

## 1. Overview

The CryoET Data Portal layer provides a concrete implementation of the CoPick abstract API defined in `models.py`, focused on accessing data from the CryoET Data Portal. This layer enables read-only access to curated datasets available through the portal's API.

This implementation is designed to:
- Provide access to public cryoET datasets without requiring local storage
- Function as a read-only layer within the multilayer architecture
- Support efficient querying and filtering of portal data
- Maintain efficient operation with large datasets through lazy loading

## 2. Core Concepts

### 2.1 Portal-Based Data Access

This layer focuses exclusively on accessing data from the CryoET Data Portal. It provides a read-only view of the portal's contents, mapping the portal's data model to CoPick's abstract API concepts.

### 2.2 Direct API Library Integration

The layer uses the `cryoet_data_portal` Python library directly to communicate with the CryoET Data Portal. This approach provides a high-level interface to the portal's data without requiring custom REST API client implementation.

```python
import cryoet_data_portal as cdp

client = cdp.Client()
datasets = cdp.Dataset.get_by_id(client, dataset_id)
```

### 2.3 Simple Layer Architecture

The CryoET Data Portal layer implements the abstract API using a clean, focused approach that exclusively queries the portal. This simplification eliminates the older overlay/static structure in favor of a direct portal access model that works seamlessly with the multilayer system.

### 2.4 Lazy Loading Pattern

Following the abstract API's design principles, the portal implementation employs lazy loading throughout:
- Metadata is loaded only when accessed
- Data collections are queried only when requested
- Tomogram data is accessed in chunks via zarr

### 2.5 Portal Metadata Extensions

The implementation extends the standard metadata classes with portal-specific fields to capture additional metadata available from the CryoET Data Portal:

```python
class CopickTomogramMetaPortal(CopickTomogramMeta):
    portal_tomo_id: Optional[int] = None
    portal_tomo_path: Optional[str] = None
    portal_metadata: Optional[PortalTomogramMeta] = PortalTomogramMeta()
```

## 3. Data Access Model

### 3.1 Portal Library Structure

The CryoET Data Portal organizes data in a hierarchical structure which is reflected in the library's object model:

```
Portal
├── Datasets
│   ├── Runs
│   │   ├── TomogramVoxelSpacings
│   │   │   ├── Tomograms
│   │   │   │   ├── Metadata
│   │   │   │   ├── Data
│   │   │   ├── Annotations
│   │   │   │   ├── AnnotationFiles (Points)
│   │   │   │   ├── AnnotationFiles (Segmentations)
```

### 3.2 CoPick to Portal Mapping

The portal layer maps CryoET Portal concepts to CoPick concepts:

| CoPick Concept | Portal Concept |
|----------------|----------------|
| Run | Run |
| VoxelSpacing | TomogramVoxelSpacing |
| Tomogram | Tomogram |
| Picks | AnnotationFile (Point or OrientedPoint) |
| Segmentation | AnnotationFile (SegmentationMask) |
| Mesh | AnnotationFile (Mesh) - Not fully implemented in portal |
| Features | Not available in portal |

### 3.3 Direct Access Approach

The implementation uses direct access to portal data through:
1. **Portal API** (via cryoet_data_portal): For metadata and annotations
2. **S3 Direct Access**: For efficient access to tomogram and annotation data

## 4. Key Classes

### 4.1 CopickConfigPortal

Extends `CopickConfig` for the CryoET Data Portal configuration.

**Attributes:**
- `config_type`: Set to "cryoet_data_portal"
- `dataset_ids`: List of dataset IDs to access from the portal
- `fs_args`: Optional arguments for S3 access (credentials, etc.)
- `layer_name`: Name to identify this layer in the multilayer stack
- `priority`: Integer priority value for the layer in the multilayer stack

**Example:**

```python
class CopickConfigPortal(CopickConfig):
    config_type: str = "cryoet_data_portal"
    dataset_ids: List[int]
    fs_args: Optional[Dict[str, Any]] = {}
    layer_name: str = "portal"
    priority: int = 100
```

### 4.2 CopickRootPortal

Implements `CopickRoot` for the portal layer.

**Attributes:**
- `config`: The portal configuration
- `datasets`: List of dataset objects from the portal
- `_fs`: Cached S3 filesystem for data access

**Key Methods:**
- `query()`: Queries available runs from the portal
- `_run_factory()` and `_object_factory()`: Return appropriate portal-specific implementations
- `go_map`: Property returning Gene Ontology mappings

**Example Implementation:**

```python
def query(self) -> List[CopickRunPortal]:
    """Query available runs from the portal."""
    client = cdp.Client()
    portal_runs = cdp.Run.find(client, [cdp.Run.dataset_id._in([d.id for d in self.datasets])])

    runs = []
    for pr in portal_runs:
        run_cls, run_meta_cls = self._run_factory()
        meta = run_meta_cls.from_portal(pr)
        runs.append(run_cls(root=self, meta=meta))

    return runs
```

### 4.3 CopickRunPortal

Implements `CopickRun` for the portal layer.

**Attributes:**
- `root`: The parent CopickRootPortal instance
- `meta`: The run metadata with portal extensions
- `portal_run_id`: ID of the corresponding portal run

**Key Methods:**
- `query_voxel_spacings()`: Queries voxel spacings from the portal
- `query_picks()`: Queries picks from the portal
- `query_segmentations()`: Queries segmentations from the portal
- `get_picks()`, `get_segmentations()`: Enhanced query methods with portal metadata filtering

**Example Implementation:**

```python
def query_picks(self) -> List[CopickPicksPortal]:
    """Query available picks from the portal."""
    if self.portal_run_id is None:
        return []

    # Find all point annotations
    client = cdp.Client()
    go_map = self.root.go_map
    point_annos = cdp.AnnotationFile.find(
        client,
        [
            cdp.AnnotationFile.annotation_shape.annotation.run_id == self.portal_run_id,
            cdp.AnnotationFile.annotation_shape.shape_type._in(["Point", "OrientedPoint"]),
            cdp.AnnotationFile.annotation_shape.annotation.object_id._in(go_map.keys()),
        ],
    )

    picks_cls, picks_meta_cls = self._picks_factory()
    return [
        picks_cls(
            run=self,
            meta=picks_meta_cls.from_portal(af, name=go_map[af.annotation_shape.annotation.object_id]),
        )
        for af in point_annos
    ]
```

### 4.4 CopickVoxelSpacingPortal

Implements `CopickVoxelSpacing` for the portal layer.

**Attributes:**
- `run`: The parent CopickRunPortal instance
- `meta`: The voxel spacing metadata with portal extensions
- `portal_vs_id`: ID of the corresponding portal voxel spacing

**Key Methods:**
- `query_tomograms()`: Queries tomograms from the portal
- `get_tomograms()`: Enhanced query method with portal metadata filtering

**Example Implementation:**

```python
def query_tomograms(self) -> List[CopickTomogramPortal]:
    """Query available tomograms from the portal."""
    if self.portal_vs_id is None:
        return []

    client = cdp.Client()
    portal_tomos = cdp.Tomogram.find(client, [cdp.Tomogram.tomogram_voxel_spacing_id == self.portal_vs_id])
    tomogram_cls, tomogram_meta_cls = self._tomogram_factory()
    
    return [
        tomogram_cls(
            voxel_spacing=self, 
            meta=tomogram_meta_cls.from_portal(t)
        )
        for t in portal_tomos
    ]
```

### 4.5 CopickTomogramPortal

Implements `CopickTomogram` for the portal layer.

**Attributes:**
- `voxel_spacing`: The parent CopickVoxelSpacingPortal instance
- `meta`: The tomogram metadata with portal extensions
- `portal_tomo_id`: ID of the corresponding portal tomogram
- `portal_tomo_path`: S3 path to the portal tomogram data

**Key Methods:**
- `query_features()`: Returns empty list (features not in portal)
- `zarr()`: Returns a zarr store for the tomogram using S3 storage
- `numpy()`: Retrieves tomogram data as numpy array

**Example Implementation:**

```python
def zarr(self) -> zarr.storage.FSStore:
    """Get zarr store for the tomogram."""
    fs = s3fs.S3FileSystem(anon=True)
    path = self.meta.portal_tomo_path
    
    return zarr.storage.FSStore(
        path,
        fs=fs,
        mode="r",
        key_separator="/",
        dimension_separator="/",
    )
```

### 4.6 CopickPicksPortal

Implements `CopickPicks` for the portal layer.

**Attributes:**
- `run`: The parent CopickRunPortal instance
- `meta`: The picks metadata with portal extensions
- `portal_annotation_file_id`: ID of the corresponding portal annotation file
- `portal_annotation_file_path`: S3 path to the portal annotation file

**Key Methods:**
- `_load()`: Loads pick data from the portal
- `store()`: Raises exception (read-only implementation)

**Example Implementation:**

```python
def _load(self) -> List[CopickPoint]:
    """Load the picks from the portal."""
    if self.meta.portal_annotation_file_id is None:
        return []
        
    client = cdp.Client()
    af = cdp.AnnotationFile.get_by_id(client, self.meta.portal_annotation_file_id)
    
    # Load points from S3
    fs = s3fs.S3FileSystem(anon=True)
    vs = af.tomogram_voxel_spacing.voxel_spacing
    points = []
    
    with fs.open(af.s3_path, "r") as f:
        for line in f:
            data = json.loads(line)
            x, y, z = data["location"]["x"] * vs, data["location"]["y"] * vs, data["location"]["z"] * vs
            
            point = CopickPoint(
                location=CopickLocation(x=x, y=y, z=z),
            )
            
            # Handle oriented points if applicable
            if af.annotation_shape.shape_type == "OrientedPoint":
                mat = np.eye(4, 4)
                mat[:3, :3] = np.array(data["xyz_rotation_matrix"])
                point.transformation_ = mat.tolist()
                
            points.append(point)
            
    return points
```

### 4.7 CopickSegmentationPortal

Implements `CopickSegmentation` for the portal layer.

**Attributes:**
- `run`: The parent CopickRunPortal instance
- `meta`: The segmentation metadata with portal extensions
- `portal_segmentation_id`: ID of the corresponding portal segmentation

**Key Methods:**
- `zarr()`: Returns a zarr store for the segmentation using S3 storage
- `numpy()`: Retrieves segmentation data as numpy array

**Example Implementation:**

```python
def zarr(self) -> zarr.storage.FSStore:
    """Get zarr store for the segmentation."""
    fs = s3fs.S3FileSystem(anon=True)
    path = self.meta.portal_annotation_file_path
    
    return zarr.storage.FSStore(
        path,
        fs=fs,
        mode="r",
        key_separator="/",
        dimension_separator="/",
    )
```

## 5. Portal-Specific Components

### 5.1 Portal Metadata Classes

The implementation includes custom classes for handling portal-specific metadata:

```python
class PortalAnnotationMeta(BaseModel):
    portal_metadata: Optional[_PortalAnnotation] = _PortalAnnotation()
    portal_authors: Optional[List[str]] = []

    @classmethod
    def from_annotation(cls, source: cdp.AnnotationFile):
        anno = source.annotation_shape.annotation
        return cls(
            portal_metadata=_PortalAnnotation(**anno.to_dict()),
            portal_authors=[a.name for a in anno.authors],
        )

    def compare(self, meta: Dict[str, Any], authors: List[str]) -> bool:
        # Metadata comparison for filtering
        qpm = _PortalAnnotation(**meta)
        qa = authors

        fields = list(qpm.model_fields_set)
        test_fields = [f for f in fields if getattr(qpm, f) is not None]

        author_condition = all(a in self.portal_authors for a in qa)
        meta_condition = all(getattr(self.portal_metadata, f) == getattr(qpm, f) for f in test_fields)

        return author_condition and meta_condition
```

These classes provide:
- Conversion from portal objects to metadata
- Advanced filtering through metadata comparison
- Standardized access to portal-specific attributes

### 5.2 Enhanced Filtering Capabilities

The implementation supports advanced filtering based on portal metadata:

```python
def get_picks(
    self,
    object_name: str = None,
    user_id: str = None,
    session_id: str = None,
    portal_meta_query: Dict[str, Any] = None,
    portal_author_query: List[str] = None,
) -> List[CopickPicksPortal]:
    """Get picks with advanced filtering options."""
    picks = super().get_picks(object_name, user_id, session_id)

    if portal_meta_query is None and portal_author_query is None:
        return picks

    if portal_meta_query is None:
        portal_meta_query = {}

    if portal_author_query is None:
        portal_author_query = []

    # Compare the metadata
    picks = [p for p in picks if p.meta.portal_metadata.compare(portal_meta_query, portal_author_query)]

    return picks
```

## 6. Integration with Multilayer System

### 6.1 Read-Only Layer Design

The portal layer is designed as a strictly read-only layer within the multilayer system:

```python
def store(self) -> None:
    """Store operation (not supported in portal layer)."""
    raise ValueError("Cannot store to the read-only CryoET Data Portal layer")
```

### 6.2 Layer Configuration

The portal layer is configured with a name and priority to determine its position in the layer stack:

```python
config = CopickConfigPortal(
    dataset_ids=[1, 2, 3],
    layer_name="portal-public",
    priority=10
)
```

## 7. Data Conversion and Transformation

### 7.1 Portal to CoPick Conversion

The implementation includes methods to convert portal objects to CoPick objects:

```python
@classmethod
def from_portal(cls, source: cdp.AnnotationFile, name: Optional[str] = None):
    """Convert portal annotation file to CoPick picks metadata."""
    anno = source.annotation_shape.annotation
    user = "data-portal"
    session = str(source.id)

    object_name = name if name else f"{camel(anno.object_name)}-{source.id}"
    portal_meta = PortalAnnotationMeta.from_annotation(source)

    return cls(
        pickable_object_name=object_name,
        user_id=user,
        session_id=session,
        portal_annotation_file_id=source.id,
        portal_annotation_file_path=source.s3_path,
        portal_metadata=portal_meta,
    )
```

### 7.2 Gene Ontology Integration

The implementation supports mapping between Gene Ontology (GO) terms and objects:

```python
@property
def go_map(self) -> Dict[str, str]:
    """Map GO IDs to human-readable names."""
    return {po.identifier: po.name for po in self.pickable_objects if po.identifier is not None}
```

This mapping allows:
- Consistent naming of objects across the portal
- Integration with standard ontologies
- Enhanced searchability of annotations

## 8. Conclusion

The CryoET Data Portal layer provides a read-only implementation of the CoPick abstract API, focused on accessing data from the portal. It is designed to:

- Provide seamless access to public cryoET datasets
- Integrate directly with the cryoet_data_portal Python library
- Support advanced filtering based on portal metadata
- Maintain the same lazy loading patterns as the abstract API
- Integrate with the multilayer system as a read-only layer

This implementation serves as a specialized component in the multilayer architecture, enabling access to curated datasets without requiring local storage. 