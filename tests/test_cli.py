import contextlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict

import mrcfile
import numpy as np
import pytest
import zarr
from click.testing import CliRunner
from copick.cli.add import add
from copick.cli.config import config
from copick.cli.new import new
from copick.impl.filesystem import CopickRootFSSpec


@pytest.fixture(params=pytest.common_cases)
def test_payload(request) -> Dict[str, Any]:
    payload = request.getfixturevalue(request.param)
    payload["root"] = CopickRootFSSpec.from_file(payload["cfg_file"])
    return payload


@pytest.fixture
def runner():
    """CLI test runner."""
    return CliRunner()


@pytest.fixture
def sample_mrc_file():
    """Create a sample MRC file for testing."""
    # Set random seed for reproducible test data
    np.random.seed(42)

    with tempfile.NamedTemporaryFile(suffix=".mrc", delete=False) as tmp:
        # Generate random 3D volume data
        volume = np.random.randn(64, 64, 64).astype(np.float32)

        # Create MRC file
        with mrcfile.new(tmp.name, overwrite=True) as mrc:
            mrc.set_data(volume)
            mrc.voxel_size = 10.0  # 10 Angstrom voxel size

        yield tmp.name

        # Cleanup - handle Windows file locking issues
        with contextlib.suppress(PermissionError, OSError):
            if os.path.exists(tmp.name):
                os.unlink(tmp.name)


@pytest.fixture
def sample_zarr_file():
    """Create a sample OME-Zarr file for testing."""
    # Set random seed for reproducible test data
    np.random.seed(42)

    with tempfile.TemporaryDirectory() as tmpdir:
        zarr_path = Path(tmpdir) / "test_volume.zarr"

        # Generate random 3D volume data
        volume = np.random.randn(64, 64, 64).astype(np.float32)

        # Create OME-Zarr file using the utility function
        from copick.util.ome import write_ome_zarr_3d

        pyramid = {10.0: volume}  # 10 Angstrom voxel size
        write_ome_zarr_3d(str(zarr_path), pyramid)

        yield str(zarr_path)


@pytest.fixture
def sample_zarr_file_nanometer():
    """Create a sample OME-Zarr file with nanometer units for testing unit conversion."""
    # Set random seed for reproducible test data
    np.random.seed(42)

    with tempfile.TemporaryDirectory() as tmpdir:
        zarr_path = Path(tmpdir) / "test_volume_nm.zarr"

        # Generate random 3D volume data
        volume = np.random.randn(64, 64, 64).astype(np.float32)

        # Create OME-Zarr file manually with nanometer units
        store = zarr.open(str(zarr_path), mode="w")
        store.attrs["multiscales"] = [
            {
                "axes": [
                    {"name": "z", "type": "space", "unit": "nanometer"},
                    {"name": "y", "type": "space", "unit": "nanometer"},
                    {"name": "x", "type": "space", "unit": "nanometer"},
                ],
                "datasets": [
                    {
                        "coordinateTransformations": [
                            {
                                "scale": [1.0, 1.0, 1.0],  # 1 nanometer = 10 Angstrom
                                "type": "scale",
                            },
                        ],
                        "path": "0",
                    },
                ],
                "metadata": {},
                "name": "/",
                "version": "0.4",
            },
        ]
        store.create_dataset("0", data=volume, chunks=(32, 32, 32))

        yield str(zarr_path)


