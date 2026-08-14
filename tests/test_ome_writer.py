"""Golden contracts for the centralized OME-Zarr 0.5 / Zarr v3 writer."""

import ast
import inspect
import json
import math
import warnings
from pathlib import Path

import copick.util.ome as ome
import numpy as np
import pytest
import zarr
from copick.ops.add import (
    _add_tomogram_em,
    _add_tomogram_tiff,
    _add_tomogram_zarr,
    add_features,
    add_tomogram,
    add_tomogram_from_file,
    z_add_tomogram_mrc,
)
from copick.util.handlers.volume.zarr import ZarrVolumeHandler
from copick.util.ome import DEFAULT_SPATIAL_CHUNKS, get_level_path, padded_shard_shape, write_ome_zarr_3d
from ome_zarr_models.v05.image import Image
from zarr.storage import LocalStore, MemoryStore


@pytest.fixture
def writer_pyramid():
    return {
        10.0: np.arange(64, dtype=np.float32).reshape(4, 4, 4),
        20.0: np.full((2, 2, 2), 7, dtype=np.float32),
    }


@pytest.mark.parametrize("target_kind", ["path", "store"])
def test_writer_emits_v3_ome_zarr_05_contract(tmp_path, writer_pyramid, target_kind):
    path = tmp_path / f"{target_kind}.zarr"
    target = str(path) if target_kind == "path" else LocalStore(path)

    write_ome_zarr_3d(target, writer_pyramid, chunk_size=(2, 2, 2))

    store = LocalStore(path)
    group = zarr.open_group(store, mode="r")
    assert json.loads((path / "zarr.json").read_text())["zarr_format"] == 3
    assert not (path / ".zgroup").exists()

    assert Image.from_zarr(group).ome_zarr_version == "0.5"
    assert group.attrs["ome"]["version"] == "0.5"
    multiscale = group.attrs["ome"]["multiscales"][0]
    assert multiscale == {
        "datasets": [
            {
                "path": "0",
                "coordinateTransformations": [{"scale": [10.0, 10.0, 10.0], "type": "scale"}],
            },
            {
                "path": "1",
                "coordinateTransformations": [{"scale": [20.0, 20.0, 20.0], "type": "scale"}],
            },
        ],
        "name": "/",
        "axes": [
            {"name": "z", "type": "space", "unit": "angstrom"},
            {"name": "y", "type": "space", "unit": "angstrom"},
            {"name": "x", "type": "space", "unit": "angstrom"},
        ],
    }

    assert [multiscale_dataset["path"] for multiscale_dataset in multiscale["datasets"]] == ["0", "1"]
    for level, expected in enumerate(writer_pyramid.values()):
        array = group[str(level)]
        assert array.chunks == (2, 2, 2)
        assert array.shards == expected.shape
        assert tuple(math.ceil(size / shard) for size, shard in zip(array.shape, array.shards, strict=True)) == (
            1,
            1,
            1,
        )
        assert array.metadata.zarr_format == 3
        assert array.metadata.dimension_names == ("z", "y", "x")
        assert array.metadata.chunk_key_encoding.to_dict() == {"name": "v2", "configuration": {"separator": "/"}}
        np.testing.assert_array_equal(array[:], expected)

    assert (path / "0" / "0" / "0" / "0").is_file()


def _file_contents(path):
    return {item.relative_to(path): item.read_bytes() for item in path.rglob("*") if item.is_file()}


def test_writer_treats_none_metadata_as_omitted(tmp_path, writer_pyramid):
    path = str(tmp_path / "metadata.zarr")
    write_ome_zarr_3d(path, writer_pyramid, metadata=None)

    group = zarr.open_group(path, mode="r")
    assert "metadata" not in group.attrs["ome"]["multiscales"][0]


def test_writer_preserves_explicit_metadata_mapping(tmp_path, writer_pyramid):
    path = str(tmp_path / "metadata.zarr")
    metadata = {"source": "golden-test"}

    write_ome_zarr_3d(path, writer_pyramid, metadata=metadata)

    group = zarr.open_group(path, mode="r")
    Image.from_zarr(group)
    assert group.attrs["ome"]["multiscales"][0]["metadata"] == metadata


