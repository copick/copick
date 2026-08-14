"""Zarr format-preservation contracts for manage copy and move operations."""

import numpy as np
import zarr
from copick.impl.filesystem import CopickConfigFSSpec, CopickRootFSSpec
from copick.ops.manage import copy_copick_objects, move_copick_objects
from copick.util.zarr_copy import verify_zarr_store_copy


def _project(tmp_path):
    root = CopickRootFSSpec(
        CopickConfigFSSpec(overlay_root=f"local://{tmp_path}", pickable_objects=[]),
    )
    run = root.new_run("run")
    source = run.new_segmentation(
        voxel_size=10.0,
        user_id="alice",
        session_id="1",
        name="source",
        is_multilabel=True,
    )
    source.from_numpy(np.arange(64, dtype=np.int16).reshape(4, 4, 4))
    return root, run, source


def test_manage_copy_preserves_legacy_store_without_numpy_round_trip(tmp_path, monkeypatch):
    root, run, source = _project(tmp_path)

    def reject_numpy(*args, **kwargs):
        raise AssertionError("manage copy must not decode the complete segmentation")

    monkeypatch.setattr(source, "numpy", reject_numpy)
    result = copy_copick_objects(
        root,
        "segmentation",
        "source:alice/1@10.0?multilabel=true",
        "copied:bob/2@10.0?multilabel=true",
        run_name="run",
    )

    assert result["errors"] == []
    assert result["copied"] == 1
    copied = run.get_segmentations(name="copied", user_id="bob", session_id="2", voxel_size=10.0)[0]
    verify_zarr_store_copy(source.zarr(), copied.zarr())
    assert zarr.open_group(copied.zarr(), mode="r").metadata.zarr_format == 2
    np.testing.assert_array_equal(copied.numpy(), np.arange(64, dtype=np.int16).reshape(4, 4, 4))


def test_manage_move_deletes_source_only_after_target_verification(tmp_path, monkeypatch):
    from copick.ops import manage

    root, run, source = _project(tmp_path)
    source_path = source.path

    def reject_verification(*args, **kwargs):
        raise IOError("verification failed")

    monkeypatch.setattr(manage, "verify_zarr_store_copy", reject_verification)
    result = move_copick_objects(
        root,
        "segmentation",
        "source:alice/1@10.0?multilabel=true",
        "moved:bob/2@10.0?multilabel=true",
        run_name="run",
    )

    assert result["moved"] == 0
    assert result["errors"] and "verification failed" in result["errors"][0]
    assert run.fs_overlay.exists(source_path)
    assert source in run.segmentations


def test_manage_move_preserves_store_and_removes_verified_source(tmp_path):
    root, run, source = _project(tmp_path)
    source_path = source.path

    result = move_copick_objects(
        root,
        "segmentation",
        "source:alice/1@10.0?multilabel=true",
        "moved:bob/2@10.0?multilabel=true",
        run_name="run",
    )

    assert result["errors"] == []
    assert result["moved"] == 1
    assert not run.fs_overlay.exists(source_path)
    moved = run.get_segmentations(name="moved", user_id="bob", session_id="2", voxel_size=10.0)[0]
    assert zarr.open_group(moved.zarr(), mode="r").metadata.zarr_format == 2
    np.testing.assert_array_equal(moved.numpy(), np.arange(64, dtype=np.int16).reshape(4, 4, 4))
