"""Tests for ops-level add functions."""

import contextlib
import os
import tempfile
from typing import Any, Dict

import mrcfile
import numpy as np
import pytest
import zarr
from copick.impl.filesystem import CopickRootFSSpec
from copick.ops.add import (
    add_features,
    add_object,
    add_object_volume,
    add_picks,
    add_run,
    add_segmentation,
    add_tomogram,
    add_voxelspacing,
    get_or_create_run,
    get_or_create_voxelspacing,
)


@pytest.fixture(params=pytest.common_cases)
def test_payload(request) -> Dict[str, Any]:
    payload = request.getfixturevalue(request.param)
    payload["root"] = CopickRootFSSpec.from_file(payload["cfg_file"])
    return payload


@pytest.fixture
def sample_csv_picks():
    """Create a sample CSV picks file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as tmp:
        header = "run_name,x,y,z,transform_00,transform_01,transform_02,transform_03,transform_10,transform_11,transform_12,transform_13,transform_20,transform_21,transform_22,transform_23,transform_30,transform_31,transform_32,transform_33,score,instance_id\n"
        tmp.write(header)
        tmp.write("TS_001,100.0,200.0,300.0,1.0,0.0,0.0,0.0,0.0,1.0,0.0,0.0,0.0,0.0,1.0,0.0,0.0,0.0,0.0,1.0,0.95,1\n")
        tmp.write("TS_001,150.0,250.0,350.0,1.0,0.0,0.0,0.0,0.0,1.0,0.0,0.0,0.0,0.0,1.0,0.0,0.0,0.0,0.0,1.0,0.87,2\n")
        tmp.flush()
        yield tmp.name

    with contextlib.suppress(PermissionError, OSError):
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)


@pytest.fixture
def sample_mrc_segmentation():
    """Create a sample MRC file for segmentation testing."""
    with tempfile.NamedTemporaryFile(suffix=".mrc", delete=False) as tmp:
        volume = np.ones((8, 8, 8), dtype=np.int16)
        with mrcfile.new(tmp.name, overwrite=True) as mrc:
            mrc.set_data(volume)
            mrc.voxel_size = 10.0
        yield tmp.name

    with contextlib.suppress(PermissionError, OSError):
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)


class TestAddRun:
    """Test cases for add_run."""

    def test_add_run_creates_new(self, test_payload):
        """Adding a new run succeeds."""
        root = test_payload["root"]
        run = add_run(root, "new-add-test-run", exist_ok=False)
        assert run.name == "new-add-test-run"
        assert root.get_run("new-add-test-run") is not None

    def test_add_run_exist_ok_true(self, test_payload):
        """Adding a duplicate run with exist_ok=True does not raise."""
        root = test_payload["root"]
        add_run(root, "run-exist-ok-test", exist_ok=False)
        run2 = add_run(root, "run-exist-ok-test", exist_ok=True)
        assert run2.name == "run-exist-ok-test"

    def test_add_run_exist_ok_false_raises(self, test_payload):
        """Adding a duplicate run with exist_ok=False raises."""
        root = test_payload["root"]
        add_run(root, "run-dup-test", exist_ok=False)
        with pytest.raises(ValueError):
            add_run(root, "run-dup-test", exist_ok=False)


class TestGetOrCreateRun:
    """Test cases for get_or_create_run."""

    def test_get_existing_run(self, test_payload):
        """Getting an existing run returns it."""
        root = test_payload["root"]
        run = get_or_create_run(root, "TS_001")
        assert run.name == "TS_001"

    def test_create_when_missing(self, test_payload):
        """Creates a new run when create=True."""
        root = test_payload["root"]
        run = get_or_create_run(root, "new-goc-run", create=True)
        assert run.name == "new-goc-run"

    def test_raises_when_create_false(self, test_payload):
        """Raises ValueError when create=False and run doesn't exist."""
        root = test_payload["root"]
        with pytest.raises(ValueError, match="Could not find run"):
            get_or_create_run(root, "nonexistent-run-xyz", create=False)