@pytest.mark.parametrize("metadata", ["invalid", ["invalid"], 3])
def test_writer_rejects_non_mapping_metadata_before_materializing_store(tmp_path, writer_pyramid, metadata):
    path = tmp_path / "invalid-metadata.zarr"

    with pytest.raises(TypeError, match="mapping or None"):
        write_ome_zarr_3d(str(path), writer_pyramid, metadata=metadata)

    assert not path.exists()


def test_writer_preserves_default_chunk_shape(tmp_path, writer_pyramid):
    path = str(tmp_path / "default-chunks.zarr")

    write_ome_zarr_3d(path, writer_pyramid)

    group = zarr.open_group(path, mode="r")
    assert group["0"].chunks == DEFAULT_SPATIAL_CHUNKS
    assert group["1"].chunks == DEFAULT_SPATIAL_CHUNKS
    assert group["0"].shards == DEFAULT_SPATIAL_CHUNKS
    assert group["1"].shards == DEFAULT_SPATIAL_CHUNKS


@pytest.mark.parametrize(
    ("dtype", "codec_names"),
    [
        (np.dtype("bool"), ["bytes", "zstd"]),
        (np.dtype("int16"), ["bytes", "zstd"]),
        (np.dtype("float32"), ["bytes", "numcodecs.shuffle", "zstd"]),
        (np.dtype("float64"), ["bytes", "numcodecs.shuffle", "zstd"]),
    ],
)
def test_writer_uses_exact_dtype_specific_codec_pipeline(tmp_path, dtype, codec_names):
    values = np.arange(60).reshape(3, 4, 5).astype(dtype)
    write_ome_zarr_3d(str(tmp_path / "codecs.zarr"), {10.0: values}, chunk_size=(2, 3, 4))

    group = zarr.open_group(tmp_path / "codecs.zarr", mode="r")
    array = group[get_level_path(group, 0)]
    metadata = array.metadata.to_dict()
    sharding = metadata["codecs"][0]
    inner_codecs = sharding["configuration"]["codecs"]
    assert sharding["name"] == "sharding_indexed"
    assert [codec["name"] for codec in inner_codecs] == codec_names
    assert inner_codecs[-1]["configuration"]["level"] == 3
    assert "blosc" not in json.dumps(metadata).lower()
    if np.issubdtype(dtype, np.floating):
        assert inner_codecs[1]["configuration"] == {"elementsize": dtype.itemsize}
    np.testing.assert_array_equal(array[:], values)


@pytest.mark.parametrize(
    ("shape", "chunks", "expected_shards"),
    [
        ((3, 4, 5), (8, 8, 8), (8, 8, 8)),
        ((5, 7, 9), (2, 3, 4), (6, 9, 12)),
        ((4, 6, 8), (2, 3, 4), (4, 6, 8)),
    ],
)
@pytest.mark.parametrize("all_fill", [False, True])
def test_writer_round_trips_one_padded_shard(shape, chunks, expected_shards, all_fill, tmp_path):
    values = np.zeros(shape, dtype=np.uint16)
    if not all_fill:
        values.flat[-1] = 7
    write_ome_zarr_3d(str(tmp_path / "padded.zarr"), {10.0: values}, chunk_size=chunks)

    group = zarr.open_group(tmp_path / "padded.zarr", mode="r")
    array = group[get_level_path(group, 0)]
    assert array.chunks == chunks
    assert array.shards == expected_shards
    assert tuple(math.ceil(size / shard) for size, shard in zip(array.shape, array.shards, strict=True)) == (1, 1, 1)
    np.testing.assert_array_equal(array[:], values)


@pytest.mark.parametrize("chunks", [(0, 2, 2), (2, -1, 2), (2, 2), (2, 2, 2, 2), (True, 2, 2)])
def test_writer_rejects_invalid_chunks(tmp_path, chunks):
    with pytest.raises(ValueError, match="chunk_size"):
        write_ome_zarr_3d(str(tmp_path / "invalid.zarr"), {10.0: np.ones((2, 2, 2))}, chunk_size=chunks)


