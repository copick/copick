"""Tests for import/export functionality."""

import contextlib
import os
import tempfile
from pathlib import Path
from typing import Any, Dict

import copick
import emfile
import numpy as np
import pytest
import tifffile
from click.testing import CliRunner
from copick.cli.add import add
from copick.cli.export import export


@pytest.fixture(params=pytest.common_cases)
def test_payload(request) -> Dict[str, Any]:
    payload = request.getfixturevalue(request.param)
    payload["root"] = copick.from_file(payload["cfg_file"])
    return payload


@pytest.fixture
def runner():
    """CLI test runner."""
    return CliRunner()


@pytest.fixture
def sample_csv_picks():
    """Create a sample CSV picks file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as tmp:
        # Write header - must use transform_{i}{j} column names to match copick CSV format
        header = "run_name,x,y,z,transform_00,transform_01,transform_02,transform_03,transform_10,transform_11,transform_12,transform_13,transform_20,transform_21,transform_22,transform_23,transform_30,transform_31,transform_32,transform_33,score,instance_id\n"
        tmp.write(header)
        # Write sample data - identity matrices
        tmp.write("TS_001,100.0,200.0,300.0,1.0,0.0,0.0,0.0,0.0,1.0,0.0,0.0,0.0,0.0,1.0,0.0,0.0,0.0,0.0,1.0,0.95,1\n")
        tmp.write("TS_001,150.0,250.0,350.0,1.0,0.0,0.0,0.0,0.0,1.0,0.0,0.0,0.0,0.0,1.0,0.0,0.0,0.0,0.0,1.0,0.87,2\n")
        tmp.flush()
        yield tmp.name

    with contextlib.suppress(PermissionError, OSError):
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)


@pytest.fixture
def sample_em_file():
    """Create a sample EM motivelist file for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        em_path = Path(tmpdir) / "motivelist.em"
        # Create a simple EM motivelist (20 x N array format)
        # emfile requires 3D array, so we use shape (1, 20, n_particles)
        # See TOM toolbox documentation for motivelist format
        n_particles = 3
        data = np.zeros((1, 20, n_particles), dtype=np.float32)

        # Set positions (columns 8, 9, 10 in 1-indexed, so 7, 8, 9 in 0-indexed)
        data[0, 7, :] = [10.0, 20.0, 30.0]  # X positions in pixels
        data[0, 8, :] = [15.0, 25.0, 35.0]  # Y positions in pixels
        data[0, 9, :] = [20.0, 30.0, 40.0]  # Z positions in pixels

        # Set Euler angles (columns 17, 18, 19 in 1-indexed)
        data[0, 16, :] = [0.0, 0.0, 0.0]  # Phi
        data[0, 17, :] = [0.0, 0.0, 0.0]  # Psi
        data[0, 18, :] = [0.0, 0.0, 0.0]  # Theta

        # Set class/tomogram number
        data[0, 4, :] = [1, 1, 1]  # Tomogram number

        emfile.write(str(em_path), data)
        yield str(em_path)


@pytest.fixture
def sample_dynamo_table():
    """Create a sample Dynamo table file for testing."""
    import dynamotable
    import pandas as pd

    with tempfile.NamedTemporaryFile(suffix=".tbl", delete=False) as tmp:
        # Create DataFrame with proper Dynamo column structure using dynamotable
        # This ensures the format is always compatible with dynamotable.read()
        df = pd.DataFrame(
            {
                "tag": [1, 2],
                "aligned": [0, 0],
                "averaged": [0, 0],
                "dx": [0.0, 0.0],
                "dy": [0.0, 0.0],
                "dz": [0.0, 0.0],
                "tdrot": [0.0, 0.0],
                "tilt": [0.0, 0.0],
                "narot": [0.0, 0.0],
                "cc": [0.0, 0.0],
                "x": [10.0, 20.0],
                "y": [15.0, 25.0],
                "z": [20.0, 30.0],
                "tomo": [1, 1],  # All particles in same tomogram
            },
        )
        dynamotable.write(df, tmp.name)
        yield tmp.name

    with contextlib.suppress(PermissionError, OSError):
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)


@pytest.fixture
def sample_star_file():
    """Create a sample STAR file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".star", delete=False, mode="w") as tmp:
        # Create minimal STAR file
        content = """
data_particles

loop_
_rlnCoordinateX #1
_rlnCoordinateY #2
_rlnCoordinateZ #3
_rlnAngleRot #4
_rlnAngleTilt #5
_rlnAnglePsi #6
10.0 15.0 20.0 0.0 0.0 0.0
20.0 25.0 30.0 0.0 0.0 0.0
30.0 35.0 40.0 0.0 0.0 0.0
"""
        tmp.write(content)
        tmp.flush()
        yield tmp.name

    with contextlib.suppress(PermissionError, OSError):
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)


@pytest.fixture
def sample_tiff_volume():
    """Create a sample TIFF stack for testing."""
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
        np.random.seed(42)
        volume = np.random.randn(32, 32, 32).astype(np.float32)
        tifffile.imwrite(tmp.name, volume)
        yield tmp.name

    with contextlib.suppress(PermissionError, OSError):
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)


@pytest.fixture
def sample_index_map():
    """Create a sample index map CSV file for testing (comma-separated, no header)."""
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as tmp:
        # Format: index,run_name (comma or tab separated, no header)
        tmp.write("1,TS_001\n")
        tmp.write("2,TS_002\n")
        tmp.write("3,TS_003\n")
        tmp.flush()
        yield tmp.name

    with contextlib.suppress(PermissionError, OSError):
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)


@pytest.fixture
def sample_star_with_tomo_name():
    """Create a sample STAR file with _rlnTomoName column for testing."""
    with tempfile.NamedTemporaryFile(suffix=".star", delete=False, mode="w") as tmp:
        content = """
data_particles

loop_
_rlnCoordinateX #1
_rlnCoordinateY #2
_rlnCoordinateZ #3
_rlnAngleRot #4
_rlnAngleTilt #5
_rlnAnglePsi #6
_rlnTomoName #7
10.0 15.0 20.0 0.0 0.0 0.0 TS_001
20.0 25.0 30.0 0.0 0.0 0.0 TS_001
30.0 35.0 40.0 0.0 0.0 0.0 TS_002
"""
        tmp.write(content)
        tmp.flush()
        yield tmp.name

    with contextlib.suppress(PermissionError, OSError):
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)


@pytest.fixture
def sample_relion5_star_files():
    """Create RELION 5.0 STAR files with centered Angstrom coordinates for testing.

    Creates:
    1. A particles STAR file with _rlnCenteredCoordinateXAngst/YAngst/ZAngst columns
    2. A tomograms STAR file with tomogram dimensions for coordinate conversion
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        # Tomogram dimensions (in pixels, at 1.0 Angstrom pixel size)
        # For simplicity: 100x100x100 tomogram with 1.0 Angstrom pixel size
        # Center: 50, 50, 50 pixels = 50, 50, 50 Angstrom
        tomo_size_x, tomo_size_y, tomo_size_z = 100, 100, 100
        pixel_size = 1.0
        binning = 4.0  # does not enter the centre: rlnTomoSize is in (unbinned) tilt-series pixels

        # Create particles STAR file with RELION 5.0 centered coordinates
        particles_path = Path(tmpdir) / "particles_relion5.star"
        particles_content = """
data_particles

loop_
_rlnCenteredCoordinateXAngst #1
_rlnCenteredCoordinateYAngst #2
_rlnCenteredCoordinateZAngst #3
_rlnAngleRot #4
_rlnAngleTilt #5
_rlnAnglePsi #6
_rlnTomoName #7
-40.0 -35.0 -30.0 0.0 0.0 0.0 TS_relion5_001
-30.0 -25.0 -20.0 0.0 0.0 0.0 TS_relion5_001
-20.0 -15.0 -10.0 0.0 0.0 0.0 TS_relion5_002
"""
        particles_path.write_text(particles_content)

        # Create tomograms STAR file with dimensions for coordinate conversion
        tomograms_path = Path(tmpdir) / "tomograms_relion5.star"
        tomograms_content = f"""
data_global

loop_
_rlnTomoName #1
_rlnTomoSizeX #2
_rlnTomoSizeY #3
_rlnTomoSizeZ #4
_rlnTomoTiltSeriesPixelSize #5
_rlnTomoTomogramBinning #6
TS_relion5_001 {tomo_size_x} {tomo_size_y} {tomo_size_z} {pixel_size} {binning}
TS_relion5_002 {tomo_size_x} {tomo_size_y} {tomo_size_z} {pixel_size} {binning}
"""
        tomograms_path.write_text(tomograms_content)

        yield {
            "particles_star": str(particles_path),
            "tomograms_star": str(tomograms_path),
            "tomo_center": (
                tomo_size_x * pixel_size / 2,
                tomo_size_y * pixel_size / 2,
                tomo_size_z * pixel_size / 2,
            ),
        }


