
## Data Entities

### Root

The project's root. This is the entry point for the copick API. It allows access to information about the [pickable
objects](#pickable-object) and [runs]() contained in the project.

??? example "Example Code - Print available objects and runs"
    ```python
    --8<-- "root_list_objects_runs.py"
    ```

    Refer to the [API Reference](api_reference/base_classes/data_entity_models/CopickRoot.md) for more information on
    the CopickRoot API.


### Pickable Object

Objects are any entity that can be labeled inside a 3D image using points, meshes or dense segmentation masks. In most
cases, these will be macromolecular complexes or other cellular structures, like membranes. They can also be more
abstract entities like "contamination particles", "carbon edges", or "sample boundaries".

In the configuration file, each object is defined by a JSON object, that allows the user to specify the object's name,
label, color, radius, and other properties.

!!! warning "Naming Conventions"
    Object names should never contain underscores!

??? example "Example Code - Read an object's density map."
    ```python
    --8<-- "object_read_map.py"
    ```

    Refer to the [API Reference](api_reference/base_classes/data_entity_models/CopickObject.md) for more information on
    the CopickObject API.

!!! note "Example Object Definition"
    The following is an example of a pickable object definition in the configuration file:
    ```json
    {
        "name": "proteasome",
        "is_particle": true,
        "pdb_id": "3J9I",
        "emdb_id": "1234",
        "identifier": "GO:0001234",
        "label": 1,
        "color": [255, 0, 0, 255],
        "radius": 60,
        "map_threshold": 0.0418,
        "metadata": {
            "source": "experimental_data",
            "confidence": 0.95,
            "notes": "High-resolution structure"
        }
    }
    ```

    - `name`: The name of the object, which should be unique within one project.
    - `is_particle`: A boolean indicating whether the object can be represented by point annotations. By default, all
        objects can be represented by mesh annotations or dense segmentations.

    - `pdb_id`: The PDB ID of the object, if available.
    - `emdb_id`: The EMDB ID of the object, if available.
    - `identifier`: An ontology/database identifier for the object, if available. Supported namespaces are
        `GO`, `UniProtKB`, `CHEBI`, `PDB` (note the dash separator, e.g. `PDB-1BXN`), `UBERON`, `CL`, and `CDPO`.
        When using the data portal, this field is matched exactly against the annotation `object_id` to find
        matching annotations in the data portal.
    - `label`: An integer that indicates which numeric label should be used in segmentations to represent this object.
    - `color`: An array of four integers that represent the RGBA color of the object when rendered in a 3D viewer.
    - `radius`: An integer that represents the radius of the object in angstroms. This is used to determine the size of the
        object when rendering it as a sphere in a 3D viewer.
    - `map_threshold`: A float that represents the threshold value to use when a density map is used to represent the
        object. This is used to determine the isosurface level to use when rendering the object as a mesh. Density maps are
        discovered by the copick API by looking for files with the same name as the object in the `Objects` directory of
        the project's root.
    - `metadata`: An optional dictionary that can contain arbitrary key-value pairs for storing additional custom
        information about the object. This field allows users to attach project-specific metadata such as confidence scores,
        data sources, or processing notes. The key `copick` is reserved for copick's own extensions of the object
        definition (see Filament Objects below).

#### Filament Objects

A filament is a continuous, typically helical or tubular assembly, such as a microtubule or an actin filament, that is
annotated with ordered points along its axis. An object is declared a filament by a `FilamentSpec` stored in its
metadata under `metadata["copick"]["filament"]`:

```json
{
    "name": "microtubule",
    "is_particle": true,
    "label": 2,
    "radius": 120,
    "metadata": {
        "copick": {
            "filament": {"polar": true, "helical_rise_a": 9.4}
        }
    }
}
```

- `polar`: Whether the structure has a polarity (`true` for microtubules and actin). Omitted if not stated.
- `helical_rise_a`, `helical_twist_deg`: Rise per subunit in angstrom and twist per subunit in degrees. Both are
  descriptive; tools never use them as a default sampling distance.

A filament object must have `is_particle: true`, because filaments are annotated with points; its `radius` is the tube
radius. Copick validates the declaration when it reads the configuration. Clients that do not know filaments read the
object as an ordinary particle, and keep the declaration when they rewrite the configuration because it lives in
`metadata`.

```python
root.new_object(name="microtubule", is_particle=True, radius=120, filament={"polar": True})
root.get_object("microtubule").is_filament  # True
```

```bash
copick add object -c config.json --name microtubule --object-type filament --radius 120 --polar
```

Picks of a filament object follow the [filament conventions](geometry.md#24-filament-frames): `instance_id` is the
filament ID, points are ordered along each filament, and the transform's +Z axis is the filament axis.


### Run

A run is a collection of data that is associated with a particular location on the sample. Run objects allow access to
any 3D image data, segmentations, and annotations that are associated with a particular location on the sample. Images
are stored in groups based on their voxel spacing, while point annotations, mesh annotations, and dense segmentations
are related to the run as a whole.

??? example "Example Code - List available segmentations for a run"
    ```python
    --8<-- "run_list_segmentations.py"
    ```

    Refer to the [API Reference](api_reference/base_classes/data_entity_models/CopickRun.md) for more information on
    the CopickRun API.


### Voxel Spacing

A voxel spacing groups together all tomograms of a particular resolution. Voxel spacings are rounded to the third
decimal place.

??? example "Example Code - List available tomograms for a voxel spacing"
    ```python
    --8<-- "voxel_spacing_list_tomograms.py"
    ```

    Refer to the [API Reference](api_reference/base_classes/data_entity_models/CopickVoxelSpacing.md) for more information
    on the CopickVoxelSpacing API.


### Image data
#### Tomogram

At each resolution, multiple tomograms can be stored. Tomograms are stored as OME-NGFF files, which are a zarr-based
format that allows for efficient access to multiscale 3D image data. The filename of the zarr file allows relating the
image to its reconstruction method or processing steps. Typical useful tomogram types are `wbp`, `sirt`, `denoised`,
etc.

??? example "Example Code - Read a tomogram into a numpy array"
    ```python
    --8<-- "tomogram_read_image.py"
    ```

    Refer to the [API Reference](api_reference/base_classes/data_entity_models/CopickTomogram.md) for more information on
    the CopickTomogram API.

!!! note "Example tomogram file name"
    Tomograms are named according to the following pattern:
    ```
    wbp.zarr
    ```

    The `wbp` part of the filename is the type of tomogram. This could be `wbp`, `sirt`, `denoised`, etc.


#### Feature Map

Feature maps are stored as OME-NGFF files with relation to the tomogram they are computed from. Feature maps are stored
as zarr files, and can be used to store any type of data that is computed from a tomogram. They may be useful for
interactive segmentation tasks.

??? example "Example Code - Read a feature map into a numpy array"
    ```python
    --8<-- "features_read_image.py"
    ```

    Refer to the [API Reference](api_reference/base_classes/data_entity_models/CopickFeatures.md) for more information on
    the CopickFeatures API.

!!! note "Example feature map file name"
    Feature maps are named according to the following pattern:
    ```
    wbp_density_features.zarr
    ```

    The `wbp` part of the filename is the type of tomogram that the feature map was computed from. The `sobel` part of
    the filename is the type of feature that the feature map represents. This could be `density`, `gradient`, `curvature`,
    etc.

### Annotation data
#### Point Annotations
Point annotations are stored as JSON files in the `Picks` directory of the run. Each file contains a list of points in
angstrom coordinates that represent the location of a particular object in the tomogram. The filename of the JSON file
allows relating the points to the user or tool that created them, as well as the object that they represent.

!!! warning "Naming Conventions"
    user_ids, session_ids, and object names should never contain underscores!

??? example "Example Code - Read point annotations from copick"
    ```python
    --8<-- "point_read.py"
    ```

    Refer to the [API Reference](api_reference/base_classes/data_entity_models/CopickPicks.md) for more information on
    the CopickPicks API.

!!! note "Example point file name"
    Point files are named according to the following pattern:
    ```
    good.picker_0_proteasome.json
    ```

    The `good.picker` part of the filename is the user or tool that created the points. The `0` part of the filename is
    the session id of the user or tool that created the points. The `proteasome` part of the filename is the name of the
    object that the points represent.

Each point has a `location` (angstrom), a `transformation` (a 4×4 matrix from the object's frame to the tomogram, whose
translation is a shift added to the location), an `instance_id` (default 0) and a `score` (default 1.0). For filament
objects, `instance_id` is the filament ID and the points are ordered along each filament; see
[Pick Geometry](geometry.md#2-pick-geometry).

```python
positions, transforms = picks.numpy()            # locations and 4x4 transforms
centres = picks.full_positions()                 # location + transform translation
picks.from_numpy(positions, transforms, instance_ids=ids, scores=scores)
ids, scores = picks.instance_ids(), picks.scores()
```



#### Mesh Annotations
Mesh annotations are stored as glb files in the `Meshes` directory of the run. Each file contains a 3D mesh, with
vertices in angstrom coordinates, that represents the shape of a particular object in the tomogram. The filename of the
glb file allows relating the mesh to the user or tool that created it, as well as the object that it represents.

!!! warning "Naming Conventions"
    user_ids, session_ids, and object names should never contain underscores!

??? example "Example Code - Read mesh annotations and visualize them in 3D"
    ```python
    --8<-- "mesh_read.py"
    ```

    Refer to the [API Reference](api_reference/base_classes/data_entity_models/CopickMesh.md) for more information on
    the CopickMesh API.

!!! note "Example mesh file name"
    Mesh files are named according to the following pattern:
    ```
    good.picker_0_proteasome.glb
    ```

    The `good.picker` part of the filename is the user or tool that created the mesh. The `0` part of the filename is
    the session id of the user or tool that created the mesh. The `proteasome` part of the filename is the name of the
    object that the mesh represents.


#### Filaments
Traced filaments are stored as JSON files in the `Filaments` directory of the run, named like point annotations
(`[user_id]_[session_id]_[object_name].json`). Each file holds the filaments of one object, each an ordered
centreline (polyline) in angstrom coordinates with its own `instance_id`:

```json
{
    "pickable_object_name": "microtubule",
    "user_id": "tracer",
    "session_id": "1",
    "voxel_spacing": 10.0,
    "unit": "angstrom",
    "version": 1,
    "filaments": [
        {"instance_id": 1, "points": [[100.0, 200.0, 50.0], [110.0, 200.5, 50.2], ...],
         "polarity_known": false, "score": 1.0, "radius": 120.0, "metadata": {}}
    ]
}
```

- `instance_id` is at least 1 and unique within the file; picks sampled from a filament use it as their
  `instance_id`.
- `points` are ordered along the filament, at least two, and should be no further apart than the voxel spacing the
  filament was traced at, so that linear interpolation follows the centreline.
- `polarity_known` says whether the point order follows the structure's polarity (meaningful for objects whose
  filament spec has `polar: true`).
- `version` is the version of this file format.

The cryoET Data Portal has no filament annotations, so data-portal projects keep filaments in their overlay; a
self-contained Croissant project (Mode A) cannot hold them.

```python
filaments = run.new_filaments(object_name="microtubule", user_id="tracer", session_id="1")
filaments.from_numpy([centreline_1, centreline_2], voxel_spacing=10.0)  # (M, 3) arrays in angstrom
for line in run.get_filaments(object_name="microtubule")[0].numpy():
    ...
```

##### Editable curves

A filament can also carry the curve its points were made from, so that an editor can reopen the clicked control points
or a fitting program's spline instead of re-deriving them from the dense points. The curve is an optional `curve` object
on a filament, beside `points`; `points` stay the centreline every reader uses, and are regenerated from the curve
whenever it changes.

```json
{"instance_id": 1,
 "points": [[100.0, 200.0, 50.0], "... regenerated from the curve ..."],
 "curve": {"kind": "catmull-rom", "alpha": 0.5, "step": 10.0,
           "control_points": [[100.0, 200.0, 50.0], [180.0, 230.0, 55.0], [260.0, 240.0, 70.0]]}}
```

| Field | Kinds | Rule |
|---|---|---|
| `kind` | all | `catmull-rom` (passes through its control points; interactive tracing), `linear`, or `bspline` (a fitted B-spline, stored exactly). Other values are reserved and kept as they are. |
| `control_points` | all | Ångström, ordered like `points`, finite. `catmull-rom`/`linear`: at least 2, consecutive points distinct. `bspline`: the coefficients, at least `degree + 1`. |
| `step` | all | > 0 Å: the spacing of the regenerated points, usually the voxel spacing. |
| `alpha` | `catmull-rom` | 0 to 1, default 0.5 (centripetal). |
| `degree`, `knots` | `bspline` | Degree 1 to 5; `len(control_points) + degree + 1` non-decreasing knots, clamped (the end values repeat exactly `degree + 1` times, interior values at most `degree` times). |
| `smoothing` | `bspline` | Optional, the fit's smoothing factor (scipy's `s`); descriptive. |

**Evaluating.** `linear` joins the control points with straight segments. `catmull-rom` is the Barry–Goldman form of the
Catmull-Rom spline with knot intervals `|P_{i+1} − P_i|^alpha`, and end points extended by `2·P_0 − P_1` and
`2·P_n − P_{n−1}`; it passes through every control point. `bspline` is evaluated with de Boor's algorithm over the
domain `[u_degree, u_n]`, exactly as scipy's `splev` evaluates a `splprep` fit; it starts and ends at its first and last
coefficient.

**Regenerating `points`.** The curve is cut into pieces at its *anchors*: the control points for `catmull-rom` and
`linear`, and the curve at each distinct knot for `bspline`. Each piece is sampled at
`m = max(16, ceil(16·ℓ/step))` equal parameter steps (ℓ: the segment's length, or the length of the span's control
polygon), starting exactly at its anchor and ending at the next. Its length `L` along those samples is then split into
`N = max(1, ceil(L/step − 1e-9))` equal arc-length steps. The pieces' points are joined, and the curve's end is
appended. So consecutive points are at most `step` apart and every anchor is one of the points. The reference
implementation is `copick.util.filaments`, and `tests/data/filament_curves.json` holds reference cases that other
implementations reproduce to within 10⁻³ Å.

**Writers** regenerate `points` whenever they change the curve, remove `curve` when they change `points` any other way,
and reverse both together. copick does not store a curve of a known kind that no longer describes its points: it drops
it, with a warning. Fitting programs store their spline as a `bspline` (`CopickFilamentCurve.from_tck`), scaling the
coefficients if they fitted voxel coordinates, and record their settings in the filament's `metadata["fit"]`.

**Readers** that do not edit ignore `curve`. A curve is *current* when the first and last points, and every anchor, lie
within `0.01·step` of the points; an editor only reuses a current curve. Without one, it derives `catmull-rom` control
points from the points: starting from the two ends, it repeatedly adds the point farthest from the curve through the
chosen ones until none is farther than the tolerance (half the voxel spacing by default;
`copick.util.filaments.control_points_from_polyline`). An editor that does not support `bspline`, or needs to insert or
delete one of its points, converts it the same way.

```python
filaments = run.new_filaments(object_name="microtubule", user_id="tracer", session_id="1")
filaments.from_control_points([clicks_1, clicks_2], voxel_spacing=10.0)  # (n, 3) control points in angstrom

curve = filaments.editable_curve(instance_id=1)  # the stored curve, or one derived from the points
edited = filaments.get(1).with_control_points(moved_control_points)
filaments.filaments = [edited, filaments.get(2)]
filaments.store()

from scipy.interpolate import splprep
from copick.models import CopickFilamentCurve

tck, _ = splprep(centreline_voxels.T, s=5.0, k=3)
fitted = CopickFilamentCurve.from_tck(tck, step=10.0, smoothing=5.0, scale=10.0)
run.new_filaments(object_name="microtubule", user_id="fitter", session_id="0").from_curves([fitted])
```

Refer to the [API Reference](api_reference/base_classes/data_entity_models/CopickFilaments.md) for the
CopickFilaments API.

#### Dense Segmentations
Dense segmentations are stored as OME-NGFF files in the run. The directory and the filename of the zarr file relate the
segmentation to the user or tool that created it and to what it represents, and record which of three types it is:

| Type | Directory | Name | Voxel values | Filename ends in |
|---|---|---|---|---|
| binary | `Segmentations` | a pickable object | 1 inside the object, 0 outside | `_[object_name].zarr` |
| multilabel | `Segmentations` | any descriptive name | the `label` of the pickable object at that voxel, 0 for background | `_[name]-multilabel.zarr` |
| instance | `InstanceSegmentations` | a pickable object | the ID of the object instance at that voxel, 0 for background | `_[object_name].zarr` |

Types added after binary and multilabel live in their own directory, so copick versions and other clients that predate
them never list them, instead of misreading their voxel values.

An **instance segmentation** holds every instance of one object, for example every microtubule or every vesicle in a
run, and tells them apart: voxel value `v > 0` belongs to the instance with `instance_id == v`. These are the same IDs
that picks and [filaments](#filaments) carry, so picks or filaments describing the same instances (from the same
user and session) use the same IDs. 0 is background, matching picks, where `instance_id` 0 means "no instance".

```python
seg = run.new_segmentation(10.0, "microtubule", "1", user_id="tracer", is_instance=True)
seg.from_numpy(labels)              # integer volume, 0 = background, n = instance n
seg.instance_ids()                  # array([1, 2, ...])
run.get_segmentations(is_instance=True)
```

Queries that do not name a type select binary and multilabel segmentations, the types every client reads:
`get_segmentations(...)` and `delete_segmentations(...)` default to `is_instance=False` (pass `is_instance=None` for any
type), and `run.segmentations` lists all of them. Segmentation URIs mark the type with `?multilabel=true` or
`?instance=true` (`microtubule:tracer/1@10.0?instance=true`); a URI without either selects binary and multilabel
segmentations, so `copick cp`, `mv`, `rm` and `export` do too. `copick sync segmentations` and
`copick stats segmentations` take `--segmentation-type binary|multilabel|instance|all`.

!!! note "Data types"
    Segmentation values are stored without loss. When no dtype is given, `from_numpy` chooses the smallest unsigned
    integer type that holds every value: `uint8` and up for binary and multilabel segmentations, `uint16` and up for
    instance segmentations. A value that does not fit a requested dtype raises an error instead of wrapping.

!!! warning "Naming Conventions"
    user_ids, session_ids, and object names should never contain underscores! Object names should also not end in
    `-multilabel`, which marks a multilabel segmentation in a filename.

??? example "Example Code - Read a segmentation into a numpy array"
    ```python
    --8<-- "segmentation_read_image.py"
    ```

    Refer to the [API Reference](api_reference/base_classes/data_entity_models/CopickSegmentation.md) for more information
    on the CopickSegmentation API.

!!! note "Example segmentation file names"
    Segmentation files are named according to the following pattern:
    ```
    10.000_good.picker_0_proteasome.zarr
    ```

    The `10.000` part of the filename is the voxel spacing of the tomogram that the segmentation was created from. The
    `good.picker` part of the filename is the user or tool that created the segmentation. The `0` part of the filename is
    the session id of the user or tool that created the segmentation. The `proteasome` part of the filename is the name of
    the object that the segmentation represents. This is a binary segmentation.

    ```
    10.000_good.picker_0_segmentation-multilabel.zarr
    ```

    The `10.000` part of the filename is the voxel spacing of the tomogram that the segmentation was created from. The
    `good.picker` part of the filename is the user or tool that created the segmentation. The `0` part of the filename is
    the session id of the user or tool that created the segmentation. The `segmentation` part of the filename is an
    arbitrary name that describes the segmentation. This is a multilabel segmentation, thus all objects in the project
    could be represented in this segmentation.

    ```
    InstanceSegmentations/10.000_tracer_1_microtubule.zarr
    ```

    An instance segmentation of the `microtubule` object by the tool `tracer` in session `1`: each microtubule's voxels
    hold its instance ID.

!!! note "cryoET Data Portal"
    In data-portal projects, the portal's `SegmentationMask` annotations appear as binary segmentations and its
    volumetric `InstanceSegmentationMask` annotations as instance segmentations (user `data-portal`, session = the
    annotation file ID). The portal's point-based `InstanceSegmentation` annotations are not segmentations and are not
    shown.

## On-disk Data Model

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
      ├─ 📁 Filaments/
      │  └─ 📄 [user_id | tool_name]_[session_id | 0]_[object_name].json
      ├─ 📁 Segmentations/
      │  ├─ 📁 [xx.yyy]_[user_id | tool_name]_[session_id | 0]_[object_name].zarr
      │  │   └─ [OME-NGFF spec at 100% scale, 50% and 25% scale]
      │  └─ 📁 [xx.yyy]_[user_id | tool_name]_[session_id | 0]_[name]-multilabel.zarr
      │      └─ [OME-NGFF spec at 100% scale, 50% and 25% scale]
      └─ 📁 InstanceSegmentations/
         └─ 📁 [xx.yyy]_[user_id | tool_name]_[session_id | 0]_[object_name].zarr
             └─ [OME-NGFF spec at 100% scale, 50% and 25% scale]
```