@pytest.mark.parametrize("dtype", ["complex64", "datetime64[D]", "S1"])
def test_writer_rejects_unsupported_dtypes_before_materializing_store(tmp_path, dtype):
    path = tmp_path / "unsupported.zarr"
    with pytest.raises(TypeError, match="does not support dtype"):
        write_ome_zarr_3d(str(path), {10.0: np.zeros((2, 2, 2), dtype=dtype)})
    assert not path.exists()


def test_padded_shard_shape_uses_chunk_aligned_ceiling():
    assert padded_shard_shape((100, 200, 300), (128, 128, 128)) == (128, 256, 384)


def test_writer_warns_above_recommended_shard_size(monkeypatch, tmp_path):
    monkeypatch.setattr(ome, "_SHARD_WARNING_BYTES", 1)
    with pytest.warns(UserWarning, match="recommended 5 GB"):
        write_ome_zarr_3d(str(tmp_path / "warning.zarr"), {10.0: np.ones((2, 2, 2), dtype=np.uint8)})


def test_writer_rejects_shards_at_array_standard_limit(monkeypatch, tmp_path):
    monkeypatch.setattr(ome, "_SHARD_LIMIT_BYTES", 1)
    with pytest.raises(ValueError, match="below 5 TB"):
        write_ome_zarr_3d(str(tmp_path / "too-large.zarr"), {10.0: np.ones((2, 2, 2), dtype=np.uint8)})


class _RecordingMemoryStore(MemoryStore):
    def __init__(self):
        super().__init__()
        self.written_keys = []

    async def set(self, key, value):
        self.written_keys.append(key)
        await super().set(key, value)


def test_complete_level_writes_its_remote_shard_once():
    store = _RecordingMemoryStore()
    values = np.arange(4 * 5 * 6, dtype=np.uint16).reshape(4, 5, 6)

    write_ome_zarr_3d(store, {10.0: values}, chunk_size=(2, 3, 4))

    assert store.written_keys.count("0/0/0/0") == 1


@pytest.mark.parametrize("target_kind", ["path", "store"])
def test_writer_converts_bare_v2_group_without_mixed_metadata(tmp_path, writer_pyramid, target_kind):
    path = tmp_path / "legacy-empty.zarr"
    zarr.group(store=LocalStore(path), zarr_format=2)
    target = str(path) if target_kind == "path" else LocalStore(path)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        write_ome_zarr_3d(target, {10.0: writer_pyramid[10.0]}, chunk_size=(2, 2, 2), overwrite=False)
        group = zarr.open_group(LocalStore(path), mode="r")

    assert group.metadata.zarr_format == 3
    assert not any("Both zarr.json" in str(warning.message) for warning in caught)
    assert not list(path.rglob(".zgroup"))
    assert not list(path.rglob(".zattrs"))


def test_writer_accepts_bare_v3_group_without_overwrite(tmp_path, writer_pyramid):
    path = tmp_path / "empty-v3.zarr"
    zarr.group(store=LocalStore(path), zarr_format=3)

    write_ome_zarr_3d(
        LocalStore(path),
        {10.0: writer_pyramid[10.0]},
        chunk_size=(2, 2, 2),
        overwrite=False,
    )

    group = zarr.open_group(LocalStore(path), mode="r")
    np.testing.assert_array_equal(group[get_level_path(group, 0)][:], writer_pyramid[10.0])


def test_writer_converts_bare_remote_v2_group_without_mixed_metadata(writer_pyramid):
    store = MemoryStore()
    zarr.group(store=store, zarr_format=2)

    write_ome_zarr_3d(
        store,
        {10.0: writer_pyramid[10.0]},
        chunk_size=(2, 2, 2),
        overwrite=False,
    )

    assert "zarr.json" in store._store_dict
    assert ".zgroup" not in store._store_dict
    assert ".zattrs" not in store._store_dict