@pytest.fixture
def sample_em_file_multi_tomo():
    """Create a sample EM motivelist file with multiple tomogram indices for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        em_path = Path(tmpdir) / "motivelist.em"

        # Create a simple EM motivelist (20 x N array format)
        # emfile requires 3D array, so we use shape (1, 20, n_particles)
        n_particles = 4
        data = np.zeros((1, 20, n_particles), dtype=np.float32)

        # Set positions (columns 8, 9, 10 in 1-indexed, so 7, 8, 9 in 0-indexed)
        data[0, 7, :] = [10.0, 20.0, 30.0, 40.0]  # X positions in pixels
        data[0, 8, :] = [15.0, 25.0, 35.0, 45.0]  # Y positions in pixels
        data[0, 9, :] = [20.0, 30.0, 40.0, 50.0]  # Z positions in pixels

        # Set Euler angles (columns 17, 18, 19 in 1-indexed)
        data[0, 16, :] = [0.0, 0.0, 0.0, 0.0]  # Phi
        data[0, 17, :] = [0.0, 0.0, 0.0, 0.0]  # Psi
        data[0, 18, :] = [0.0, 0.0, 0.0, 0.0]  # Theta

        # Set tomogram number - particles from different tomograms
        data[0, 4, :] = [1, 1, 2, 2]  # Tomogram numbers

        emfile.write(str(em_path), data)
        yield str(em_path)


@pytest.fixture
def sample_dynamo_table_multi_tomo():
    """Create a sample Dynamo table file with multiple tomogram indices for testing."""
    import dynamotable
    import pandas as pd

    with tempfile.NamedTemporaryFile(suffix=".tbl", delete=False) as tmp:
        # Create DataFrame with proper Dynamo column structure using dynamotable
        # This ensures the format is always compatible with dynamotable.read()
        df = pd.DataFrame(
            {
                "tag": [1, 2, 3],
                "aligned": [0, 0, 0],
                "averaged": [0, 0, 0],
                "dx": [0.0, 0.0, 0.0],
                "dy": [0.0, 0.0, 0.0],
                "dz": [0.0, 0.0, 0.0],
                "tdrot": [0.0, 0.0, 0.0],
                "tilt": [0.0, 0.0, 0.0],
                "narot": [0.0, 0.0, 0.0],
                "cc": [0.0, 0.0, 0.0],
                "x": [10.0, 20.0, 30.0],
                "y": [15.0, 25.0, 35.0],
                "z": [20.0, 30.0, 40.0],
                "tomo": [1, 1, 2],  # Two particles in tomo 1, one in tomo 2
            },
        )
        dynamotable.write(df, tmp.name)
        yield tmp.name

    with contextlib.suppress(PermissionError, OSError):
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)


class TestPicksImport:
    """Test cases for picks import functionality."""

    def test_import_picks_csv(self, test_payload, runner, sample_csv_picks):
        """Test importing picks from CSV file."""
        config_file = test_payload["cfg_file"]

        result = runner.invoke(
            add,
            [
                "picks",
                "--config",
                str(config_file),
                "--object-name",
                "ribosome",
                "--user-id",
                "test-user",
                "--session-id",
                "1",
                "--file-type",
                "csv",
                sample_csv_picks,
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify picks were imported
        root = copick.from_file(config_file)
        run = root.get_run("TS_001")
        assert run is not None, "Run should be created from CSV"

        picks_list = run.get_picks(object_name="ribosome", user_id="test-user", session_id="1")
        assert len(picks_list) > 0, "Picks should be imported"

        picks = picks_list[0]
        assert len(picks.points) == 2, "Should have 2 picks from CSV"

    def test_import_picks_star(self, test_payload, runner, sample_star_file):
        """Test importing picks from STAR file."""
        config_file = test_payload["cfg_file"]

        result = runner.invoke(
            add,
            [
                "picks",
                "--config",
                str(config_file),
                "--run",
                "test_star_run",
                "--object-name",
                "ribosome",
                "--user-id",
                "test-user",
                "--session-id",
                "1",
                "--voxel-size",
                "10.0",
                "--file-type",
                "star",
                sample_star_file,
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify picks were imported
        root = copick.from_file(config_file)
        run = root.get_run("test_star_run")
        assert run is not None, "Run should be created"

        picks_list = run.get_picks(object_name="ribosome", user_id="test-user", session_id="1")
        assert len(picks_list) > 0, "Picks should be imported"

        picks = picks_list[0]
        assert len(picks.points) == 3, "Should have 3 picks from STAR"

    def test_import_picks_missing_voxel_size(self, test_payload, runner, sample_star_file):
        """Test that import fails when voxel size is required but not provided."""
        config_file = test_payload["cfg_file"]

        result = runner.invoke(
            add,
            [
                "picks",
                "--config",
                str(config_file),
                "--run",
                "test_run",
                "--object-name",
                "ribosome",
                "--user-id",
                "test-user",
                "--session-id",
                "1",
                # Missing --voxel-size for STAR file
                "--file-type",
                "star",
                sample_star_file,
            ],
        )

        assert result.exit_code != 0, "Command should fail without voxel size"

    def test_import_picks_auto_detect_csv(self, test_payload, runner, sample_csv_picks):
        """Test automatic file type detection for CSV."""
        config_file = test_payload["cfg_file"]

        result = runner.invoke(
            add,
            [
                "picks",
                "--config",
                str(config_file),
                "--object-name",
                "ribosome",
                "--user-id",
                "auto-detect",
                "--session-id",
                "1",
                # No --file-type, should auto-detect from .csv extension
                sample_csv_picks,
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"


class TestSpecializedPicksImport:
    """Test cases for specialized picks import commands (picks-em, picks-dynamo, picks-relion)."""

    def test_add_picks_em_basic(self, test_payload, runner, sample_em_file_multi_tomo, sample_index_map):
        """Test batch import from EM motivelist with index map."""
        config_file = test_payload["cfg_file"]

        result = runner.invoke(
            add,
            [
                "picks-em",
                "--config",
                str(config_file),
                "--object-name",
                "ribosome",
                "--voxel-size",
                "10.0",
                "--index-map",
                sample_index_map,
                "--user-id",
                "em-test",
                "--session-id",
                "1",
                "--create",  # Create runs if they don't exist
                sample_em_file_multi_tomo,
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify picks were imported to correct runs
        root = copick.from_file(config_file)

        # Should have picks in TS_001 and TS_002
        run1 = root.get_run("TS_001")
        assert run1 is not None, "Run TS_001 should be created"
        picks1 = run1.get_picks(object_name="ribosome", user_id="em-test", session_id="1")
        assert len(picks1) > 0, "Picks should be imported for TS_001"

        run2 = root.get_run("TS_002")
        assert run2 is not None, "Run TS_002 should be created"
        picks2 = run2.get_picks(object_name="ribosome", user_id="em-test", session_id="1")
        assert len(picks2) > 0, "Picks should be imported for TS_002"

    def test_add_picks_em_missing_index_map(self, test_payload, runner, sample_em_file_multi_tomo):
        """Test error when index map is missing for picks-em (required)."""
        config_file = test_payload["cfg_file"]

        result = runner.invoke(
            add,
            [
                "picks-em",
                "--config",
                str(config_file),
                "--object-name",
                "ribosome",
                "--voxel-size",
                "10.0",
                # Missing --index-map
                "--user-id",
                "em-test",
                "--session-id",
                "1",
                sample_em_file_multi_tomo,
            ],
        )

        assert result.exit_code != 0, "Command should fail without index map"

    def test_add_picks_em_missing_voxel_size(self, test_payload, runner, sample_em_file_multi_tomo, sample_index_map):
        """Test error when voxel size is missing for picks-em."""
        config_file = test_payload["cfg_file"]

        result = runner.invoke(
            add,
            [
                "picks-em",
                "--config",
                str(config_file),
                "--object-name",
                "ribosome",
                # Missing --voxel-size
                "--index-map",
                sample_index_map,
                "--user-id",
                "em-test",
                "--session-id",
                "1",
                sample_em_file_multi_tomo,
            ],
        )

        assert result.exit_code != 0, "Command should fail without voxel size"

    def test_add_picks_dynamo_with_index_map(
        self,
        test_payload,
        runner,
        sample_dynamo_table_multi_tomo,
        sample_index_map,
    ):
        """Test batch import from Dynamo table with index map."""
        config_file = test_payload["cfg_file"]

        result = runner.invoke(
            add,
            [
                "picks-dynamo",
                "--config",
                str(config_file),
                "--object-name",
                "ribosome",
                "--voxel-size",
                "10.0",
                "--index-map",
                sample_index_map,
                "--user-id",
                "dynamo-test",
                "--session-id",
                "1",
                "--create",  # Create runs if they don't exist
                "--debug",  # Raise exceptions to see actual errors
                sample_dynamo_table_multi_tomo,
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify picks were imported
        root = copick.from_file(config_file)
        run1 = root.get_run("TS_001")
        assert run1 is not None, "Run TS_001 should be created"
        picks1 = run1.get_picks(object_name="ribosome", user_id="dynamo-test", session_id="1")
        assert len(picks1) > 0, "Picks should be imported for TS_001"

    def test_add_picks_dynamo_missing_voxel_size(
        self,
        test_payload,
        runner,
        sample_dynamo_table_multi_tomo,
        sample_index_map,
    ):
        """Test error when voxel size is missing for picks-dynamo."""
        config_file = test_payload["cfg_file"]

        result = runner.invoke(
            add,
            [
                "picks-dynamo",
                "--config",
                str(config_file),
                "--object-name",
                "ribosome",
                # Missing --voxel-size
                "--index-map",
                sample_index_map,
                "--user-id",
                "dynamo-test",
                "--session-id",
                "1",
                sample_dynamo_table_multi_tomo,
            ],
        )

        assert result.exit_code != 0, "Command should fail without voxel size"

    def test_add_picks_relion_basic(self, test_payload, runner, sample_star_with_tomo_name):
        """Test batch import from RELION particles star file."""
        config_file = test_payload["cfg_file"]

        result = runner.invoke(
            add,
            [
                "picks-relion",
                "--config",
                str(config_file),
                "--object-name",
                "ribosome",
                "--voxel-size",
                "10.0",
                "--user-id",
                "relion-test",
                "--session-id",
                "1",
                "--create",  # Create runs if they don't exist
                sample_star_with_tomo_name,
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify picks were imported to correct runs based on _rlnTomoName
        root = copick.from_file(config_file)

        run1 = root.get_run("TS_001")
        assert run1 is not None, "Run TS_001 should be created from _rlnTomoName"
        picks1 = run1.get_picks(object_name="ribosome", user_id="relion-test", session_id="1")
        assert len(picks1) > 0, "Picks should be imported for TS_001"

        run2 = root.get_run("TS_002")
        assert run2 is not None, "Run TS_002 should be created from _rlnTomoName"
        picks2 = run2.get_picks(object_name="ribosome", user_id="relion-test", session_id="1")
        assert len(picks2) > 0, "Picks should be imported for TS_002"

    def test_add_picks_relion_missing_voxel_size(self, test_payload, runner, sample_star_with_tomo_name):
        """Test error when voxel size missing for picks-relion."""
        config_file = test_payload["cfg_file"]

        result = runner.invoke(
            add,
            [
                "picks-relion",
                "--config",
                str(config_file),
                "--object-name",
                "ribosome",
                # Missing --voxel-size
                "--user-id",
                "relion-test",
                "--session-id",
                "1",
                sample_star_with_tomo_name,
            ],
        )

        assert result.exit_code != 0, "Command should fail without voxel size"

    def test_add_picks_relion5_with_tomograms_star(self, test_payload, runner, sample_relion5_star_files):
        """Test RELION 5.0 centered coordinate import with tomograms.star file."""
        config_file = test_payload["cfg_file"]

        result = runner.invoke(
            add,
            [
                "picks-relion",
                "--config",
                str(config_file),
                "--object-name",
                "ribosome",
                "--voxel-size",
                "1.0",  # Use 1.0 to match the fixture
                "--user-id",
                "relion5-test",
                "--session-id",
                "1",
                "--create",
                "--tomograms-star",
                sample_relion5_star_files["tomograms_star"],
                sample_relion5_star_files["particles_star"],
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify picks were imported
        root = copick.from_file(config_file)

        run1 = root.get_run("TS_relion5_001")
        assert run1 is not None, "Run TS_relion5_001 should be created"
        picks1 = run1.get_picks(object_name="ribosome", user_id="relion5-test", session_id="1")
        assert len(picks1) > 0, "Picks should be imported for TS_relion5_001"

        # Verify coordinates were converted from centered to absolute
        # Centered: (-40, -35, -30), Center: (50, 50, 50)
        # Absolute should be: (10, 15, 20) Angstrom
        pick = picks1[0]
        points = pick.points
        assert len(points) == 2, "Should have 2 picks for TS_relion5_001"

        # First pick: centered (-40, -35, -30) + center (50, 50, 50) = (10, 15, 20)
        first_pick = points[0]
        assert abs(first_pick.location.x - 10.0) < 0.1, f"Expected x=10, got {first_pick.location.x}"
        assert abs(first_pick.location.y - 15.0) < 0.1, f"Expected y=15, got {first_pick.location.y}"
        assert abs(first_pick.location.z - 20.0) < 0.1, f"Expected z=20, got {first_pick.location.z}"

        run2 = root.get_run("TS_relion5_002")
        assert run2 is not None, "Run TS_relion5_002 should be created"
        picks2 = run2.get_picks(object_name="ribosome", user_id="relion5-test", session_id="1")
        assert len(picks2) > 0, "Picks should be imported for TS_relion5_002"

    def test_add_picks_relion_version_option(self, test_payload, runner, sample_star_with_tomo_name):
        """Test --relion-version option for explicit version selection."""
        config_file = test_payload["cfg_file"]

        # Test with explicit relion4 version
        result = runner.invoke(
            add,
            [
                "picks-relion",
                "--config",
                str(config_file),
                "--object-name",
                "ribosome",
                "--voxel-size",
                "10.0",
                "--user-id",
                "relion4-explicit",
                "--session-id",
                "1",
                "--create",
                "--relion-version",
                "relion4",
                sample_star_with_tomo_name,
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify picks were imported
        root = copick.from_file(config_file)
        run1 = root.get_run("TS_001")
        assert run1 is not None, "Run TS_001 should exist"
        picks1 = run1.get_picks(object_name="ribosome", user_id="relion4-explicit", session_id="1")
        assert len(picks1) > 0, "Picks should be imported with explicit relion4 version"

    def test_add_picks_relion5_missing_tomograms_star_error(self, test_payload, runner, sample_relion5_star_files):
        """Test error when RELION 5.0 coordinates used without tomograms.star or existing tomograms."""
        config_file = test_payload["cfg_file"]

        # Don't create runs or tomograms first - should fail
        result = runner.invoke(
            add,
            [
                "picks-relion",
                "--config",
                str(config_file),
                "--object-name",
                "ribosome",
                "--voxel-size",
                "1.0",
                "--user-id",
                "relion5-test",
                "--session-id",
                "1",
                "--create",
                # Missing --tomograms-star and runs don't exist
                sample_relion5_star_files["particles_star"],
            ],
        )

        # Should fail because RELION 5.0 coordinates require tomogram dimensions
        assert result.exit_code != 0, "Command should fail without tomograms.star for RELION 5.0"
        assert "RELION 5.0" in result.output or "tomogram" in result.output.lower()


class TestPicksExport:
    """Test cases for picks export functionality."""

    def test_export_picks_csv(self, test_payload, runner):
        """Test exporting picks to CSV format."""
        config_file = test_payload["cfg_file"]
        test_payload["root"]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            result = runner.invoke(
                export,
                [
                    "picks",
                    "--config",
                    str(config_file),
                    "--picks-uri",
                    "*:*/*",
                    "--output-dir",
                    str(output_dir),
                    "--output-format",
                    "csv",
                ],
            )

            assert result.exit_code == 0, f"Command failed: {result.output}"

            # Check that CSV files were created
            list(output_dir.glob("**/*.csv"))
            # We may or may not have picks in the test project
            # Just verify the command succeeded

    def test_export_picks_star(self, test_payload, runner):
        """Test exporting picks to STAR format."""
        config_file = test_payload["cfg_file"]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            result = runner.invoke(
                export,
                [
                    "picks",
                    "--config",
                    str(config_file),
                    "--picks-uri",
                    "*:*/*",
                    "--output-dir",
                    str(output_dir),
                    "--output-format",
                    "star",
                    "--voxel-size",
                    "10.0",
                ],
            )

            assert result.exit_code == 0, f"Command failed: {result.output}"

    def test_export_picks_missing_voxel_size(self, test_payload, runner):
        """Test that export fails when voxel size is required but not provided."""
        config_file = test_payload["cfg_file"]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            result = runner.invoke(
                export,
                [
                    "picks",
                    "--config",
                    str(config_file),
                    "--picks-uri",
                    "*:*/*",
                    "--output-dir",
                    str(output_dir),
                    "--output-format",
                    "star",
                    # Missing --voxel-size
                ],
            )

            assert result.exit_code != 0, "Command should fail without voxel size"

    def test_export_picks_combined_csv(self, test_payload, runner):
        """Test combined export to single CSV file using existing picks."""
        config_file = test_payload["cfg_file"]

        # Use existing picks in the sample project (ribosome:test.user/1234)
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = Path(tmpdir) / "combined.csv"

            result = runner.invoke(
                export,
                [
                    "picks",
                    "--config",
                    str(config_file),
                    "--picks-uri",
                    "ribosome:test.user/*",  # Use existing picks in sample project
                    "--output-file",
                    str(output_file),
                    "--output-format",
                    "csv",
                ],
            )

            assert result.exit_code == 0, f"Command failed: {result.output}"
            assert output_file.exists(), "Combined CSV file should be created"

    def test_export_picks_combined_star(self, test_payload, runner, sample_csv_picks):
        """Test combined export to single STAR file with _rlnTomoName column."""
        config_file = test_payload["cfg_file"]

        # First import picks with valid rotation matrices from our test CSV
        result1 = runner.invoke(
            add,
            [
                "picks",
                "--config",
                str(config_file),
                "--object-name",
                "ribosome",
                "--user-id",
                "star-export-test",
                "--session-id",
                "1",
                sample_csv_picks,
            ],
        )
        assert result1.exit_code == 0, f"Import failed: {result1.output}"

        # Now export to STAR format
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = Path(tmpdir) / "particles.star"

            result = runner.invoke(
                export,
                [
                    "picks",
                    "--config",
                    str(config_file),
                    "--picks-uri",
                    "ribosome:star-export-test/*",
                    "--output-file",
                    str(output_file),
                    "--output-format",
                    "star",
                    "--voxel-size",
                    "10.0",
                ],
            )

            assert result.exit_code == 0, f"Command failed: {result.output}"
            assert output_file.exists(), "Combined STAR file should be created"

    def test_export_picks_combined_em_missing_index_map(self, test_payload, runner):
        """Test error when index map missing for combined EM export."""
        config_file = test_payload["cfg_file"]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = Path(tmpdir) / "particles.em"

            result = runner.invoke(
                export,
                [
                    "picks",
                    "--config",
                    str(config_file),
                    "--picks-uri",
                    "*:*/*",
                    "--output-file",
                    str(output_file),
                    "--output-format",
                    "em",
                    "--voxel-size",
                    "10.0",
                    # Missing --index-map which is required for combined EM export
                ],
            )

            assert result.exit_code != 0, "Command should fail without index map for combined EM export"

    def test_export_picks_combined_dynamo_missing_index_map(self, test_payload, runner):
        """Test error when index map missing for combined Dynamo export."""
        config_file = test_payload["cfg_file"]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = Path(tmpdir) / "particles.tbl"

            result = runner.invoke(
                export,
                [
                    "picks",
                    "--config",
                    str(config_file),
                    "--picks-uri",
                    "*:*/*",
                    "--output-file",
                    str(output_file),
                    "--output-format",
                    "dynamo",
                    "--voxel-size",
                    "10.0",
                    # Missing --index-map which is required for combined Dynamo export
                ],
            )

            assert result.exit_code != 0, "Command should fail without index map for combined Dynamo export"

    def test_export_picks_mutual_exclusion(self, test_payload, runner):
        """Test error when both --output-dir and --output-file provided."""
        config_file = test_payload["cfg_file"]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "dir"
            output_file = Path(tmpdir) / "file.csv"

            result = runner.invoke(
                export,
                [
                    "picks",
                    "--config",
                    str(config_file),
                    "--picks-uri",
                    "*:*/*",
                    "--output-dir",
                    str(output_dir),
                    "--output-file",
                    str(output_file),
                    "--output-format",
                    "csv",
                ],
            )

            assert result.exit_code != 0, "Command should fail with both output options"

    def test_export_picks_no_output_specified(self, test_payload, runner):
        """Test error when neither --output-dir nor --output-file provided."""
        config_file = test_payload["cfg_file"]

        result = runner.invoke(
            export,
            [
                "picks",
                "--config",
                str(config_file),
                "--picks-uri",
                "*:*/*",
                "--output-format",
                "csv",
                # Missing both --output-dir and --output-file
            ],
        )

        assert result.exit_code != 0, "Command should fail without output specification"

    def test_export_picks_per_run_with_index_map(self, test_payload, runner, sample_csv_picks, sample_index_map):
        """Test per-run export uses index map for tomogram indices."""
        config_file = test_payload["cfg_file"]

        # First import some picks
        result1 = runner.invoke(
            add,
            [
                "picks",
                "--config",
                str(config_file),
                "--object-name",
                "ribosome",
                "--user-id",
                "index-map-test",
                "--session-id",
                "1",
                sample_csv_picks,
            ],
        )
        assert result1.exit_code == 0, f"Import failed: {result1.output}"

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            result = runner.invoke(
                export,
                [
                    "picks",
                    "--config",
                    str(config_file),
                    "--picks-uri",
                    "ribosome:index-map-test/*",
                    "--output-dir",
                    str(output_dir),
                    "--output-format",
                    "em",
                    "--voxel-size",
                    "10.0",
                    "--index-map",
                    sample_index_map,
                ],
            )

            assert result.exit_code == 0, f"Command failed: {result.output}"


class TestTomogramExport:
    """Test cases for tomogram export functionality."""

    def test_export_tomogram_mrc(self, test_payload, runner):
        """Test exporting tomograms to MRC format."""
        config_file = test_payload["cfg_file"]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            result = runner.invoke(
                export,
                [
                    "tomogram",
                    "--config",
                    str(config_file),
                    "--tomogram-uri",
                    "*@*",
                    "--output-dir",
                    str(output_dir),
                    "--output-format",
                    "mrc",
                ],
            )

            assert result.exit_code == 0, f"Command failed: {result.output}"

    def test_export_tomogram_tiff(self, test_payload, runner):
        """Test exporting tomograms to TIFF format."""
        config_file = test_payload["cfg_file"]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            result = runner.invoke(
                export,
                [
                    "tomogram",
                    "--config",
                    str(config_file),
                    "--tomogram-uri",
                    "*@*",
                    "--output-dir",
                    str(output_dir),
                    "--output-format",
                    "tiff",
                    "--compression",
                    "lzw",
                ],
            )

            assert result.exit_code == 0, f"Command failed: {result.output}"


class TestSegmentationExport:
    """Test cases for segmentation export functionality."""

    def test_export_segmentation_mrc(self, test_payload, runner):
        """Test exporting segmentations to MRC format."""
        config_file = test_payload["cfg_file"]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            result = runner.invoke(
                export,
                [
                    "segmentation",
                    "--config",
                    str(config_file),
                    "--segmentation-uri",
                    "*:*/*@*",
                    "--output-dir",
                    str(output_dir),
                    "--output-format",
                    "mrc",
                ],
            )

            assert result.exit_code == 0, f"Command failed: {result.output}"


class TestRoundTrip:
    """Round-trip tests for import/export functionality."""

    def test_csv_round_trip(self, test_payload, runner, sample_csv_picks):
        """Test import -> export -> re-import round trip for CSV."""
        config_file = test_payload["cfg_file"]

        # Step 1: Import CSV picks
        result1 = runner.invoke(
            add,
            [
                "picks",
                "--config",
                str(config_file),
                "--object-name",
                "ribosome",
                "--user-id",
                "round-trip-test",
                "--session-id",
                "1",
                sample_csv_picks,
            ],
        )
        assert result1.exit_code == 0, f"Import failed: {result1.output}"

        # Step 2: Export to CSV
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            result2 = runner.invoke(
                export,
                [
                    "picks",
                    "--config",
                    str(config_file),
                    "--picks-uri",
                    "ribosome:round-trip-test/*",
                    "--output-dir",
                    str(output_dir),
                    "--output-format",
                    "csv",
                ],
            )
            assert result2.exit_code == 0, f"Export failed: {result2.output}"

            # Step 3: Re-import the exported CSV
            csv_files = list(output_dir.glob("**/*.csv"))
            if csv_files:
                result3 = runner.invoke(
                    add,
                    [
                        "picks",
                        "--config",
                        str(config_file),
                        "--object-name",
                        "ribosome",
                        "--user-id",
                        "round-trip-reimport",
                        "--session-id",
                        "1",
                        str(csv_files[0]),
                    ],
                )
                assert result3.exit_code == 0, f"Re-import failed: {result3.output}"


class TestFormatUtilities:
    """Test cases for format utility functions."""

    def test_euler_to_matrix_identity(self):
        """Test Euler angle to matrix conversion for identity."""
        from copick.util.formats import euler_to_matrix

        angles = np.array([[0.0, 0.0, 0.0]])
        matrices = euler_to_matrix(angles, convention="ZYZ", degrees=True)

        expected = np.eye(3)
        np.testing.assert_array_almost_equal(matrices[0], expected, decimal=5)

    def test_matrix_to_euler_identity(self):
        """Test matrix to Euler angle conversion for identity."""
        from copick.util.formats import matrix_to_euler

        matrices = np.array([np.eye(3)])
        angles = matrix_to_euler(matrices, convention="ZYZ", degrees=True)

        # For identity matrix, all Euler angles should be 0 (or equivalent)
        # Note: There can be multiple valid Euler representations for identity
        reconstructed = np.array([[angles[0, 0], angles[0, 1], angles[0, 2]]])
        from copick.util.formats import euler_to_matrix

        reconstructed_matrix = euler_to_matrix(reconstructed, convention="ZYZ", degrees=True)
        np.testing.assert_array_almost_equal(reconstructed_matrix[0], np.eye(3), decimal=5)

    def test_euler_round_trip(self):
        """Test that Euler angle conversions are invertible."""
        from copick.util.formats import euler_to_matrix, matrix_to_euler

        original_angles = np.array([[30.0, 45.0, 60.0], [0.0, 90.0, 0.0], [45.0, 45.0, 45.0]])

        matrices = euler_to_matrix(original_angles, convention="ZYZ", degrees=True)
        recovered_angles = matrix_to_euler(matrices, convention="ZYZ", degrees=True)
        recovered_matrices = euler_to_matrix(recovered_angles, convention="ZYZ", degrees=True)

        # The matrices should be the same (angles may differ due to non-uniqueness)
        np.testing.assert_array_almost_equal(matrices, recovered_matrices, decimal=5)

    def test_csv_coordinate_preservation(self):
        """Test that CSV format preserves coordinates exactly."""
        from copick.util.formats import read_picks_csv, write_picks_csv

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "test.csv"

            # Create test data
            run_name = "test_run"
            positions = np.array([[100.5, 200.5, 300.5], [150.25, 250.75, 350.125]])
            transforms = np.array([np.eye(4), np.eye(4)])
            scores = np.array([0.95, 0.87])
            instance_ids = np.array([1, 2])

            # Write CSV
            write_picks_csv(str(csv_path), run_name, positions, transforms, scores, instance_ids)

            # Read CSV
            df = read_picks_csv(str(csv_path))

            # Verify coordinates are preserved
            np.testing.assert_array_almost_equal(df["x"].values, positions[:, 0], decimal=6)
            np.testing.assert_array_almost_equal(df["y"].values, positions[:, 1], decimal=6)
            np.testing.assert_array_almost_equal(df["z"].values, positions[:, 2], decimal=6)
            np.testing.assert_array_almost_equal(df["score"].values, scores, decimal=6)


# =============================================================================
# RELION geometry: rotation order, shifts, coordinate units, tomogram centres
# =============================================================================


def _relion_matrix(rot, tilt, psi):
    """RELION's Euler matrix (jaz/math/Euler_angles_relion.h, Euler::anglesToMatrix3), angles in degrees."""
    phi, theta, chi = np.radians([rot, tilt, psi])
    sp, cp, st, ct, sc, cc = np.sin(phi), np.cos(phi), np.sin(theta), np.cos(theta), np.sin(chi), np.cos(chi)
    return np.array(
        [
            [cc * ct * cp - sc * sp, cc * ct * sp + sc * cp, -cc * st],
            [-sc * ct * cp - cc * sp, -sc * ct * sp + cc * cp, sc * st],
            [st * cp, st * sp, ct],
        ],
    )


