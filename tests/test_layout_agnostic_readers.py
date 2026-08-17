"""Reader gates for supported noncanonical Zarr layouts and codecs."""

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import zarr
from copick.models import CopickFeatures, CopickFeaturesMeta, CopickTomogram, CopickTomogramMeta
from copick.util.handlers.volume.zarr import ZarrVolumeHandler
from copick.util.ome import get_level_path, write_single_level_ome_zarr
from copick.util.zarr_copy import copy_zarr_store
from numcodecs import Blosc, Delta
from numcodecs import Shuffle as V2Shuffle
from numcodecs import Zstd as V2Zstd
from ome_zarr_models.v05.image import Image
from zarr.codecs import (
    BloscCodec,
    Crc32cCodec,
    GzipCodec,
    Shuffle,
    TransposeCodec,
    ZstdCodec,
)
from zarr.metadata.migrate_v3 import migrate_v2_to_v3
from zarr.storage import LocalStore

CASES = (
    "v2-uncompressed-large-chunks",
    "v2-delta-blosc",
    "v2-shuffle-zstd",
    "v3-uncompressed-default-keys",
    "v3-gzip-default-keys",
    "v3-blosc-v2-keys",
    "v3-crc32c-default-keys",
    "v3-transpose-zstd",
    "v3-multishard-shuffle-zstd",
)


class _StoredTomogram(CopickTomogram):
    def __init__(self, store):
        super().__init__(SimpleNamespace(voxel_size=10.0), CopickTomogramMeta(tomo_type="noncanonical"))
        self._store = store

    def zarr(self):
        return self._store


class _StoredFeatures(CopickFeatures):
    def __init__(self, store):
        tomogram = SimpleNamespace(voxel_spacing=SimpleNamespace(voxel_size=10.0))
        super().__init__(tomogram, CopickFeaturesMeta(tomo_type="noncanonical", feature_type="multi"))
        self._store = store

    def zarr(self):
        return self._store


def _ome_axes():
    return [{"name": axis, "type": "space", "unit": "angstrom"} for axis in ("z", "y", "x")]


def _write_metadata(group, zarr_format):
    multiscales = [
        {
            "version": "0.5" if zarr_format == 3 else "0.4",
            "axes": _ome_axes(),
            "datasets": [
                {
                    "path": "s0",
                    "coordinateTransformations": [{"type": "scale", "scale": [10.0, 10.0, 10.0]}],
                },
            ],
        },
    ]
    if zarr_format == 3:
        group.attrs["ome"] = {"version": "0.5", "multiscales": multiscales}
    else:
        group.attrs["multiscales"] = multiscales


def _case_options(case):
    if case == "v2-uncompressed-large-chunks":
        return 2, {"chunks": (256, 256, 256), "compressor": None}
    if case == "v2-delta-blosc":
        return 2, {
            "chunks": (2, 3, 4),
            "filters": (Delta(dtype=np.dtype("<i2")),),
            "compressor": Blosc(cname="zstd", clevel=2, shuffle=Blosc.BITSHUFFLE),
        }
    if case == "v2-shuffle-zstd":
        return 2, {
            "chunks": (1, 2, 3),
            "filters": (V2Shuffle(elementsize=2),),
            "compressor": V2Zstd(level=4),
        }
    if case == "v3-uncompressed-default-keys":
        return 3, {"chunks": (2, 3, 4), "compressors": None}
    if case == "v3-gzip-default-keys":
        return 3, {"chunks": (1, 2, 3), "compressors": (GzipCodec(level=2),)}
    if case == "v3-blosc-v2-keys":
        return 3, {
            "chunks": (2, 3, 4),
            "compressors": (BloscCodec(cname="lz4", clevel=2),),
            "chunk_key_encoding": {"name": "v2", "separator": "/"},
        }
    if case == "v3-crc32c-default-keys":
        return 3, {"chunks": (2, 3, 4), "compressors": (Crc32cCodec(),)}
    if case == "v3-transpose-zstd":
        return 3, {
            "chunks": (2, 3, 4),
            "filters": (TransposeCodec(order=(2, 1, 0)),),
            "compressors": (ZstdCodec(level=2),),
        }
    if case == "v3-multishard-shuffle-zstd":
        return 3, {
            "chunks": (1, 2, 3),
            "shards": (2, 4, 6),
            "compressors": (Shuffle(elementsize=2), ZstdCodec(level=5)),
            "chunk_key_encoding": {"name": "v2", "separator": "/"},
        }
    raise AssertionError(f"Unknown case: {case}")