@pytest.mark.parametrize("zarr_format", [2, 3])
def test_writer_refuses_populated_target_without_mutation(tmp_path, writer_pyramid, zarr_format):
    path = tmp_path / f"populated-v{zarr_format}.zarr"
    group = zarr.group(store=LocalStore(path), zarr_format=zarr_format)
    group.create_array("0", data=np.ones((2, 2, 2), dtype=np.uint8), chunks=(2, 2, 2))
    before = _file_contents(path)

    with pytest.raises(FileExistsError, match="not empty"):
        write_ome_zarr_3d(
            LocalStore(path),
            {10.0: writer_pyramid[10.0]},
            chunk_size=(2, 2, 2),
            overwrite=False,
        )

    assert _file_contents(path) == before


def test_writer_refuses_mixed_root_metadata_without_mutation(tmp_path, writer_pyramid):
    path = tmp_path / "mixed.zarr"
    zarr.group(store=LocalStore(path), zarr_format=2)
    (path / "zarr.json").write_text('{"zarr_format": 3, "node_type": "group", "attributes": {}}')
    before = _file_contents(path)

    with pytest.raises(FileExistsError, match="not empty"):
        write_ome_zarr_3d(
            LocalStore(path),
            {10.0: writer_pyramid[10.0]},
            chunk_size=(2, 2, 2),
            overwrite=False,
        )

    assert _file_contents(path) == before


@pytest.mark.parametrize(
    "writer",
    [
        add_tomogram,
        z_add_tomogram_mrc,
        _add_tomogram_zarr,
        add_features,
        _add_tomogram_tiff,
        _add_tomogram_em,
        add_tomogram_from_file,
    ],
)
def test_public_add_writer_defaults_use_128_cube_chunks(writer):
    assert inspect.signature(writer).parameters["chunks"].default == DEFAULT_SPATIAL_CHUNKS


def test_zarr_handler_uses_canonical_writer_contract(tmp_path, writer_pyramid):
    path = str(tmp_path / "handler.zarr")
    volume = writer_pyramid[10.0]

    ZarrVolumeHandler().write(path, volume, 10.0, chunks=(2, 2, 2))

    store = LocalStore(path)
    group = zarr.open_group(store, mode="r")
    assert group.metadata.zarr_format == 3
    assert group.attrs["ome"]["version"] == "0.5"
    assert group.attrs["ome"]["multiscales"][0]["datasets"][0]["path"] == "0"
    assert group["0"].metadata.dimension_names == ("z", "y", "x")
    np.testing.assert_array_equal(group["0"][:], volume)


def test_writer_replaces_deeper_v2_pyramid_without_orphaned_metadata(tmp_path, writer_pyramid):
    path = tmp_path / "legacy.zarr"
    legacy = zarr.group(store=LocalStore(path), zarr_format=2)
    legacy.create_array("0", data=np.ones((2, 2, 2)), chunks=(2, 2, 2))
    legacy.create_array("1", data=np.ones((1, 1, 1)), chunks=(1, 1, 1))
    legacy.create_array("2", data=np.ones((1, 1, 1)), chunks=(1, 1, 1))
    legacy.attrs["multiscales"] = [{"version": "0.4", "datasets": [{"path": str(i)} for i in range(3)]}]

    write_ome_zarr_3d(LocalStore(path), {10.0: writer_pyramid[10.0]}, chunk_size=(2, 2, 2))

    group = zarr.open_group(LocalStore(path), mode="r")
    assert group.metadata.zarr_format == 3
    assert set(group.array_keys()) == {"0"}
    assert set(group.attrs) == {"ome"}
    assert not list(path.rglob(".zgroup"))
    assert not list(path.rglob(".zarray"))
    assert not list(path.rglob(".zattrs"))
    assert not list(path.rglob(".zmetadata"))


def test_shared_helper_is_the_only_multiscales_metadata_writer_callsite():
    source_root = Path(__file__).parents[1] / "src" / "copick"
    callsites = []
    imports = []

    for source_path in source_root.rglob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        relative_path = source_path.relative_to(source_root)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "write_multiscales_metadata"
            ):
                callsites.append(relative_path)
            if (
                isinstance(node, ast.ImportFrom)
                and node.module == "ome_zarr.writer"
                and any(alias.name == "write_multiscales_metadata" for alias in node.names)
            ):
                imports.append(relative_path)

    assert callsites == [Path("util/ome.py")]
    assert imports == [Path("util/ome.py")]
