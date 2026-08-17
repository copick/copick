"""Zarr format-preservation contracts for manage copy and move operations."""

from unittest.mock import patch

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
    values = np.arange(64, dtype=np.int16).reshape(4, 4, 4)
    group = zarr.group(store=source.zarr(), overwrite=True, zarr_format=2)
    group.create_array("0", data=values, chunks=(2, 2, 2), chunk_key_encoding={"name": "v2", "separator": "/"})
    group.attrs["multiscales"] = [
        {
            "version": "0.4",
            "axes": [{"name": axis, "type": "space", "unit": "angstrom"} for axis in ("z", "y", "x")],
            "datasets": [
                {
                    "path": "0",
                    "coordinateTransformations": [{"type": "scale", "scale": [10.0, 10.0, 10.0]}],
                },
            ],
        },
    ]
    return root, run, source


def test_manage_copy_preserves_legacy_store_without_numpy_round_trip(tmp_path, monkeypatch):
    from copick.ops import manage

    root, run, source = _project(tmp_path)

    def reject_numpy(*args, **kwargs):
        raise AssertionError("manage copy must not decode the complete segmentation")

    monkeypatch.setattr(source, "numpy", reject_numpy)
    with patch.object(manage, "copy_zarr_store", wraps=manage.copy_zarr_store) as raw_copy:
        result = copy_copick_objects(
            root,
            "segmentation",
            "source:alice/1@10.0?multilabel=true",
            "copied:bob/2@10.0?multilabel=true",
            run_name="run",
        )

    assert result["errors"] == []
    assert result["copied"] == 1
    assert raw_copy.call_args.kwargs["verify"] is False
    copied = run.get_segmentations(name="copied", user_id="bob", session_id="2", voxel_size=10.0)[0]
    verify_zarr_store_copy(source.zarr(), copied.zarr())
    assert zarr.open_group(copied.zarr(), mode="r").metadata.zarr_format == 2
    np.testing.assert_array_equal(copied.numpy(), np.arange(64, dtype=np.int16).reshape(4, 4, 4))


def test_manage_move_deletes_source_only_after_target_verification(tmp_path, monkeypatch):
    from copick.ops import manage

    root, run, source = _project(tmp_path)
    source_path = source.path

    def reject_verification(*args, **kwargs):
        assert kwargs["verify"] is True
        raise IOError("verification failed")

    monkeypatch.setattr(manage, "copy_zarr_store", reject_verification)
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
    from copick.util import zarr_copy

    root, run, source = _project(tmp_path)
    source_path = source.path

    with patch.object(zarr_copy, "_verify_manifest", wraps=zarr_copy._verify_manifest) as verification:
        result = move_copick_objects(
            root,
            "segmentation",
            "source:alice/1@10.0?multilabel=true",
            "moved:bob/2@10.0?multilabel=true",
            run_name="run",
        )

    assert result["errors"] == []
    assert result["moved"] == 1
    assert verification.call_count == 1
    assert not run.fs_overlay.exists(source_path)
    moved = run.get_segmentations(name="moved", user_id="bob", session_id="2", voxel_size=10.0)[0]
    assert zarr.open_group(moved.zarr(), mode="r").metadata.zarr_format == 2
    np.testing.assert_array_equal(moved.numpy(), np.arange(64, dtype=np.int16).reshape(4, 4, 4))
