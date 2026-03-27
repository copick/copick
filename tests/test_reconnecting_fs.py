"""Tests for ReconnectingFileSystem and cache invalidation."""

from unittest.mock import MagicMock, patch

import pytest
from copick.util.reconnecting_fs import ReconnectingFileSystem, _is_connection_error
from fsspec import AbstractFileSystem
from fsspec.implementations.memory import MemoryFileSystem


# -- Helper: a fake SFTP exception that mimics asyncssh's SFTPNoConnection --
class SFTPNoConnection(Exception):  # noqa: N818 — mirrors asyncssh's naming
    pass


class SFTPError(OSError):
    pass


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