def _write_case(path, case):
    zarr_format, options = _case_options(case)
    values = np.arange(4 * 5 * 6, dtype=np.int16).reshape(4, 5, 6)
    store = LocalStore(path)
    group = zarr.group(store=store, zarr_format=zarr_format)
    if zarr_format == 3:
        options["dimension_names"] = ("z", "y", "x")
    group.create_array("s0", data=values, attributes={"layout-case": case}, **options)
    _write_metadata(group, zarr_format)
    return store, values


def _snapshot(path: Path):
    return {item.relative_to(path).as_posix(): item.read_bytes() for item in path.rglob("*") if item.is_file()}


@pytest.mark.parametrize("case", CASES)
def test_public_read_copy_and_export_paths_accept_noncanonical_layouts(tmp_path, case):
    source_path = tmp_path / f"{case}.zarr"
    source, expected = _write_case(source_path, case)
    source_group = zarr.open_group(source, mode="r")
    source_array = source_group[get_level_path(source_group, 0)]
    layout_before = source_array.metadata.to_dict()
    tomogram = _StoredTomogram(source)

    np.testing.assert_array_equal(tomogram.numpy(), expected)
    chunk_region = tuple(
        slice(0, min(size, chunk)) for size, chunk in zip(expected.shape, source_array.chunks, strict=True)
    )
    np.testing.assert_array_equal(
        tomogram.numpy(z=chunk_region[0], y=chunk_region[1], x=chunk_region[2]),
        expected[chunk_region],
    )
    np.testing.assert_array_equal(tomogram.numpy(z=slice(0, 3), y=slice(0, 5), x=slice(0, 6)), expected[:3, :5, :6])
    np.testing.assert_array_equal(tomogram.numpy(z=slice(1, 2), y=slice(2, 3), x=slice(3, 4)), expected[1:2, 2:3, 3:4])

    replacement = np.full((2, 2, 2), -7, dtype=np.int16)
    tomogram.set_region(replacement, z=slice(1, 3), y=slice(1, 3), x=slice(1, 3))
    expected[1:3, 1:3, 1:3] = replacement
    np.testing.assert_array_equal(tomogram.numpy(), expected)
    assert zarr.open_group(source, mode="r")[get_level_path(source_group, 0)].metadata.to_dict() == layout_before

    handled, voxel_size = ZarrVolumeHandler().read(str(source_path))
    np.testing.assert_array_equal(handled, expected)
    assert voxel_size == 10.0

    raw_target_path = tmp_path / f"{case}-raw.zarr"
    copy_zarr_store(source, LocalStore(raw_target_path))
    assert _snapshot(raw_target_path) == _snapshot(source_path)

    semantic_target = LocalStore(tmp_path / f"{case}-semantic.zarr")
    write_single_level_ome_zarr(zarr.open_group(source, mode="r"), semantic_target)
    semantic_group = zarr.open_group(semantic_target, mode="r")
    semantic = semantic_group[get_level_path(semantic_group, 0)]
    np.testing.assert_array_equal(semantic[:], expected)
    assert semantic.chunks == (128, 128, 128)
    assert semantic.shards == (128, 128, 128)
    assert semantic.metadata.chunk_key_encoding.to_dict()["name"] == "v2"


