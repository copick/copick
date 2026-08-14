"""Reconnecting filesystem wrapper for automatic recovery from broken connections.

Provides a ``ReconnectingFileSystem`` that wraps any fsspec ``AbstractFileSystem`` and
transparently retries operations when the underlying connection (e.g. SSH tunnel) drops.
"""

import logging
import threading
import weakref
from functools import wraps
from typing import Any, Dict, Mapping, Optional

import fsspec
from fsspec import AbstractFileSystem

logger = logging.getLogger(__name__)

# Exception class names that indicate a stale/broken connection.
# Checked by class name through the MRO to avoid hard dependencies on asyncssh etc.
_CONNECTION_ERROR_NAMES = frozenset(
    {
        "SFTPNoConnection",
        "SFTPError",
        "SFTPConnectionLost",
        "ConnectionLost",
        "DisconnectError",
        "BrokenPipeError",
        "ConnectionResetError",
        "ConnectionRefusedError",
        "ConnectionAbortedError",
    },
)


def _is_connection_error(exc: BaseException) -> bool:
    """Check if an exception indicates a broken or stale connection."""
    for cls in type(exc).__mro__:
        if cls.__name__ in _CONNECTION_ERROR_NAMES:
            return True
    # OSError with errno for broken pipe (32) or connection reset (104)
    return isinstance(exc, OSError) and exc.errno in (32, 104)


def _make_retry_method(method_name: str):
    """Create a method that delegates to the wrapped filesystem with retry on connection error."""

    def method(self, *args, **kwargs):
        return self._call_with_retry(method_name, *args, **kwargs)

    method.__name__ = method_name
    method.__qualname__ = f"ReconnectingFileSystem.{method_name}"
    return method


class ReconnectingFileSystem(AbstractFileSystem):
    """A filesystem wrapper that automatically reconnects on connection errors.

    Subclasses ``AbstractFileSystem`` so that ``isinstance`` checks pass. Delegates all
    operations to a wrapped filesystem created from a URL and fs_args. When a connection
    error is detected (e.g. ``SFTPNoConnection``), the wrapped filesystem is recreated
    from the stored configuration and the operation is retried once.

    Attributes:
        _url: The URL used to create the wrapped filesystem.
        _fs_args: The arguments used to create the wrapped filesystem.
        _fs: The current wrapped filesystem instance.
        _root_ref: Weak reference to the CopickRoot for cache invalidation.
    """

    protocol = "reconnecting"
    cachable = False

    def __init__(self, url: str, fs_args: Optional[Dict[str, Any]] = None, **kwargs):
        super().__init__(skip_instance_cache=True, **kwargs)
        self._url = url
        self._fs_args = fs_args or {}
        self._reconnect_lock = threading.Lock()
        self._generation = 0
        self._fs: AbstractFileSystem = fsspec.core.url_to_fs(url, **self._fs_args)[0]
        self.protocol = self._fs.protocol
        self._root_ref: Optional[weakref.ref] = None

    def _snapshot(self) -> tuple[AbstractFileSystem, int]:
        """Capture the current filesystem and connection generation."""
        with self._reconnect_lock:
            return self._fs, self._generation

    def _create_filesystem(self) -> AbstractFileSystem:
        return fsspec.core.url_to_fs(self._url, **self._fs_args)[0]

    def _invalidate_root_caches(self) -> None:
        if self._root_ref is not None:
            root = self._root_ref()
            if root is not None:
                root._invalidate_all_caches()

    def _reconnect(self, expected_generation: Optional[int] = None) -> AbstractFileSystem:
        """Recreate the underlying filesystem from stored configuration.

        Clears fsspec's instance cache for the wrapped filesystem class, creates a fresh
        filesystem instance, and invalidates all copick data caches (if a root reference
        is set) so stale objects are re-queried on next access.

        When ``expected_generation`` is supplied, another caller's newer connection is
        reused instead of being replaced again.  Calls without it are explicit user
        reconnect requests and always replace the filesystem.
        """
        with self._reconnect_lock:
            if expected_generation is not None and self._generation != expected_generation:
                return self._fs

            logger.info("Reconnecting filesystem for %s", self._url)
            type(self._fs).clear_instance_cache()
            replacement = self._create_filesystem()
            self._fs = replacement
            self.protocol = replacement.protocol
            self._generation += 1
            self._invalidate_root_caches()
            return replacement

    @staticmethod
    def _result_has_connection_error(result: Any) -> bool:
        return isinstance(result, Mapping) and any(
            isinstance(value, BaseException) and _is_connection_error(value) for value in result.values()
        )

    def _call_with_retry(self, method_name: str, *args, **kwargs):
        filesystem, generation = self._snapshot()
        try:
            result = getattr(filesystem, method_name)(*args, **kwargs)
        except Exception as original_exc:
            if not _is_connection_error(original_exc):
                raise
            logger.warning("Connection error during %s, reconnecting: %s", method_name, original_exc)
            try:
                filesystem = self._reconnect(expected_generation=generation)
            except Exception:
                raise original_exc from None
            return getattr(filesystem, method_name)(*args, **kwargs)

        if self._result_has_connection_error(result):
            logger.warning("Connection error in batched %s result, reconnecting", method_name)
            try:
                filesystem = self._reconnect(expected_generation=generation)
            except Exception:
                return result
            return getattr(filesystem, method_name)(*args, **kwargs)
        return result

    # -- Explicitly overridden methods (used by copick, Zarr's fsspec adapter, and fsspec FSMap) --
    # Each delegates to self._fs with automatic retry on connection error.

    # Core directory/file info methods
    ls = _make_retry_method("ls")
    info = _make_retry_method("info")
    glob = _make_retry_method("glob")
    find = _make_retry_method("find")
    du = _make_retry_method("du")
    exists = _make_retry_method("exists")
    isdir = _make_retry_method("isdir")
    isfile = _make_retry_method("isfile")

    # File read/write methods
    cat = _make_retry_method("cat")
    cat_file = _make_retry_method("cat_file")
    pipe = _make_retry_method("pipe")
    pipe_file = _make_retry_method("pipe_file")
    open = _make_retry_method("open")

    # Directory creation methods
    mkdir = _make_retry_method("mkdir")
    mkdirs = _make_retry_method("mkdirs")
    makedirs = _make_retry_method("makedirs")

    # File/directory removal methods
    rm = _make_retry_method("rm")
    rm_file = _make_retry_method("rm_file")
    rmdir = _make_retry_method("rmdir")

    # Other methods used by zarr/fsspec
    touch = _make_retry_method("touch")
    get_mapper = _make_retry_method("get_mapper")

    # Cache management — delegate without retry (not I/O)
    def invalidate_cache(self, path=None):
        filesystem, _ = self._snapshot()
        return filesystem.invalidate_cache(path)

    # Protocol/path utilities — delegate to the wrapped filesystem class
    def _strip_protocol(self, path):
        filesystem, _ = self._snapshot()
        return filesystem._strip_protocol(path)

    @staticmethod
    def _parent(path):
        # Delegate to the general AbstractFileSystem implementation
        return AbstractFileSystem._parent(path)

    # -- Fallback for any method not explicitly overridden --

    def __getattr__(self, name):
        """Delegate attribute access to the wrapped filesystem with retry for callables."""
        filesystem, _ = self._snapshot()
        attr = getattr(filesystem, name)
        if not callable(attr):
            return attr

        @wraps(attr)
        def wrapper(*args, **kwargs):
            return self._call_with_retry(name, *args, **kwargs)

        return wrapper
