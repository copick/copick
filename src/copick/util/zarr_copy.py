"""Format-preserving whole-store Zarr copy support.

This module contains the only bridge from copick's synchronous APIs to Zarr
3's asynchronous store protocol.  ``zarr.core.sync.sync`` is private because
Zarr currently exposes no public synchronous store-key bridge; keeping the
import here makes that compatibility risk explicit and easy to test.
"""

import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from zarr.abc.store import Store
from zarr.core.buffer import default_buffer_prototype
from zarr.core.sync import sync as _zarr_sync
from zarr.storage import FsspecStore, LocalStore

IfExists = Literal["raise", "replace", "skip"]
_VALID_IF_EXISTS = frozenset({"raise", "replace", "skip"})


@dataclass(frozen=True)
class RawCopyResult:
    """Counts returned by :func:`copy_zarr_store`."""

    copied_keys: int
    copied_bytes: int
    skipped_keys: int = 0


async def _list_keys(store: Store) -> list[str]:
    return sorted([key async for key in store.list()])


async def _get_bytes(store: Store, key: str) -> bytes:
    value = await store.get(key, default_buffer_prototype())
    if value is None:
        raise FileNotFoundError(f"Zarr store key disappeared during copy: {key}")
    return value.to_bytes()


def _root_metadata_key(keys: list[str]) -> str | None:
    for key in (".zgroup", ".zarray", "zarr.json"):
        if key in keys:
            return key
    return None


def _validate_root_metadata(store: Store, keys: list[str]) -> None:
    metadata_key = _root_metadata_key(keys)
    if metadata_key is None:
        raise ValueError("Source is not a Zarr store: valid root metadata was not found")

    try:
        metadata = json.loads(_zarr_sync(_get_bytes(store, metadata_key)))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Source has invalid Zarr root metadata in {metadata_key}") from exc

    expected_format = 3 if metadata_key == "zarr.json" else 2
    if metadata.get("zarr_format") != expected_format:
        raise ValueError(f"Source has invalid Zarr root metadata in {metadata_key}")
    if metadata_key == "zarr.json" and metadata.get("node_type") not in {"group", "array"}:
        raise ValueError("Source zarr.json root metadata has no valid node_type")


def _same_store(source: Store, target: Store) -> bool:
    if source is target:
        return True
    if isinstance(source, LocalStore) and isinstance(target, LocalStore):
        return Path(source.root).resolve() == Path(target.root).resolve()
    if isinstance(source, FsspecStore) and isinstance(target, FsspecStore):
        source_fs = getattr(source.fs, "sync_fs", source.fs)
        target_fs = getattr(target.fs, "sync_fs", target.fs)
        return source_fs is target_fs and source.path == target.path
    return False


async def _copy_keys(source: Store, target: Store, keys: list[str]) -> RawCopyResult:
    copied_bytes = 0
    for key in keys:
        value = await source.get(key, default_buffer_prototype())
        if value is None:
            raise FileNotFoundError(f"Zarr store key disappeared during copy: {key}")
        await target.set(key, value)
        copied_bytes += len(value)
    return RawCopyResult(copied_keys=len(keys), copied_bytes=copied_bytes)


async def _verify_keys(source: Store, target: Store, keys: list[str]) -> None:
    target_keys = await _list_keys(target)
    if target_keys != keys:
        raise IOError("Copied Zarr store key set does not match the source")
    for key in keys:
        source_value = await source.get(key, default_buffer_prototype())
        target_value = await target.get(key, default_buffer_prototype())
        if source_value is None or target_value is None or source_value.to_bytes() != target_value.to_bytes():
            raise IOError(f"Copied Zarr store key does not match the source: {key}")


def _copy_local_replacement(source: Store, target: LocalStore, keys: list[str]) -> RawCopyResult:
    target_root = Path(target.root)
    target_root.parent.mkdir(parents=True, exist_ok=True)
    stage_root = Path(tempfile.mkdtemp(prefix=f".{target_root.name}.copick-stage-", dir=target_root.parent))
    backup_root: Path | None = None
    try:
        stage_store = LocalStore(stage_root)
        result = _zarr_sync(_copy_keys(source, stage_store, keys))
        _zarr_sync(_verify_keys(source, stage_store, keys))

        if target_root.exists():
            backup_root = Path(tempfile.mkdtemp(prefix=f".{target_root.name}.copick-backup-", dir=target_root.parent))
            backup_root.rmdir()
            os.replace(target_root, backup_root)
        try:
            os.replace(stage_root, target_root)
        except Exception:
            if backup_root is not None and backup_root.exists():
                os.replace(backup_root, target_root)
            raise
        if backup_root is not None:
            shutil.rmtree(backup_root)
        return result
    finally:
        if stage_root.exists():
            shutil.rmtree(stage_root)
        if backup_root is not None and backup_root.exists():
            shutil.rmtree(backup_root)


def copy_zarr_store(source: Store, target: Store, *, if_exists: IfExists = "raise") -> RawCopyResult:
    """Copy every raw key from one Zarr store to another.

    The operation never decodes array data, so Zarr format, metadata, chunk or
    shard layout, codec payloads, and non-Zarr keys are preserved byte for
    byte.  Local replacement is staged and verified before a same-filesystem
    directory swap.  Other backends are validated and fully listed first, but
    replacement is necessarily non-atomic: the target is cleared once and
    then populated key by key.

    Args:
        source: Source Zarr 3 store.
        target: Writable destination Zarr 3 store.
        if_exists: ``raise``, ``replace``, or ``skip``.

    Returns:
        Copied key, byte, and skipped-key counts.
    """
    if if_exists not in _VALID_IF_EXISTS:
        raise ValueError(f"if_exists must be one of {sorted(_VALID_IF_EXISTS)}, got {if_exists!r}")
    if _same_store(source, target):
        raise ValueError("Source and target Zarr stores must be different")

    source_keys = _zarr_sync(_list_keys(source))
    _validate_root_metadata(source, source_keys)
    if not source_keys:
        raise ValueError("Source Zarr store contains no keys")

    target_keys = _zarr_sync(_list_keys(target))
    if target_keys and if_exists == "raise":
        raise FileExistsError("Target Zarr store is not empty")
    if target_keys and if_exists == "skip":
        return RawCopyResult(copied_keys=0, copied_bytes=0, skipped_keys=len(source_keys))

    if if_exists == "replace" and isinstance(target, LocalStore):
        return _copy_local_replacement(source, target, source_keys)

    if target_keys and if_exists == "replace":
        _zarr_sync(target.delete_dir(""))

    result = _zarr_sync(_copy_keys(source, target, source_keys))
    if result.copied_keys == 0:
        raise IOError("Zarr store copy unexpectedly copied zero keys")
    return result


def verify_zarr_store_copy(source: Store, target: Store) -> None:
    """Verify that a copied target has exactly the source's raw keys and bytes."""
    source_keys = _zarr_sync(_list_keys(source))
    target_keys = _zarr_sync(_list_keys(target))
    _validate_root_metadata(source, source_keys)
    _validate_root_metadata(target, target_keys)
    _zarr_sync(_verify_keys(source, target, source_keys))
