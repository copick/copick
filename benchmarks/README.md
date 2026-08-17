# Canonical Zarr v3 I/O benchmark

`benchmarks/zarr_v3_io.py` makes the storage tradeoffs of copick's canonical
OME-Zarr 0.5 / Zarr v3 layout observable. It records elapsed time, store-level
requests, transferred bytes, and sampled peak process RSS (both the absolute
peak and the increase from the operation's baseline) for:

- a full-level write;
- full-volume, one-inner-chunk, multi-inner-chunk, and small-region reads; and
- a small region update.

The default `small` volume fits inside one `(128, 128, 128)` inner chunk. The
default `large` volume is `(257, 257, 257)`, so it crosses inner-chunk
boundaries in every dimension. Both levels still use copick's one-element
shard grid. The benchmark fails if a full write produces more than one data
object, if a region update changes the layout, or if any value is wrong after
the update.

The request and byte measurements are taken at the Zarr store boundary. A
coalesced ranged read counts as one request and includes the complete fetched
span. `io_amplification_median` is total data bytes read plus written divided
by the logical bytes requested or updated. Compression can make a one-way
read or write ratio less than one; the region-update total is the relevant
tradeoff because updating a compressed shard reads and rewrites that shard.

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

## CI evidence and interpretation

The `Zarr v3 I/O benchmarks` workflow runs the same representative cases on
local storage, Moto S3, and the repository SSH container. It uploads both JSON
and Markdown reports as the `zarr-v3-io-<backend>` artifacts. These emulators
make request behavior reproducible, but their latencies are not representative
of a production network.

MLCroissant is a catalog/configuration backend rather than another physical
Zarr transport. Its Zarr v3 correctness is covered by the named
`ubuntu mlcroissant v3 corpus py3.13` job in the main test workflow. Together,
that parity job and the three benchmark artifacts are the evidence set for
the backend matrix.

The expected tradeoff is intentional: one complete level is created by one
data-object write, indexed reads can fetch only the compressed inner chunks
needed, and an in-place region update has to read and rewrite the containing
volume-sized shard. Callers performing many small updates should stage a
complete level and invoke the canonical writer once.
