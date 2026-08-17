"""Golden contracts for the centralized OME-Zarr 0.5 / Zarr v3 writer."""

import ast
import json
from pathlib import Path

import numpy as np
import pytest
import zarr
from copick.util.handlers.volume.zarr import ZarrVolumeHandler
from copick.util.ome import write_ome_zarr_3d
from ome_zarr_models.v05.image import Image
from zarr.storage import LocalStore


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
        assert array.metadata.zarr_format == 3
        assert array.metadata.dimension_names == ("z", "y", "x")
        np.testing.assert_array_equal(array[:], expected)


@pytest.mark.parametrize("metadata", [None, {"source": "golden-test"}])
def test_writer_preserves_explicit_metadata_value(tmp_path, writer_pyramid, metadata):
    path = str(tmp_path / "metadata.zarr")
    write_ome_zarr_3d(path, writer_pyramid, metadata=metadata)

    group = zarr.open_group(path, mode="r")
    assert group.attrs["ome"]["multiscales"][0]["metadata"] == metadata


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
