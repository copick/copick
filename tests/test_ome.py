"""Tests for OME-Zarr metadata-driven level access."""

import inspect
import json
from types import SimpleNamespace

import mrcfile
import numpy as np
import pytest
import zarr
from click.testing import CliRunner
from copick.cli.export import export as export_cli
from copick.models import (
    CopickFeatures,
    CopickObject,
    CopickSegmentation,
    CopickTomogram,
    CopickTomogramMeta,
)
from copick.ops.export import export_tomogram
from copick.util.handlers.volume.zarr import ZarrVolumeHandler
from copick.util.ome import get_level_path, get_multiscales, get_voxel_size_from_zarr
from copick.util.path_util import get_data_from_file


def _write_named_pyramid(path, metadata_layout="0.4"):
    group = zarr.open(path, mode="w")
    level_zero = np.arange(64, dtype=np.float32).reshape(4, 4, 4)
    level_one = np.full((2, 2, 2), 7, dtype=np.float32)
    group.create_dataset("s0", data=level_zero, chunks=(2, 2, 2), dimension_separator="/")
    group.create_dataset("s1", data=level_one, chunks=(2, 2, 2), dimension_separator="/")

    multiscales = [
        {
            "version": metadata_layout,
            "axes": [
                {"name": "z", "type": "space", "unit": "angstrom"},
                {"name": "y", "type": "space", "unit": "angstrom"},
                {"name": "x", "type": "space", "unit": "angstrom"},
            ],
            "datasets": [
                {
                    "path": "s0",
                    "coordinateTransformations": [{"type": "scale", "scale": [10.0, 10.0, 10.0]}],
                },
                {
                    "path": "s1",
                    "coordinateTransformations": [{"type": "scale", "scale": [20.0, 20.0, 20.0]}],
                },
            ],
        },
    ]
    if metadata_layout == "0.4":
        group.attrs["multiscales"] = multiscales
    else:
        group.attrs["ome"] = {"version": metadata_layout, "multiscales": multiscales}

    return level_zero, level_one


class _TomogramWithStore(CopickTomogram):
    def __init__(self, store):
        super().__init__(SimpleNamespace(voxel_size=10.0), CopickTomogramMeta(tomo_type="test"))
        self._store = store

    def zarr(self):
        return self._store


@pytest.mark.parametrize("metadata_layout", ["0.4", "0.5"])
def test_multiscales_and_level_paths_support_both_metadata_layouts(tmp_path, metadata_layout):
    path = str(tmp_path / f"named-{metadata_layout}.zarr")
    _write_named_pyramid(path, metadata_layout)
    group = zarr.open(path, mode="r")

    assert get_multiscales(group)[0]["version"] == metadata_layout
    assert get_level_path(group, 0) == "s0"
    assert get_level_path(group, 1) == "s1"
    assert get_voxel_size_from_zarr(group) == 10.0
    assert "s0/0/0/0" in group.store
    assert "s0/0.0.0" not in group.store


def test_level_path_rejects_invalid_levels_before_array_access():
    metadata_only_group = SimpleNamespace(
        attrs={
            "multiscales": [
                {
                    "datasets": [
                        {"path": "s0"},
                    ],
                },
            ],
        },
    )

    with pytest.raises(ValueError, match=r"Level -1 .*max: 0"):
        get_level_path(metadata_only_group, -1)
    with pytest.raises(ValueError, match=r"Level 1 .*max: 0"):
        get_level_path(metadata_only_group, 1)


def test_public_volume_apis_default_to_metadata_level_zero():
    for cls in (CopickObject, CopickTomogram, CopickFeatures, CopickSegmentation):
        assert inspect.signature(cls.numpy).parameters["zarr_group"].default is None
        assert inspect.signature(cls.set_region).parameters["zarr_group"].default is None


def test_tomogram_numpy_and_region_write_use_named_metadata_path(tmp_path):
    path = str(tmp_path / "tomogram.zarr")
    level_zero, level_one = _write_named_pyramid(path)
    tomogram = _TomogramWithStore(path)

    np.testing.assert_array_equal(tomogram.numpy(), level_zero)
    np.testing.assert_array_equal(tomogram.numpy(zarr_group="s1"), level_one)

    replacement = np.full((2, 2, 2), 99, dtype=np.float32)
    tomogram.set_region(replacement, x=slice(1, 3), y=slice(1, 3), z=slice(1, 3))

    group = zarr.open(path, mode="r")
    np.testing.assert_array_equal(group["s0"][1:3, 1:3, 1:3], replacement)


def test_named_level_works_in_handler_path_helper_and_export(tmp_path):
    path = str(tmp_path / "named.zarr")
    level_zero, level_one = _write_named_pyramid(path)

    handler_volume, voxel_size = ZarrVolumeHandler().read(path, level=1)
    np.testing.assert_array_equal(handler_volume, level_one)
    assert voxel_size == 20.0

    path_volume, path_voxel_size = get_data_from_file(path, "zarr")
    np.testing.assert_array_equal(path_volume, level_zero)
    assert path_voxel_size == 10.0

    output_path = str(tmp_path / "level-one.mrc")
    export_tomogram(_TomogramWithStore(path), output_path, "mrc", level=1)
    with mrcfile.open(output_path) as output:
        np.testing.assert_array_equal(output.data, level_one)

    single_level_path = str(tmp_path / "single-level.zarr")
    export_tomogram(_TomogramWithStore(path), single_level_path, "zarr", copy_all_levels=False)
    single_level_group = zarr.open(single_level_path, mode="r")
    assert get_level_path(single_level_group, 0) == "s0"
    np.testing.assert_array_equal(single_level_group["s0"], level_zero)


def test_named_level_works_through_export_cli(tmp_path):
    project = tmp_path / "project"
    tomogram_path = project / "ExperimentRuns" / "run_001" / "VoxelSpacing10.000" / "wbp.zarr"
    _, level_one = _write_named_pyramid(str(tomogram_path))

    config_path = tmp_path / "filesystem.json"
    config_path.write_text(
        json.dumps(
            {
                "config_type": "filesystem",
                "pickable_objects": [],
                "overlay_root": f"local://{project}",
                "overlay_fs_args": {"auto_mkdir": True},
            },
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "exported"

    result = CliRunner().invoke(
        export_cli,
        [
            "tomogram",
            "--config",
            str(config_path),
            "--run-names",
            "run_001",
            "--tomogram-uri",
            "wbp@10.0",
            "--output-dir",
            str(output_dir),
            "--output-format",
            "mrc",
            "--level",
            "1",
            "--max-workers",
            "1",
        ],
    )

    assert result.exit_code == 0, result.output
    output_path = output_dir / "run_001" / "VoxelSpacing10.000" / "wbp.mrc"
    assert output_path.exists()
    with mrcfile.open(output_path) as output:
        np.testing.assert_array_equal(output.data, level_one)
        assert output.voxel_size.x == 20.0


@pytest.mark.parametrize("level", [-1, 2])
def test_handler_rejects_invalid_named_levels(tmp_path, level):
    path = str(tmp_path / "named.zarr")
    _write_named_pyramid(path)

    with pytest.raises(ValueError, match=rf"Level {level} .*max: 1"):
        ZarrVolumeHandler().read(path, level=level)
