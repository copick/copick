"""Contract tests for object density-map stores and registration."""

import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from types import SimpleNamespace

import fsspec
import numpy as np
import pytest
from copick.impl.cryoet_data_portal import CopickObjectCDP
from copick.impl.filesystem import CopickConfigFSSpec, CopickObjectFSSpec, CopickRootFSSpec
from copick.impl.mlcroissant import CopickObjectMLC
from copick.models import CopickObject, PickableObject
from copick.util.ome import zarr_root_exists


def _metadata(path, name=".zgroup"):
    path.mkdir(parents=True, exist_ok=True)
    payload = {"zarr_format": 2} if name == ".zgroup" else {"zarr_format": 3, "node_type": "group"}
    (path / name).write_text(json.dumps(payload))


def _filesystem_root(tmp_path):
    static = tmp_path / "static"
    overlay = tmp_path / "overlay"
    static.mkdir()
    overlay.mkdir()
    config = CopickConfigFSSpec(
        pickable_objects=[
            PickableObject(name="particle", is_particle=True),
            PickableObject(name="surface", is_particle=False),
        ],
        static_root=f"local://{static}",
        static_fs_args={"auto_mkdir": False},
        overlay_root=f"local://{overlay}",
        overlay_fs_args={"auto_mkdir": True},
    )
    return CopickRootFSSpec(config), static, overlay


def test_empty_store_directory_is_not_a_density_map(tmp_path):
    root, static, overlay = _filesystem_root(tmp_path)
    (static / "Objects" / "particle.zarr").mkdir(parents=True)

    particle = root.get_object("particle")
    assert particle.read_only is False
    assert particle.has_density_map() is False
    assert particle.zarr() is not None
    assert particle.has_density_map() is False
    assert (overlay / "Objects").is_dir()
    assert not (overlay / "Objects" / "particle.zarr").exists()

    surface = root.get_object("surface")
    assert surface.has_density_map() is False
    assert surface.zarr() is None


@pytest.mark.parametrize("root_metadata", [".zgroup", "zarr.json"])
def test_static_root_metadata_selects_read_only_store(tmp_path, root_metadata):
    root, static, overlay = _filesystem_root(tmp_path)
    _metadata(static / "Objects" / "particle.zarr", root_metadata)
    (overlay / "Objects" / "particle.zarr").mkdir(parents=True)

    particle = root.get_object("particle")
    assert particle.read_only is True
    assert particle.has_density_map() is True
    assert particle.zarr() is not None


def test_overlay_root_metadata_selects_writable_store(tmp_path):
    root, static, overlay = _filesystem_root(tmp_path)
    _metadata(static / "Objects" / "particle.zarr")
    _metadata(overlay / "Objects" / "particle.zarr")

    particle = root.get_object("particle")
    assert particle.read_only is False
    assert particle.has_density_map() is True
    assert particle.zarr() is not None


def test_absent_read_only_density_map_returns_none(tmp_path):
    root, static, _ = _filesystem_root(tmp_path)
    (static / "Objects" / "particle.zarr").mkdir(parents=True)
    particle = CopickObjectFSSpec(root, root.config.pickable_objects[0], read_only=True)

    assert particle.has_density_map() is False
    assert particle.zarr() is None


class _QuietHTTPHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


def test_http_zarr_root_metadata_is_detected(tmp_path):
    _metadata(tmp_path / "v2.zarr", ".zgroup")
    _metadata(tmp_path / "v3.zarr", "zarr.json")
    (tmp_path / "empty.zarr").mkdir()

    handler = partial(_QuietHTTPHandler, directory=str(tmp_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        fs = fsspec.filesystem("http")
        base_url = f"http://127.0.0.1:{server.server_port}"

        assert fs.exists(f"{base_url}/empty.zarr") is True
        assert zarr_root_exists(fs, f"{base_url}/empty.zarr") is False
        assert zarr_root_exists(fs, f"{base_url}/v2.zarr") is True
        assert zarr_root_exists(fs, f"{base_url}/v3.zarr") is True
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


class _ObjectWithoutStore(CopickObject):
    def zarr(self):
        return None

    def has_density_map(self):
        return False


def test_object_writes_reject_missing_destination():
    obj = _ObjectWithoutStore(SimpleNamespace(), PickableObject(name="particle", is_particle=True))
    data = np.ones((2, 2, 2), dtype=np.float32)

    with pytest.raises(ValueError, match="no writable Zarr store"):
        obj.from_numpy(data, voxel_size=10.0)
    with pytest.raises(ValueError, match="no writable Zarr store"):
        obj.set_region(data)


def test_cdp_object_write_uses_absent_overlay_as_destination(tmp_path):
    fs = fsspec.filesystem("file", auto_mkdir=True)
    root = SimpleNamespace(root_overlay=str(tmp_path), fs_overlay=fs)
    obj = CopickObjectCDP(root, PickableObject(name="particle", is_particle=True), read_only=False)
    data = np.arange(27, dtype=np.float32).reshape(3, 3, 3)

    assert obj.has_density_map() is False
    assert obj.zarr() is not None
    obj.from_numpy(data, voxel_size=10.0)

    assert obj.has_density_map() is True
    np.testing.assert_array_equal(obj.numpy(), data)


class _CroissantIndex:
    def __init__(self, base_url):
        self.base_url = base_url
        self.static_fs_args = {}
        self.objects = []
        self.added_rows = []

    def add_row(self, record_set, row):
        assert record_set == "copick/objects"
        self.added_rows.append(row)
        self.objects.append(row)

    def remove_row(self, record_set, row):
        self.objects.remove(row)


def _mlc_object(tmp_path):
    index = _CroissantIndex(str(tmp_path))
    root = SimpleNamespace(
        index=index,
        mode="A",
        overlay_base_url=None,
        fs_overlay=fsspec.filesystem("file", auto_mkdir=True),
    )
    obj = CopickObjectMLC(root, PickableObject(name="particle", is_particle=True), read_only=False)
    return obj, index


def test_mode_a_object_registration_follows_first_successful_write(tmp_path):
    obj, index = _mlc_object(tmp_path)
    data = np.ones((3, 3, 3), dtype=np.float32)

    assert obj.zarr() is not None
    assert index.added_rows == []

    obj.from_numpy(data, voxel_size=10.0)
    obj.from_numpy(data * 2, voxel_size=10.0)

    assert index.added_rows == [{"name": "particle", "url": "Objects/particle.zarr"}]


def test_mode_a_object_registration_is_skipped_after_failed_write(tmp_path, monkeypatch):
    obj, index = _mlc_object(tmp_path)

    def fail_write(*args, **kwargs):
        raise RuntimeError("write failed")

    monkeypatch.setattr("copick.models.write_ome_zarr_3d", fail_write)
    with pytest.raises(RuntimeError, match="write failed"):
        obj.from_numpy(np.ones((2, 2, 2), dtype=np.float32), voxel_size=10.0)

    assert index.added_rows == []
    assert obj.has_density_map() is False