def _star(path, particles, optics=None):
    import pandas as pd
    import starfile

    data = pd.DataFrame(particles)
    if optics is not None:
        data = {"optics": pd.DataFrame(optics), "particles": data}
    starfile.write(data, path, overwrite=True)
    return str(path)


def _random_transforms(n, seed=0):
    from scipy.spatial.transform import Rotation

    rng = np.random.default_rng(seed)
    transforms = np.tile(np.eye(4), (n, 1, 1))
    transforms[:, :3, :3] = Rotation.random(n, random_state=seed).as_matrix()
    transforms[:, :3, 3] = rng.uniform(-20.0, 20.0, (n, 3))
    return transforms


SUB_ANGLES = (30.0, 60.0, -45.0)
PARTICLE_ANGLES = (-100.0, 20.0, 75.0)
ORIGIN = np.array([4.0, -2.5, 1.5])


class TestRelionGeometry:
    """copick reads and writes RELION tomography particles the way RELION does."""

    def test_tomogram_centre_ignores_binning(self, tmp_path):
        from copick.util.formats import read_relion5_tomogram_centers, read_relion_tomograms

        path = _star(
            tmp_path / "tomograms.star",
            {
                "rlnTomoName": ["TS_01"],
                "rlnTomoSizeX": [4096],
                "rlnTomoSizeY": [4096],
                "rlnTomoSizeZ": [2048],
                "rlnTomoTiltSeriesPixelSize": [1.35],
                "rlnTomoTomogramBinning": [8.0],
                "rlnVoltage": [300.0],
            },
        )

        tomogram = read_relion_tomograms(path)["TS_01"]
        assert tomogram.center_angstrom == pytest.approx((2764.8, 2764.8, 1382.4))
        assert tomogram.tilt_series_pixel_size == 1.35
        assert tomogram.voltage == 300.0
        assert tomogram.amplitude_contrast is None
        assert read_relion5_tomogram_centers(path)["TS_01"] == pytest.approx((2764.8, 2764.8, 1382.4))

    def test_from_df_composes_rotations_and_shifts_as_relion(self, test_payload):
        import pandas as pd

        picks = (
            test_payload["root"]
            .get_run("TS_001")
            .new_picks(object_name="ribosome", user_id="relion-order", session_id="1")
        )
        centered = np.array([10.0, -20.0, 30.0])
        df = pd.DataFrame(
            {
                "rlnCenteredCoordinateXAngst": [centered[0]],
                "rlnCenteredCoordinateYAngst": [centered[1]],
                "rlnCenteredCoordinateZAngst": [centered[2]],
                "rlnTomoSubtomogramRot": [SUB_ANGLES[0]],
                "rlnTomoSubtomogramTilt": [SUB_ANGLES[1]],
                "rlnTomoSubtomogramPsi": [SUB_ANGLES[2]],
                "rlnAngleRot": [PARTICLE_ANGLES[0]],
                "rlnAngleTilt": [PARTICLE_ANGLES[1]],
                "rlnAnglePsi": [PARTICLE_ANGLES[2]],
                "rlnOriginXAngst": [ORIGIN[0]],
                "rlnOriginYAngst": [ORIGIN[1]],
                "rlnOriginZAngst": [ORIGIN[2]],
            },
        )

        picks.from_df(df, tomogram_center=(100.0, 100.0, 100.0))

        positions, transforms = picks.numpy()
        a_sub, a_particle = _relion_matrix(*SUB_ANGLES), _relion_matrix(*PARTICLE_ANGLES)
        # RELION ParticleSet: A = A_subtomogram * A_particle; position = coordinate - A_subtomogram * origin
        assert transforms[0, :3, :3] == pytest.approx(a_sub @ a_particle)
        assert positions[0] == pytest.approx(centered + 100.0 - a_sub @ ORIGIN)
        assert transforms[0, :3, 3] == pytest.approx(np.zeros(3))

    def test_cli_star_import_uses_optics_pixel_size_shifts_and_subtomogram_angles(
        self,
        test_payload,
        runner,
        tmp_path,
    ):
        coordinate = np.array([100.0, 150.0, 50.0])
        path = _star(
            tmp_path / "particles.star",
            {
                "rlnTomoName": ["TS_001"],
                "rlnCoordinateX": [coordinate[0]],
                "rlnCoordinateY": [coordinate[1]],
                "rlnCoordinateZ": [coordinate[2]],
                "rlnTomoSubtomogramRot": [SUB_ANGLES[0]],
                "rlnTomoSubtomogramTilt": [SUB_ANGLES[1]],
                "rlnTomoSubtomogramPsi": [SUB_ANGLES[2]],
                "rlnAngleRot": [PARTICLE_ANGLES[0]],
                "rlnAngleTilt": [PARTICLE_ANGLES[1]],
                "rlnAnglePsi": [PARTICLE_ANGLES[2]],
                "rlnOriginXAngst": [ORIGIN[0]],
                "rlnOriginYAngst": [ORIGIN[1]],
                "rlnOriginZAngst": [ORIGIN[2]],
                "rlnOpticsGroup": [1],
            },
            optics={"rlnOpticsGroup": [1], "rlnOpticsGroupName": ["optics1"], "rlnTomoTiltSeriesPixelSize": [2.0]},
        )

        # No --voxel-size: the optics table states the tilt-series pixel size
        result = runner.invoke(
            add,
            [
                "picks",
                "--config",
                str(test_payload["cfg_file"]),
                "--run",
                "TS_001",
                "--object-name",
                "ribosome",
                "--user-id",
                "relion-cli",
                "--session-id",
                "1",
                path,
            ],
        )
        assert result.exit_code == 0, result.output

        picks = copick.from_file(test_payload["cfg_file"]).get_run("TS_001").get_picks("ribosome", "relion-cli", "1")[0]
        positions, transforms = picks.numpy()
        a_sub, a_particle = _relion_matrix(*SUB_ANGLES), _relion_matrix(*PARTICLE_ANGLES)
        assert positions[0] == pytest.approx(coordinate * 2.0 - a_sub @ ORIGIN)
        assert transforms[0, :3, :3] == pytest.approx(a_sub @ a_particle)

    def test_cli_star_import_prefers_centred_coordinates(self, test_payload, runner, tmp_path):
        # TS_001's tomogram is centred at 320 A; the pixel columns are deliberately inconsistent and must be ignored
        path = _star(
            tmp_path / "both.star",
            {
                "rlnCoordinateX": [1.0],
                "rlnCoordinateY": [1.0],
                "rlnCoordinateZ": [1.0],
                "rlnCenteredCoordinateXAngst": [-20.0],
                "rlnCenteredCoordinateYAngst": [10.0],
                "rlnCenteredCoordinateZAngst": [0.0],
            },
        )
        result = runner.invoke(
            add,
            [
                "picks",
                "--config",
                str(test_payload["cfg_file"]),
                "--run",
                "TS_001",
                "--object-name",
                "ribosome",
                "--user-id",
                "relion-centred",
                "--session-id",
                "1",
                "--voxel-size",
                "10.0",
                path,
            ],
        )
        assert result.exit_code == 0, result.output

        picks = (
            copick.from_file(test_payload["cfg_file"]).get_run("TS_001").get_picks("ribosome", "relion-centred", "1")
        )
        assert picks[0].numpy()[0][0] == pytest.approx([300.0, 330.0, 320.0])

    @pytest.mark.parametrize("source", ["argument", "optics"])
    def test_pixel_coordinates_use_the_tilt_series_pixel_size(self, test_payload, source):
        import pandas as pd

        picks = (
            test_payload["root"]
            .get_run("TS_001")
            .new_picks(object_name="ribosome", user_id="relion-pixels", session_id=source)
        )
        df = pd.DataFrame({"rlnCoordinateX": [10.0], "rlnCoordinateY": [20.0], "rlnCoordinateZ": [30.0]})
        if source == "argument":
            picks.from_df(df, tilt_series_pixel_size=1.5)
        else:
            picks.from_df(df, optics=pd.DataFrame({"rlnTomoTiltSeriesPixelSize": [1.5]}))

        assert picks.numpy()[0][0] == pytest.approx([15.0, 30.0, 45.0])

    @pytest.mark.parametrize("tilt_series_pixel_size", [None, 2.5])
    def test_star_export_round_trip(self, test_payload, tmp_path, tilt_series_pixel_size):
        import starfile
        from copick.ops.add import add_picks_from_file
        from copick.ops.export import export_picks

        run = test_payload["root"].get_run("TS_001")
        points = np.array([[100.0, 200.0, 300.0], [400.0, 150.0, 250.0], [320.0, 320.0, 320.0]])
        transforms = _random_transforms(3)
        picks = run.new_picks(object_name="ribosome", user_id="relion-export", session_id="1")
        picks.from_numpy(points, transforms)

        path = str(tmp_path / "export.star")
        export_picks(picks, path, "star", voxel_spacing=10.0, tilt_series_pixel_size=tilt_series_pixel_size)

        data = starfile.read(path)
        particles = data["particles"] if isinstance(data, dict) else data
        assert (particles["rlnTomoName"] == "TS_001").all()
        assert {"rlnCenteredCoordinateXAngst", "rlnCenteredCoordinateYAngst", "rlnCenteredCoordinateZAngst"} <= set(
            particles.columns,
        )
        if tilt_series_pixel_size is None:
            assert not isinstance(data, dict), "no optics table without a tilt-series pixel size"
            assert "rlnCoordinateX" not in particles.columns
        else:
            assert data["optics"]["rlnTomoTiltSeriesPixelSize"].tolist() == [tilt_series_pixel_size]
            assert particles["rlnOpticsGroup"].tolist() == [1, 1, 1]
            assert particles["rlnCoordinateX"].to_numpy() == pytest.approx(
                (points[:, 0] + transforms[:, 0, 3]) / tilt_series_pixel_size,
            )

        imported = add_picks_from_file(test_payload["root"], "TS_001", path, "ribosome", "relion-export", "2", 10.0)
        assert imported.full_positions() == pytest.approx(picks.full_positions())
        assert imported.numpy()[1][:, :3, :3] == pytest.approx(transforms[:, :3, :3])

    def test_combined_star_export_keeps_shifts(self, test_payload, tmp_path):
        from copick.ops.add import add_picks_grouped_from_file
        from copick.ops.export import export_picks_combined

        run = test_payload["root"].get_run("TS_001")
        points = np.array([[100.0, 200.0, 300.0], [400.0, 150.0, 250.0]])
        transforms = _random_transforms(2, seed=1)
        picks = run.new_picks(object_name="ribosome", user_id="relion-combined", session_id="1")
        picks.from_numpy(points, transforms)

        path = str(tmp_path / "combined.star")
        export_picks_combined(
            str(test_payload["cfg_file"]),
            path,
            "ribosome:relion-combined/1",
            "star",
            voxel_spacing=10.0,
            tilt_series_pixel_size=2.0,
            log=True,
        )

        results = add_picks_grouped_from_file(
            test_payload["root"],
            path,
            "ribosome",
            "relion-combined",
            "2",
            None,
            {},
            file_type="star",
        )
        assert results["TS_001"].full_positions() == pytest.approx(picks.full_positions())
        assert results["TS_001"].numpy()[1][:, :3, :3] == pytest.approx(transforms[:, :3, :3])


