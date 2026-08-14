"""Tests for format-preserving raw Zarr store copies."""

from pathlib import Path

import fsspec
import numpy as np
import pytest
import zarr
from copick.util.store import copick_store
from copick.util.zarr_copy import copy_zarr_store
from numcodecs import Blosc, Delta
from zarr.codecs import ZstdCodec
from zarr.core.buffer import default_buffer_prototype
from zarr.storage import LocalStore, MemoryStore


def _create_store(path: Path, zarr_format: int, value: int) -> LocalStore:
    store = LocalStore(path)
    group = zarr.group(store=store, overwrite=True, zarr_format=zarr_format)
    kwargs = {"chunks": (2, 2)}
    if zarr_format == 3:
        kwargs["shards"] = (4, 4)
        kwargs["compressors"] = [ZstdCodec(level=7, checksum=True)]
    else:
        kwargs["filters"] = [Delta(dtype=np.dtype("<i2"))]
        kwargs["compressor"] = Blosc(cname="zstd", clevel=2, shuffle=Blosc.BITSHUFFLE)
    group.create_array("nested/data", data=np.full((5, 5), value, dtype=np.int16), **kwargs)
    (path / "custom" / "non-zarr-key").parent.mkdir(parents=True, exist_ok=True)
    (path / "custom" / "non-zarr-key").write_bytes(b"copick-raw-payload")
    return store


def _snapshot(path: Path) -> dict[str, bytes]:
    return {file.relative_to(path).as_posix(): file.read_bytes() for file in path.rglob("*") if file.is_file()}


def _snapshot_memory_store(store: MemoryStore) -> dict[str, bytes]:
    return {key: value.to_bytes() for key, value in store._store_dict.items()}


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
    target_group = zarr.open_group(target, mode="r")
    array_path = "0"
    np.testing.assert_array_equal(target_group[array_path][:], np.arange(8))


def test_separately_constructed_remote_stores_reject_same_target():
    source_fs = fsspec.filesystem("memory", skip_instance_cache=True)
    target_fs = fsspec.filesystem("memory", skip_instance_cache=True)
    source = copick_store(source_fs, "memory://same/store.zarr", create=True)
    zarr.group(store=source, zarr_format=2)
    target = copick_store(target_fs, "memory://same/store.zarr")

    with pytest.raises(ValueError, match="non-overlapping"):
        copy_zarr_store(source, target, if_exists="replace")


@pytest.mark.parametrize(
    ("source_path", "target_path"),
    [
        ("memory://nested/source.zarr", "memory://nested/source.zarr/child.zarr"),
        ("memory://nested/parent.zarr/child.zarr", "memory://nested/parent.zarr"),
    ],
)
def test_remote_store_containment_is_rejected_before_mutation(source_path, target_path):
    source_fs = fsspec.filesystem("memory", skip_instance_cache=True)
    target_fs = fsspec.filesystem("memory", skip_instance_cache=True)
    source = copick_store(source_fs, source_path, create=True)
    zarr.group(store=source, zarr_format=2)
    target = copick_store(target_fs, target_path)

    with pytest.raises(ValueError, match="non-overlapping"):
        copy_zarr_store(source, target, if_exists="replace")


def test_failed_local_stage_verification_preserves_target(tmp_path, monkeypatch):
    from copick.util import zarr_copy

    source = _create_store(tmp_path / "source.zarr", 3, 7)
    target_path = tmp_path / "target.zarr"
    target = _create_store(target_path, 2, 3)
    before = _snapshot(target_path)

    async def fail_verification(target, keys, manifest):
        raise IOError("verification failed")

    monkeypatch.setattr(zarr_copy, "_verify_manifest", fail_verification)
    with pytest.raises(IOError, match="verification failed"):
        copy_zarr_store(source, target, if_exists="replace")

    assert _snapshot(target_path) == before


