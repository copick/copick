"""Tests for format-preserving raw Zarr store copies."""

from pathlib import Path

import fsspec
import numpy as np
import pytest
import zarr
from zarr.storage import LocalStore, MemoryStore

from copick.util.store import copick_store
from copick.util.zarr_copy import copy_zarr_store


def _create_store(path: Path, zarr_format: int, value: int) -> LocalStore:
    store = LocalStore(path)
    group = zarr.group(store=store, overwrite=True, zarr_format=zarr_format)
    kwargs = {"chunks": (2, 2)}
    if zarr_format == 3:
        kwargs["shards"] = (4, 4)
    group.create_array("nested/data", data=np.full((5, 5), value, dtype=np.int16), **kwargs)
    (path / "custom" / "non-zarr-key").parent.mkdir(parents=True, exist_ok=True)
    (path / "custom" / "non-zarr-key").write_bytes(b"copick-raw-payload")
    return store


def _snapshot(path: Path) -> dict[str, bytes]:
    return {file.relative_to(path).as_posix(): file.read_bytes() for file in path.rglob("*") if file.is_file()}


@pytest.mark.parametrize(("source_format", "target_format"), [(2, 3), (3, 2)])
def test_replace_preserves_source_format_and_every_raw_key(tmp_path, source_format, target_format):
    source_path = tmp_path / "source.zarr"
    target_path = tmp_path / "target.zarr"
    source = _create_store(source_path, source_format, 7)
    target = _create_store(target_path, target_format, 3)
    expected = _snapshot(source_path)

    result = copy_zarr_store(source, target, if_exists="replace")

    assert _snapshot(target_path) == expected
    assert result.copied_keys == len(expected)
    assert result.copied_bytes == sum(map(len, expected.values()))
    assert result.skipped_keys == 0
    assert (target_path / "zarr.json").exists() is (source_format == 3)
    assert (target_path / ".zgroup").exists() is (source_format == 2)


def test_invalid_source_is_rejected_before_target_mutation(tmp_path):
    source_path = tmp_path / "source.zarr"
    source_path.mkdir()
    (source_path / "payload").write_bytes(b"not-zarr")
    target_path = tmp_path / "target.zarr"
    target = _create_store(target_path, 2, 3)
    before = _snapshot(target_path)

    with pytest.raises(ValueError, match="valid root metadata"):
        copy_zarr_store(LocalStore(source_path), target, if_exists="replace")

    assert _snapshot(target_path) == before


def test_raise_and_skip_are_preflight_policies(tmp_path):
    source_path = tmp_path / "source.zarr"
    target_path = tmp_path / "target.zarr"
    source = _create_store(source_path, 2, 7)
    target = _create_store(target_path, 3, 3)
    before = _snapshot(target_path)

    with pytest.raises(FileExistsError, match="not empty"):
        copy_zarr_store(source, target, if_exists="raise")
    assert _snapshot(target_path) == before

    result = copy_zarr_store(source, target, if_exists="skip")
    assert result.copied_keys == 0
    assert result.copied_bytes == 0
    assert result.skipped_keys == len(_snapshot(source_path))
    assert _snapshot(target_path) == before


def test_invalid_policy_and_same_store_are_rejected(tmp_path):
    store = _create_store(tmp_path / "source.zarr", 2, 7)

    with pytest.raises(ValueError, match="if_exists"):
        copy_zarr_store(store, LocalStore(tmp_path / "target.zarr"), if_exists="merge")
    with pytest.raises(ValueError, match="must be different"):
        copy_zarr_store(store, LocalStore(tmp_path / "source.zarr"), if_exists="replace")


def test_scheme_bearing_remote_source_copies_nonzero_keys():
    fs = fsspec.filesystem("memory")
    source = copick_store(fs, "memory://bucket/source.zarr", create=True)
    target = copick_store(fs, "memory://bucket/target.zarr", create=True)
    group = zarr.group(store=source, zarr_format=2)
    group.create_array("0", data=np.arange(8), chunks=(2,))

    result = copy_zarr_store(source, target)

    assert result.copied_keys > 0
    np.testing.assert_array_equal(zarr.open_group(target, mode="r")["0"][:], np.arange(8))


def test_failed_local_stage_verification_preserves_target(tmp_path, monkeypatch):
    from copick.util import zarr_copy

    source = _create_store(tmp_path / "source.zarr", 3, 7)
    target_path = tmp_path / "target.zarr"
    target = _create_store(target_path, 2, 3)
    before = _snapshot(target_path)

    async def fail_verification(source, target, keys):
        raise IOError("verification failed")

    monkeypatch.setattr(zarr_copy, "_verify_keys", fail_verification)
    with pytest.raises(IOError, match="verification failed"):
        copy_zarr_store(source, target, if_exists="replace")

    assert _snapshot(target_path) == before


class _CountingMemoryStore(MemoryStore):
    def __init__(self, store_dict=None, read_only=False):
        super().__init__(store_dict=store_dict, read_only=read_only)
        self.delete_calls = 0

    async def delete_dir(self, prefix: str) -> None:
        self.delete_calls += 1
        await super().delete_dir(prefix)


def test_remote_replacement_clears_target_once():
    source = MemoryStore()
    target = _CountingMemoryStore()
    zarr.group(store=source, zarr_format=2).create_array("new", data=np.arange(4))
    zarr.group(store=target, zarr_format=3).create_array("old", data=np.arange(2))

    copy_zarr_store(source, target, if_exists="replace")

    assert target.delete_calls == 1
    assert list(zarr.open_group(target, mode="r").array_keys()) == ["new"]
