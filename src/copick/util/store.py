"""Protocol-aware Zarr store construction.

Copick keeps configured fsspec filesystem objects alive because they may carry
credentials, endpoint settings, or reconnect behavior which cannot safely be
reconstructed from serialized configuration.  Zarr 3 requires asynchronous
filesystems for remote stores, so synchronous fsspec instances are adapted in
place with :class:`AsyncFileSystemWrapper`.
"""

from fsspec import AbstractFileSystem
from fsspec.implementations.asyn_wrapper import AsyncFileSystemWrapper
from fsspec.implementations.local import LocalFileSystem
from zarr.abc.store import Store
from zarr.storage import FsspecStore, LocalStore


def copick_store(
    fs: AbstractFileSystem,
    path: str,
    *,
    read_only: bool = False,
    create: bool = False,
) -> Store:
    """Return a Zarr 3 store backed by an already-configured filesystem.

    Args:
        fs: Configured synchronous or asynchronous fsspec filesystem.
        path: Store path, with or without a protocol prefix.
        read_only: Whether writes through the returned store are forbidden.
        create: Whether this call represents creation of a new entity store.
            Store construction remains lazy; only the parent directory is
            materialized here so nested writes work on all supported backends.

    Returns:
        A local or fsspec-backed Zarr 3 store.
    """
    normalized_path = fs._strip_protocol(path).rstrip("/")
    if create:
        parent = fs._parent(normalized_path)
        if parent:
            fs.makedirs(parent, exist_ok=True)

    configured_fs = getattr(fs, "_fs", fs)
    if isinstance(configured_fs, LocalFileSystem):
        return LocalStore(normalized_path, read_only=read_only)

    async_fs = fs if getattr(fs, "asynchronous", False) else AsyncFileSystemWrapper(fs=fs, asynchronous=True)
    return FsspecStore(fs=async_fs, path=normalized_path, read_only=read_only)
