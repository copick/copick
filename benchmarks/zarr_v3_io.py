"""Measure canonical Zarr v3 read and region-write behavior.

This benchmark deliberately records store-level requests and payload sizes
instead of setting pass/fail latency thresholds.  It is intended to make the
one-shard tradeoff observable on local, S3-compatible, and SSH storage.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import statistics
import tempfile
import threading
import time
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import psutil
import zarr
from zarr.abc.store import Store
from zarr.storage import WrapperStore

from copick.util.ome import get_level_path, write_ome_zarr_3d
from copick.util.reconnecting_fs import ReconnectingFileSystem
from copick.util.store import copick_store

DEFAULT_CASES = {
    "small": (96, 112, 120),
    "large": (257, 257, 257),
}
DEFAULT_CHUNKS = (128, 128, 128)
_SENSITIVE_OPTION_PARTS = ("credential", "key", "password", "secret", "token")


def _is_data_key(key: str) -> bool:
    """Return whether a store key contains array payload rather than metadata."""
    return not key.endswith(("zarr.json", ".zarray", ".zattrs", ".zgroup", ".zmetadata"))


@dataclass
class IOStats:
    """Store traffic observed during one operation."""

    read_requests: int = 0
    read_bytes: int = 0
    write_requests: int = 0
    write_bytes: int = 0
    data_read_requests: int = 0
    data_read_bytes: int = 0
    data_write_requests: int = 0
    data_write_bytes: int = 0
    reads_by_key: dict[str, dict[str, int]] = field(default_factory=dict)
    writes_by_key: dict[str, dict[str, int]] = field(default_factory=dict)


class RecordingStore(WrapperStore):
    """A transparent Zarr store wrapper which records payload I/O.

    ``get_ranges`` yields one batch per underlying I/O operation.  The byte
    count includes the complete coalesced span for explicit ranges, including
    gaps which the backend had to transfer.
    """

    def __init__(self, store: Store) -> None:
        super().__init__(store)
        self._stats_lock = threading.Lock()
        self._reads: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        self._writes: dict[str, list[int]] = defaultdict(lambda: [0, 0])

    def _record_read(self, key: str, size: int) -> None:
        with self._stats_lock:
            self._reads[key][0] += 1
            self._reads[key][1] += size

    def _record_write(self, key: str, size: int) -> None:
        with self._stats_lock:
            self._writes[key][0] += 1
            self._writes[key][1] += size

    def snapshot(self) -> IOStats:
        with self._stats_lock:
            reads = {key: {"requests": value[0], "bytes": value[1]} for key, value in self._reads.items()}
            writes = {key: {"requests": value[0], "bytes": value[1]} for key, value in self._writes.items()}
        return IOStats(
            read_requests=sum(value["requests"] for value in reads.values()),
            read_bytes=sum(value["bytes"] for value in reads.values()),
            write_requests=sum(value["requests"] for value in writes.values()),
            write_bytes=sum(value["bytes"] for value in writes.values()),
            data_read_requests=sum(value["requests"] for key, value in reads.items() if _is_data_key(key)),
            data_read_bytes=sum(value["bytes"] for key, value in reads.items() if _is_data_key(key)),
            data_write_requests=sum(value["requests"] for key, value in writes.items() if _is_data_key(key)),
            data_write_bytes=sum(value["bytes"] for key, value in writes.items() if _is_data_key(key)),
            reads_by_key=reads,
            writes_by_key=writes,
        )

    @staticmethod
    def delta(after: IOStats, before: IOStats) -> IOStats:
        def mapping_delta(
            newer: Mapping[str, Mapping[str, int]],
            older: Mapping[str, Mapping[str, int]],
        ) -> dict[str, dict[str, int]]:
            result = {}
            for key in set(newer) | set(older):
                requests = newer.get(key, {}).get("requests", 0) - older.get(key, {}).get("requests", 0)
                size = newer.get(key, {}).get("bytes", 0) - older.get(key, {}).get("bytes", 0)
                if requests or size:
                    result[key] = {"requests": requests, "bytes": size}
            return dict(sorted(result.items()))

        scalar_fields = (
            "read_requests",
            "read_bytes",
            "write_requests",
            "write_bytes",
            "data_read_requests",
            "data_read_bytes",
            "data_write_requests",
            "data_write_bytes",
        )
        values = {name: getattr(after, name) - getattr(before, name) for name in scalar_fields}
        return IOStats(
            **values,
            reads_by_key=mapping_delta(after.reads_by_key, before.reads_by_key),
            writes_by_key=mapping_delta(after.writes_by_key, before.writes_by_key),
        )

    async def get(self, key, prototype, byte_range=None):
        value = await self._store.get(key, prototype, byte_range)
        self._record_read(key, 0 if value is None else len(value))
        return value

    async def get_partial_values(self, prototype, key_ranges):
        ranges = list(key_ranges)
        values = await self._store.get_partial_values(prototype, ranges)
        for (key, _byte_range), value in zip(ranges, values, strict=True):
            self._record_read(key, 0 if value is None else len(value))
        return values

    async def get_ranges(self, key, byte_ranges, **kwargs):
        ranges = list(byte_ranges)
        async for group in self._store.get_ranges(key, ranges, **kwargs):
            indexes = [index for index, _value in group]
            explicit = [ranges[index] for index in indexes]
            if explicit and all(hasattr(item, "start") and hasattr(item, "end") for item in explicit):
                size = max(item.end for item in explicit) - min(item.start for item in explicit)
            else:
                size = sum(0 if value is None else len(value) for _index, value in group)
            self._record_read(key, size)
            yield group

    async def _get_many(self, requests):
        request_list = list(requests)
        async for key, value in self._store._get_many(request_list):
            self._record_read(key, 0 if value is None else len(value))
            yield key, value

    async def set(self, key, value):
        self._record_write(key, len(value))
        await self._store.set(key, value)

    async def set_if_not_exists(self, key, value):
        self._record_write(key, len(value))
        await self._store.set_if_not_exists(key, value)

    async def _set_many(self, values: Iterable[tuple[str, Any]]) -> None:
        value_list = list(values)
        for key, value in value_list:
            self._record_write(key, len(value))
        await self._store._set_many(value_list)


class PeakRSS:
    """Sample the process resident set size while an operation runs."""

    def __init__(self, interval_seconds: float = 0.005) -> None:
        self.interval_seconds = interval_seconds
        self.process = psutil.Process()
        self.baseline_bytes = 0
        self.peak_bytes = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "PeakRSS":
        self.baseline_bytes = self.process.memory_info().rss
        self.peak_bytes = self.baseline_bytes
        self._thread = threading.Thread(target=self._sample, daemon=True)
        self._thread.start()
        return self

    def _sample(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            self.peak_bytes = max(self.peak_bytes, self.process.memory_info().rss)

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.peak_bytes = max(self.peak_bytes, self.process.memory_info().rss)
        self._stop.set()
        if self._thread is not None:
            self._thread.join()

    @property
    def delta_bytes(self) -> int:
        return max(0, self.peak_bytes - self.baseline_bytes)


@dataclass
class OperationSample:
    elapsed_seconds: float
    baseline_rss_bytes: int
    peak_rss_bytes: int
    peak_rss_delta_bytes: int
    logical_uncompressed_bytes: int
    checksum: float | None
    io: IOStats


@dataclass
class OperationResult:
    name: str
    selection: list[list[int]] | None
    samples: list[OperationSample]

    def summary(self) -> dict[str, float | int]:
        elapsed = [sample.elapsed_seconds for sample in self.samples]
        peak_rss = [sample.peak_rss_bytes for sample in self.samples]
        rss = [sample.peak_rss_delta_bytes for sample in self.samples]
        reads = [sample.io.data_read_bytes for sample in self.samples]
        writes = [sample.io.data_write_bytes for sample in self.samples]
        logical = self.samples[0].logical_uncompressed_bytes
        return {
            "elapsed_median_seconds": statistics.median(elapsed),
            "elapsed_mean_seconds": statistics.mean(elapsed),
            "peak_rss_max_bytes": max(peak_rss),
            "peak_rss_delta_max_bytes": max(rss),
            "data_read_bytes_median": statistics.median(reads),
            "data_write_bytes_median": statistics.median(writes),
            "logical_uncompressed_bytes": logical,
            "read_amplification_median": statistics.median(reads) / logical if logical else 0.0,
            "write_amplification_median": statistics.median(writes) / logical if logical else 0.0,
            "io_amplification_median": statistics.median(
                (read + write) / logical if logical else 0.0 for read, write in zip(reads, writes, strict=True)
            ),
        }


def _measure(
    recorder: RecordingStore,
    operation: Callable[[], np.ndarray | None],
    *,
    logical_uncompressed_bytes: int,
) -> OperationSample:
    before = recorder.snapshot()
    with PeakRSS() as memory:
        started = time.perf_counter()
        value = operation()
        elapsed = time.perf_counter() - started
    after = recorder.snapshot()
    checksum = None if value is None else float(np.asarray(value, dtype=np.float64).sum())
    return OperationSample(
        elapsed_seconds=elapsed,
        baseline_rss_bytes=memory.baseline_bytes,
        peak_rss_bytes=memory.peak_bytes,
        peak_rss_delta_bytes=memory.delta_bytes,
        logical_uncompressed_bytes=logical_uncompressed_bytes,
        checksum=checksum,
        io=recorder.delta(after, before),
    )


def _selection(shape: Sequence[int], starts: Sequence[int], stops: Sequence[int]) -> tuple[slice, ...]:
    return tuple(slice(max(0, start), min(size, stop)) for size, start, stop in zip(shape, starts, stops, strict=True))


def _selection_json(selection: tuple[slice, ...]) -> list[list[int]]:
    return [[item.start or 0, item.stop or 0] for item in selection]


def _logical_bytes(selection: tuple[slice, ...], dtype: np.dtype) -> int:
    return math.prod((item.stop or 0) - (item.start or 0) for item in selection) * dtype.itemsize


def _layout(array: zarr.Array) -> dict[str, Any]:
    metadata = array.metadata
    codec = metadata.codecs[0]
    return {
        "zarr_format": metadata.zarr_format,
        "shape": list(array.shape),
        "dtype": str(array.dtype),
        "dimension_names": list(metadata.dimension_names),
        "chunks": list(array.chunks),
        "shards": list(array.shards),
        "shard_grid_shape": [math.ceil(size / shard) for size, shard in zip(array.shape, array.shards, strict=True)],
        "chunk_key_encoding": metadata.chunk_key_encoding.to_dict(),
        "sharding_codec": codec.to_dict(),
    }


def _values(shape: tuple[int, ...]) -> np.ndarray:
    # Deterministic noise is a closer compression proxy for reconstructed
    # tomograms than ramps or repeating fixtures.
    return np.random.default_rng(20260817).standard_normal(shape, dtype=np.float32)


def run_case(store: Store, name: str, shape: tuple[int, ...], chunks: tuple[int, ...], repeats: int) -> dict[str, Any]:
    """Run the complete benchmark suite for one volume shape."""
    recorder = RecordingStore(store)
    values = _values(shape)
    full_selection = tuple(slice(0, size) for size in shape)

    write_sample = _measure(
        recorder,
        lambda: (write_ome_zarr_3d(recorder, {10.0: values}, chunk_size=chunks), None)[1],
        logical_uncompressed_bytes=values.nbytes,
    )
    if write_sample.io.data_write_requests != 1:
        raise AssertionError(
            "Canonical full-level write must write exactly one data shard; "
            f"observed {write_sample.io.data_write_requests} writes",
        )

    group = zarr.open_group(recorder, mode="r+")
    array = group[get_level_path(group, 0)]
    original_layout = _layout(array)
    if original_layout["shard_grid_shape"] != [1] * len(shape):
        raise AssertionError(f"Expected a one-element shard grid, got {original_layout['shard_grid_shape']}")

    single = _selection(shape, (0, 0, 0), chunks)
    multi = _selection(shape, tuple(chunk // 2 for chunk in chunks), tuple(chunk + chunk // 2 for chunk in chunks))
    small = _selection(shape, (3, 5, 7), (11, 13, 15))
    operations = [
        OperationResult("write_full_level", _selection_json(full_selection), [write_sample]),
    ]

    for operation_name, selection in (
        ("read_full_volume", full_selection),
        ("read_single_inner_chunk", single),
        ("read_multiple_inner_chunks", multi),
        ("read_small_region", small),
    ):
        array[selection]  # warm the runtime without including it in measurements
        samples = [
            _measure(
                recorder,
                lambda selection=selection: np.asarray(array[selection]),
                logical_uncompressed_bytes=_logical_bytes(selection, array.dtype),
            )
            for _index in range(repeats)
        ]
        operations.append(OperationResult(operation_name, _selection_json(selection), samples))

    update = np.full(tuple(item.stop - item.start for item in small), -31.25, dtype=array.dtype)
    update_sample = _measure(
        recorder,
        lambda: (array.__setitem__(small, update), None)[1],
        logical_uncompressed_bytes=update.nbytes,
    )
    operations.append(OperationResult("write_small_region", _selection_json(small), [update_sample]))
    values[small] = update

    if _layout(array) != original_layout:
        raise AssertionError("Region write changed the canonical shard grid or codec pipeline")
    np.testing.assert_array_equal(array[:], values)

    return {
        "name": name,
        "shape": list(shape),
        "chunks": list(chunks),
        "layout": original_layout,
        "operations": [
            {
                "name": result.name,
                "selection": result.selection,
                "summary": result.summary(),
                "samples": [asdict(sample) for sample in result.samples],
            }
            for result in operations
        ],
    }


def _parse_shape(value: str) -> tuple[str, tuple[int, int, int]]:
    try:
        name, raw_shape = value.split("=", 1)
        shape = tuple(int(item) for item in raw_shape.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("shapes must use NAME=Z,Y,X") from exc
    if not name or len(shape) != 3 or any(item <= 0 for item in shape):
        raise argparse.ArgumentTypeError("shapes must use NAME=Z,Y,X with three positive dimensions")
    return name, shape


def _parse_chunks(value: str) -> tuple[int, int, int]:
    try:
        chunks = tuple(int(item) for item in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("chunks must use Z,Y,X") from exc
    if len(chunks) != 3 or any(item <= 0 for item in chunks):
        raise argparse.ArgumentTypeError("chunks must contain three positive dimensions")
    return chunks


def _parse_option(value: str) -> tuple[str, Any]:
    try:
        key, raw = value.split("=", 1)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("storage options must use KEY=JSON_VALUE") from exc
    if not key:
        raise argparse.ArgumentTypeError("storage option keys cannot be empty")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = raw
    return key, parsed


def _safe_options(options: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: "<redacted>" if any(part in key.lower() for part in _SENSITIVE_OPTION_PARTS) else value
        for key, value in sorted(options.items())
    }


def _default_root(backend: str) -> str:
    if backend == "local":
        return f"local://{tempfile.mkdtemp(prefix='copick-zarr-v3-benchmark-')}"
    if backend == "s3":
        return "s3://copick-zarr-v3-benchmark"
    return "ssh:///config/copick-zarr-v3-benchmark"


def _join_url(root: str, *parts: str) -> str:
    return "/".join([root.rstrip("/"), *(part.strip("/") for part in parts)])


def _prepare_filesystem(backend: str, root: str, options: Mapping[str, Any]) -> ReconnectingFileSystem:
    filesystem = ReconnectingFileSystem(root, dict(options))
    if backend == "s3":
        stripped = filesystem._strip_protocol(root).strip("/")
        bucket = stripped.split("/", 1)[0]
        if not filesystem.exists(bucket):
            filesystem.mkdir(bucket)
    return filesystem


def _markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# Canonical Zarr v3 I/O benchmark",
        "",
        f"- Recorded: `{report['recorded_at']}`",
        f"- Backend: `{report['backend']}`",
        f"- Python: `{report['runtime']['python']}`",
        f"- Zarr: `{report['runtime']['zarr']}`",
        f"- Repeats per read: `{report['repeats']}`",
        "",
        "| Case | Operation | Median elapsed (s) | Data reads | Read bytes | Data writes | Write bytes | Peak RSS | I/O / logical bytes |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for case in report["cases"]:
        for operation in case["operations"]:
            summary = operation["summary"]
            sample = operation["samples"][0]
            amplification = summary["io_amplification_median"]
            lines.append(
                "| {case} | {operation} | {elapsed:.6f} | {reads} | {read_bytes} | {writes} | "
                "{write_bytes} | {rss} | {amplification:.2f}× |".format(
                    case=case["name"],
                    operation=operation["name"],
                    elapsed=summary["elapsed_median_seconds"],
                    reads=sample["io"]["data_read_requests"],
                    read_bytes=int(summary["data_read_bytes_median"]),
                    writes=sample["io"]["data_write_requests"],
                    write_bytes=int(summary["data_write_bytes_median"]),
                    rss=summary["peak_rss_max_bytes"],
                    amplification=amplification,
                ),
            )
    lines.extend(
        [
            "",
            "Request and byte counts are observed at the Zarr store boundary. Timings are diagnostic and are not CI",
            "thresholds. The JSON report contains every sample and the per-key traffic breakdown.",
            "",
        ],
    )
    return "\n".join(lines)


def run_benchmark(
    *,
    backend: str,
    root: str,
    storage_options: Mapping[str, Any],
    cases: Mapping[str, tuple[int, ...]],
    chunks: tuple[int, ...],
    repeats: int,
    keep: bool,
) -> dict[str, Any]:
    filesystem = _prepare_filesystem(backend, root, storage_options)
    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{os.getpid()}"
    results = []
    locations = []
    try:
        for name, shape in cases.items():
            location = _join_url(root, run_id, f"{name}.zarr")
            locations.append(location)
            store = copick_store(filesystem, location, create=True)
            results.append(run_case(store, name, tuple(shape), chunks, repeats))
    finally:
        if not keep:
            for location in reversed(locations):
                stripped = filesystem._strip_protocol(location)
                if filesystem.exists(stripped):
                    filesystem.rm(stripped, recursive=True)

    return {
        "schema_version": 1,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "backend": backend,
        "root": root,
        "storage_options": _safe_options(storage_options),
        "chunks": list(chunks),
        "repeats": repeats,
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "zarr": zarr.__version__,
            "numpy": np.__version__,
        },
        "cases": results,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("local", "s3", "ssh"), default="local")
    parser.add_argument("--root", help="Backend URL under which unique benchmark stores are created")
    parser.add_argument(
        "--storage-option",
        action="append",
        default=[],
        type=_parse_option,
        metavar="KEY=JSON_VALUE",
        help="fsspec option; repeat as needed (sensitive values are redacted from reports)",
    )
    parser.add_argument(
        "--shape",
        action="append",
        type=_parse_shape,
        metavar="NAME=Z,Y,X",
        help="replace the default representative small and large cases",
    )
    parser.add_argument("--chunks", type=_parse_chunks, default=DEFAULT_CHUNKS)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-markdown", type=Path)
    parser.add_argument("--keep", action="store_true", help="retain benchmark stores after completion")
    args = parser.parse_args(argv)
    if args.repeats < 1:
        parser.error("--repeats must be at least 1")

    report = run_benchmark(
        backend=args.backend,
        root=args.root or _default_root(args.backend),
        storage_options=dict(args.storage_option),
        cases=dict(args.shape) if args.shape else DEFAULT_CASES,
        chunks=args.chunks,
        repeats=args.repeats,
        keep=args.keep,
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    markdown = _markdown(report)
    if args.output_markdown:
        args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
        args.output_markdown.write_text(markdown, encoding="utf-8")
    print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
