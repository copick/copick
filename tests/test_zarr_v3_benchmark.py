"""Focused tests for the canonical Zarr v3 I/O benchmark."""

import json
import sys
from pathlib import Path

from zarr.storage import LocalStore

# The benchmark is intentionally repository tooling rather than a wheel package.
sys.path.insert(0, str(Path(__file__).parents[1]))
from benchmarks import zarr_v3_io as benchmark  # noqa: E402


def _operations(result):
    return {operation["name"]: operation for operation in result["operations"]}


def test_run_case_measures_one_shard_io_and_preserves_values(tmp_path):
    result = benchmark.run_case(LocalStore(tmp_path / "case.zarr"), "unit", (12, 14, 16), (8, 8, 8), repeats=1)
    operations = _operations(result)

    assert result["layout"]["zarr_format"] == 3
    assert result["layout"]["shard_grid_shape"] == [1, 1, 1]
    assert operations["write_full_level"]["samples"][0]["io"]["data_write_requests"] == 1

    region = operations["write_small_region"]
    io = region["samples"][0]["io"]
    assert io["data_read_requests"] == 1
    assert io["data_write_requests"] == 1
    assert set(io["reads_by_key"]) == set(io["writes_by_key"])
    assert region["summary"]["io_amplification_median"] > 1
    assert set(io["read_methods"]) <= set(benchmark.READ_BYTE_SEMANTICS)


def test_run_benchmark_records_zarr_concurrency(tmp_path):
    with benchmark.zarr.config.set({"async.concurrency": 1}):
        report = benchmark.run_benchmark(
            backend="local",
            root=f"local://{tmp_path}",
            storage_options={},
            cases={"unit": (12, 14, 16)},
            chunks=(8, 8, 8),
            repeats=1,
            keep=False,
        )

    assert report["runtime"]["zarr_async_concurrency"] == 1
    assert report["measurement"]["read_methods_observed"]
    assert report["measurement"]["read_byte_semantics"] == benchmark.READ_BYTE_SEMANTICS


def test_cli_writes_machine_and_human_readable_reports(tmp_path, monkeypatch):
    json_path = tmp_path / "nested" / "result.json"
    markdown_path = tmp_path / "nested" / "result.md"
    report = {
        "schema_version": 2,
        "recorded_at": "2026-08-17T00:00:00+00:00",
        "backend": "local",
        "chunks": [8, 8, 8],
        "repeats": 1,
        "runtime": {"python": "3.13.3", "zarr": "3.3.0"},
        "measurement": {"read_methods_observed": [], "read_byte_semantics": benchmark.READ_BYTE_SEMANTICS},
        "cases": [],
    }
    monkeypatch.setattr(benchmark, "run_benchmark", lambda **_kwargs: report)

    status = benchmark.main(
        [
            "--shape",
            "unit=12,14,16",
            "--chunks",
            "8,8,8",
            "--repeats",
            "1",
            "--output-json",
            str(json_path),
            "--output-markdown",
            str(markdown_path),
        ],
    )

    written_report = json.loads(json_path.read_text(encoding="utf-8"))
    assert status == 0
    assert written_report == report
    assert markdown_path.read_text(encoding="utf-8") == benchmark._markdown(report)


def test_safe_options_redacts_credentials_by_option_name():
    assert benchmark._safe_options(
        {
            "client_kwargs": {"region_name": "us-west-2"},
            "endpoint_url": "http://127.0.0.1:4001",
            "key": "test-key",
            "password": "test-password",
        },
    ) == {
        "client_kwargs": {"region_name": "us-west-2"},
        "endpoint_url": "http://127.0.0.1:4001",
        "key": "<redacted>",
        "password": "<redacted>",
    }