def test_noncanonical_matrix_covers_required_layout_and_codec_families(tmp_path):
    descriptions = {}
    for case in CASES:
        store, _ = _write_case(tmp_path / f"{case}.zarr", case)
        group = zarr.open_group(store, mode="r")
        array = group[get_level_path(group, 0)]
        descriptions[case] = json.dumps(array.metadata.to_dict(), default=str)

    assert '"chunks": [256, 256, 256]' in descriptions["v2-uncompressed-large-chunks"]
    assert '"id": "delta"' in descriptions["v2-delta-blosc"]
    assert '"id": "shuffle"' in descriptions["v2-shuffle-zstd"]
    assert '"name": "gzip"' in descriptions["v3-gzip-default-keys"]
    assert '"name": "blosc"' in descriptions["v3-blosc-v2-keys"]
    assert '"name": "crc32c"' in descriptions["v3-crc32c-default-keys"]
    assert '"name": "transpose"' in descriptions["v3-transpose-zstd"]
    assert '"name": "sharding_indexed"' in descriptions["v3-multishard-shuffle-zstd"]
    assert '"name": "numcodecs.shuffle"' in descriptions["v3-multishard-shuffle-zstd"]


def test_feature_reader_accepts_noncanonical_unsharded_4d_layout(tmp_path):
    path = tmp_path / "features.zarr"
    store = LocalStore(path)
    values = np.arange(3 * 4 * 5 * 6, dtype=np.float32).reshape(3, 4, 5, 6)
    group = zarr.group(store=store, zarr_format=3)
    group.create_array(
        "features",
        data=values,
        chunks=(2, 1, 2, 3),
        compressors=(GzipCodec(level=1),),
        dimension_names=("feature", "z", "y", "x"),
    )
    group.attrs["ome"] = {
        "version": "0.5",
        "multiscales": [
            {
                "axes": [{"name": "feature"}, *_ome_axes()],
                "datasets": [
                    {
                        "path": "features",
                        "coordinateTransformations": [{"type": "scale", "scale": [1.0, 10.0, 10.0, 10.0]}],
                    },
                ],
            },
        ],
    }
    features = _StoredFeatures(store)

    np.testing.assert_array_equal(features.numpy(), values)
    selection = (slice(1, 3), slice(1, 3), slice(2, 4), slice(3, 5))
    np.testing.assert_array_equal(features.numpy(slices=selection), values[selection])
    replacement = np.full((1, 1, 1, 1), 42, dtype=np.float32)
    features.set_region(replacement, slices=(slice(2, 3), slice(3, 4), slice(4, 5), slice(5, 6)))
    assert features.numpy(slices=(slice(2, 3), slice(3, 4), slice(4, 5), slice(5, 6))).item() == 42


def test_metadata_migrated_portal_shaped_v3_fixture_reads_without_normalization(tmp_path):
    path = tmp_path / "portal-migrated.zarr"
    store = LocalStore(path)
    values = np.arange(4 * 5 * 6, dtype=np.int16).reshape(4, 5, 6)
    group = zarr.group(store=store, zarr_format=2)
    group.create_array(
        "s0",
        data=values,
        chunks=(2, 3, 4),
        compressor=Blosc(cname="lz4", clevel=3, shuffle=Blosc.SHUFFLE),
    )
    _write_metadata(group, 2)

    migrate_v2_to_v3(input_store=store)
    root_metadata = json.loads((path / "zarr.json").read_text(encoding="utf-8"))
    multiscales = root_metadata["attributes"].pop("multiscales")
    multiscales[0].pop("version")
    root_metadata["attributes"]["ome"] = {"version": "0.5", "multiscales": multiscales}
    (path / "zarr.json").write_text(json.dumps(root_metadata), encoding="utf-8")
    array_metadata = json.loads((path / "s0" / "zarr.json").read_text(encoding="utf-8"))
    array_metadata["dimension_names"] = ["z", "y", "x"]
    (path / "s0" / "zarr.json").write_text(json.dumps(array_metadata), encoding="utf-8")

    migrated = zarr.open_group(store, mode="r")
    assert Image.from_zarr(migrated).ome_zarr_version == "0.5"
    assert migrated[get_level_path(migrated, 0)].metadata.chunk_key_encoding.to_dict()["name"] == "v2"
    np.testing.assert_array_equal(_StoredTomogram(store).numpy(), values)
    handled, voxel_size = ZarrVolumeHandler().read(str(path))
    np.testing.assert_array_equal(handled, values)
    assert voxel_size == 10.0
