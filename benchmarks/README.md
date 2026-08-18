# Canonical Zarr v3 I/O benchmark

`benchmarks/zarr_v3_io.py` makes the storage tradeoffs of copick's canonical
OME-Zarr 0.5 / Zarr v3 layout observable. It records elapsed time, store-level
requests, transferred bytes, and the sampled increase in process RSS from each
operation's baseline for:

- a full-level write;
- full-volume, one-inner-chunk, multi-inner-chunk, and small-region reads; and
- a small region update.

The default `small` volume fits inside one `(128, 128, 128)` inner chunk. The
default `large` volume is `(257, 257, 257)`, so it crosses inner-chunk
boundaries in every dimension. Both levels still use copick's one-element
shard grid. The benchmark fails if a full write produces more than one data
object, if a region update changes the layout, or if any value is wrong after
the update.

The request and byte measurements are taken at the Zarr store boundary. The
JSON report records the store API used for each read. With Zarr 3.1.6,
`get_partial_values` and `_get_many` account for the returned payload bytes.
Newer Zarr releases can use `get_ranges`; for explicit coalesced ranges that
path accounts for the complete fetched span, including gaps. Compare byte and
amplification measurements only when the report identifies compatible
accounting paths.

`logical_uncompressed_bytes` is the uncompressed size of the array selection
the caller requested or updated. `io_amplification_median` is the total data
payload bytes read plus written divided by that logical baseline:

```text
I/O amplification = (data read bytes + data write bytes) / logical uncompressed selection bytes
```

It is not a comparison with Zarr v2 and does not include metadata or protocol
overhead. Compression can make a one-way read or write ratio less than one;
the region-update total is the relevant tradeoff because updating a compressed
shard reads and rewrites that shard.

## Reproduce locally

Install the locked development environment and run:

```bash
uv sync --locked --extra test --extra dev
uv run --no-sync python -m benchmarks.zarr_v3_io \
  --backend local \
  --repeats 3 \
  --output-json benchmark-results/local.json \
  --output-markdown benchmark-results/local.md
```

Use repeated `--shape NAME=Z,Y,X` flags to replace the two default cases and
`--chunks Z,Y,X` to change the inner chunks. Timings are diagnostics, not CI
thresholds: compare runs only when their runner, service topology, versions,
shapes, chunks, and repeat count match.

The following opt-in case pads a float32 shard beyond the writer's 5 GB
warning threshold. It requires substantially more than 6 GB of available
memory and scratch space and is never run automatically:

```bash
uv run --no-sync python -m benchmarks.zarr_v3_io \
  --backend local --shape warning-threshold=1152,1152,1152 \
  --repeats 1 --output-json benchmark-results/warning-threshold.json
```

For an S3-compatible service:

```bash
uv run --no-sync python -m benchmarks.zarr_v3_io \
  --backend s3 --root s3://copick-zarr-v3-benchmark \
  --storage-option key=test --storage-option secret=test \
  --storage-option endpoint_url=http://127.0.0.1:4001 \
  --storage-option 'client_kwargs={"region_name":"us-west-2"}' \
  --repeats 3 --output-json benchmark-results/s3.json
```

For the repository's SSH test service:

```bash
uv run --no-sync python -m benchmarks.zarr_v3_io \
  --backend ssh --root ssh:///config/test_data/copick-zarr-v3-benchmark \
  --storage-option host=127.0.0.1 --storage-option port=2222 \
  --storage-option username=test.user --storage-option password=password \
  --storage-option known_hosts=null \
  --repeats 3 --output-json benchmark-results/ssh.json
```

Sensitive storage-option values are redacted from reports. Do not pass
production credentials on a shared command line; use the backend's normal
environment or credential provider instead.

## Interpretation

The benchmark is an on-demand diagnostic and does not run in CI. Local, S3,
and SSH reports should be collected in the same environment when a comparable
three-backend result set is needed. MLCroissant is a catalog/configuration
backend rather than another physical Zarr transport; its correctness remains
covered by the main Zarr v3 corpus tests.

The expected tradeoff is intentional: one complete level is created by one
data-object write, indexed reads can fetch only the compressed inner chunks
needed, and an in-place region update has to read and rewrite the containing
volume-sized shard. Callers performing many small updates should stage a
complete level and invoke the canonical writer once. The benchmark writes one
pyramid level. Its direct array assignment produces the same data traffic as
`set_region()`, but does not include the metadata reads needed to reopen the
group for each `set_region()` call.