@pytest.mark.parametrize("format_name", ["star", "em", "dynamo", "csv"])
def test_picks_handler_write_read_round_trip(format_name, tmp_path):
    """Every handler that can write reads its own output back: same particle centres and rotations."""
    from copick.util.handlers import FormatRegistry, unpack_picks_data

    handler = FormatRegistry.get_picks_handler(format_name)
    assert handler.capabilities.can_write

    points = np.array([[100.0, 200.0, 300.0], [400.0, 150.0, 250.0], [10.0, 20.0, 30.0]])
    transforms = _random_transforms(3, seed=2)
    path = str(tmp_path / f"picks.{ {'dynamo': 'tbl'}.get(format_name, format_name) }")

    if format_name == "star":
        handler.write(path, points, transforms, 10.0, tomo_name="TS_001", tilt_series_pixel_size=10.0)
    else:
        handler.write(path, points, transforms, 10.0)
    positions, read_transforms, _, _ = unpack_picks_data(handler.read(path, 10.0))

    assert positions + read_transforms[:, :3, 3] == pytest.approx(points + transforms[:, :3, 3], abs=1e-3)
    assert read_transforms[:, :3, :3] == pytest.approx(transforms[:, :3, :3], abs=1e-4)


# =============================================================================
# RELION filament conventions
# =============================================================================


