"""Build the exact copick OME-Zarr 0.5 / Zarr v3 direct-reader fixture.

The archive contains boolean, integer, and floating-point two-level images.
Every level crosses the canonical writer, uses a single indexed shard, and is
described by a checksumed manifest suitable for recording external-reader
evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import tempfile
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import zarr
from ome_zarr_models.v05.image import Image

from copick.util.ome import DEFAULT_SPATIAL_CHUNKS, write_ome_zarr_3d

FIXTURE_NAME = "copick-v3-direct-reader-fixture"
FIXTURE_SCHEMA_VERSION = 1
BASE_SHAPE = (129, 130, 131)
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


def _sample_coordinates(shape: Sequence[int]) -> list[tuple[int, int, int]]:
    last = tuple(size - 1 for size in shape)
    middle = tuple(size // 2 for size in shape)
    boundary = tuple(min(128, size - 1) for size in shape)
    return list(dict.fromkeys([(0, 0, 0), middle, boundary, last]))


def _json_scalar(value: np.generic) -> bool | int | float:
    return value.item()


def _level_manifest(array: zarr.Array, level: int, voxel_size: float, expected: np.ndarray) -> dict[str, Any]:
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
    if tuple(metadata["dimension_names"]) != ("z", "y", "x"):
        raise AssertionError("Fixture arrays must declare z/y/x dimension names")
    shard_grid = [math.ceil(size / shard) for size, shard in zip(array.shape, array.shards, strict=True)]
    if shard_grid != [1, 1, 1]:
        raise AssertionError(f"Fixture level must have one shard, got grid {shard_grid!r}")

    actual = np.asarray(array)
    np.testing.assert_array_equal(actual, expected)
    coordinates = _sample_coordinates(array.shape)
    return {
        "path": str(level),
        "voxel_size_angstrom": voxel_size,
        "shape": list(array.shape),
        "dtype": str(array.dtype),
        "dimension_names": list(metadata["dimension_names"]),
        "inner_chunks": list(array.chunks),
        "shards": list(array.shards),
        "shard_grid_shape": shard_grid,
        "shard_key": f"{level}/0/0/0",
        "chunk_key_encoding": metadata["chunk_key_encoding"],
        "sharding_index_location": sharding["configuration"]["index_location"],
        "inner_codecs": inner_codecs,
        "decoded_sha256": _sha256_bytes(actual.tobytes(order="C")),
        "samples": [
            {"coordinate_zyx": list(coordinate), "value": _json_scalar(actual[coordinate])}
            for coordinate in coordinates
        ],
    }


def _versions() -> dict[str, str]:
    return {
        name: importlib.metadata.version(name)
        for name in ("copick", "numpy", "numcodecs", "ome-zarr", "ome-zarr-models", "zarr")
    }


def build_fixture(directory: Path) -> dict[str, Any]:
    """Write the unpacked fixture and return its manifest."""
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
        group = zarr.open_group(store_path, mode="r")
        validated = Image.from_zarr(group)
        if validated.ome_zarr_version != "0.5":
            raise AssertionError(f"Expected OME-Zarr 0.5, got {validated.ome_zarr_version!r}")
        multiscale = group.attrs["ome"]["multiscales"][0]
        levels_manifest = [
            _level_manifest(group[str(level)], level, voxel_size, expected)
            for level, (voxel_size, expected) in enumerate(zip(VOXEL_SIZES, levels, strict=True))
        ]
        for level in levels_manifest:
            if not (store_path / level["shard_key"]).is_file():
                raise AssertionError(f"Missing expected shard key {name}.zarr/{level['shard_key']}")
        stores[name] = {
            "path": f"{name}.zarr",
            "ome_zarr_version": group.attrs["ome"]["version"],
            "multiscale": multiscale,
            "levels": levels_manifest,
        }

    files = {
        str(path.relative_to(directory)): _sha256_file(path) for path in sorted(directory.rglob("*")) if path.is_file()
    }
    manifest = {
        "schema_version": FIXTURE_SCHEMA_VERSION,
        "fixture": FIXTURE_NAME,
        "producer": _versions(),
        "canonical_policy": {
            "ome_zarr_version": "0.5",
            "zarr_format": 3,
            "inner_chunks": list(DEFAULT_SPATIAL_CHUNKS),
            "one_shard_per_level": True,
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


def build_archive(output: Path) -> Mapping[str, Any]:
    """Build a deterministic fixture archive at ``output``."""
    with tempfile.TemporaryDirectory(prefix="copick-v3-direct-reader-") as temporary:
        source = Path(temporary) / FIXTURE_NAME
        manifest = build_fixture(source)
        _write_archive(source, output)
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="Destination .zip path")
    args = parser.parse_args(argv)
    build_archive(args.output)
    print(f"{_sha256_file(args.output)}  {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
