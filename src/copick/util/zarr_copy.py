"""Format-preserving whole-store Zarr copy support.

This module contains the only bridge from copick's synchronous APIs to Zarr
3's asynchronous store protocol.  ``zarr.core.sync.sync`` is private because
Zarr currently exposes no public synchronous store-key bridge; keeping the
import here makes that compatibility risk explicit and easy to test.
"""

import hashlib
import json
import os
import posixpath
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
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


@dataclass(frozen=True)
class _KeyDigest:
    size: int
    sha256: bytes


@dataclass(frozen=True)
class _CopyOutcome:
    result: RawCopyResult
    manifest: dict[str, _KeyDigest]


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


def _path_parts(path: str) -> tuple[str, ...]:
    normalized = posixpath.normpath(f"/{path.strip('/')}")
    return PurePosixPath(normalized).parts


def _paths_overlap(source_path: str, target_path: str) -> bool:
    source_parts = _path_parts(source_path)
    target_parts = _path_parts(target_path)
    return source_parts == target_parts[: len(source_parts)] or target_parts == source_parts[: len(target_parts)]


def _filesystem_namespace(filesystem) -> tuple[tuple[str, ...], object, object]:
    protocol = getattr(filesystem, "protocol", "")
    protocols = tuple(sorted(protocol if isinstance(protocol, (tuple, list)) else (protocol,)))
    storage_options = getattr(filesystem, "storage_options", {})
    client_options = getattr(filesystem, "client_kwargs", {})
    endpoint = (
        getattr(filesystem, "endpoint_url", None)
        or client_options.get("endpoint_url")
        or storage_options.get("endpoint_url")
        or storage_options.get("host")
        or getattr(filesystem, "host", None)
    )
    port = storage_options.get("port") or getattr(filesystem, "port", None)
    return protocols, endpoint, port


def _same_filesystem_namespace(source_fs, target_fs) -> bool:
    if source_fs is target_fs:
        return True
    source_token = getattr(source_fs, "_fs_token_", None)
    target_token = getattr(target_fs, "_fs_token_", None)
    if source_token is not None and source_token == target_token:
        return True
    return _filesystem_namespace(source_fs) == _filesystem_namespace(target_fs)


def _stores_overlap(source: Store, target: Store) -> bool:
    if source is target:
        return True
    if isinstance(source, LocalStore) and isinstance(target, LocalStore):
        source_root = Path(source.root).resolve()
        target_root = Path(target.root).resolve()
        return source_root == target_root or source_root in target_root.parents or target_root in source_root.parents
    if isinstance(source, FsspecStore) and isinstance(target, FsspecStore):
        source_fs = getattr(source.fs, "sync_fs", source.fs)
        target_fs = getattr(target.fs, "sync_fs", target.fs)
        return _same_filesystem_namespace(source_fs, target_fs) and _paths_overlap(source.path, target.path)
    return False


async def _is_materialized_empty_group(store: Store, keys: list[str]) -> bool:
    key_set = set(keys)
    if key_set in ({".zgroup"}, {".zgroup", ".zattrs"}):
        try:
            group_metadata = json.loads((await _get_bytes(store, ".zgroup")).decode())
            attributes = json.loads((await _get_bytes(store, ".zattrs")).decode()) if ".zattrs" in key_set else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False
        return group_metadata.get("zarr_format") == 2 and attributes == {}
    if key_set == {"zarr.json"}:
        try:
            metadata = json.loads((await _get_bytes(store, "zarr.json")).decode())
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False
        return (
            metadata.get("zarr_format") == 3
            and metadata.get("node_type") == "group"
            and metadata.get("attributes", {}) == {}
        )
    return False


def zarr_store_is_empty(store: Store) -> bool:
    """Return whether a store contains no keys at all."""
    return _zarr_sync(store.is_empty(""))


async def _prepare_store_for_write(store: Store, overwrite: bool) -> None:
    keys = await _list_keys(store)
    if not keys:
        return

    if await _is_materialized_empty_group(store, keys):
        # A bare v3 group is already the desired writable container. A bare
        # v2 group is the legacy entity-materialization contract; remove only
        # its root metadata so the v3 writer cannot leave a mixed hierarchy.
        if ".zgroup" in keys:
            for key in keys:
                await store.delete(key)
        return

    if not overwrite:
        raise FileExistsError("Zarr write target is not empty")


def prepare_zarr_store_for_write(store: Store, overwrite: bool) -> None:
    """Validate a writer target and clean up a bare legacy v2 group.

    Populated targets are rejected before mutation unless ``overwrite`` is
    enabled. Bare groups materialized by copick are treated as empty, and a
    bare v2 group is converted without leaving v2 metadata beside v3 output.
    """
    _zarr_sync(_prepare_store_for_write(store, overwrite))


def _digest(data: bytes) -> _KeyDigest:
    return _KeyDigest(size=len(data), sha256=hashlib.sha256(data).digest())


async def _copy_keys(source: Store, target: Store, keys: list[str]) -> _CopyOutcome:
    copied_bytes = 0
    manifest = {}
    for key in keys:
        value = await source.get(key, default_buffer_prototype())
        if value is None:
            raise FileNotFoundError(f"Zarr store key disappeared during copy: {key}")
        manifest[key] = _digest(value.to_bytes())
        await target.set(key, value)
        copied_bytes += len(value)
    return _CopyOutcome(
        result=RawCopyResult(copied_keys=len(keys), copied_bytes=copied_bytes),
        manifest=manifest,
    )


