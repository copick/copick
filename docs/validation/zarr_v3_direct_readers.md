# Zarr v3 direct-reader validation

The OME-Zarr 0.5 output cutover has an external compatibility gate: every
required deployed reader must either pass the exact copick-produced fixture or
receive an explicit release-owner decision. Repository inspection alone is
not a deployed-reader pass.

## Exact test artifact

The `Zarr v3 direct-reader fixture` workflow uploads
`copick-v3-direct-reader-fixture.zip` and its SHA-256 checksum. The archive is
deterministic and contains two-level boolean, uint16, and float32 images. The
level-0 shape `(129, 130, 131)` crosses the `(128, 128, 128)` inner-chunk
boundary in every dimension while retaining one padded shard.

Every archive contains `manifest.json`, with per-file and decoded-array
SHA-256 values, exact sample coordinates and values, dependency versions,
multiscale metadata, dimension names, chunk/shard shapes, shard keys, and
codec JSON. The builder rejects any output that is not:

- OME-Zarr 0.5 on Zarr v3;
- indexed sharding with one shard per level;
- v2-style slash-separated shard keys;
- standalone Zstandard level 3 for boolean/integer data; or
- byte shuffle followed by standalone Zstandard level 3 for floating data.

This pipeline is the required writer contract. A reader failure is not fixed
for this release by silently substituting a different codec or shard layout.

The development build was regenerated twice with byte-identical output and
passed `ome-zarr-models` validation plus exact decoded checksums for every
level. Its archive SHA-256 was
`0ec69224f70cc213c18cc3eac04a3a4babd66c4c43e5b2b4073200f373d4b34f`
with copick 1.26.1, Zarr 3.3.0, ome-zarr 0.13.0,
ome-zarr-models 1.7, NumPy 2.4.2, and numcodecs 0.16.5. The PR workflow must
record its own artifact checksum before that artifact is used for deployed
evidence.

## Audited reader candidates

The following versions were recorded on 2026-08-17. “Pending” means that the
fixture has not yet been exercised in an identified deployed build; it is not
a compatibility claim.

| Consumer | Audited release and source | Relevant repository evidence | Deployed result |
| --- | --- | --- | --- |
| CryoET Data Portal Neuroglancer tooling | [v1.7.1](https://github.com/chanzuckerberg/cryoet-data-portal-neuroglancer/releases/tag/v1.7.1), commit `75b3d8c6427b6924a3e7cb96c40584eb15f36199` | Its [tagged Python manifest](https://github.com/chanzuckerberg/cryoet-data-portal-neuroglancer/blob/v1.7.1/pyproject.toml) pins Zarr 2.18 and ome-zarr 0.9. That describes the Python tooling, not enough to infer the deployed browser decoder. | **Pending — release gate** |
| copick-web client | [client-v0.1.2](https://github.com/copick/copick-web/releases/tag/client-v0.1.2), audited main commit `0f3bb06fc945922ecc3e2ebea9521759efcac1f2` | The [tagged client manifest](https://github.com/copick/copick-web/blob/client-v0.1.2/client/package.json) uses `@idetik/core` 0.32.2. | **Pending — owner must classify whether required** |
| napari-copick | [v1.9.0](https://github.com/copick/napari-copick/releases/tag/napari-copick-v1.9.0), commit `fbd3afbe12f4c990f911f3aebd68f6a8bc035841` | Its [tagged manifest](https://github.com/copick/napari-copick/blob/napari-copick-v1.9.0/pyproject.toml) delegates array access through copick/Zarr and napari-ome-zarr. | **Pending — owner must classify whether required** |
| chimerax-copick | [v1.12.1](https://github.com/copick/chimerax-copick/releases/tag/chimerax-copick-v1.12.1), commit `35120cf48c43f9f85579c552197732ca40b21fe2` | Its [tagged manifest](https://github.com/copick/chimerax-copick/blob/chimerax-copick-v1.12.1/pyproject.toml) depends on ChimeraX-OME-Zarr 0.5.4 or newer. | **Pending — owner must classify whether required** |

## Evidence protocol and cutover decision

For each required deployed reader, record all of the following in issue #378
or a linked durable report:

1. fixture archive SHA-256 and workflow run URL;
2. product name plus exact deployed build, image digest, or commit;
3. result for both levels of the boolean, integer, and floating stores;
4. evidence that decoded checksums or manifest sample values match, not only
   that metadata loaded;
5. screenshot/log URL, tester, date, and environment; and
6. PASS or the exact failure including unsupported codec/metadata details.

The release owner then records one outcome, with their name and date:

- all required readers passed, so output cutover may proceed;
- output cutover is delayed until named failures are fixed; or
- the incompatibility is accepted and linked user-facing communication is
  approved before release.

Until that record exists, issue #378 and the final alpha gate remain open.