class _CountingMemoryStore(MemoryStore):
    def __init__(self, store_dict=None, read_only=False):
        super().__init__(store_dict=store_dict, read_only=read_only)
        self.delete_calls = 0
        self.get_calls = {}

    async def delete_dir(self, prefix: str) -> None:
        self.delete_calls += 1
        await super().delete_dir(prefix)

    async def get(self, key, prototype, byte_range=None):
        self.get_calls[key] = self.get_calls.get(key, 0) + 1
        return await super().get(key, prototype, byte_range)


class _CorruptingMemoryStore(_CountingMemoryStore):
    def __init__(self, store_dict=None, read_only=False):
        super().__init__(store_dict=store_dict, read_only=read_only)
        self.corrupted = False

    async def set(self, key, value):
        if not self.corrupted and key not in {".zgroup", ".zattrs", "zarr.json"}:
            payload = bytearray(value.to_bytes())
            payload[-1] ^= 1
            value = default_buffer_prototype().buffer.from_bytes(payload)
            self.corrupted = True
        await super().set(key, value)


def test_remote_replacement_clears_target_once():
    source = MemoryStore()
    target = _CountingMemoryStore()
    zarr.group(store=source, zarr_format=2).create_array("new", data=np.arange(4))
    zarr.group(store=target, zarr_format=3).create_array("old", data=np.arange(2))

    copy_zarr_store(source, target, if_exists="replace")

    assert target.delete_calls == 1
    assert list(zarr.open_group(target, mode="r").array_keys()) == ["new"]


@pytest.mark.parametrize("target_format", [2, 3])
def test_materialized_empty_group_is_available_to_raise_policy(target_format):
    source = MemoryStore()
    target = MemoryStore()
    zarr.group(store=source, zarr_format=2).create_array("data", data=np.arange(4))
    zarr.group(store=target, zarr_format=target_format)

    result = copy_zarr_store(source, target, if_exists="raise", verify=True)

    assert result.copied_keys > 0
    np.testing.assert_array_equal(zarr.open_group(target, mode="r")["data"][:], np.arange(4))


def test_nonempty_materialized_group_still_honors_raise_and_skip():
    source = MemoryStore()
    target = MemoryStore()
    zarr.group(store=source, zarr_format=2).create_array("data", data=np.arange(4))
    target_group = zarr.group(store=target, zarr_format=2)
    target_group.attrs["owner"] = "existing"

    with pytest.raises(FileExistsError, match="not empty"):
        copy_zarr_store(source, target, if_exists="raise")
    result = copy_zarr_store(source, target, if_exists="skip")

    assert result.copied_keys == 0
    assert zarr.open_group(target, mode="r").attrs["owner"] == "existing"


def test_remote_verification_reads_each_target_key_once():
    source = MemoryStore()
    target = _CountingMemoryStore()
    zarr.group(store=source, zarr_format=2).create_array("data", data=np.arange(8), chunks=(2,))
    expected_keys = sorted(_snapshot_memory_store(source))

    copy_zarr_store(source, target, verify=True)

    assert target.get_calls == {key: 1 for key in expected_keys}


def test_remote_verification_failure_clears_partial_replacement():
    source = MemoryStore()
    target = _CorruptingMemoryStore()
    zarr.group(store=source, zarr_format=2).create_array("new", data=np.arange(8), chunks=(2,))
    zarr.group(store=target, zarr_format=3).create_array("old", data=np.arange(2))
    target.corrupted = False

    with pytest.raises(IOError, match="does not match"):
        copy_zarr_store(source, target, if_exists="replace", verify=True)

    assert target.delete_calls == 2
    assert _snapshot_memory_store(target) == {}


def test_remote_failure_restores_new_entity_materialization():
    source = MemoryStore()
    target = _CorruptingMemoryStore()
    zarr.group(store=source, zarr_format=2).create_array("new", data=np.arange(8), chunks=(2,))
    zarr.group(store=target, zarr_format=2)
    materialized = _snapshot_memory_store(target)

    with pytest.raises(IOError, match="does not match"):
        copy_zarr_store(source, target, if_exists="raise", verify=True)

    assert _snapshot_memory_store(target) == materialized