async def _build_manifest(source: Store, keys: list[str]) -> dict[str, _KeyDigest]:
    manifest = {}
    for key in keys:
        value = await source.get(key, default_buffer_prototype())
        if value is None:
            raise FileNotFoundError(f"Zarr store key disappeared during verification: {key}")
        manifest[key] = _digest(value.to_bytes())
    return manifest


async def _verify_manifest(target: Store, keys: list[str], manifest: dict[str, _KeyDigest]) -> None:
    target_keys = await _list_keys(target)
    if target_keys != keys:
        raise IOError("Copied Zarr store key set does not match the source")
    for key in keys:
        target_value = await target.get(key, default_buffer_prototype())
        if target_value is None or _digest(target_value.to_bytes()) != manifest[key]:
            raise IOError(f"Copied Zarr store key does not match the source: {key}")


async def _snapshot_keys(store: Store, keys: list[str]) -> dict[str, bytes]:
    return {key: await _get_bytes(store, key) for key in keys}


async def _restore_keys(store: Store, snapshot: dict[str, bytes]) -> None:
    buffer_type = default_buffer_prototype().buffer
    for key, value in snapshot.items():
        await store.set(key, buffer_type.from_bytes(value))


def _copy_local_replacement(source: Store, target: LocalStore, keys: list[str]) -> RawCopyResult:
    target_root = Path(target.root)
    target_root.parent.mkdir(parents=True, exist_ok=True)
    stage_root = Path(tempfile.mkdtemp(prefix=f".{target_root.name}.copick-stage-", dir=target_root.parent))
    backup_root: Path | None = None
    try:
        stage_store = LocalStore(stage_root)
        outcome = _zarr_sync(_copy_keys(source, stage_store, keys))
        _zarr_sync(_verify_manifest(stage_store, keys, outcome.manifest))

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
        return outcome.result
    finally:
        if stage_root.exists():
            shutil.rmtree(stage_root)
        if backup_root is not None and backup_root.exists():
            shutil.rmtree(backup_root)


def copy_zarr_store(
    source: Store,
    target: Store,
    *,
    if_exists: IfExists = "raise",
    verify: bool = False,
) -> RawCopyResult:
    """Copy every raw key from one Zarr store to another.

    The operation never decodes array data, so Zarr format, metadata, chunk or
    shard layout, codec payloads, and non-Zarr keys are preserved byte for
    byte.  Local replacement is staged and verified before a same-filesystem
    directory swap.  Other backends are validated and fully listed first, but
    replacement is necessarily non-atomic: the target is cleared once and
    then populated key by key.  Safety-critical remote callers may request a
    post-copy hash-manifest verification without rereading the source.

    Args:
        source: Source Zarr 3 store.
        target: Writable destination Zarr 3 store.
        if_exists: ``raise``, ``replace``, or ``skip``.
        verify: Verify the remote target's key set, sizes, and SHA-256 hashes.
            Local replacement is always verified before its atomic swap.

    Returns:
        Copied key, byte, and skipped-key counts.
    """
    if if_exists not in _VALID_IF_EXISTS:
        raise ValueError(f"if_exists must be one of {sorted(_VALID_IF_EXISTS)}, got {if_exists!r}")
    if _stores_overlap(source, target):
        raise ValueError("Source and target Zarr stores must be different and non-overlapping")

    source_keys = _zarr_sync(_list_keys(source))
    _validate_root_metadata(source, source_keys)

    target_keys = _zarr_sync(_list_keys(target))
    materialized_empty = bool(target_keys) and _zarr_sync(_is_materialized_empty_group(target, target_keys))
    target_occupied = bool(target_keys) and not materialized_empty
    if target_occupied and if_exists == "raise":
        raise FileExistsError("Target Zarr store is not empty")
    if target_occupied and if_exists == "skip":
        return RawCopyResult(copied_keys=0, copied_bytes=0, skipped_keys=len(source_keys))

    if isinstance(target, LocalStore) and (if_exists == "replace" or target_keys):
        return _copy_local_replacement(source, target, source_keys)

    original_empty_group = _zarr_sync(_snapshot_keys(target, target_keys)) if materialized_empty else {}
    if target_keys:
        _zarr_sync(target.delete_dir(""))

    try:
        outcome = _zarr_sync(_copy_keys(source, target, source_keys))
        if verify:
            _zarr_sync(_verify_manifest(target, source_keys, outcome.manifest))
        return outcome.result
    except Exception:
        try:
            _zarr_sync(target.delete_dir(""))
            if original_empty_group:
                _zarr_sync(_restore_keys(target, original_empty_group))
        except Exception:
            pass
        raise


def verify_zarr_store_copy(source: Store, target: Store) -> None:
    """Verify that a copied target has exactly the source's raw keys and hashes."""
    source_keys = _zarr_sync(_list_keys(source))
    target_keys = _zarr_sync(_list_keys(target))
    _validate_root_metadata(source, source_keys)
    _validate_root_metadata(target, target_keys)
    manifest = _zarr_sync(_build_manifest(source, source_keys))
    _zarr_sync(_verify_manifest(target, source_keys, manifest))