class TestAddVoxelSpacing:
    """Test cases for add_voxelspacing."""

    def test_add_voxelspacing_creates_new(self, test_payload):
        """Adding a new voxel spacing succeeds."""
        root = test_payload["root"]
        vs = add_voxelspacing(root, "TS_001", 15.0, exist_ok=False)
        assert vs.voxel_size == 15.0

    def test_add_voxelspacing_exist_ok(self, test_payload):
        """Adding a duplicate voxel spacing with exist_ok=True does not raise."""
        root = test_payload["root"]
        add_voxelspacing(root, "TS_001", 25.0, exist_ok=False)
        vs2 = add_voxelspacing(root, "TS_001", 25.0, exist_ok=True)
        assert vs2.voxel_size == 25.0


class TestGetOrCreateVoxelSpacing:
    """Test cases for get_or_create_voxelspacing."""

    def test_get_existing_voxelspacing(self, test_payload):
        """Getting an existing voxel spacing returns it."""
        root = test_payload["root"]
        run = root.get_run("TS_001")
        vs = get_or_create_voxelspacing(run, 10.0)
        assert vs.voxel_size == 10.0

    def test_raises_when_create_false(self, test_payload):
        """Raises ValueError when create=False and voxel spacing doesn't exist."""
        root = test_payload["root"]
        run = root.get_run("TS_001")
        with pytest.raises(ValueError):
            get_or_create_voxelspacing(run, 999.0, create=False)


class TestAddTomogram:
    """Test cases for add_tomogram."""

    def test_add_tomogram_numpy_array(self, test_payload):
        """Adding a tomogram from a numpy array succeeds."""
        root = test_payload["root"]
        volume = np.random.randn(8, 8, 8).astype(np.float32)
        tomo = add_tomogram(root, "TS_001", "test-tomo-np", volume, voxel_spacing=10.0, exist_ok=True)
        assert tomo.tomo_type == "test-tomo-np"

        # Verify data is stored
        zarr_group = zarr.open(tomo.zarr())
        assert "0" in zarr_group
        assert zarr_group["0"].shape == (8, 8, 8)

    def test_add_tomogram_dict_pyramid(self, test_payload):
        """Adding a tomogram from a dict pyramid writes multiple levels."""
        root = test_payload["root"]
        volume = {10.0: np.zeros((8, 8, 8), dtype=np.float32), 20.0: np.zeros((4, 4, 4), dtype=np.float32)}
        tomo = add_tomogram(root, "TS_001", "test-tomo-pyr", volume, exist_ok=True)
        assert tomo.tomo_type == "test-tomo-pyr"

    def test_add_tomogram_missing_voxel_spacing_raises(self, test_payload):
        """Missing voxel_spacing with numpy array raises ValueError."""
        root = test_payload["root"]
        volume = np.zeros((8, 8, 8), dtype=np.float32)
        with pytest.raises(ValueError, match="Voxel spacing must be provided"):
            add_tomogram(root, "TS_001", "test-tomo-bad", volume, voxel_spacing=None, exist_ok=True)

    def test_add_tomogram_wrong_voxel_spacing_in_dict_raises(self, test_payload):
        """voxel_spacing not in dict keys raises ValueError."""
        root = test_payload["root"]
        volume = {10.0: np.zeros((8, 8, 8), dtype=np.float32)}
        with pytest.raises(ValueError, match="not found in provided pyramid"):
            add_tomogram(root, "TS_001", "test-tomo-bad2", volume, voxel_spacing=99.0, exist_ok=True)

    def test_add_tomogram_transpose(self, test_payload):
        """Transpose rearranges axes of stored volume."""
        root = test_payload["root"]
        volume = np.random.randn(4, 6, 8).astype(np.float32)
        tomo = add_tomogram(
            root,
            "TS_001",
            "test-tomo-transpose",
            volume,
            voxel_spacing=10.0,
            transpose="2,1,0",
            exist_ok=True,
        )
        zarr_group = zarr.open(tomo.zarr())
        assert zarr_group["0"].shape == (8, 6, 4)

    def test_add_tomogram_flip(self, test_payload):
        """Flip reverses specified axis."""
        root = test_payload["root"]
        volume = np.arange(8).reshape(2, 2, 2).astype(np.float32)
        tomo = add_tomogram(root, "TS_001", "test-tomo-flip", volume, voxel_spacing=10.0, flip="0", exist_ok=True)
        zarr_group = zarr.open(tomo.zarr())
        stored = np.array(zarr_group["0"])
        expected = np.flip(volume, axis=0)
        np.testing.assert_array_equal(stored, expected)

    def test_add_tomogram_create_pyramid(self, test_payload):
        """create_pyramid=True generates multiple pyramid levels."""
        root = test_payload["root"]
        volume = np.random.randn(16, 16, 16).astype(np.float32)
        tomo = add_tomogram(
            root,
            "TS_001",
            "test-tomo-cpyr",
            volume,
            voxel_spacing=10.0,
            create_pyramid=True,
            pyramid_levels=2,
            exist_ok=True,
        )
        zarr_group = zarr.open(tomo.zarr())
        assert "0" in zarr_group
        assert "1" in zarr_group


