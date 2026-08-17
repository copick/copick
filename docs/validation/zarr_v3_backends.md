# Zarr v3 backend and portal validation

Copick's release-gating Zarr v3 backend set is local filesystem, S3, SSH, and
MLCroissant. SMB is tested when practical but is explicitly best-effort and
non-gating.

## Recorded required-backend evidence

The merged hardening run on 2026-08-14 selected the independently generated
Zarr v3 corpus and passed all four named parity jobs:

| Backend | Required result | Evidence |
| --- | --- | --- |
| Local filesystem | **PASS** | [`ubuntu local v3 corpus py3.13`](https://github.com/copick/copick/actions/runs/31848882273/job/94920748071) |
| Moto S3 | **PASS** | [`ubuntu s3 v3 corpus py3.13`](https://github.com/copick/copick/actions/runs/31848882273/job/94920748062) |
| Container SSH | **PASS** | [`ubuntu ssh v3 corpus py3.13`](https://github.com/copick/copick/actions/runs/31848882273/job/94920748203) |
| MLCroissant | **PASS** | [`ubuntu mlcroissant v3 corpus py3.13`](https://github.com/copick/copick/actions/runs/31848882273/job/94920748191) |

Those jobs validate decoded values, OME metadata, entity discovery, copy and
mutation paths, feature arrays, and local/S3/SSH/MLC parity against the same
corpus selection. They are release gates; a failure cannot be replaced by an
SMB result.

## Live public portal smoke

The public smoke uses dataset `10301`, run `14077`, voxel spacing `7.84 Å`,
tomogram type `wbp-denoised-ctfdeconv`, and the `cytoplasm` segmentation from
user `data-portal`, session `76313`. It verifies:

- the CLI creates and reopens a portal-backed copick configuration;
- both scheme-bearing stores list a metadata-defined level and return a
  bounded decoded array sample;
- both stores report `7.84 Å` from OME coordinate transformations;
- raw copy reports nonzero keys and bytes; and
- the copied segmentation sample exactly equals the live source sample.

The pre-strengthening live job was already green in the [2026-08-14 test
run](https://github.com/copick/copick/actions/runs/31848882273/job/94920748095).
The pull request carrying this document must supply the new value-level live
job result before its portal claim is considered current.

## Real migrated portal store

As of 2026-08-17, no real public portal OME-Zarr 0.5 / Zarr v3 store identity
has been supplied for this gate. That is an external-data blocker, not a
synthetic-validation failure and not evidence that no such store exists. When
one is available, record its dataset, run, object/file identifier, immutable
URL or version, OME-Zarr/Zarr versions, test date, and mixed 0.4/0.5 session
result here and in issue #379.

Until then, `test_metadata_migrated_portal_shaped_v3_fixture_reads_without_normalization`
is the package release gate for independently generated portal-shaped 0.5/v3
input. A claim that a real migrated portal store was verified is prohibited.

## Optional SMB evidence

SMB is not scheduled in the release-gating CI matrix. It can be exercised
manually against the repository's Samba container by selecting `BACKEND=smb`,
`RUN_ALL=1`, `COPICK_TEST_ZARR_FORMAT=v3`, and the `remote_corpus_parity`
marker. A successful manual run may support a dated best-effort compatibility
statement, but cannot replace one of the four verified required backends.