def _frames_along(tangent, n, roll_seed=0):
    """(n, 3, 3) rotations whose +Z column is ``tangent`` and whose roll about it varies."""
    from scipy.spatial.transform import Rotation

    z = np.asarray(tangent, dtype=float) / np.linalg.norm(tangent)
    helper = np.array([1.0, 0.0, 0.0]) if abs(z[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    x = np.cross(helper, z)
    x /= np.linalg.norm(x)
    base = np.stack([x, np.cross(z, x), z], axis=1)
    rolls = np.random.default_rng(roll_seed).uniform(0, 360, n)
    return np.stack([base @ Rotation.from_euler("z", roll, degrees=True).as_matrix() for roll in rolls])


def _relion_filament_rows(tomo_name, centred_points, frames, tube_id, pixel_size=1.0):
    """Rows as RELION's get_particle_poses/filaments.py writes them (subtomogram frame = O @ Ry(90))."""
    from scipy.spatial.transform import Rotation

    ry90 = Rotation.from_euler("y", 90, degrees=True).as_matrix()
    sub = Rotation.from_matrix(frames @ ry90).inv().as_euler("ZYZ", degrees=True)
    n = len(centred_points)
    return {
        "rlnTomoName": [tomo_name] * n,
        "rlnCenteredCoordinateXAngst": centred_points[:, 0],
        "rlnCenteredCoordinateYAngst": centred_points[:, 1],
        "rlnCenteredCoordinateZAngst": centred_points[:, 2],
        "rlnTomoSubtomogramRot": sub[:, 0],
        "rlnTomoSubtomogramTilt": sub[:, 1],
        "rlnTomoSubtomogramPsi": sub[:, 2],
        "rlnAngleRot": np.zeros(n),
        "rlnAngleTilt": np.full(n, 90.0),
        "rlnAnglePsi": np.zeros(n),
        "rlnAngleTiltPrior": np.full(n, 90.0),
        "rlnAnglePsiPrior": np.zeros(n),
        "rlnHelicalTubeID": [tube_id] * n,
        "rlnHelicalTrackLengthAngst": np.linspace(0, 1, n) * (n - 1) * 40.0 / pixel_size,
        "rlnAnglePsiFlipRatio": np.full(n, 0.5),
    }


class TestRelionFilaments:
    """RELION's filament particles in and out of copick."""

    def test_import_relion_filament_particles(self, test_payload, tmp_path):
        import pandas as pd
        from copick.ops.add import add_picks_from_file

        steps = np.arange(5)[:, None] * 40.0
        along_x = np.array([-80.0, -50.0, 10.0]) + steps * np.array([1.0, 0.0, 0.0])
        along_y = np.array([60.0, -90.0, -20.0]) + steps * np.array([0.0, 1.0, 0.0])
        rows = pd.concat(
            [
                pd.DataFrame(_relion_filament_rows("TS_001", along_x, _frames_along([1, 0, 0], 5), 1)),
                pd.DataFrame(_relion_filament_rows("TS_001", along_y, _frames_along([0, 1, 0], 5, 1), 2)),
            ],
            ignore_index=True,
        )
        shuffled = rows.sample(frac=1.0, random_state=3).reset_index(drop=True)
        path = _star(tmp_path / "filaments.star", shuffled.to_dict(orient="list"))

        # TS_001's copick tomogram is centred at 320 A
        picks = add_picks_from_file(test_payload["root"], "TS_001", path, "ribosome", "relion-filaments", "1", 10.0)

        assert picks.instance_ids().tolist() == [1] * 5 + [2] * 5
        positions, transforms = picks.numpy()
        assert positions == pytest.approx(np.vstack([along_x, along_y]) + 320.0)
        tangents = transforms[:, :3, 2]
        assert tangents[:5] == pytest.approx(np.tile([1.0, 0.0, 0.0], (5, 1)), abs=1e-6)
        assert tangents[5:] == pytest.approx(np.tile([0.0, 1.0, 0.0], (5, 1)), abs=1e-6)

    @pytest.mark.parametrize("polarity_known", [False, True])
    def test_filament_export_round_trip(self, test_payload, tmp_path, polarity_known):
        import starfile
        from copick.ops.add import add_picks_from_file
        from copick.ops.export import export_picks

        root = test_payload["root"]
        root.new_object(name="microtubule", is_particle=True, radius=120, filament={"polar": True})
        steps = np.arange(4)[:, None] * 82.0
        points = np.vstack(
            [np.array([100.0, 100.0, 300.0]) + steps * [1, 0, 0], np.array([400.0, 50.0, 200.0]) + steps * [0, 1, 0]],
        )
        transforms = np.tile(np.eye(4), (8, 1, 1))
        transforms[:4, :3, :3] = _frames_along([1, 0, 0], 4)
        transforms[4:, :3, :3] = _frames_along([0, 1, 0], 4, 1)
        picks = root.get_run("TS_001").new_picks(object_name="microtubule", user_id="filament-export", session_id="1")
        picks.from_numpy(points, transforms, instance_ids=[1] * 4 + [2] * 4)

        if polarity_known:
            # The same session's Filaments state the polarity
            filaments = root.get_run("TS_001").new_filaments("microtubule", "1", user_id="filament-export")
            filaments.from_numpy([points[:4], points[4:]], instance_ids=[1, 2], polarity_known=[True, True])

        path = str(tmp_path / "filaments.star")
        export_picks(picks, path, "star", voxel_spacing=10.0, tilt_series_pixel_size=2.0)

        particles = starfile.read(path)["particles"]
        assert particles["rlnHelicalTubeID"].tolist() == [1] * 4 + [2] * 4
        assert particles["rlnHelicalTrackLengthAngst"].tolist() == pytest.approx([0, 82, 164, 246] * 2)
        assert (particles["rlnAngleTilt"] == 90).all() and (particles["rlnAngleTiltPrior"] == 90).all()
        assert (particles["rlnAnglePsiFlipRatio"] == (0.0 if polarity_known else 0.5)).all()

        imported = add_picks_from_file(root, "TS_001", path, "microtubule", "filament-export", "2", 10.0)
        assert imported.instance_ids().tolist() == [1] * 4 + [2] * 4
        assert imported.full_positions() == pytest.approx(points)
        assert imported.numpy()[1][:, :3, :3] == pytest.approx(transforms[:, :3, :3], abs=1e-6)

    def test_filament_export_needs_filament_ids(self, test_payload, tmp_path):
        from copick.ops.export import export_picks

        picks = (
            test_payload["root"].get_run("TS_001").new_picks(object_name="ribosome", user_id="no-ids", session_id="1")
        )
        picks.from_numpy(np.array([[100.0, 100.0, 100.0], [200.0, 100.0, 100.0]]), instance_ids=[1, 0])

        with pytest.raises(ValueError, match="1 of 2 picks in TS_001 have no filament ID"):
            export_picks(picks, str(tmp_path / "f.star"), "star", voxel_spacing=10.0, filament_columns="on")
        # The default ("auto") exports a non-filament object with plain angles
        export_picks(picks, str(tmp_path / "p.star"), "star", voxel_spacing=10.0)

    def test_combined_export_mixing_objects_writes_plain_angles(self, test_payload, tmp_path):
        import starfile
        from copick.ops.export import export_picks_combined

        root = test_payload["root"]
        root.new_object(name="actin", is_particle=True, radius=35, filament={"polar": True})
        root.save_config(test_payload["cfg_file"])
        run = root.get_run("TS_001")
        run.new_picks(object_name="actin", user_id="mixed", session_id="1").from_numpy(
            np.array([[100.0, 100.0, 100.0]]),
            instance_ids=[1],
        )
        run.new_picks(object_name="ribosome", user_id="mixed", session_id="1").from_numpy(
            np.array([[150.0, 100.0, 100.0]]),
        )

        path = str(tmp_path / "mixed.star")
        export_picks_combined(str(test_payload["cfg_file"]), path, "*:mixed/1", "star", voxel_spacing=10.0)

        data = starfile.read(path)
        particles = data["particles"] if isinstance(data, dict) else data
        assert "rlnHelicalTubeID" not in particles.columns


def _polar_filament_project(test_payload, picks_session="1", filaments_session="1", picks_user="sampler"):
    """TS_001 with three microtubules picked in point order (IDs 1-3), and the Filaments they were sampled from, of
    which only filament 1 has known polarity."""
    root = test_payload["root"]
    root.new_object(name="microtubule", is_particle=True, radius=120, filament={"polar": True})
    root.save_config(test_payload["cfg_file"])
    run = root.get_run("TS_001")
    steps = np.arange(3)[:, None] * 82.0
    starts = ([100.0, 100.0, 300.0], [400.0, 50.0, 200.0], [150.0, 500.0, 250.0])
    axes = ([1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [1.0, 0.0, 0.0])
    lines = [np.array(start) + steps * np.array(axis) for start, axis in zip(starts, axes, strict=True)]
    transforms = np.tile(np.eye(4), (9, 1, 1))
    for i, axis in enumerate(axes):
        transforms[3 * i : 3 * i + 3, :3, :3] = _frames_along(axis, 3, i)
    picks = run.new_picks(object_name="microtubule", user_id=picks_user, session_id=picks_session)
    picks.from_numpy(np.vstack(lines), transforms, instance_ids=[1] * 3 + [2] * 3 + [3] * 3)
    filaments = run.new_filaments("microtubule", filaments_session, user_id="tracer")
    filaments.from_numpy(lines, instance_ids=[1, 2, 3], polarity_known=[True, False, False])
    return root, picks, filaments, np.vstack(lines), transforms


def _star_particles(path):
    import starfile

    data = starfile.read(path)
    return data["particles"] if isinstance(data, dict) else data


class TestFilamentPolarity:
    """rlnAnglePsiFlipRatio from each filament's polarity_known."""

    def test_builder_takes_per_row_polarity(self):
        from copick.util.formats import build_relion_particles_df

        positions = np.array([[0.0, 0.0, 0.0], [82.0, 0.0, 0.0], [0.0, 0.0, 100.0], [0.0, 82.0, 100.0]])
        transforms = np.tile(np.eye(4), (4, 1, 1))
        transforms[:2, :3, :3] = _frames_along([1, 0, 0], 2)
        transforms[2:, :3, :3] = _frames_along([0, 1, 0], 2)
        kwargs = {"tomogram_center": (0.0, 0.0, 0.0), "instance_ids": np.array([1, 1, 2, 2]), "filament": True}

        mixed = build_relion_particles_df(positions, transforms, polarity_known=[True, True, False, False], **kwargs)
        assert mixed["rlnAnglePsiFlipRatio"].tolist() == [0.0, 0.0, 0.5, 0.5]
        # A bool applies to every row, and known polarity is written as 0, since RELION reads a missing column as 0.5
        assert (
            build_relion_particles_df(positions, transforms, polarity_known=True, **kwargs)[
                "rlnAnglePsiFlipRatio"
            ].tolist()
            == [0.0] * 4
        )
        assert build_relion_particles_df(positions, transforms, **kwargs)["rlnAnglePsiFlipRatio"].tolist() == [0.5] * 4
        with pytest.raises(ValueError, match="one value per pick"):
            build_relion_particles_df(positions, transforms, polarity_known=[True, False], **kwargs)

    def test_picks_to_df_relion_takes_per_row_polarity(self, test_payload):
        from copick.util.relion import filament_polarity_known, picks_to_df_relion

        root, picks, *_ = _polar_filament_project(test_payload, picks_user="tracer")

        known = filament_polarity_known(picks)
        assert known.tolist() == [True] * 3 + [False] * 6
        df = picks_to_df_relion(picks, voxel_spacing=10.0, polarity_known=known)
        assert df["rlnAnglePsiFlipRatio"].tolist() == [0.0] * 3 + [0.5] * 6

    def test_same_uri_filaments_give_mixed_flip_ratios(self, test_payload, tmp_path):
        """copick-helix writes Filaments and picks under one URI: they are the default polarity source."""
        from copick.ops.export import export_picks

        root, picks, *_ = _polar_filament_project(test_payload, picks_user="tracer")

        path = str(tmp_path / "same-uri.star")
        export_picks(picks, path, "star", voxel_spacing=10.0)
        particles = _star_particles(path)
        assert particles["rlnHelicalTubeID"].tolist() == [1] * 3 + [2] * 3 + [3] * 3
        assert particles["rlnAnglePsiFlipRatio"].tolist() == [0.0] * 3 + [0.5] * 6

        export_picks(picks, path, "star", voxel_spacing=10.0, polarity_from_filaments=False)
        assert _star_particles(path)["rlnAnglePsiFlipRatio"].tolist() == [0.5] * 9

    def test_explicit_filaments_uri(self, test_payload, tmp_path):
        """Picks sampled into their own session (fil2picks -o) take the polarity from the Filaments they came from."""
        from copick.ops.export import export_picks, export_picks_combined

        root, picks, *_ = _polar_filament_project(test_payload)

        path = str(tmp_path / "no-source.star")
        export_picks(picks, path, "star", voxel_spacing=10.0)
        assert _star_particles(path)["rlnAnglePsiFlipRatio"].tolist() == [0.5] * 9

        export_picks(picks, path, "star", voxel_spacing=10.0, filaments_uri="microtubule:tracer/1")
        assert _star_particles(path)["rlnAnglePsiFlipRatio"].tolist() == [0.0] * 3 + [0.5] * 6

        combined = str(tmp_path / "combined.star")
        export_picks_combined(
            str(test_payload["cfg_file"]),
            combined,
            "microtubule:sampler/1",
            "star",
            voxel_spacing=10.0,
            filaments_uri="microtubule:tracer/*",
        )
        assert _star_particles(combined)["rlnAnglePsiFlipRatio"].tolist() == [0.0] * 3 + [0.5] * 6

        with pytest.raises(ValueError, match="polarity_from_filaments is False"):
            export_picks(
                picks,
                path,
                "star",
                voxel_spacing=10.0,
                filaments_uri="microtubule:tracer/1",
                polarity_from_filaments=False,
            )

    def test_ambiguous_filaments_uri_is_an_error(self, test_payload, tmp_path):
        from copick.ops.export import export_picks_combined

        root, picks, _, lines, _ = _polar_filament_project(test_payload)
        root.get_run("TS_001").new_filaments("microtubule", "2", user_id="tracer").from_numpy([lines[:3]])

        with pytest.raises(ValueError, match="matches several Filaments"):
            export_picks_combined(
                str(test_payload["cfg_file"]),
                str(tmp_path / "ambiguous.star"),
                "microtubule:sampler/1",
                "star",
                voxel_spacing=10.0,
                filaments_uri="microtubule:tracer/*",
            )

    def test_missing_filaments_are_an_error(self, test_payload, runner, tmp_path):
        from copick.ops.export import export_picks

        root, picks, filaments, points, _ = _polar_filament_project(test_payload)
        lines = [points[:3], points[3:6], points[6:]]
        path = str(tmp_path / "missing.star")

        # Filament 3 is not in the named source
        filaments.from_numpy(lines[:2], instance_ids=[1, 2], polarity_known=[True, False])
        with pytest.raises(ValueError, match=r"in TS_001 have no filament in microtubule:tracer/1: \[3\]"):
            export_picks(picks, path, "star", voxel_spacing=10.0, filaments_uri="microtubule:tracer/1")

        # The default source, the Filaments under the picks' own URI, is held to the same rule
        own = picks.run.new_filaments("microtubule", "1", user_id="sampler")
        own.from_numpy(lines[:1], instance_ids=[1], polarity_known=[True])
        with pytest.raises(ValueError, match=r"have no filament in microtubule:sampler/1: \[2, 3\]"):
            export_picks(picks, path, "star", voxel_spacing=10.0)

        # A named source that matches no Filaments in the run
        with pytest.raises(ValueError, match="No Filaments match microtubule:nobody/1 in TS_001"):
            export_picks(picks, path, "star", voxel_spacing=10.0, filaments_uri="microtubule:nobody/1")

        # The CLI fails, with one output file or one per run
        base = ["picks", "-c", str(test_payload["cfg_file"]), "--picks-uri", "microtubule:sampler/1"]
        base += ["--output-format", "star", "--voxel-size", "10.0", "--filaments-uri", "microtubule:tracer/1"]
        for output in (["--output-file", path], ["--output-dir", str(tmp_path / "per-run")]):
            result = runner.invoke(export, [*base, *output])
            assert result.exit_code != 0
            assert "have no filament in microtubule:tracer/1" in result.output

    def test_cli_filaments_uri_and_round_trip(self, test_payload, runner, tmp_path):
        """The CLI's polarity options, and export -> `copick add picks` reproducing IDs, order and frames."""
        root, picks, _, points, transforms = _polar_filament_project(test_payload)
        config = str(test_payload["cfg_file"])
        path = str(tmp_path / "cli.star")
        base = ["picks", "-c", config, "--picks-uri", "microtubule:sampler/1", "--output-file", path]
        base += ["--output-format", "star", "--voxel-size", "10.0", "--tilt-series-pixel-size", "2.0"]

        result = runner.invoke(export, [*base, "--filaments-uri", "microtubule:tracer/1"])
        assert result.exit_code == 0, result.output
        assert _star_particles(path)["rlnAnglePsiFlipRatio"].tolist() == [0.0] * 3 + [0.5] * 6

        result = runner.invoke(
            export,
            [*base, "--filaments-uri", "microtubule:tracer/1", "--no-polarity-from-filaments"],
        )
        assert result.exit_code != 0
        assert "--no-polarity-from-filaments" in result.output

        result = runner.invoke(
            add,
            ["picks", "-c", config, "--run", "TS_001", "--object-name", "microtubule", "--user-id", "round-trip"]
            + ["--session-id", "1", "--file-type", "star", "--voxel-size", "10.0", path],
        )
        assert result.exit_code == 0, result.output
        imported = copick.from_file(config).get_run("TS_001").get_picks("microtubule", "round-trip", "1")[0]
        assert imported.instance_ids().tolist() == [1] * 3 + [2] * 3 + [3] * 3
        assert imported.full_positions() == pytest.approx(points)
        assert imported.numpy()[1][:, :3, :3] == pytest.approx(transforms[:, :3, :3], abs=1e-6)
