# Upgrading to copick 2.0

Copick 2.0 moves its image runtime to Zarr 3 and changes new image output to
OME-Zarr 0.5 backed by Zarr v3. Existing Zarr v2 projects remain readable;
upgrading copick does not rewrite them in place.

## Runtime requirements

Copick 2.0 requires Python 3.11 or newer and installs `zarr>=3.1.6,<4`,
`ome-zarr>=0.12.2`, and `numcodecs>=0.16.4`. Recreate environments that were
solved for copick 1.x instead of mixing Zarr 2 and Zarr 3 packages in the same
environment.

```shell
python -m pip install "copick[all]>=2,<3"
```

## Public API changes

The `.zarr()` methods on objects, tomograms, features, and segmentations now
return a `zarr.abc.store.Store`. They no longer return a `MutableMapping` or
Zarr 2 `FSStore`. Pass the returned store directly to Zarr 3:

```python
import zarr

from copick.util.ome import get_level_path

group = zarr.open_group(tomogram.zarr(), mode="r")
for path, array in group.arrays():
    print(path, array.shape)

level_zero = group[get_level_path(group, 0)]
```

OME multiscale metadata defines dataset paths. Inputs may use labels such as
`"s0"`; do not assume a path is `"0"`, select the first value returned by
`Group.arrays()`, or rely on array iteration order. The optional `zarr_group`
arguments to `.numpy()` and `.set_region()` remain available for explicitly
named arrays. Omitting them resolves level 0 from metadata.

If another process changes the backing project, call `root.refresh()` or the
most specific entity `refresh()` method before querying again. For a dropped
remote connection, `root.reconnect()` recreates the filesystem connection and
invalidates cached children.

## What copick writes

New and semantically rebuilt image pyramids use OME-Zarr 0.5 / Zarr v3.
Copick-authored levels currently use numeric paths, while reads remain
metadata-driven. The default writer policy follows the
[Dynamic Cell Atlas Array Standard v0.2 performance guidance](https://chanzuckerberg.github.io/dynamic-cell-atlas-specs/v0.2/array-standard.html#performance):

- inner chunks default to `(128, 128, 128)` and may be overridden;
- each 3D level has one logical shard, padded per dimension as
  `chunks[i] * ceil(shape[i] / chunks[i])`;
- boolean and integer arrays use standalone Zstandard level 3;
- floating arrays use dtype-sized `numcodecs.shuffle` followed by standalone
  Zstandard level 3; and
- padded uncompressed shards above 5 GB warn, while shards at or above 5 TB
  are rejected.

A small region update can rewrite the containing shard. With the default
one-shard-per-level policy, that can mean rewriting a volume-sized shard, so
use explicit `chunks` and `shards` for write-heavy workloads.

These rules constrain copick writes only. Readers accept supported legacy and
noncanonical chunk shapes, shard grids, key encodings, and codec layouts from
their metadata.

Feature arrays preserve the 1.x 3D `(z, y, x)` API and additionally support
feature-major 4D `(feature, z, y, x)` data. The 4D default uses one feature per
inner chunk and one padded spatial shard per feature volume; `chunks` and
`shards` override that layout.

## Copying versus semantic export

Choose the operation according to whether storage identity matters:

- Whole-store copy paths, including segmentation copy/move, project sync, and
  Zarr export with `--copy-all-levels`, copy raw keys and preserve the source
  Zarr version, metadata, chunk/shard layout, codecs, and non-Zarr keys.
- Array-based writes and single-level Zarr export decode values and write a
  new canonical OME-Zarr 0.5 / Zarr v3 hierarchy. A single-level export
  rebuilds metadata for that level and writes it at the output level path
  `"0"`; it is not a byte-preserving copy.

Raw copy is not a format migration. To deliberately migrate or normalize a
store, use a semantic read/write path and validate the decoded values and OME
metadata.

## Storage backends

The Zarr v3 release gates cover local filesystems, S3, SSH, and MLCroissant.
Writable S3 and SSH overlays must allow parent-prefix or intermediate-directory
creation. For non-AWS S3 endpoints that reject newer request checksums, set
`config_kwargs.request_checksum_calculation` to `"when_required"`.

SMB remains best-effort and is not a copick 2.0 release gate. Validate it
against the intended server before making a deployment-specific compatibility
claim.
