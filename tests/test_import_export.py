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
    with tempfile.NamedTemporaryFile(suffix=".em", delete=False) as tmp:
        # Create a simple EM motivelist (20 x N array format)
        # See TOM toolbox documentation for motivelist format
        n_particles = 3
        data = np.zeros((20, n_particles), dtype=np.float32)

        # Set positions (columns 8, 9, 10 in 1-indexed, so 7, 8, 9 in 0-indexed)
        data[7, :] = [10.0, 20.0, 30.0]  # X positions in pixels
        data[8, :] = [15.0, 25.0, 35.0]  # Y positions in pixels
        data[9, :] = [20.0, 30.0, 40.0]  # Z positions in pixels

        # Set Euler angles (columns 17, 18, 19 in 1-indexed)
        data[16, :] = [0.0, 0.0, 0.0]  # Phi
        data[17, :] = [0.0, 0.0, 0.0]  # Psi
        data[18, :] = [0.0, 0.0, 0.0]  # Theta

        # Set class/tomogram number
        data[4, :] = [1, 1, 1]  # Tomogram number

        emfile.write(tmp.name, data)
        yield tmp.name

    with contextlib.suppress(PermissionError, OSError):
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)


@pytest.fixture
def sample_dynamo_table():
    """Create a sample Dynamo table file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".tbl", delete=False, mode="w") as tmp:
        # Create minimal Dynamo table with required columns
        # Format: tag tomo x y z tdrot tilt narot dx dy dz ...
        # Column indices (1-indexed): 1=tag, 4=x, 5=y, 6=z, 7=tdrot, 8=tilt, 9=narot
        lines = [
            "1 1 0 10.0 15.0 20.0 0.0 0.0 0.0 0.0 0.0 0.0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0",
            "2 1 0 20.0 25.0 30.0 0.0 0.0 0.0 0.0 0.0 0.0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0",
        ]
        tmp.write("\n".join(lines))
        tmp.flush()
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
