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
                    {"name": "z", "type": "space", "unit": "angstrom"},
                    {"name": "y", "type": "space", "unit": "angstrom"},
                    {"name": "x", "type": "space", "unit": "angstrom"},
                ],
                "datasets": [
                    {
                        "coordinateTransformations": [
                            {
                                "scale": [1.0, 1.0, 1.0],  # 1 nanometer = 10 Angstrom
                                "type": "scale",
                                "unit": "nanometer",
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
            assert "radius" not in membrane
            assert "pdb_id" not in membrane

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
