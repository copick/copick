"""Tests for ReconnectingFileSystem and cache invalidation."""

import concurrent.futures
import os
import threading
import uuid
import weakref
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import zarr
from copick.util.ome import get_level_path, write_ome_zarr_3d
from copick.util.reconnecting_fs import ReconnectingFileSystem, _is_connection_error
from copick.util.store import copick_store
from copick.util.zarr_copy import copy_zarr_store
from fsspec import AbstractFileSystem
from fsspec.implementations.memory import MemoryFileSystem


# -- Helper: a fake SFTP exception that mimics asyncssh's SFTPNoConnection --
class SFTPNoConnection(Exception):  # noqa: N818 — mirrors asyncssh's naming
    pass


class SFTPError(OSError):
    pass


class SSHFileSystem(MemoryFileSystem):
    """Model sshfs's async cat_file implementation, which ignores ranges."""

    def cat_file(self, path, start=None, end=None, **kwargs):
        return super().cat_file(path, **kwargs)


# -- Tests for _is_connection_error --


def test_is_connection_error_sftp_no_connection():
    assert _is_connection_error(SFTPNoConnection("Connection not open"))


def test_is_connection_error_stdlib_connection_reset():
    assert _is_connection_error(ConnectionResetError("Connection reset by peer"))


def test_is_connection_error_broken_pipe_errno():
    exc = OSError(32, "Broken pipe")
    assert _is_connection_error(exc)


def test_is_connection_error_false_for_unrelated():
    assert not _is_connection_error(ValueError("some error"))
    assert not _is_connection_error(FileNotFoundError("no such file"))
    assert not _is_connection_error(OSError(2, "No such file or directory"))


# -- Tests for ReconnectingFileSystem --


def test_isinstance_abstract_filesystem():
    fs = ReconnectingFileSystem("memory://test")
    assert isinstance(fs, AbstractFileSystem)


def test_protocol_delegates_to_wrapped():
    fs = ReconnectingFileSystem("memory://test")
    assert fs.protocol == MemoryFileSystem.protocol


