# Zarr v3 release checklist

This is the durable status record for the copick 2.0 OME-Zarr 0.5 / Zarr v3
migration. A checked repository gate does not replace an external consumer
decision.

## Repository gates

- [x] Python 3.11-3.14 metadata, lock, and CI coverage are aligned.
- [x] Zarr 3 runtime accepts legacy Zarr v2 and metadata-defined Zarr v3 input.
- [x] Canonical OME-Zarr 0.5 / Zarr v3 writer and 3D/4D feature contracts are
  covered by tests.
- [x] Required local, S3, SSH, and MLCroissant corpus jobs have named green
  evidence in [backend validation](zarr_v3_backends.md).
- [x] The independently generated twin is digest-pinned and cold/warm-cache
  tested.
- [x] The exact direct-reader fixture is deterministic and structurally
  validated as described in [direct-reader validation](zarr_v3_direct_readers.md).
- [x] User-facing 2.0 migration guidance and the stable changelog summary cover
  the public API, output format, copy semantics, writer tradeoffs, and cache
  refresh behavior.

## External decisions

- [ ] The release owner has classified required deployed readers and recorded
  either a pass for the exact fixture or an explicit compatibility decision.
  This is the remaining output-cutover release gate; see issue #378.
- [ ] A real migrated public portal OME-Zarr 0.5 / Zarr v3 store has been
  identified and exercised in a mixed 0.4/0.5 session. This blocks portal
  corpus cutover, not the independently generated package-validation gate.

SMB is explicitly excluded from the definition of done. Its optional job may
support a narrow, dated compatibility statement but cannot block copick 2.0.

## Pre-tag commands

Run these from a clean checkout of the exact candidate commit:

```shell
uv lock --check
uv sync --locked --extra test --extra dev
pre-commit run --all-files
pytest
```

Also require the named Zarr v3 corpus, portal smoke, exact-fixture, and direct
reader decision above on that commit. Do not tag while any required item is
unchecked.

After the final alpha is installed and validated from PyPI, synchronize `v2.0`
with current `main`, rerun the release gates, merge `v2.0` to `main` with
`Release-As: 2.0.0`, review the complete stable changelog, and merge the normal
Release Please pull request. Only that final `main` release is the stable
copick 2.0 migration release.
