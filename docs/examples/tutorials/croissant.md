# mlcroissant tutorial

This tutorial walks you through exporting an existing copick project to an
mlcroissant manifest, reading it back through the mlcroissant backend, adding
new annotations with live auto-sync, and republishing.

## Prerequisites

Install copick with its mlcroissant dependencies:

```bash
pip install "copick"
```

(`mlcroissant` and `aiohttp` are declared as core dependencies since v1.24.)

## 1. Start from a filesystem project

We'll use the test `sample_project` that copick ships as a pooch-cached test
fixture. Download and extract it:

```bash
python -c "
import copick.tests.conftest as c
c.TOTO.fetch('sample_project.zip', processor=__import__('pooch').Unzip())
print(c.OZ / 'sample_project')
"
```

Alternatively, create a minimal project by hand — any copick filesystem
project with runs / picks / tomograms will work.

## 2. Export the Croissant

From Python:

```python
import copick
from copick.ops.croissant import export_croissant

root = copick.from_file("path/to/sample_project/filesystem.json")

export_croissant(
    root,
    project_root="path/to/sample_project",
    base_url="file://path/to/sample_project",  # local use
    dataset_name="Sample copick project",
    description="Cryo-ET data with picks and segmentations.",
    license="CC-BY-4.0",
)
```

Or from the CLI:

```bash
copick config export-croissant \
    --config path/to/sample_project/filesystem.json \
    --project-root path/to/sample_project \
    --base-url file://path/to/sample_project
```

The command writes `path/to/sample_project/Croissant/`:

```
Croissant/
    metadata.json
    runs.csv
    voxel_spacings.csv
    tomograms.csv
    features.csv
    picks.csv
    meshes.csv
    segmentations.csv
    objects.csv
```

Every CSV gets a real sha256 recorded in `metadata.json`, and per-file
sha256 hashes are embedded as columns in `picks.csv` and `meshes.csv`.

## 3. Inspect the output

Open `Croissant/metadata.json` in your editor. Key fields:

- `@context`: the canonical Croissant 1.1 vocabulary plus our
  `copick:` namespace additions.
- `copick:baseUrl`: the absolute URL that CSV `url` columns resolve
  relative to.
- `copick:config`: the `CopickConfig` as an embedded JSON blob —
  pickable objects, user id, etc.
- `distribution`: 8 `cr:FileObject` entries (one per CSV) with sha256.
- `recordSet`: 8 `cr:RecordSet` entries, one per artifact type, each
  sourcing its fields from a CSV column.

Open `Croissant/picks.csv` — you should see one row per existing pick:

```csv
run,user_id,session_id,object_name,url,sha256
run_001,alice,42,ribosome,ExperimentRuns/run_001/Picks/alice_42_ribosome.json,e14c...
```

## 4. Open the project through the mlcroissant backend

```python
import copick

root = copick.from_croissant(
    "path/to/sample_project/Croissant/metadata.json",
)

print(f"Project: {root.config.name} (mode {root.mode})")
for run in root.runs:
    print(f"  {run.name}: "
          f"{len(run.voxel_spacings)} VS, "
          f"{len(run.picks)} picks, "
          f"{len(run.meshes)} meshes, "
          f"{len(run.segmentations)} segs")
```

Because `copick:baseUrl` is a writable `file://` URL, the backend enters
**Mode A** (self-contained). Writes will auto-sync to the Croissant CSVs.

## 5. Add a new pick with live auto-sync

```python
from copick.models import CopickLocation, CopickPoint

run = root.get_run("run_001")
picks = run.new_picks(object_name="ribosome", user_id="bob", session_id="99")
picks.points = [
    CopickPoint(location=CopickLocation(x=100.0, y=200.0, z=300.0)),
    CopickPoint(location=CopickLocation(x=110.0, y=210.0, z=310.0)),
]
picks.store()
```

After `store()`:

- A new JSON file is written at
  `path/to/sample_project/ExperimentRuns/run_001/Picks/bob_99_ribosome.json`.
- A new row is appended to `Croissant/picks.csv` (with a freshly computed
  sha256).
- The `picks-csv` entry in `Croissant/metadata.json` gets its `sha256`
  refreshed.

Re-opening the project from a fresh Python process confirms the update:

```python
root2 = copick.from_croissant("path/to/sample_project/Croissant/metadata.json")
print([p.user_id for p in root2.get_run("run_001").picks])
# ['alice', 'bob']
```

## 6. Bulk imports with `batch()`

If you're about to write many artifacts in a tight loop, rewriting
`metadata.json` after every call is wasteful. Wrap the loop in
`root.batch()` to defer the flush:

```python
with root.batch():
    for i, coords in enumerate(my_predicted_points):
        picks = run.new_picks(object_name="ribosome", user_id="model", session_id=str(i))
        picks.points = [CopickPoint(location=CopickLocation(*coords))]
        picks.store()
# metadata.json is rewritten exactly once here, on context exit.
```

## 7. Mode B — remote Croissant, local overlay

If someone published the Croissant to an HTTPS or public S3 location and you
want to annotate locally without mutating the published data, provide a
separate `overlay_root`:

```python
root = copick.from_croissant(
    "https://data.example.org/sample_project/Croissant/metadata.json",
    overlay_root="/tmp/my_local_overlay",
)
# root.mode == "B"
```

Writes now land under `/tmp/my_local_overlay/ExperimentRuns/...`; the remote
Croissant is not modified. To publish your overlay as a new Croissant:

```bash
copick config export-croissant \
    --config path/to/my/croissant-mode-b.json \
    --project-root /tmp/my_merged_project \
    --base-url https://mymirror.example.org/merged
```

This rebuilds a fresh Croissant from the merged filesystem + overlay view.

## 8. Republishing the project

The exporter never touches data files under `ExperimentRuns/` or
`Objects/` — only `Croissant/` is (re)written. To publish:

```bash
tar czf sample_project.tar.gz sample_project/
# or
aws s3 sync sample_project/ s3://my-bucket/sample_project/
```

Consumers fetch the archive, point `copick.from_croissant` at
`<project>/Croissant/metadata.json`, and get an immediately usable copick
project.

## See also

- [mlcroissant setup](../setup/croissant.md) — reference for config templates.
- [mlcroissant API reference](../../api_reference/implementations/Croissant.md).
- [Croissant 1.1 spec](https://docs.mlcommons.org/croissant/docs/croissant-spec.html).
