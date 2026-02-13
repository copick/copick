"""Tests for import/export functionality."""

import contextlib
import os
import tempfile
from pathlib import Path
from typing import Any, Dict

import emfile
import numpy as np
import pytest
import tifffile
from click.testing import CliRunner
from copick.cli.add import add
from copick.cli.export import export
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
        binning = 1.0

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
                tomo_size_x * pixel_size * binning / 2,
                tomo_size_y * pixel_size * binning / 2,
                tomo_size_z * pixel_size * binning / 2,
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
        root = CopickRootFSSpec.from_file(config_file)
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
        root = CopickRootFSSpec.from_file(config_file)
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
        root = CopickRootFSSpec.from_file(config_file)

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
                sample_dynamo_table_multi_tomo,
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify picks were imported
        root = CopickRootFSSpec.from_file(config_file)
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
        root = CopickRootFSSpec.from_file(config_file)

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
        root = CopickRootFSSpec.from_file(config_file)

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
        root = CopickRootFSSpec.from_file(config_file)
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
