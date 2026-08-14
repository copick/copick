# Test fixture regeneration

This directory contains helper scripts that regenerate the Zenodo-hosted
`sample_project.zip` test fixture used by the copick test suite.

## When to regenerate

Any time the **layout** or **content** of the test fixture needs to change —
e.g. adding Croissant sidecars for the `mlcroissant` backend, updating the
pickable objects list, or adding new artifact types. The regenerated archive
must be uploaded to Zenodo (as a new version of record 19686100, or a new
record) and `copick/tests/conftest.py:18-25` must be updated with the new DOI
and md5 so pooch pulls the new version.

## Building the independent Zarr v3 twin

```bash
python copick/tests/scripts/build_v3_twin.py \
  /path/to/current/sample_project.zip \
  --output /tmp/sample_project.zip
```

`build_v3_twin.py` deliberately imports zarr, ome-zarr, and
ome-zarr-models directly and must never import copick. It retains every legacy
file, adds sibling `sample_project_v3`, `sample_overlay_v3`, and v3 config
paths, independently converts all 23 stores and 61 arrays, and adds a
standalone feature-major 4D fixture. It validates each converted image and
compares its decoded values with the legacy source before emitting the zip.
The archive writer fixes timestamps and permissions, so repeated builds from
the same source have identical hashes.

Before publishing, build the archive twice, compare its MD5 and SHA-256, then
run both selections from a cold cache and again from the populated cache:

```bash
COPICK_TEST_ZARR_FORMAT=v2 pytest -m corpus_parity tests
COPICK_TEST_ZARR_FORMAT=v3 pytest -m corpus_parity tests
```

The default is `v2`; format-insensitive tests therefore continue to run only
once. CI sets `COPICK_TEST_ZARR_FORMAT=v3` in dedicated local, S3, SSH, and ML
Croissant parity jobs. Corpus extraction is keyed by the pooch registry digest
rather than directory existence, so changing the registered archive forces a
fresh extraction even when the old directory is still cached.

## Regenerating `sample_project.zip` with Croissant sidecars

```bash
python copick/tests/scripts/regenerate_sample_zip.py --output-dir /tmp
```

The script:

1. Downloads the current `sample_project.zip` from `doi:10.5281/zenodo.21939821` (updated as new versions are published; see `regenerate_sample_zip.py::CURRENT_DOI`)
   via pooch (reusing the existing cache when possible).
2. Extracts it to a temp directory.
3. Loads the filesystem project and calls `copick.ops.croissant.export_croissant`
   on the static `sample_project/` subdirectory, passing `base_url=""` so the
   generated Croissant uses **relative URLs** and remains portable across user
   pooch caches (independent of where pooch extracts it).
4. Repacks the archive (Croissant + ExperimentRuns + Objects + the existing
   `sample_overlay`).
5. Prints the new md5 and the path to the regenerated zip.

## Uploading to Zenodo

1. Go to <https://zenodo.org/record/19686100> and create a new version (or a
   new record).
2. Upload the exact validated `sample_project.zip` without renaming it.
3. Publish and record the immutable, version-specific DOI (not only the
   concept DOI). Zenodo assigns a DOI such as
   `10.5281/zenodo.<NEW-RECORD-ID>`.

## Updating `conftest.py`

Edit `copick/tests/conftest.py` lines 18–25:

```python
OZ = Path(os.environ.get("COPICK_TEST_DATA_CACHE", pooch.os_cache("test_data")))
TOTO = pooch.create(
    path=OZ,
    base_url="doi:10.5281/zenodo.<NEW-RECORD-ID>",
    registry={
        "sample_project.zip": "md5:<NEW-MD5>",
    },
)
```

The next test run pulls the new archive into the local pooch cache.

`tests/corpus_registry.py` is the single source of truth for these values.
The `prepare-test-corpus` CI job first restores a digest-keyed Actions cache,
runs `fetch_test_corpus.py` once to verify or fetch the zip, and uploads the
verified file as a short-lived workflow artifact. Every test-matrix runner
downloads that artifact into `COPICK_TEST_DATA_CACHE`. This avoids concurrent
Zenodo downloads and the resulting rate-limit failures; repeated runs for the
same corpus normally make no Zenodo request at all.

## Flags

- `--output-dir PATH`: where to write the regenerated zip (default: a temp
  directory).
- `--keep-workdir`: don't delete the intermediate extraction directory (useful
  for inspecting what the script generated).