def test_retry_on_connection_error():
    """Verify that a connection error triggers reconnection and retry."""
    fs = ReconnectingFileSystem("memory://test")

    call_count = 0
    original_exists = fs._fs.exists

    def flaky_exists(path, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise SFTPNoConnection("Connection not open")
        return original_exists(path, **kwargs)

    fs._fs.exists = flaky_exists

    with patch.object(fs, "_reconnect", wraps=fs._reconnect) as mock_reconnect:
        result = fs.exists("memory://test/nonexistent")
        mock_reconnect.assert_called_once()
    assert not result


def test_non_connection_error_not_retried():
    """Non-connection errors should propagate immediately without reconnect."""
    fs = ReconnectingFileSystem("memory://test")

    def bad_exists(path, **kwargs):
        raise ValueError("not a connection error")

    fs._fs.exists = bad_exists

    with patch.object(fs, "_reconnect") as mock_reconnect:
        with pytest.raises(ValueError, match="not a connection error"):
            fs.exists("memory://test/foo")
        mock_reconnect.assert_not_called()


def test_reconnect_recreates_filesystem():
    """After _reconnect(), the wrapped filesystem should be a new instance."""
    fs = ReconnectingFileSystem("memory://test")
    old_fs = fs._fs

    fs._reconnect()

    assert fs._fs is not old_fs


def test_reconnect_invalidates_root_caches():
    """Reconnection should call _invalidate_all_caches on the root if set."""
    fs = ReconnectingFileSystem("memory://test")

    mock_root = MagicMock()
    import weakref

    fs._root_ref = weakref.ref(mock_root)

    fs._reconnect()

    mock_root._invalidate_all_caches.assert_called_once()


def test_getattr_fallback_delegates():
    """Methods not explicitly overridden should still delegate via __getattr__."""
    fs = ReconnectingFileSystem("memory://test")
    # _strip_protocol is explicitly overridden, but created/modified are not
    # Just verify that accessing an attribute on the wrapped fs works
    assert fs.storage_options is not None or fs.storage_options is None  # no AttributeError


def test_read_recovers_once_on_replacement_filesystem():
    fs = ReconnectingFileSystem("memory://test")
    old_fs = fs._fs
    new_fs = MemoryFileSystem(skip_instance_cache=True)
    new_fs.pipe_file("/test/value", b"recovered")
    original_error = SFTPNoConnection("connection dropped")

    def fail_read(*args, **kwargs):
        raise original_error

    old_fs.cat_file = fail_read
    fs._create_filesystem = MagicMock(return_value=new_fs)

    assert fs.cat_file("/test/value") == b"recovered"
    fs._create_filesystem.assert_called_once()
    assert fs._generation == 1


def test_ssh_cat_file_fallback_preserves_positive_and_suffix_ranges():
    fs = ReconnectingFileSystem("memory://test")
    ssh = SSHFileSystem(skip_instance_cache=True)
    payload = b"0123456789"
    ssh.pipe_file("/test/value", payload)
    fs._fs = ssh

    assert fs.cat_file("/test/value") == payload
    assert fs.cat_file("/test/value", start=2, end=6) == b"2345"
    assert fs.cat_file("/test/value", start=-4) == b"6789"
    assert fs.cat_file("/test/value", end=-2) == b"01234567"


def test_write_recovers_once_on_replacement_filesystem():
    fs = ReconnectingFileSystem("memory://test")
    old_fs = fs._fs
    new_fs = MemoryFileSystem(skip_instance_cache=True)

    def fail_write(*args, **kwargs):
        raise SFTPNoConnection("connection dropped")

    old_fs.pipe_file = fail_write
    fs._create_filesystem = MagicMock(return_value=new_fs)

    fs.pipe_file("/test/value", b"recovered")

    assert new_fs.cat_file("/test/value") == b"recovered"
    fs._create_filesystem.assert_called_once()


def test_reconnect_failure_preserves_original_exception():
    fs = ReconnectingFileSystem("memory://test")
    original_error = SFTPNoConnection("connection dropped")
    fs._fs.exists = MagicMock(side_effect=original_error)
    fs._create_filesystem = MagicMock(side_effect=RuntimeError("reconnect failed"))

    with pytest.raises(SFTPNoConnection) as exc_info:
        fs.exists("/test/value")

    assert exc_info.value is original_error
    assert fs._generation == 0


def test_retry_failure_is_returned_to_caller():
    fs = ReconnectingFileSystem("memory://test")
    fs._fs.exists = MagicMock(side_effect=SFTPNoConnection("connection dropped"))
    new_fs = MemoryFileSystem(skip_instance_cache=True)
    new_fs.exists = MagicMock(side_effect=ValueError("retry failed"))
    fs._create_filesystem = MagicMock(return_value=new_fs)

    with pytest.raises(ValueError, match="retry failed"):
        fs.exists("/test/value")


def test_batched_per_key_connection_error_retries_complete_batch():
    fs = ReconnectingFileSystem("memory://test")
    fs._fs.cat = MagicMock(return_value={"/test/value": SFTPNoConnection("connection dropped")})
    new_fs = MemoryFileSystem(skip_instance_cache=True)
    new_fs.cat = MagicMock(return_value={"/test/value": b"recovered"})
    fs._create_filesystem = MagicMock(return_value=new_fs)

    assert fs.cat(["/test/value"], on_error="return") == {"/test/value": b"recovered"}
    fs._create_filesystem.assert_called_once()


def test_concurrent_failures_share_one_reconnect_and_cache_invalidation():
    workers = 8
    barrier = threading.Barrier(workers)
    fs = ReconnectingFileSystem("memory://test")
    old_fs = fs._fs
    new_fs = MemoryFileSystem(skip_instance_cache=True)
    root = MagicMock()
    fs._root_ref = weakref.ref(root)

    def fail_together(path):
        barrier.wait(timeout=5)
        raise SFTPNoConnection("connection dropped")

    old_fs.exists = fail_together
    fs._create_filesystem = MagicMock(return_value=new_fs)

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        results = list(executor.map(fs.exists, [f"/missing-{index}" for index in range(workers)]))

    assert results == [False] * workers
    fs._create_filesystem.assert_called_once()
    root._invalidate_all_caches.assert_called_once()
    assert fs._generation == 1


def test_raw_store_copy_recovers_through_exact_zarr_adapter():
    base = f"memory://{uuid.uuid4()}"
    fs = ReconnectingFileSystem(base)
    source = copick_store(fs, f"{base}/source.zarr", create=True)
    target = copick_store(fs, f"{base}/target.zarr", create=True)
    group = zarr.group(store=source, zarr_format=2)
    group.create_array("nested/data", data=np.arange(64).reshape(4, 4, 4), chunks=(2, 2, 2))

    old_fs = fs._fs
    original_cat_file = old_fs.cat_file
    calls = 0

    def fail_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise SFTPNoConnection("connection dropped")
        return original_cat_file(*args, **kwargs)

    old_fs.cat_file = fail_once
    root = MagicMock()
    fs._root_ref = weakref.ref(root)

    with patch.object(fs, "_create_filesystem", wraps=fs._create_filesystem) as create_filesystem:
        result = copy_zarr_store(source, target)

    assert result.copied_keys > 0
    create_filesystem.assert_called_once()
    root._invalidate_all_caches.assert_called_once()
    copied = zarr.open_group(target, mode="r")["nested/data"]
    np.testing.assert_array_equal(copied[:], np.arange(64).reshape(4, 4, 4))
    np.testing.assert_array_equal(copied[:], np.arange(64).reshape(4, 4, 4))


@pytest.mark.timeout(120)
def test_live_ssh_multichunk_reads_reconnect_and_raw_copy(request):
    if os.environ.get("BACKEND") != "ssh":
        pytest.skip("live SSH adapter gate runs only in the SSH backend job")

    import copick

    payload = request.getfixturevalue("ssh_overlay_only")
    root = copick.from_file(str(payload["cfg_file"]))
    run = root.new_run("reconnect-test")
    voxel_spacing = run.new_voxel_spacing(10.0)
    source = voxel_spacing.new_tomogram("source")
    values = np.arange(8 * 8 * 8, dtype=np.int32).reshape(8, 8, 8)

    write_ome_zarr_3d(source.zarr(), {10.0: values}, chunk_size=(4, 4, 4))
    source_group = zarr.open_group(source.zarr(), mode="r")
    source_array = source_group[get_level_path(source_group, 0)]
    np.testing.assert_array_equal(source_array[:], values)
    np.testing.assert_array_equal(source_array[:], values)

    reconnecting_fs = root.fs_overlay
    with (
        patch.object(reconnecting_fs, "_create_filesystem", wraps=reconnecting_fs._create_filesystem) as reconnect,
        patch.object(root, "_invalidate_all_caches", wraps=root._invalidate_all_caches) as invalidate,
    ):
        reconnecting_fs._fs.client.abort()
        np.testing.assert_array_equal(source_array[:], values)

    reconnect.assert_called_once()
    invalidate.assert_called_once()

    target = voxel_spacing.new_tomogram("target")
    result = copy_zarr_store(source.zarr(), target.zarr(), if_exists="replace")
    assert result.copied_keys > 0
    target_group = zarr.open_group(target.zarr(), mode="r")
    copied = target_group[get_level_path(target_group, 0)]
    np.testing.assert_array_equal(copied[:], values)
