# Test fixture regeneration

This directory contains helper scripts that regenerate the Zenodo-hosted
`sample_project.zip` test fixture used by the copick test suite.

## Building the direct-reader interoperability fixture

```bash
python tests/scripts/build_v3_interop_fixture.py \
  --source-revision "$(git rev-parse HEAD)" \
  --output /tmp/copick-v3-direct-reader-fixture.zip
```

This fixture is intentionally produced through copick's centralized writer,
unlike the independent corpus twin below. It contains two-level boolean,
uint16, and float32 OME-Zarr 0.5 / Zarr v3 stores, plus a feature-major 4D
float32 store and a manifest with exact codec metadata, sample values, source
revision, and SHA-256 checksums. The 3D level-0 shape crosses all three
inner-chunk boundaries while preserving the required one-shard grid; the 4D
store writes one padded spatial shard per feature volume. Building the same
locked revision twice must produce byte-identical archives.

Use this artifact for deployed direct-reader validation; do not modify its
codec pipeline to accommodate a failing reader. Record the archive checksum,
source revision, deployed reader build, decoded values/checksums, and evidence
in issue #378 or a linked report.

## The archive

One `sample_project.zip` serves both release lines:

- **The legacy tree** (Zarr v2, OME-NGFF 0.4): `sample_project/`, `sample_overlay/`,
  `filesystem.json` and `filesystem_overlay_only.json`. The 1.x line reads it, and so
  does the 2.0 line with `COPICK_TEST_ZARR_FORMAT=v2`.
- **The Zarr v3 twin** that the 2.0 line adds: `sample_project_v3/`,
  `sample_overlay_v3/`, `filesystem_v3.json`, `filesystem_overlay_only_v3.json` and
  `wbp_multifeature_features.zarr`.

The shipped configs carry placeholder storage roots
(`local:///PATH/TO/EXTRACTED/sample_project` and `.../sample_overlay`); every test
fixture replaces them, and the build refuses to pack a config or metadata file that
names a local path.

Run `TS_002` holds the segmentation-type fixtures: an instance segmentation
(`InstanceSegmentations/10.000_annotator_1_ribosome.zarr`, ribosomes 1-3) and a
panoptic segmentation (`PanopticSegmentations/10.000_annotator_1_cell.zarr`: a
membrane region, the same three ribosomes and one proteasome).

## The Zarr v3 twin

`build_v3_twin.py` deliberately imports zarr, ome-zarr, and ome-zarr-models
directly and must never import copick. It retains every legacy file, adds sibling
`sample_project_v3`, `sample_overlay_v3`, and v3 config paths, independently
converts all 25 stores and 67 arrays (channel-first stores such as the panoptic
segmentation keep their channel axis, one channel per chunk), and adds a
standalone feature-major 4D fixture. It validates each converted image and
compares its decoded values with the legacy source before emitting the zip. The
archive writer fixes timestamps and permissions, so repeated builds from the same
source have identical hashes.

The default test format is `v2`; format-insensitive tests therefore run only
once. CI sets `COPICK_TEST_ZARR_FORMAT=v3` in dedicated local, S3, SSH, and ML
Croissant parity jobs. Corpus extraction is keyed by the pooch registry digest
rather than directory existence, so changing the registered archive forces a
fresh extraction even when the old directory is still cached.

`tests/corpus_registry.py` is the single source of truth for the DOI and digest.
The `prepare-test-corpus` CI job first restores a digest-keyed Actions cache, runs
`fetch_test_corpus.py` once to verify or fetch the zip, and uploads the verified
file as a short-lived workflow artifact. Every test-matrix runner downloads that
artifact into `COPICK_TEST_DATA_CACHE`.

## When to regenerate

Any time the **layout** or **content** of the test fixture needs to change — e.g.
updating the pickable objects list or adding new artifact types. Add the content in
`regenerate_sample_zip.py` (or the twin builder), then follow the steps below.

## Regenerating

1. **Legacy tree, on the 1.x (`main`) line**, whose copick writes the Zarr v2 stores
   (the script refuses to run under Zarr 3):

   ```bash
   python tests/scripts/regenerate_sample_zip.py --output-dir /tmp/legacy
   ```

   It downloads the archive named by `CURRENT_DOI`, drops any Zarr v3 twin, adds the
   segmentation-type fixtures with copick, replaces the configs' storage roots with
   the placeholders, re-exports `sample_project/Croissant/` with `base_url=""` (so its
   URLs stay relative), checks every metadata file for local paths, and packs the
   tree with sorted entries and fixed timestamps.

2. **Zarr v3 twin, on the 2.0 (`v2.0`) line:**

   ```bash
   python tests/scripts/build_v3_twin.py /tmp/legacy/sample_project.zip \
     --output /tmp/corpus/sample_project.zip
   ```

   This is the archive to upload. Two regenerations hold the same data but not the
   same bytes (the Croissant lists rows in directory order, and compressed chunks
   may differ), so test the exact archive you upload.

3. **Test both lines against it before uploading.** On each line, with the zip in
   `<dir>`:

   ```bash
   COPICK_TEST_DATA_CACHE=<dir> COPICK_TEST_DATA_DIGEST=md5:<md5> BACKEND=local pytest tests
   ```

   On 2.0, run it with `COPICK_TEST_ZARR_FORMAT=v2` and again with `v3` (which runs
   the corpus parity gate). The suite unpacks the archive again whenever the md5
   changes.

## Uploading to Zenodo

1. Create a new version of the sample project record on Zenodo.
2. Upload the exact validated `sample_project.zip` without renaming it.
3. Publish and record the immutable, version-specific DOI (not only the concept
   DOI), e.g. `10.5281/zenodo.<NEW-RECORD-ID>`.

## Pointing the tests at the new archive

On both lines:

- `tests/corpus_registry.py`: `CORPUS_DOI` and `CORPUS_DIGEST`. CI caches the
  archive under a key derived from this file, so changing it fetches the new one.
- `regenerate_sample_zip.py`: `CURRENT_DOI` and `CURRENT_MD5`, so the next
  regeneration starts from it.

## Flags (`regenerate_sample_zip.py`)

- `--output-dir PATH`: where to write the regenerated zip (default: a temp
  directory).
- `--keep-workdir`: don't delete the intermediate extraction directory (useful
  for inspecting what the script generated).
