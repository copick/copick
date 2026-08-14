"""Tests for protocol-aware Zarr 3 store construction."""

import fsspec
import numpy as np
import pytest
import zarr
from fsspec.implementations.asyn_wrapper import AsyncFileSystemWrapper
from zarr.storage import FsspecStore, LocalStore

from copick.util.reconnecting_fs import ReconnectingFileSystem
from copick.util.store import copick_store


def test_local_store_uses_local_store_and_creates_parent(tmp_path):
    fs = ReconnectingFileSystem(f"file://{tmp_path}")
    path = f"file://{tmp_path}/nested/volume.zarr"

    store = copick_store(fs, path, create=True)

    assert isinstance(store, LocalStore)
    assert (tmp_path / "nested").is_dir()
    assert not (tmp_path / "nested" / "volume.zarr").exists()


def test_remote_store_reuses_configured_filesystem_and_strips_protocol():
    fs = fsspec.filesystem("memory")
    store = copick_store(fs, "memory://bucket/volume.zarr", create=True)

    assert isinstance(store, FsspecStore)
    assert store.path == "/bucket/volume.zarr"
    assert isinstance(store.fs, AsyncFileSystemWrapper)
    assert store.fs.sync_fs is fs

    group = zarr.group(store=store, zarr_format=2)
    group.create_array("0", data=np.arange(4))

    reopened = zarr.open_group(store, mode="r")
    assert list(reopened.array_keys()) == ["0"]
    np.testing.assert_array_equal(reopened["0"][:], np.arange(4))


def test_read_only_store_rejects_writes(tmp_path):
    writable = copick_store(fsspec.filesystem("file"), str(tmp_path / "volume.zarr"), create=True)
    zarr.group(store=writable, zarr_format=2)

    read_only = copick_store(fsspec.filesystem("file"), str(tmp_path / "volume.zarr"), read_only=True)
    with pytest.raises(ValueError, match="read-only"):
        zarr.open_group(read_only, mode="a")
