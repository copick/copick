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

## Regenerating `sample_project.zip` with Croissant sidecars

```bash
python copick/tests/scripts/regenerate_sample_zip.py --output-dir /tmp
```

The script:

1. Downloads the current `sample_project.zip` from `doi:10.5281/zenodo.19686100` (updated as new versions are published; see `regenerate_sample_zip.py::CURRENT_DOI`)
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
2. Upload the regenerated `sample_project.zip`.
3. Publish. Zenodo assigns a new DOI (`10.5281/zenodo.<NEW-RECORD-ID>`).

## Updating `conftest.py`

Edit `copick/tests/conftest.py` lines 18–25:

```python
OZ = pooch.os_cache("test_data")
TOTO = pooch.create(
    path=OZ,
    base_url="doi:10.5281/zenodo.<NEW-RECORD-ID>",
    registry={
        "sample_project.zip": "md5:<NEW-MD5>",
    },
)
```

The next test run pulls the new archive into the local pooch cache.

## Flags

- `--output-dir PATH`: where to write the regenerated zip (default: a temp
  directory).
- `--keep-workdir`: don't delete the intermediate extraction directory (useful
  for inspecting what the script generated).
