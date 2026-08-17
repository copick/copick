"""Build the exact copick OME-Zarr 0.5 / Zarr v3 direct-reader fixture.

The archive contains boolean, integer, and floating-point two-level images,
plus a feature-major floating-point image. Every level crosses the canonical
writer and is described by a checksummed manifest suitable for recording
external-reader evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import itertools
import json
import math
import tempfile
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import zarr
from copick.util.ome import DEFAULT_SPATIAL_CHUNKS, ome_zarr_axes, padded_shard_shape, write_ome_zarr, write_ome_zarr_3d
from ome_zarr_models.v05.image import Image

FIXTURE_NAME = "copick-v3-direct-reader-fixture"
FIXTURE_SCHEMA_VERSION = 2
BASE_SHAPE = (129, 130, 131)
FEATURE_SHAPE = (2, 65, 66, 67)
VOXEL_SIZES = (10.0, 20.0)
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
EXPECTED_CODECS = {
    "boolean": ["bytes", "zstd"],
    "integer": ["bytes", "zstd"],
    "floating": ["bytes", "numcodecs.shuffle", "zstd"],
}


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def _case_values() -> dict[str, tuple[np.ndarray, np.ndarray]]:
    z, y, x = np.indices(BASE_SHAPE, sparse=True)
    full = {
        "boolean": ((3 * z + 5 * y + 7 * x) % 11 < 3).astype(np.bool_),
        "integer": (257 * z + 17 * y + x).astype(np.uint16),
        "floating": (0.5 * z - 0.25 * y + 0.125 * x).astype(np.float32),
    }
    return {name: (values, values[::2, ::2, ::2].copy()) for name, values in full.items()}


def _feature_values() -> tuple[np.ndarray, np.ndarray]:
    feature, z, y, x = np.indices(FEATURE_SHAPE, sparse=True)
    values = (2.0 * feature + 0.5 * z - 0.25 * y + 0.125 * x).astype(np.float32)
    return values, values[:, ::2, ::2, ::2].copy()


def _sample_coordinates(shape: Sequence[int]) -> list[tuple[int, ...]]:
    first = (0,) * len(shape)
    last = tuple(size - 1 for size in shape)
    middle = tuple(size // 2 for size in shape)
    boundary = tuple(min(128, size - 1) for size in shape)
    return list(dict.fromkeys([first, middle, boundary, last]))


def _json_scalar(value: np.generic) -> bool | int | float:
    return value.item()


def _level_manifest(
    array: zarr.Array,
    level_path: str,
    voxel_size: float,
    expected: np.ndarray,
    expected_dimensions: tuple[str, ...],
) -> dict[str, Any]:
    metadata = array.metadata.to_dict()
    sharding = metadata["codecs"][0]
    inner_codecs = sharding["configuration"]["codecs"]
    expected_codecs = EXPECTED_CODECS["floating" if np.issubdtype(array.dtype, np.floating) else "integer"]
    if np.issubdtype(array.dtype, np.bool_):
        expected_codecs = EXPECTED_CODECS["boolean"]

    if metadata["zarr_format"] != 3 or sharding["name"] != "sharding_indexed":
        raise AssertionError("Fixture arrays must use Zarr v3 indexed sharding")
    if [codec["name"] for codec in inner_codecs] != expected_codecs:
        raise AssertionError(f"Unexpected canonical codec pipeline: {inner_codecs!r}")
    if metadata["chunk_key_encoding"] != {"name": "v2", "configuration": {"separator": "/"}}:
        raise AssertionError("Fixture arrays must use v2-style slash-separated shard keys")
    if tuple(metadata["dimension_names"]) != expected_dimensions:
        raise AssertionError(f"Fixture array dimensions must be {expected_dimensions!r}")
    shard_grid = [math.ceil(size / shard) for size, shard in zip(array.shape, array.shards, strict=True)]
    expected_grid = [1, 1, 1] if array.ndim == 3 else [array.shape[0], 1, 1, 1]
    if shard_grid != expected_grid:
        raise AssertionError(f"Fixture level must have one spatial shard per feature volume, got {shard_grid!r}")

    actual = np.asarray(array)
    np.testing.assert_array_equal(actual, expected)
    coordinates = _sample_coordinates(array.shape)
    shard_keys = [
        f"{level_path}/{'/'.join(str(index) for index in coordinate)}"
        for coordinate in itertools.product(*(range(size) for size in shard_grid))
    ]
    return {
        "path": level_path,
        "voxel_size_angstrom": voxel_size,
        "shape": list(array.shape),
        "dtype": str(array.dtype),
        "dimension_names": list(metadata["dimension_names"]),
        "inner_chunks": list(array.chunks),
        "shards": list(array.shards),
        "shard_grid_shape": shard_grid,
        "shard_keys": shard_keys,
        "chunk_key_encoding": metadata["chunk_key_encoding"],
        "sharding_index_location": sharding["configuration"]["index_location"],
        "inner_codecs": inner_codecs,
        "decoded_sha256": _sha256_bytes(actual.tobytes(order="C")),
        "samples": [
            {"coordinate": list(coordinate), "value": _json_scalar(actual[coordinate])} for coordinate in coordinates
        ],
    }


def _versions() -> dict[str, str]:
    return {
        name: importlib.metadata.version(name)
        for name in ("copick", "numpy", "numcodecs", "ome-zarr", "ome-zarr-models", "zarr")
    }


def _store_manifest(
    store_path: Path,
    name: str,
    levels: tuple[np.ndarray, ...],
    expected_dimensions: tuple[str, ...],
) -> dict[str, Any]:
    group = zarr.open_group(store_path, mode="r")
    validated = Image.from_zarr(group)
    if validated.ome_zarr_version != "0.5":
        raise AssertionError(f"Expected OME-Zarr 0.5, got {validated.ome_zarr_version!r}")
    multiscale = group.attrs["ome"]["multiscales"][0]
    level_paths = [dataset["path"] for dataset in multiscale["datasets"]]
    if len(level_paths) != len(levels):
        raise AssertionError(f"Expected {len(levels)} levels, got paths {level_paths!r}")
    levels_manifest = [
        _level_manifest(group[level_path], level_path, voxel_size, expected, expected_dimensions)
        for level_path, (voxel_size, expected) in zip(
            level_paths,
            zip(VOXEL_SIZES, levels, strict=True),
            strict=True,
        )
    ]
    for level in levels_manifest:
        for shard_key in level["shard_keys"]:
            if not (store_path / shard_key).is_file():
                raise AssertionError(f"Missing expected shard key {name}.zarr/{shard_key}")
    return {
        "path": f"{name}.zarr",
        "ome_zarr_version": group.attrs["ome"]["version"],
        "multiscale": multiscale,
        "levels": levels_manifest,
    }


def build_fixture(directory: Path, source_revision: str = "unknown") -> dict[str, Any]:
    """Write the unpacked fixture and return its manifest."""
    if not source_revision:
        raise ValueError("source_revision must be a non-empty string")
    directory.mkdir(parents=True, exist_ok=False)
    stores = {}
    for name, levels in _case_values().items():
        store_path = directory / f"{name}.zarr"
        pyramid = dict(zip(VOXEL_SIZES, levels, strict=True))
        write_ome_zarr_3d(
            str(store_path),
            pyramid,
            metadata={"fixture": FIXTURE_NAME, "dtype_case": name},
        )
        stores[name] = _store_manifest(store_path, name, levels, ("z", "y", "x"))

    feature_name = "floating_features"
    feature_levels = _feature_values()
    feature_path = directory / f"{feature_name}.zarr"
    write_ome_zarr(
        str(feature_path),
        dict(zip(VOXEL_SIZES, feature_levels, strict=True)),
        ome_zarr_axes(4),
        (1, *DEFAULT_SPATIAL_CHUNKS),
        metadata={"fixture": FIXTURE_NAME, "dtype_case": feature_name},
        shard_size=(1, *padded_shard_shape(FEATURE_SHAPE[1:], DEFAULT_SPATIAL_CHUNKS)),
    )
    stores[feature_name] = _store_manifest(
        feature_path,
        feature_name,
        feature_levels,
        ("feature", "z", "y", "x"),
    )

    files = {
        str(path.relative_to(directory)): _sha256_file(path) for path in sorted(directory.rglob("*")) if path.is_file()
    }
    manifest = {
        "schema_version": FIXTURE_SCHEMA_VERSION,
        "fixture": FIXTURE_NAME,
        "producer": {**_versions(), "source_revision": source_revision},
        "canonical_policy": {
            "ome_zarr_version": "0.5",
            "zarr_format": 3,
            "spatial_inner_chunks": list(DEFAULT_SPATIAL_CHUNKS),
            "feature_inner_chunks": [1, *DEFAULT_SPATIAL_CHUNKS],
            "one_spatial_shard_per_feature_volume": True,
            "chunk_key_encoding": {"name": "v2", "configuration": {"separator": "/"}},
            "indexed_sharding": True,
            "integer_boolean_codecs": EXPECTED_CODECS["integer"],
            "floating_codecs": EXPECTED_CODECS["floating"],
        },
        "stores": stores,
        "files": files,
    }
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def _write_archive(source: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for path in sorted(source.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(source)
            info = zipfile.ZipInfo(f"{FIXTURE_NAME}/{relative}", ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())


def build_archive(output: Path, source_revision: str = "unknown") -> Mapping[str, Any]:
    """Build a deterministic fixture archive at ``output``."""
    with tempfile.TemporaryDirectory(prefix="copick-v3-direct-reader-") as temporary:
        source = Path(temporary) / FIXTURE_NAME
        manifest = build_fixture(source, source_revision)
        _write_archive(source, output)
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="Destination .zip path")
    parser.add_argument(
        "--source-revision",
        default="unknown",
        help="Source commit recorded in the manifest (CI passes the exact GitHub SHA)",
    )
    args = parser.parse_args(argv)
    build_archive(args.output, args.source_revision)
    print(f"{_sha256_file(args.output)}  {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
