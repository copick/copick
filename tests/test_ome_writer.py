"""Golden contracts for the centralized OME-Zarr 0.4 / Zarr v2 writer."""

import ast
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import zarr
from copick.util.handlers.volume.zarr import ZarrVolumeHandler
from copick.util.ome import write_ome_zarr_3d


@pytest.fixture
def writer_pyramid():
    return {
        10.0: np.arange(64, dtype=np.float32).reshape(4, 4, 4),
        20.0: np.full((2, 2, 2), 7, dtype=np.float32),
    }


@pytest.mark.parametrize("target_kind", ["path", "store"])
def test_writer_preserves_v2_golden_contract(tmp_path, writer_pyramid, target_kind):
    path = tmp_path / f"{target_kind}.zarr"
    target = str(path) if target_kind == "path" else zarr.DirectoryStore(str(path))

    write_ome_zarr_3d(target, writer_pyramid, chunk_size=(2, 2, 2))

    store = zarr.DirectoryStore(str(path))
    group = zarr.open_group(store, mode="r")
    assert json.loads(store[".zgroup"])["zarr_format"] == 2

    multiscale = group.attrs["multiscales"][0]
    assert multiscale == {
        "version": "0.4",
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
        "metadata": {},
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
        assert array.compressor.get_config() == {
            "id": "blosc",
            "cname": "lz4",
            "clevel": 5,
            "shuffle": 1,
            "blocksize": 0,
        }
        assert json.loads(store[f"{level}/.zarray"])["dimension_separator"] == "/"
        np.testing.assert_array_equal(array[:], expected)

    assert "0/0/0/0" in store
    assert "0/0.0.0" not in store
    assert hashlib.sha256(store["0/0/0/0"]).hexdigest() == (
        "c7a26c789036035c6e7ab41ca5f84ead654aca7654df2321229d3b9a688e8a16"
    )


@pytest.mark.parametrize("metadata", [None, {"source": "golden-test"}])
def test_writer_preserves_explicit_metadata_value(tmp_path, writer_pyramid, metadata):
    path = str(tmp_path / "metadata.zarr")
    write_ome_zarr_3d(path, writer_pyramid, metadata=metadata)

    group = zarr.open_group(path, mode="r")
    assert group.attrs["multiscales"][0]["metadata"] == metadata


def test_writer_preserves_default_chunk_shape(tmp_path, writer_pyramid):
    path = str(tmp_path / "default-chunks.zarr")

    write_ome_zarr_3d(path, writer_pyramid)

    group = zarr.open_group(path, mode="r")
    assert group["0"].chunks == (256, 256, 256)
    assert group["1"].chunks == (256, 256, 256)


def test_zarr_handler_uses_canonical_writer_contract(tmp_path, writer_pyramid):
    path = str(tmp_path / "handler.zarr")
    volume = writer_pyramid[10.0]

    ZarrVolumeHandler().write(path, volume, 10.0, chunks=(2, 2, 2))

    store = zarr.DirectoryStore(path)
    group = zarr.open_group(store, mode="r")
    assert group.attrs["multiscales"][0]["version"] == "0.4"
    assert group.attrs["multiscales"][0]["datasets"][0]["path"] == "0"
    assert "0/0/0/0" in store
    np.testing.assert_array_equal(group["0"][:], volume)


def test_shared_helper_is_the_only_write_multiscale_callsite():
    source_root = Path(__file__).parents[1] / "src" / "copick"
    callsites = []
    imports = []

    for source_path in source_root.rglob("*.py"):
        tree = ast.parse(source_path.read_text())
        relative_path = source_path.relative_to(source_root)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "write_multiscale":
                callsites.append(relative_path)
            if (
                isinstance(node, ast.ImportFrom)
                and node.module == "ome_zarr.writer"
                and any(alias.name == "write_multiscale" for alias in node.names)
            ):
                imports.append(relative_path)

    assert callsites == [Path("util/ome.py")]
    assert imports == [Path("util/ome.py")]