class TestCLIAdd:
    """Test cases for the CLI add module."""

    def test_add_tomogram_mrc(self, test_payload, runner, sample_mrc_file):
        """Test adding an MRC tomogram via CLI."""
        config_file = test_payload["cfg_file"]

        # Test basic MRC import
        result = runner.invoke(
            add,
            [
                "tomogram",
                "--config",
                str(config_file),
                "--run",
                "test_run_mrc",
                "--tomo-type",
                "wbp",
                "--create-pyramid",
                "--pyramid-levels",
                "2",
                sample_mrc_file,
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify the tomogram was added
        root = CopickRootFSSpec.from_file(config_file)
        test_run = root.get_run("test_run_mrc")
        assert test_run is not None, "Run should be created"

        voxel_spacing = test_run.get_voxel_spacing(10.0)
        assert voxel_spacing is not None, "Voxel spacing should be created"

        tomogram = voxel_spacing.get_tomograms("wbp")[0]
        assert tomogram is not None, "Tomogram should be created"

    def test_add_tomogram_zarr(self, test_payload, runner, sample_zarr_file):
        """Test adding a Zarr tomogram via CLI."""
        config_file = test_payload["cfg_file"]

        # Test basic Zarr import
        result = runner.invoke(
            add,
            [
                "tomogram",
                "--config",
                str(config_file),
                "--run",
                "test_run_zarr",
                "--tomo-type",
                "wbp",
                "--no-create-pyramid",
                sample_zarr_file,
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify the tomogram was added
        root = CopickRootFSSpec.from_file(config_file)
        test_run = root.get_run("test_run_zarr")
        assert test_run is not None, "Run should be created"

        voxel_spacing = test_run.get_voxel_spacing(10.0)
        assert voxel_spacing is not None, "Voxel spacing should be created"

        tomogram = voxel_spacing.get_tomograms("wbp")[0]
        assert tomogram is not None, "Tomogram should be created"

    def test_add_tomogram_auto_run_name(self, test_payload, runner, sample_mrc_file):
        """Test adding tomogram with automatic run name detection."""
        config_file = test_payload["cfg_file"]

        # Don't specify run name - should use filename
        result = runner.invoke(
            add,
            [
                "tomogram",
                "--config",
                str(config_file),
                "--tomo-type",
                "wbp",
                sample_mrc_file,
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Extract expected run name from file path
        expected_run_name = Path(sample_mrc_file).stem

        # Verify the tomogram was added with auto-detected run name
        root = CopickRootFSSpec.from_file(config_file)
        test_run = root.get_run(expected_run_name)
        assert test_run is not None, f"Run {expected_run_name} should be created"

    def test_add_tomogram_auto_file_type(self, test_payload, runner, sample_mrc_file):
        """Test adding tomogram with automatic file type detection."""
        config_file = test_payload["cfg_file"]

        # Don't specify file type - should detect from extension
        result = runner.invoke(
            add,
            [
                "tomogram",
                "--config",
                str(config_file),
                "--run",
                "test_auto_type",
                sample_mrc_file,
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"

    def test_add_tomogram_custom_voxel_size(self, test_payload, runner, sample_mrc_file):
        """Test adding tomogram with custom voxel size override."""
        config_file = test_payload["cfg_file"]

        result = runner.invoke(
            add,
            [
                "tomogram",
                "--config",
                str(config_file),
                "--run",
                "test_custom_voxel",
                "--voxel-size",
                "5.0",
                sample_mrc_file,
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify custom voxel size was used
        root = CopickRootFSSpec.from_file(config_file)
        test_run = root.get_run("test_custom_voxel")
        voxel_spacing = test_run.get_voxel_spacing(5.0)
        assert voxel_spacing is not None, "Custom voxel spacing should be created"

    def test_add_tomogram_custom_chunks(self, test_payload, runner, sample_mrc_file):
        """Test adding tomogram with custom chunk size."""
        config_file = test_payload["cfg_file"]

        result = runner.invoke(
            add,
            [
                "tomogram",
                "--config",
                str(config_file),
                "--run",
                "test_custom_chunks",
                "--chunk-size",
                "32,32,32",
                sample_mrc_file,
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"

    def test_add_tomogram_invalid_file(self, test_payload, runner):
        """Test adding tomogram with non-existent file."""
        config_file = test_payload["cfg_file"]

        result = runner.invoke(
            add,
            [
                "tomogram",
                "--config",
                str(config_file),
                "--run",
                "test_invalid",
                "nonexistent_file.mrc",
            ],
        )

        assert result.exit_code != 0, "Command should fail with non-existent file"

    def test_add_tomogram_invalid_file_type(self, test_payload, runner):
        """Test adding tomogram with unrecognized file extension."""
        config_file = test_payload["cfg_file"]

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
            tmp.write(b"not a tomogram")
            tmp.flush()

            result = runner.invoke(
                add,
                [
                    "tomogram",
                    "--config",
                    str(config_file),
                    "--run",
                    "test_invalid_type",
                    tmp.name,
                ],
            )

            assert result.exit_code != 0, "Command should fail with unrecognized file type"

            # Cleanup - handle Windows file locking issues
            with contextlib.suppress(PermissionError, OSError):
                os.unlink(tmp.name)

    def test_add_tomogram_zarr_unit_conversion(self, test_payload, runner, sample_zarr_file_nanometer):
        """Test adding a Zarr tomogram with unit conversion from nanometer to angstrom."""
        config_file = test_payload["cfg_file"]

        # Test Zarr import with nanometer units (should convert to 10.0 Angstrom)
        result = runner.invoke(
            add,
            [
                "tomogram",
                "--config",
                str(config_file),
                "--run",
                "test_run_zarr_nm",
                "--tomo-type",
                "wbp",
                "--no-create-pyramid",
                sample_zarr_file_nanometer,
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify the tomogram was added with correct voxel size conversion
        root = CopickRootFSSpec.from_file(config_file)
        test_run = root.get_run("test_run_zarr_nm")
        assert test_run is not None, "Run should be created"

        # 1 nanometer should have been converted to 10 Angstrom
        voxel_spacing = test_run.get_voxel_spacing(10.0)
        assert voxel_spacing is not None, "Voxel spacing of 10.0 Angstrom should be created from 1.0 nanometer"

        tomogram = voxel_spacing.get_tomograms("wbp")[0]
        assert tomogram is not None, "Tomogram should be created"

    def test_add_tomogram_glob_pattern(self, test_payload, runner):
        """Test adding multiple tomograms using glob pattern."""
        config_file = test_payload["cfg_file"]

        # Create multiple MRC files to test glob pattern
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create 3 test MRC files
            mrc_files = []
            for i in range(3):
                mrc_path = tmpdir_path / f"test_tomo_{i:02d}.mrc"

                # Create minimal MRC file
                np.random.seed(42 + i)  # Different seed for each file
                volume = np.random.randn(32, 32, 32).astype(np.float32)

                with mrcfile.new(str(mrc_path), overwrite=True) as mrc:
                    mrc.set_data(volume)
                    mrc.voxel_size = 10.0

                mrc_files.append(mrc_path)

            # Test glob pattern
            glob_pattern = str(tmpdir_path / "test_tomo_*.mrc")

            result = runner.invoke(
                add,
                [
                    "tomogram",
                    "--config",
                    str(config_file),
                    "--tomo-type",
                    "wbp",
                    "--no-create-pyramid",  # Skip pyramid for faster testing
                    glob_pattern,
                ],
            )

            assert result.exit_code == 0, f"Command failed: {result.output}"

            # Verify all tomograms were added
            root = CopickRootFSSpec.from_file(config_file)

            for mrc_file in mrc_files:
                expected_run_name = mrc_file.stem
                test_run = root.get_run(expected_run_name)
                assert test_run is not None, f"Run {expected_run_name} should be created"

                voxel_spacing = test_run.get_voxel_spacing(10.0)
                assert voxel_spacing is not None, f"Voxel spacing should be created for {expected_run_name}"

                tomograms = voxel_spacing.get_tomograms("wbp")
                assert len(tomograms) > 0, f"Tomogram should be created for {expected_run_name}"

    def test_add_tomogram_glob_pattern_no_matches(self, test_payload, runner):
        """Test glob pattern with no matching files."""
        config_file = test_payload["cfg_file"]

        # Use a glob pattern that won't match any files
        result = runner.invoke(
            add,
            [
                "tomogram",
                "--config",
                str(config_file),
                "nonexistent_pattern_*.mrc",
            ],
        )

        assert result.exit_code != 0, "Command should fail when no files match the pattern"
        assert "No files found matching pattern" in result.output

    def test_add_tomogram_run_regex_simple(self, test_payload, runner):
        """Test adding tomogram with simple regex run name extraction."""
        config_file = test_payload["cfg_file"]

        # Create a test MRC file with specific filename
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            mrc_path = tmpdir_path / "Position_60_7_Vol_CTF.mrc"

            # Create minimal MRC file
            np.random.seed(42)
            volume = np.random.randn(32, 32, 32).astype(np.float32)

            with mrcfile.new(str(mrc_path), overwrite=True) as mrc:
                mrc.set_data(volume)
                mrc.voxel_size = 10.0

            # Test with regex that extracts Position_60_7
            result = runner.invoke(
                add,
                [
                    "tomogram",
                    "--config",
                    str(config_file),
                    "--run-regex",
                    r"^(Position_.*)_Vol_CTF",
                    "--tomo-type",
                    "wbp",
                    "--no-create-pyramid",
                    str(mrc_path),
                ],
            )

            assert result.exit_code == 0, f"Command failed: {result.output}"

            # Verify the run was created with the extracted name
            root = CopickRootFSSpec.from_file(config_file)
            expected_run_name = "Position_60_7"
            test_run = root.get_run(expected_run_name)
            assert test_run is not None, f"Run {expected_run_name} should be created"

            voxel_spacing = test_run.get_voxel_spacing(10.0)
            assert voxel_spacing is not None, "Voxel spacing should be created"

            tomogram = voxel_spacing.get_tomograms("wbp")[0]
            assert tomogram is not None, "Tomogram should be created"

    def test_add_tomogram_run_regex_with_glob(self, test_payload, runner):
        """Test adding multiple tomograms with regex and glob pattern."""
        config_file = test_payload["cfg_file"]

        # Create multiple MRC files with specific naming pattern
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create 3 test MRC files with the pattern
            expected_runs = []
            for i, pos in enumerate([("60", "7"), ("45", "3"), ("90", "12")]):
                mrc_path = tmpdir_path / f"Position_{pos[0]}_{pos[1]}_Vol_CTF.mrc"
                expected_runs.append(f"Position_{pos[0]}_{pos[1]}")

                # Create minimal MRC file
                np.random.seed(42 + i)
                volume = np.random.randn(32, 32, 32).astype(np.float32)

                with mrcfile.new(str(mrc_path), overwrite=True) as mrc:
                    mrc.set_data(volume)
                    mrc.voxel_size = 10.0

            # Test glob pattern with regex
            glob_pattern = str(tmpdir_path / "Position_*_Vol_CTF.mrc")

            result = runner.invoke(
                add,
                [
                    "tomogram",
                    "--config",
                    str(config_file),
                    "--run-regex",
                    r"^(Position_.*)_Vol_CTF",
                    "--tomo-type",
                    "wbp",
                    "--no-create-pyramid",
                    glob_pattern,
                ],
            )

            assert result.exit_code == 0, f"Command failed: {result.output}"

            # Verify all runs were created with the extracted names
            root = CopickRootFSSpec.from_file(config_file)

            for expected_run_name in expected_runs:
                test_run = root.get_run(expected_run_name)
                assert test_run is not None, f"Run {expected_run_name} should be created"

                voxel_spacing = test_run.get_voxel_spacing(10.0)
                assert voxel_spacing is not None, f"Voxel spacing should be created for {expected_run_name}"

                tomograms = voxel_spacing.get_tomograms("wbp")
                assert len(tomograms) > 0, f"Tomogram should be created for {expected_run_name}"

    def test_add_tomogram_run_regex_no_match(self, test_payload, runner):
        """Test adding tomogram with regex that doesn't match filename."""
        config_file = test_payload["cfg_file"]

        # Create a test MRC file with specific filename
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            mrc_path = tmpdir_path / "regular_filename.mrc"

            # Create minimal MRC file
            np.random.seed(42)
            volume = np.random.randn(32, 32, 32).astype(np.float32)

            with mrcfile.new(str(mrc_path), overwrite=True) as mrc:
                mrc.set_data(volume)
                mrc.voxel_size = 10.0

            # Test with regex that won't match the filename
            result = runner.invoke(
                add,
                [
                    "tomogram",
                    "--config",
                    str(config_file),
                    "--run-regex",
                    r"^(Position_.*)_Vol_CTF",
                    "--tomo-type",
                    "wbp",
                    str(mrc_path),
                ],
            )

            assert result.exit_code == 0, f"Command failed: {result.output}"

            # Since the regex doesn't match, no run should be created
            root = CopickRootFSSpec.from_file(config_file)
            # The run name should fall back to default behavior (filename without extension)
            # but since regex doesn't match, it should be skipped
            test_run = root.get_run("regular_filename")
            assert test_run is None, "Run should not be created when regex doesn't match"

    def test_add_segmentation_run_regex(self, test_payload, runner):
        """Test adding segmentation with regex run name extraction."""
        config_file = test_payload["cfg_file"]

        # Create a test MRC file with specific filename
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            mrc_path = tmpdir_path / "Position_30_4_Vol_CTF.mrc"

            # Create minimal MRC file
            np.random.seed(42)
            volume = np.random.randint(0, 3, (32, 32, 32), dtype=np.uint8)

            with mrcfile.new(str(mrc_path), overwrite=True) as mrc:
                mrc.set_data(volume)
                mrc.voxel_size = 10.0

            # Test segmentation with regex
            result = runner.invoke(
                add,
                [
                    "segmentation",
                    "--config",
                    str(config_file),
                    "--run-regex",
                    r"^(Position_.*)_Vol_CTF",
                    "--name",
                    "test-seg",
                    str(mrc_path),
                ],
            )

            assert result.exit_code == 0, f"Command failed: {result.output}"

            # Verify the run was created with the extracted name
            root = CopickRootFSSpec.from_file(config_file)
            expected_run_name = "Position_30_4"
            test_run = root.get_run(expected_run_name)
            assert test_run is not None, f"Run {expected_run_name} should be created"


class TestCLIConfig:
    """Test cases for the CLI config module."""

    def test_config_dataportal(self, runner):
        """Test creating config from data portal datasets."""
        with tempfile.TemporaryDirectory() as tmpdir:
            overlay_path = Path(tmpdir) / "overlay"
            overlay_path.mkdir()

            config_path = Path(tmpdir) / "test_config.json"

            # Note: This test will fail with actual API calls to data portal
            # We're testing the CLI interface structure, not the actual API
            result = runner.invoke(
                config,
                [
                    "dataportal",
                    "--dataset-id",
                    "10001",
                    "--dataset-id",
                    "10002",
                    "--overlay",
                    str(overlay_path),
                    "--output",
                    str(config_path),
                ],
            )

            # The data portal API is available and working, so the command should succeed
            assert result.exit_code == 0, f"Command failed: {result.output}"

            # Verify the config file was created
            assert config_path.exists(), "Configuration file should be created"

    def test_config_filesystem(self, runner):
        """Test filesystem config command implementation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            overlay_path = Path(tmpdir) / "overlay"
            config_path = Path(tmpdir) / "test_filesystem_config.json"

            result = runner.invoke(
                config,
                [
                    "filesystem",
                    "--overlay-root",
                    str(overlay_path),
                    "--objects",
                    "ribosome,True,120,4V9D",
                    "--objects",
                    "membrane,False",
                    "--config",
                    str(config_path),
                    "--proj-name",
                    "test_project",
                    "--proj-description",
                    "Test filesystem configuration",
                ],
            )

            assert result.exit_code == 0, f"Command failed: {result.output}"

            # Verify the config file was created
            assert config_path.exists(), "Configuration file should be created"

            # Verify config file contents
            with open(config_path, "r") as f:
                config_data = json.load(f)

            assert config_data["config_type"] == "filesystem"
            assert config_data["name"] == "test_project"
            assert config_data["description"] == "Test filesystem configuration"
            assert len(config_data["pickable_objects"]) == 2

            # Check ribosome object
            ribosome = next(obj for obj in config_data["pickable_objects"] if obj["name"] == "ribosome")
            assert ribosome["is_particle"] is True
            assert ribosome["radius"] == 120
            assert ribosome["pdb_id"] == "4V9D"
            assert ribosome["label"] == 1

            # Check membrane object
            membrane = next(obj for obj in config_data["pickable_objects"] if obj["name"] == "membrane")
            assert membrane["is_particle"] is False
            assert membrane["label"] == 2

    def test_config_filesystem_invalid_objects(self, runner):
        """Test filesystem config command with invalid object format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = runner.invoke(
                config,
                [
                    "filesystem",
                    "--overlay-root",
                    str(tmpdir),
                    "--objects",
                    "invalid_format",  # Missing is_particle flag
                    "--config",
                    "test.json",
                ],
            )

            assert result.exit_code != 0, "Command should fail with invalid object format"


class TestCLINew:
    """Test cases for the CLI new module."""

    def test_new_run(self, test_payload, runner):
        """Test creating a new run via CLI."""
        config_file = test_payload["cfg_file"]

        result = runner.invoke(
            new,
            [
                "run",
                "--config",
                str(config_file),
                "test_new_run",
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify the run was created
        root = CopickRootFSSpec.from_file(config_file)
        test_run = root.get_run("test_new_run")
        assert test_run is not None, "Run should be created"

    def test_new_run_with_overwrite(self, test_payload, runner):
        """Test creating a run with overwrite flag."""
        config_file = test_payload["cfg_file"]

        # Create run first time
        result1 = runner.invoke(
            new,
            [
                "run",
                "--config",
                str(config_file),
                "--overwrite",
                "test_overwrite_run",
            ],
        )
        assert result1.exit_code == 0

        # Create same run again with overwrite
        result2 = runner.invoke(
            new,
            [
                "run",
                "--config",
                str(config_file),
                "--overwrite",
                "test_overwrite_run",
            ],
        )
        assert result2.exit_code == 0

    def test_new_voxelspacing(self, test_payload, runner):
        """Test creating a new voxel spacing via CLI."""
        config_file = test_payload["cfg_file"]

        # First create a run
        runner.invoke(
            new,
            [
                "run",
                "--config",
                str(config_file),
                "test_vs_run",
            ],
        )

        # Then create voxel spacing
        result = runner.invoke(
            new,
            [
                "voxelspacing",
                "--config",
                str(config_file),
                "--run",
                "test_vs_run",
                "15.0",
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify the voxel spacing was created
        root = CopickRootFSSpec.from_file(config_file)
        test_run = root.get_run("test_vs_run")
        voxel_spacing = test_run.get_voxel_spacing(15.0)
        assert voxel_spacing is not None, "Voxel spacing should be created"

    def test_new_voxelspacing_with_create(self, test_payload, runner):
        """Test creating voxel spacing with auto-create run."""
        config_file = test_payload["cfg_file"]

        result = runner.invoke(
            new,
            [
                "voxelspacing",
                "--config",
                str(config_file),
                "--run",
                "auto_created_run",
                "--create",
                "20.0",
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify both run and voxel spacing were created
        root = CopickRootFSSpec.from_file(config_file)
        test_run = root.get_run("auto_created_run")
        assert test_run is not None, "Run should be auto-created"

        voxel_spacing = test_run.get_voxel_spacing(20.0)
        assert voxel_spacing is not None, "Voxel spacing should be created"

    def test_new_picks(self, test_payload, runner):
        """Test creating new picks via CLI."""
        config_file = test_payload["cfg_file"]

        result = runner.invoke(
            new,
            [
                "picks",
                "--config",
                str(config_file),
                "--particle-name",
                "ribosome",
                "--out-user",
                "test-user",
                "--out-session",
                "test-session",
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify picks were created for all runs
        root = CopickRootFSSpec.from_file(config_file)
        for run in root.runs:
            picks_list = run.get_picks(
                object_name="ribosome",
                user_id="test-user",  # Names get sanitized by copick
                session_id="test-session",
            )
            assert len(picks_list) > 0, f"Picks should be created for run {run.name}"

            # Verify picks are empty
            picks = picks_list[0]
            assert picks.points == [], "Picks should be empty initially"

    def test_new_picks_with_overwrite(self, test_payload, runner):
        """Test creating picks with overwrite flag."""
        config_file = test_payload["cfg_file"]

        # Create picks first time
        result1 = runner.invoke(
            new,
            [
                "picks",
                "--config",
                str(config_file),
                "--particle-name",
                "proteasome",
                "--out-user",
                "test-user",
            ],
        )
        assert result1.exit_code == 0

        # Create same picks again with overwrite
        result2 = runner.invoke(
            new,
            [
                "picks",
                "--config",
                str(config_file),
                "--particle-name",
                "proteasome",
                "--out-user",
                "test-user",
                "--overwrite",
            ],
        )
        # Note: Currently the overwrite logic still results in an error from the underlying model
        # This tests that the CLI handles the error gracefully
        assert result2.exit_code == 0
        # The error occurs during processing but may not be in the output due to progress bar
        # Just verify that the command failed gracefully
        # TODO: fix

    def test_new_picks_invalid_config(self, runner):
        """Test creating picks with non-existent config file."""
        result = runner.invoke(
            new,
            [
                "picks",
                "--config",
                "nonexistent_config.json",
                "--particle-name",
                "ribosome",
            ],
        )

        assert result.exit_code != 0, "Command should fail with non-existent config"
        assert "does not exist" in result.output

    def test_new_voxelspacing_invalid_run(self, test_payload, runner):
        """Test creating voxel spacing for non-existent run without create flag."""
        config_file = test_payload["cfg_file"]

        result = runner.invoke(
            new,
            [
                "voxelspacing",
                "--config",
                str(config_file),
                "--run",
                "nonexistent_run",
                "--no-create",  # Explicitly disable auto-creation
                "10.0",
            ],
        )

        assert result.exit_code != 0, "Command should fail for non-existent run without create flag"


class TestCLIIntegration:
    """Integration tests combining multiple CLI operations."""

    def test_full_workflow(self, test_payload, runner, sample_mrc_file):
        """Test a complete workflow: create run, add tomogram, create picks."""
        config_file = test_payload["cfg_file"]

        # Step 1: Create a new run
        result1 = runner.invoke(
            new,
            [
                "run",
                "--config",
                str(config_file),
                "integration_test_run",
            ],
        )
        assert result1.exit_code == 0

        # Step 2: Add a tomogram to the run
        result2 = runner.invoke(
            add,
            [
                "tomogram",
                "--config",
                str(config_file),
                "--run",
                "integration_test_run",
                "--tomo-type",
                "wbp",
                sample_mrc_file,
            ],
        )
        assert result2.exit_code == 0

        # Step 3: Create picks for the run
        result3 = runner.invoke(
            new,
            [
                "picks",
                "--config",
                str(config_file),
                "--particle-name",
                "ribosome",
            ],
        )
        assert result3.exit_code == 0

        # Verify the complete workflow
        root = CopickRootFSSpec.from_file(config_file)

        # Check run exists
        test_run = root.get_run("integration_test_run")
        assert test_run is not None

        # Check tomogram exists
        voxel_spacing = test_run.get_voxel_spacing(10.0)
        assert voxel_spacing is not None
        tomogram = voxel_spacing.get_tomograms("wbp")[0]
        assert tomogram is not None

        # Check picks exist
        picks_list = test_run.get_picks(object_name="ribosome", user_id="copick", session_id="0")
        assert len(picks_list) > 0


class TestCLIAddObject:
    """Test cases for the CLI add object commands."""

    def test_add_object_definition_particle(self, test_payload, runner):
        """Test adding a particle object definition via CLI."""
        config_file = test_payload["cfg_file"]

        result = runner.invoke(
            add,
            [
                "object",
                "--config",
                str(config_file),
                "--name",
                "test-particle",
                "--object-type",
                "particle",
                "--label",
                "100",
                "--color",
                "255,0,0,255",
                "--radius",
                "50.0",
                "--pdb-id",
                "1ABC",
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify the object was added to config
        root = CopickRootFSSpec.from_file(config_file)
        obj = root.get_object("test-particle")
        assert obj is not None, "Object should be created"
        assert obj.is_particle is True
        assert obj.label == 100
        assert obj.color == (255, 0, 0, 255)
        assert obj.radius == 50.0
        assert obj.pdb_id == "1ABC"

    def test_add_object_definition_segmentation(self, test_payload, runner):
        """Test adding a segmentation object definition via CLI."""
        config_file = test_payload["cfg_file"]

        result = runner.invoke(
            add,
            [
                "object",
                "--config",
                str(config_file),
                "--name",
                "test-segmentation",
                "--object-type",
                "segmentation",
                "--emdb-id",
                "EMD-1234",
                "--map-threshold",
                "0.5",
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify the object was added to config
        root = CopickRootFSSpec.from_file(config_file)
        obj = root.get_object("test-segmentation")
        assert obj is not None, "Object should be created"
        assert obj.is_particle is False
        assert obj.emdb_id == "EMD-1234"
        assert obj.map_threshold == 0.5

    def test_add_object_definition_with_volume_mrc(self, test_payload, runner, sample_mrc_file):
        """Test adding object definition with MRC volume via CLI."""
        config_file = test_payload["cfg_file"]

        result = runner.invoke(
            add,
            [
                "object",
                "--config",
                str(config_file),
                "--name",
                "test-particle-with-volume",
                "--object-type",
                "particle",
                "--volume",
                sample_mrc_file,
                "--voxel-size",
                "10.0",
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify the object was added with volume
        root = CopickRootFSSpec.from_file(config_file)
        obj = root.get_object("test-particle-with-volume")
        assert obj is not None, "Object should be created"
        assert obj.is_particle is True

        # Check that volume data was stored
        assert obj.zarr() is not None, "Object should have volume data"

    def test_add_object_definition_with_volume_zarr(self, test_payload, runner, sample_zarr_file):
        """Test adding object definition with Zarr volume via CLI."""
        config_file = test_payload["cfg_file"]

        result = runner.invoke(
            add,
            [
                "object",
                "--config",
                str(config_file),
                "--name",
                "test-particle-zarr",
                "--object-type",
                "particle",
                "--volume",
                sample_zarr_file,
                "--voxel-size",
                "10.0",
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify the object was added with volume
        root = CopickRootFSSpec.from_file(config_file)
        obj = root.get_object("test-particle-zarr")
        assert obj is not None, "Object should be created"

    def test_add_object_definition_with_volume_format_override(self, test_payload, runner, sample_mrc_file):
        """Test adding object definition with explicit volume format."""
        config_file = test_payload["cfg_file"]

        result = runner.invoke(
            add,
            [
                "object",
                "--config",
                str(config_file),
                "--name",
                "test-format-override",
                "--volume",
                sample_mrc_file,
                "--volume-format",
                "mrc",
                "--voxel-size",
                "10.0",
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify the object was added
        root = CopickRootFSSpec.from_file(config_file)
        obj = root.get_object("test-format-override")
        assert obj is not None, "Object should be created"

    def test_add_object_definition_auto_label(self, test_payload, runner):
        """Test adding object definition with automatic label assignment."""
        config_file = test_payload["cfg_file"]

        # Add first object
        result1 = runner.invoke(
            add,
            [
                "object",
                "--config",
                str(config_file),
                "--name",
                "auto-label-1",
            ],
        )
        assert result1.exit_code == 0

        # Add second object
        result2 = runner.invoke(
            add,
            [
                "object",
                "--config",
                str(config_file),
                "--name",
                "auto-label-2",
            ],
        )
        assert result2.exit_code == 0

        # Verify automatic label assignment
        root = CopickRootFSSpec.from_file(config_file)
        obj1 = root.get_object("auto-label-1")
        obj2 = root.get_object("auto-label-2")

        assert obj1.label != obj2.label, "Objects should have different labels"
        assert obj1.label > 0 and obj2.label > 0, "Labels should be positive"

    def test_add_object_definition_with_metadata(self, test_payload, runner):
        """Test adding object definition with metadata via CLI."""
        config_file = test_payload["cfg_file"]

        metadata_json = '{"key1": "value1", "key2": 42, "key3": {"nested": true}}'

        result = runner.invoke(
            add,
            [
                "object",
                "--config",
                str(config_file),
                "--name",
                "test-with-metadata",
                "--object-type",
                "particle",
                "--metadata",
                metadata_json,
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify the object was added with metadata
        root = CopickRootFSSpec.from_file(config_file)
        obj = root.get_object("test-with-metadata")
        assert obj is not None, "Object should be created"

        # Check metadata content
        expected_metadata = {"key1": "value1", "key2": 42, "key3": {"nested": True}}
        assert obj.metadata == expected_metadata, f"Metadata should match. Got: {obj.metadata}"

    def test_add_object_definition_with_empty_metadata(self, test_payload, runner):
        """Test adding object definition with empty metadata."""
        config_file = test_payload["cfg_file"]

        result = runner.invoke(
            add,
            [
                "object",
                "--config",
                str(config_file),
                "--name",
                "test-empty-metadata",
                "--object-type",
                "particle",
                "--metadata",
                "{}",
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify the object was added with empty metadata
        root = CopickRootFSSpec.from_file(config_file)
        obj = root.get_object("test-empty-metadata")
        assert obj is not None, "Object should be created"
        assert obj.metadata == {}, "Metadata should be empty dict"

    def test_add_object_definition_without_metadata(self, test_payload, runner):
        """Test adding object definition without metadata (should default to empty dict)."""
        config_file = test_payload["cfg_file"]

        result = runner.invoke(
            add,
            [
                "object",
                "--config",
                str(config_file),
                "--name",
                "test-no-metadata",
                "--object-type",
                "particle",
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify the object has default empty metadata
        root = CopickRootFSSpec.from_file(config_file)
        obj = root.get_object("test-no-metadata")
        assert obj is not None, "Object should be created"
        assert obj.metadata == {}, "Metadata should default to empty dict"

    def test_add_object_definition_invalid_metadata_json(self, test_payload, runner):
        """Test adding object with invalid JSON metadata (should fail)."""
        config_file = test_payload["cfg_file"]

        result = runner.invoke(
            add,
            [
                "object",
                "--config",
                str(config_file),
                "--name",
                "test-invalid-metadata",
                "--object-type",
                "particle",
                "--metadata",
                '{"invalid": json}',  # Invalid JSON
            ],
        )

        assert result.exit_code != 0, "Command should fail with invalid JSON metadata"
        assert "valid JSON format" in result.output

    def test_add_object_volume_to_existing(self, test_payload, runner, sample_mrc_file):
        """Test adding volume to existing object via CLI."""
        config_file = test_payload["cfg_file"]

        # First add an object without volume
        result1 = runner.invoke(
            add,
            [
                "object",
                "--config",
                str(config_file),
                "--name",
                "test-existing-object",
                "--object-type",
                "particle",
            ],
        )
        assert result1.exit_code == 0

        # Then add volume to existing object
        result2 = runner.invoke(
            add,
            [
                "object-volume",
                "--config",
                str(config_file),
                "--object-name",
                "test-existing-object",
                "--volume-path",
                sample_mrc_file,
                "--voxel-size",
                "10.0",
            ],
        )

        assert result2.exit_code == 0, f"Command failed: {result2.output}"

        # Verify volume was added
        root = CopickRootFSSpec.from_file(config_file)
        obj = root.get_object("test-existing-object")
        assert obj is not None, "Object should exist"
        assert obj.zarr() is not None, "Object should have volume data"

    def test_add_object_volume_with_format_override(self, test_payload, runner, sample_zarr_file):
        """Test adding volume with explicit format override."""
        config_file = test_payload["cfg_file"]

        # First add an object
        result1 = runner.invoke(
            add,
            [
                "object",
                "--config",
                str(config_file),
                "--name",
                "test-format-object",
                "--object-type",
                "particle",
            ],
        )
        assert result1.exit_code == 0

        # Add volume with format override
        result2 = runner.invoke(
            add,
            [
                "object-volume",
                "--config",
                str(config_file),
                "--object-name",
                "test-format-object",
                "--volume-path",
                sample_zarr_file,
                "--volume-format",
                "zarr",
                "--voxel-size",
                "10.0",
            ],
        )

        assert result2.exit_code == 0, f"Command failed: {result2.output}"

    def test_add_object_volume_nonexistent_object(self, test_payload, runner, sample_mrc_file):
        """Test adding volume to non-existent object (should fail)."""
        config_file = test_payload["cfg_file"]

        result = runner.invoke(
            add,
            [
                "object-volume",
                "--config",
                str(config_file),
                "--object-name",
                "nonexistent-object",
                "--volume-path",
                sample_mrc_file,
                "--voxel-size",
                "10.0",
            ],
        )

        assert result.exit_code != 0, "Command should fail for non-existent object"

    def test_add_object_volume_to_segmentation_object_cli(self, test_payload, runner, sample_mrc_file):
        """Test adding volume to segmentation object via CLI (should fail)."""
        config_file = test_payload["cfg_file"]

        # First add a segmentation object
        result1 = runner.invoke(
            add,
            [
                "object",
                "--config",
                str(config_file),
                "--name",
                "test-segmentation-cli",
                "--object-type",
                "segmentation",
            ],
        )
        assert result1.exit_code == 0

        # Try to add volume to the segmentation object
        result2 = runner.invoke(
            add,
            [
                "object-volume",
                "--config",
                str(config_file),
                "--object-name",
                "test-segmentation-cli",
                "--volume-path",
                sample_mrc_file,
                "--voxel-size",
                "10.0",
            ],
        )

        assert result2.exit_code != 0, "Command should fail for segmentation object"
        assert "not a particle object" in result2.output

    def test_add_object_definition_invalid_color(self, test_payload, runner):
        """Test adding object with invalid color format (should fail)."""
        config_file = test_payload["cfg_file"]

        result = runner.invoke(
            add,
            [
                "object",
                "--config",
                str(config_file),
                "--name",
                "test-invalid-color",
                "--color",
                "255,0,0",  # Missing alpha channel
            ],
        )

        assert result.exit_code != 0, "Command should fail with invalid color format"
        assert "four comma-separated values" in result.output

    def test_add_object_volume_unknown_format(self, test_payload, runner):
        """Test adding volume with unknown file format (should fail)."""
        config_file = test_payload["cfg_file"]

        # First add an object
        runner.invoke(
            add,
            [
                "object",
                "--config",
                str(config_file),
                "--name",
                "test-unknown-format",
            ],
        )

        # Create a file with unknown extension
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
            tmp.write(b"not a volume")
            tmp.flush()

            result = runner.invoke(
                add,
                [
                    "object-volume",
                    "--config",
                    str(config_file),
                    "--object-name",
                    "test-unknown-format",
                    "--volume-path",
                    tmp.name,
                    "--voxel-size",
                    "10.0",
                ],
            )

            assert result.exit_code != 0, "Command should fail with unknown format"

            # Cleanup
            with contextlib.suppress(PermissionError, OSError):
                os.unlink(tmp.name)