class TestAddFeatures:
    """Test cases for add_features."""

    def test_add_features_basic(self, test_payload):
        """Adding features to an existing tomogram succeeds."""
        root = test_payload["root"]

        # add_features hardcodes voxel_spacing=1.0 for get_or_create_voxelspacing
        # We need a tomogram at voxel_spacing 1.0, so add one first
        volume = np.random.randn(8, 8, 8).astype(np.float32)
        add_tomogram(root, "TS_001", "feat-test-tomo", volume, voxel_spacing=1.0, exist_ok=True)

        features_vol = np.random.randn(8, 8, 8).astype(np.float32)
        feat = add_features(root, "TS_001", 1.0, "feat-test-tomo", "sobel-test", features_vol, exist_ok=True)
        assert feat.feature_type == "sobel-test"

    def test_add_features_missing_tomogram_raises(self, test_payload):
        """Missing tomogram raises ValueError."""
        root = test_payload["root"]
        # Ensure run and voxel spacing exist but tomogram doesn't
        add_voxelspacing(root, "TS_001", 1.0, exist_ok=True)
        features_vol = np.random.randn(8, 8, 8).astype(np.float32)
        with pytest.raises(ValueError, match="Could not find tomogram"):
            add_features(root, "TS_001", 1.0, "nonexistent-tomo-xyz", "sobel", features_vol)


class TestAddSegmentation:
    """Test cases for add_segmentation."""

    def test_add_segmentation_from_mrc(self, test_payload, sample_mrc_segmentation):
        """Adding a segmentation from an MRC file succeeds."""
        root = test_payload["root"]
        seg = add_segmentation(
            root,
            "TS_001",
            sample_mrc_segmentation,
            10.0,
            "ribosome",
            "test-user",
            "seg-session-1",
            exist_ok=True,
        )
        assert seg.name == "ribosome"
        assert seg.user_id == "test-user"

        # Verify data is stored
        zarr_group = zarr.open(seg.zarr())
        assert zarr_group["0"].shape == (8, 8, 8)

    def test_add_segmentation_unsupported_format_raises(self, test_payload, tmp_path):
        """Unsupported file format raises ValueError."""
        root = test_payload["root"]
        fake_file = tmp_path / "seg.tiff"
        fake_file.write_bytes(b"\x00" * 100)
        with pytest.raises(ValueError, match="Unsupported file type"):
            add_segmentation(root, "TS_001", str(fake_file), 10.0, "test-seg", "test-user", "1")

    def test_add_segmentation_with_transpose(self, test_payload):
        """Segmentation with transpose changes stored shape."""
        root = test_payload["root"]
        with tempfile.NamedTemporaryFile(suffix=".mrc", delete=False) as tmp:
            volume = np.ones((4, 6, 8), dtype=np.int16)
            with mrcfile.new(tmp.name, overwrite=True) as mrc:
                mrc.set_data(volume)
            try:
                seg = add_segmentation(
                    root,
                    "TS_001",
                    tmp.name,
                    10.0,
                    "membrane",
                    "test-user",
                    "tp-session",
                    transpose="2,1,0",
                    exist_ok=True,
                )
                zarr_group = zarr.open(seg.zarr())
                assert zarr_group["0"].shape == (8, 6, 4)
            finally:
                with contextlib.suppress(PermissionError, OSError):
                    os.unlink(tmp.name)


