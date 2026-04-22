# mlcroissant setup

The mlcroissant backend reads a copick project's *structure* from an
[mlcroissant](https://docs.mlcommons.org/croissant/docs/croissant-spec.html)
JSON-LD manifest plus a set of CSV sidecars, all living under a new
`Croissant/` subdirectory alongside `ExperimentRuns/` and `Objects/`.

A Croissant-backed copick project looks like this on disk:

```
<project_root>/
  Croissant/
    metadata.json           # Croissant JSON-LD
    runs.csv
    voxel_spacings.csv
    tomograms.csv
    features.csv
    picks.csv
    meshes.csv
    segmentations.csv
    objects.csv
  ExperimentRuns/
    run_001/
      VoxelSpacing10.000/
        wbp.zarr/
      Picks/
      Meshes/
      Segmentations/
    ...
  Objects/
    ribosome.zarr/
    ...
```

The `Croissant/metadata.json` is a standards-compliant Croissant 1.1
manifest. Its `distribution` lists the 8 CSVs as `cr:FileObject` entries, and
its `recordSet` declares one RecordSet per artifact type, with Fields sourced
from CSV columns via `cr:Source` + `cr:Extract`. **Zarr / JSON / GLB URLs are
values in CSV `url` columns, not spec-level resources** — this keeps the
Croissant small (O(artifact types)) even for huge projects.

Project-specific configuration (pickable objects, user ID, session ID, name,
description, version) is embedded under a `copick:config` property on the
dataset as an opaque JSON blob. The `copick:baseUrl` string property on the
dataset determines how relative CSV `url` values are resolved at read time;
users can override it via `CopickConfigMLCroissant.croissant_base_url` when a
dataset has been mirrored to a different location.

## Two operational modes

**Mode A — self-contained project** (default). The Croissant's `copick:baseUrl`
points at the project root, which is writable via fsspec (e.g. `file://` for a
local path or a private `s3://` bucket with write credentials). No separate
overlay is needed. Writes through copick's APIs auto-update both the data
files *and* the corresponding CSV rows, so the Croissant always reflects the
current project state.

**Mode B — remote Croissant + local overlay**. When `copick:baseUrl` points at
a read-only location (e.g. a published `https://` URL) and the user wants to
annotate locally, a separate `overlay_root` is configured. Writes go to the
overlay only; the Croissant stays untouched. To publish the edits, re-run
`copick config export-croissant --project-root <new-location>` to rebuild a
fresh Croissant from the merged filesystem + overlay view.

### Picking up external writes: `root.refresh()`

Each `CopickRootMLC` caches the parsed Croissant manifest in memory for
performance — reads don't re-parse `metadata.json` and the CSV sidecars on
every call. When another process (or another root instance in the same
process, e.g. `copick sync` running inside a test runner) has mutated the
project, call `root.refresh()` on the existing root to re-read the manifest
+ CSVs and pick up the external changes.

## Creating a Croissant from an existing copick project

Use the `export-croissant` CLI command. For a filesystem-backed source,
`--base-url` is the absolute URL that will resolve to `--project-root` at
consumer read time (for a private project, this can be a `file://` URL; for a
public mirror, the HTTPS / S3 URL where the data will be hosted):

```bash
copick config export-croissant \
    --config my_project/filesystem.json \
    --project-root my_project \
    --base-url https://data.example.org/my_project/ \
    --dataset-name "My cryoET project" \
    --description "Picks + tomograms for run XYZ" \
    --license CC-BY-4.0
```

The command writes `my_project/Croissant/metadata.json` plus the 8 CSVs,
computing sha256 for each CSV plus optional per-file sha256 for picks JSONs
and mesh GLBs. Pass `--no-file-sha256` to skip the per-file hashing when
speed matters.

For a CryoET Data Portal-backed source, `--base-url` is ignored — the
exporter uses the canonical `s3://cryoet-data-portal-public/` as `copick:baseUrl`.
The generated Croissant's CSV `url` columns contain absolute `s3://` paths
straight from the portal, so consumers can read data without the portal
GraphQL API.

### Exporting a subset

By default `export-croissant` emits every run, voxel spacing, tomogram,
feature, pick, mesh, segmentation, and object density map from the source
project. To restrict the export, pass any combination of the following
filter flags. An omitted flag means "no filter — include everything of that
type"; URIs follow copick's standard per-type URI grammar and each URI
flag can be repeated to union multiple selectors.

| Flag              | Accepts                                           |
|-------------------|---------------------------------------------------|
| `--runs`          | comma-separated run names                         |
| `--tomograms`     | URI (e.g. `wbp@10.0`), repeatable                 |
| `--features`      | URI (e.g. `wbp@10.0:sobel`), repeatable           |
| `--picks`         | URI (e.g. `ribosome:*/*`), repeatable             |
| `--meshes`        | URI (e.g. `ribosome:*/*`), repeatable             |
| `--segmentations` | URI (e.g. `membrane:*/*@10.0`), repeatable        |
| `--objects`       | comma-separated pickable-object names (density maps) |

Example — restrict to two runs + only ribosome picks at 10 Å tomograms:

```bash
copick config export-croissant \
    --config my_project/filesystem.json \
    --project-root my_project \
    --base-url https://data.example.org/my_project/ \
    --runs TS_001,TS_002 \
    --tomograms "wbp@10.0" \
    --picks "ribosome:*/*"
```

Example — export only the membrane segmentations at VS 10.0 across all runs:

```bash
copick config export-croissant \
    --config my_project/filesystem.json \
    --project-root my_project \
    --base-url https://data.example.org/my_project/ \
    --segmentations "membrane:*/*@10.0"
```

The filters are independent: omitting `--picks` while setting `--tomograms`
exports all picks and only the matching tomograms. Voxel-spacings rows are
derived — they're emitted only for `(run, voxel_size)` pairs observed in at
least one surviving tomogram / feature / segmentation, so a filter that
selects only picks yields an empty `voxel_spacings.csv`.

## Opening a Croissant-backed project

Use the `mlcroissant` config command to generate a copick config:

```bash
copick config mlcroissant \
    --croissant-url my_project/Croissant/metadata.json \
    --output my_project/croissant.json
```

Or call the helper directly in Python:

```python
import copick

root = copick.from_croissant("my_project/Croissant/metadata.json")
# ... walk runs / tomograms / picks ...
```

With a separate overlay (Mode B):

```python
root = copick.from_croissant(
    "https://data.example.org/my_project/Croissant/metadata.json",
    overlay_root="/path/to/my/local/overlay",
)
```

## Config template

```json
{
    "config_type": "mlcroissant",
    "pickable_objects": [],
    "croissant_url": "https://data.example.org/my_project/Croissant/metadata.json",
    "overlay_root": null,
    "overlay_fs_args": {},
    "croissant_fs_args": {}
}
```

- `croissant_url`: URL / path to the Croissant `metadata.json`.
- `croissant_base_url` (optional): override for `copick:baseUrl` (use when the
  referenced data has been mirrored to a different location).
- `overlay_root` (optional): if set, writes go to this fsspec location; the
  Croissant is treated as read-only (Mode B). If omitted, the Croissant's
  `copick:baseUrl` location is used for writes and the CSVs auto-sync (Mode A).
- `croissant_fs_args`: fsspec kwargs for fetching the Croissant itself
  (e.g. when loading from a remote URL).
- `overlay_fs_args`: fsspec kwargs for the overlay filesystem (Mode B only).

`pickable_objects`, `user_id`, `session_id`, `name`, `description`, and
`version` are loaded from the Croissant's `copick:config` at open time — the
config JSON only needs to point at the manifest.

## See also

- [mlcroissant API reference](../../api_reference/implementations/Croissant.md)
- [Croissant 1.1 spec](https://docs.mlcommons.org/croissant/docs/croissant-spec.html)
- [mlcroissant tutorial](../tutorials/croissant.md)