class TestAddObject:
    """Test cases for add_object."""

    def test_add_object_basic(self, test_payload):
        """Adding a basic particle object succeeds."""
        root = test_payload["root"]
        obj = add_object(root, "test-particle-obj", is_particle=True, radius=50.0, exist_ok=True)
        assert obj.name == "test-particle-obj"
        assert obj.is_particle is True
        assert obj.radius == 50.0

    def test_add_object_with_volume(self, test_payload):
        """Adding an object with volume data succeeds."""
        root = test_payload["root"]
        volume = np.zeros((8, 8, 8), dtype=np.float32)
        obj = add_object(
            root,
            "test-vol-obj",
            is_particle=True,
            volume=volume,
            voxel_size=10.0,
            exist_ok=True,
        )
        assert obj.name == "test-vol-obj"

    def test_add_object_volume_without_voxel_size_raises(self, test_payload):
        """Providing volume without voxel_size raises ValueError."""
        root = test_payload["root"]
        volume = np.zeros((8, 8, 8), dtype=np.float32)
        with pytest.raises(ValueError, match="voxel_size must be provided"):
            add_object(root, "test-bad-vol-obj", is_particle=True, volume=volume, voxel_size=None)

    def test_add_object_save_config_without_path_raises(self, test_payload):
        """save_config=True without config_path raises ValueError."""
        root = test_payload["root"]
        with pytest.raises(ValueError, match="config_path must be provided"):
            add_object(root, "test-save-obj", is_particle=True, save_config=True, config_path=None)

    def test_add_object_save_config(self, test_payload, tmp_path):
        """save_config=True writes configuration to disk."""
        root = test_payload["root"]
        config_path = str(tmp_path / "saved_config.json")
        add_object(
            root,
            "test-saved-obj",
            is_particle=True,
            save_config=True,
            config_path=config_path,
            exist_ok=True,
        )
        assert os.path.exists(config_path)


class TestAddObjectVolume:
    """Test cases for add_object_volume."""

    def test_add_object_volume_basic(self, test_payload):
        """Adding volume to an existing particle object succeeds."""
        root = test_payload["root"]
        add_object(root, "vol-test-particle", is_particle=True, exist_ok=True)
        volume = np.zeros((8, 8, 8), dtype=np.float32)
        obj = add_object_volume(root, "vol-test-particle", volume, 10.0)
        assert obj.name == "vol-test-particle"

    def test_add_object_volume_not_found_raises(self, test_payload):
        """Non-existent object raises ValueError."""
        root = test_payload["root"]
        volume = np.zeros((8, 8, 8), dtype=np.float32)
        with pytest.raises(ValueError, match="not found"):
            add_object_volume(root, "nonexistent-obj-xyz", volume, 10.0)

    def test_add_object_volume_not_particle_raises(self, test_payload):
        """Non-particle object raises ValueError."""
        root = test_payload["root"]
        add_object(root, "non-particle-obj", is_particle=False, exist_ok=True)
        volume = np.zeros((8, 8, 8), dtype=np.float32)
        with pytest.raises(ValueError, match="not a particle"):
            add_object_volume(root, "non-particle-obj", volume, 10.0)


class TestAddPicks:
    """Test cases for add_picks."""

    def test_add_picks_csv_direct(self, test_payload, sample_csv_picks):
        """Direct call to add_picks with CSV file succeeds."""
        root = test_payload["root"]
        picks = add_picks(
            root,
            "TS_001",
            sample_csv_picks,
            "ribosome",
            "ops-test-user",
            "ops-test-1",
            voxel_spacing=10.0,
            file_type="csv",
            exist_ok=True,
        )
        assert len(picks.points) == 2

    def test_add_picks_auto_detect_csv(self, test_payload, sample_csv_picks):
        """Auto-detection of CSV file type works."""
        root = test_payload["root"]
        picks = add_picks(
            root,
            "TS_001",
            sample_csv_picks,
            "ribosome",
            "ops-auto-user",
            "ops-auto-1",
            voxel_spacing=10.0,
            file_type=None,
            exist_ok=True,
        )
        assert len(picks.points) == 2

    def test_add_picks_unsupported_type_raises(self, test_payload, sample_csv_picks):
        """Unsupported file type raises ValueError."""
        root = test_payload["root"]
        with pytest.raises(ValueError, match="Unsupported file type"):
            add_picks(
                root,
                "TS_001",
                sample_csv_picks,
                "ribosome",
                "user",
                "1",
                voxel_spacing=10.0,
                file_type="xyz",
            )

    def test_add_picks_undetectable_extension_raises(self, test_payload, tmp_path):
        """Unrecognizable file extension raises ValueError."""
        root = test_payload["root"]
        fake_file = tmp_path / "picks.unknown"
        fake_file.write_text("some data")
        with pytest.raises(ValueError, match="Could not determine file type"):
            add_picks(root, "TS_001", str(fake_file), "ribosome", "user", "1", voxel_spacing=10.0)
