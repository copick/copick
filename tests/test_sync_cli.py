"""Tests for the sync CLI commands."""

import json
import tempfile
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pytest
import trimesh
from click.testing import CliRunner
from copick.cli.sync import sync
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
def source_target_configs(test_payload):
    """Create source and target configurations for sync CLI tests."""
    # Create a target configuration in a temporary location
    with tempfile.TemporaryDirectory() as tmpdir:
        target_config_path = Path(tmpdir) / "target_config.json"

        # Copy and modify source config for target
        with open(test_payload["cfg_file"], "r") as f:
            source_config = json.load(f)

        # Create target config with different overlay root
        target_config = source_config.copy()
        if "overlay_root" in target_config:
            # Modify the overlay root to point to a different directory
            overlay_root = target_config["overlay_root"]
            if overlay_root.startswith("local://"):
                target_overlay_path = Path(tmpdir) / "target_overlay"
                target_overlay_path.mkdir()
                target_config["overlay_root"] = f"local://{target_overlay_path}"
            else:
                # For other protocols, just modify the path
                target_config["overlay_root"] = overlay_root.rstrip("/") + "_target"

        # Write target config
        with open(target_config_path, "w") as f:
            json.dump(target_config, f)

        yield {
            "source_config": test_payload["cfg_file"],
            "target_config": str(target_config_path),
            "source_root": test_payload["root"],
            "target_root": CopickRootFSSpec.from_file(target_config_path),
        }


class TestSyncPicksCLI:
    """Test cases for the sync picks CLI command."""

    def test_sync_picks_basic(self, source_target_configs, runner):
        """Test basic picks synchronization via CLI."""
        source_config = source_target_configs["source_config"]
        target_config = source_target_configs["target_config"]
        source_root = source_target_configs["source_root"]

        # Add test picks to source
        runs = list(source_root.runs)
        if not runs:
            test_run = source_root.new_run("test_run", exist_ok=True)
            runs = [test_run]

        source_run = runs[0]
        objects = list(source_root.pickable_objects)
        if not objects:
            pytest.skip("No pickable objects available for testing")

        source_obj = objects[0]

        # Create test picks
        picks = source_run.new_picks(
            object_name=source_obj.name,
            user_id="test-user",
            session_id="test-session",
            exist_ok=True,
        )
        picks.from_numpy(np.array([[10, 20, 30], [40, 50, 60]]))
        picks.store()

        # Run sync command
        result = runner.invoke(
            sync,
            [
                "picks",
                "--config",
                source_config,
                "--target-config",
                target_config,
                "--log",
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"
        assert "completed successfully" in result.output

        # Verify picks were synchronized
        target_root = CopickRootFSSpec.from_file(target_config)
        target_run = target_root.get_run(source_run.name)
        assert target_run is not None, "Target run should be created"

        target_picks_list = target_run.get_picks(
            object_name=source_obj.name,
            user_id="test-user",
            session_id="test-session",
        )
        assert len(target_picks_list) > 0, "Target picks should be created"

        target_picks = target_picks_list[0]
        assert len(target_picks.points) == 2, "Target picks should have same number of points"

    def test_sync_picks_with_name_mapping(self, source_target_configs, runner):
        """Test picks synchronization with name mapping via CLI."""
        source_config = source_target_configs["source_config"]
        target_config = source_target_configs["target_config"]
        source_root = source_target_configs["source_root"]
        target_root = source_target_configs["target_root"]

        # Add test picks to source
        runs = list(source_root.runs)
        if not runs:
            test_run = source_root.new_run("source_run", exist_ok=True)
            runs = [test_run]

        source_run = runs[0]
        objects = list(source_root.pickable_objects)
        if not objects:
            pytest.skip("No pickable objects available for testing")

        source_obj = objects[0]

        picks = source_run.new_picks(
            object_name=source_obj.name,
            user_id="source-user",
            session_id="test-session",
            exist_ok=True,
        )
        picks.from_numpy(np.array([[10, 20, 30]]))
        picks.store()

        # Ensure target object exists
        target_root.new_object(
            name="target-object",
            is_particle=source_obj.is_particle,
            label=999,  # Use a unique label to avoid conflicts
            exist_ok=True,
        )

        # Run sync command with name mapping
        result = runner.invoke(
            sync,
            [
                "picks",
                "--config",
                source_config,
                "--target-config",
                target_config,
                "--source-runs",
                source_run.name,
                "--target-runs",
                f"{source_run.name}:target_run",
                "--source-objects",
                source_obj.name,
                "--target-objects",
                f"{source_obj.name}:target-object",
                "--source-users",
                "source-user",
                "--target-users",
                "source-user:target-user",
                "--log",
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify with mapped names
        target_run = target_root.get_run("target_run")
        assert target_run is not None, "Target run should be created with mapped name"

        target_picks_list = target_run.get_picks(
            object_name="target-object",
            user_id="target-user",  # Fix hyphen vs underscore
            session_id="test-session",
        )
        assert len(target_picks_list) > 0, "Target picks should be created with mapped names"

    def test_sync_picks_with_user_filtering(self, source_target_configs, runner):
        """Test picks synchronization with user filtering via CLI."""
        source_config = source_target_configs["source_config"]
        target_config = source_target_configs["target_config"]
        source_root = source_target_configs["source_root"]

        # Add test picks from multiple users
        runs = list(source_root.runs)
        if not runs:
            test_run = source_root.new_run("test_run", exist_ok=True)
            runs = [test_run]

        source_run = runs[0]
        objects = list(source_root.pickable_objects)
        if not objects:
            pytest.skip("No pickable objects available for testing")

        source_obj = objects[0]

        # Create picks from user1
        picks1 = source_run.new_picks(
            object_name=source_obj.name,
            user_id="user1",
            session_id="session1",
            exist_ok=True,
        )
        picks1.from_numpy(np.array([[10, 20, 30]]))
        picks1.store()

        # Create picks from user2
        picks2 = source_run.new_picks(
            object_name=source_obj.name,
            user_id="user2",
            session_id="session2",
            exist_ok=True,
        )
        picks2.from_numpy(np.array([[40, 50, 60]]))
        picks2.store()

        # Sync only user1's picks
        result = runner.invoke(
            sync,
            [
                "picks",
                "--config",
                source_config,
                "--target-config",
                target_config,
                "--source-users",
                "user1",
                "--log",
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify only user1's picks were synchronized
        target_root = CopickRootFSSpec.from_file(target_config)
        target_run = target_root.get_run(source_run.name)

        user1_picks = target_run.get_picks(
            object_name=source_obj.name,
            user_id="user1",
            session_id="session1",
        )
        assert len(user1_picks) > 0, "User1 picks should be synchronized"

        user2_picks = target_run.get_picks(
            object_name=source_obj.name,
            user_id="user2",
            session_id="session2",
        )
        assert len(user2_picks) == 0, "User2 picks should not be synchronized"

    def test_sync_picks_with_exist_ok(self, source_target_configs, runner):
        """Test picks synchronization with exist_ok flag via CLI."""
        source_config = source_target_configs["source_config"]
        target_config = source_target_configs["target_config"]
        source_root = source_target_configs["source_root"]

        # Add test picks to source
        runs = list(source_root.runs)
        if not runs:
            test_run = source_root.new_run("test_run", exist_ok=True)
            runs = [test_run]

        source_run = runs[0]
        objects = list(source_root.pickable_objects)
        if not objects:
            pytest.skip("No pickable objects available for testing")

        source_obj = objects[0]

        picks = source_run.new_picks(
            object_name=source_obj.name,
            user_id="test-user",
            session_id="test-session",
            exist_ok=True,
        )
        picks.from_numpy(np.array([[10.0, 20.0, 30.0]]))
        picks.store()

        # First sync
        result1 = runner.invoke(
            sync,
            [
                "picks",
                "--config",
                source_config,
                "--target-config",
                target_config,
                "--log",
            ],
        )
        assert result1.exit_code == 0

        # Modify source picks
        picks.from_numpy(np.array([[10.0, 20.0, 30.0], [70.0, 80.0, 90.0]]))
        picks.store()

        # Second sync with exist_ok
        result2 = runner.invoke(
            sync,
            [
                "picks",
                "--config",
                source_config,
                "--target-config",
                target_config,
                "--exist-ok",
                "--log",
            ],
        )
        assert result2.exit_code == 0, f"Second sync failed: {result2.output}"

        # Verify updated picks
        target_root = CopickRootFSSpec.from_file(target_config)
        target_run = target_root.get_run(source_run.name)
        target_picks_list = target_run.get_picks(
            object_name=source_obj.name,
            user_id="test-user",
            session_id="test-session",
        )
        target_picks = target_picks_list[0]
        assert len(target_picks.points) == 2, "Target picks should be updated"

    def test_sync_picks_max_workers(self, source_target_configs, runner):
        """Test picks synchronization with custom max_workers via CLI."""
        source_config = source_target_configs["source_config"]
        target_config = source_target_configs["target_config"]
        source_root = source_target_configs["source_root"]

        # Add test data to multiple runs
        for i in range(3):
            test_run = source_root.new_run(f"test_run_{i}", exist_ok=True)
            objects = list(source_root.pickable_objects)
            if objects:
                source_obj = objects[0]
                picks = test_run.new_picks(
                    object_name=source_obj.name,
                    user_id="test-user",
                    session_id="test-session",
                    exist_ok=True,
                )
                picks.from_numpy(np.array([[i * 10.0, i * 20.0, i * 30.0]]))
                picks.store()

        # Run sync with custom max_workers
        result = runner.invoke(
            sync,
            [
                "picks",
                "--config",
                source_config,
                "--target-config",
                target_config,
                "--max-workers",
                "2",
                "--log",
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"

    def test_sync_picks_invalid_config(self, runner):
        """Test picks synchronization with invalid config files."""
        # Test with non-existent source config
        result = runner.invoke(
            sync,
            [
                "picks",
                "--config",
                "nonexistent_source.json",
                "--target-config",
                "nonexistent_target.json",
            ],
        )

        assert result.exit_code != 0, "Command should fail with non-existent config"

    def test_sync_picks_missing_target_config(self, source_target_configs, runner):
        """Test picks synchronization without target config (should fail)."""
        source_config = source_target_configs["source_config"]

        result = runner.invoke(
            sync,
            [
                "picks",
                "--config",
                source_config,
                # Missing --target-config
            ],
        )

        assert result.exit_code != 0, "Command should fail without target config"


class TestSyncMeshesCLI:
    """Test cases for the sync meshes CLI command."""

    def test_sync_meshes_basic(self, source_target_configs, runner):
        """Test basic meshes synchronization via CLI."""
        source_config = source_target_configs["source_config"]
        target_config = source_target_configs["target_config"]
        source_root = source_target_configs["source_root"]

        # Add test mesh to source
        runs = list(source_root.runs)
        if not runs:
            test_run = source_root.new_run("test_run", exist_ok=True)
            runs = [test_run]

        source_run = runs[0]
        objects = list(source_root.pickable_objects)
        if not objects:
            pytest.skip("No pickable objects available for testing")

        source_obj = objects[0]

        # Create test mesh
        mesh = source_run.new_mesh(
            object_name=source_obj.name,
            user_id="test-user",
            session_id="test-session",
            exist_ok=True,
        )

        # Create simple mesh data
        vertices = np.array([[0, 0, 0], [1, 0, 0], [0.5, 1, 0]], dtype=np.float32)
        faces = np.array([[0, 1, 2]], dtype=np.uint32)
        mesh.mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
        mesh.store()

        # Run sync command
        result = runner.invoke(
            sync,
            [
                "meshes",
                "--config",
                source_config,
                "--target-config",
                target_config,
                "--log",
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"
        assert "completed successfully" in result.output

        # Verify mesh was synchronized
        target_root = CopickRootFSSpec.from_file(target_config)
        target_run = target_root.get_run(source_run.name)
        assert target_run is not None, "Target run should be created"

        target_meshes = target_run.get_meshes(
            object_name=source_obj.name,
            user_id="test-user",
            session_id="test-session",
        )
        assert len(target_meshes) > 0, "Target mesh should be created"

    def test_sync_meshes_with_mapping(self, source_target_configs, runner):
        """Test meshes synchronization with name mapping via CLI."""
        source_config = source_target_configs["source_config"]
        target_config = source_target_configs["target_config"]
        source_root = source_target_configs["source_root"]
        target_root = source_target_configs["target_root"]

        # Add test mesh to source
        runs = list(source_root.runs)
        if not runs:
            test_run = source_root.new_run("source_run", exist_ok=True)
            runs = [test_run]

        source_run = runs[0]
        objects = list(source_root.pickable_objects)
        if not objects:
            pytest.skip("No pickable objects available for testing")

        source_obj = objects[0]

        mesh = source_run.new_mesh(
            object_name=source_obj.name,
            user_id="source-user",
            session_id="test-session",
            exist_ok=True,
        )
        vertices = np.array([[0, 0, 0]], dtype=np.float32)
        faces = np.array([[0]], dtype=np.uint32)
        mesh.mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
        mesh.store()

        # Ensure target object exists
        target_root.new_object(
            name="target-object",
            is_particle=source_obj.is_particle,
            label=998,  # Use a unique label to avoid conflicts
            exist_ok=True,
        )

        # Run sync with mapping
        result = runner.invoke(
            sync,
            [
                "meshes",
                "--config",
                source_config,
                "--target-config",
                target_config,
                "--source-runs",
                source_run.name,
                "--target-runs",
                f"{source_run.name}:target_run",
                "--source-objects",
                source_obj.name,
                "--target-objects",
                f"{source_obj.name}:target-object",
                "--source-users",
                "source-user",
                "--target-users",
                "source-user:target-user",
                "--log",
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify with mapped names
        target_run = target_root.get_run("target_run")
        assert target_run is not None, "Target run should be created with mapped name"

        target_meshes = target_run.get_meshes(
            object_name="target-object",
            user_id="target-user",
            session_id="test-session",
        )
        assert len(target_meshes) > 0, "Target mesh should be created with mapped names"


class TestSyncSegmentationsCLI:
    """Test cases for the sync segmentations CLI command."""

    def test_sync_segmentations_basic(self, source_target_configs, runner):
        """Test basic segmentations synchronization via CLI."""
        source_config = source_target_configs["source_config"]
        target_config = source_target_configs["target_config"]
        source_root = source_target_configs["source_root"]

        # Add test segmentation to source
        runs = list(source_root.runs)
        if not runs:
            test_run = source_root.new_run("test_run", exist_ok=True)
            runs = [test_run]

        source_run = runs[0]

        segmentation = source_run.new_segmentation(
            name="test-segmentation",
            user_id="test-user",
            session_id="test-session",
            voxel_size=10.0,
            is_multilabel=True,  # Use multilabel to avoid needing pickable object
            exist_ok=True,
        )
        test_data = np.random.randint(0, 3, (16, 16, 16), dtype=np.uint8)
        segmentation.from_numpy(test_data)

        # Run sync command
        result = runner.invoke(
            sync,
            [
                "segmentations",
                "--config",
                source_config,
                "--target-config",
                target_config,
                "--log",
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"
        assert "completed successfully" in result.output

        # Verify segmentation was synchronized
        target_root = CopickRootFSSpec.from_file(target_config)
        target_run = target_root.get_run(source_run.name)
        assert target_run is not None, "Target run should be created"

        target_segmentations = target_run.get_segmentations(
            name="test-segmentation",
            user_id="test-user",
            session_id="test-session",
            voxel_size=10.0,
        )
        assert len(target_segmentations) > 0, "Target segmentation should be created"

    def test_sync_segmentations_with_voxel_filtering(self, source_target_configs, runner):
        """Test segmentations synchronization with voxel spacing filtering via CLI."""
        source_config = source_target_configs["source_config"]
        target_config = source_target_configs["target_config"]
        source_root = source_target_configs["source_root"]

        # Add test segmentations at different voxel spacings
        # Create a unique run for this test to avoid conflicts with existing data
        source_run = source_root.new_run("voxel-filter-test-run", exist_ok=True)

        # Create segmentations at different voxel sizes
        seg1 = source_run.new_segmentation(
            name="test-seg-10",
            user_id="test-user",
            session_id="test-session",
            voxel_size=10.0,
            is_multilabel=True,  # Use multilabel to avoid needing pickable object
            exist_ok=True,
        )
        test_data = np.random.randint(0, 3, (8, 8, 8), dtype=np.uint8)
        seg1.from_numpy(test_data)

        seg2 = source_run.new_segmentation(
            name="test-seg-20",
            user_id="test-user",
            session_id="test-session",
            voxel_size=20.0,
            is_multilabel=True,  # Use multilabel to avoid needing pickable object
            exist_ok=True,
        )
        seg2.from_numpy(test_data)

        # Sync only 10.0 voxel spacing
        result = runner.invoke(
            sync,
            [
                "segmentations",
                "--config",
                source_config,
                "--target-config",
                target_config,
                "--voxel-spacings",
                "10.0",
                "--log",
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify only 10.0 spacing was synchronized
        target_root = CopickRootFSSpec.from_file(target_config)
        target_run = target_root.get_run(source_run.name)

        target_segs_10 = target_run.get_segmentations(voxel_size=10.0)
        assert len(target_segs_10) > 0, "10.0 voxel spacing should be synchronized"

        target_segs_20 = target_run.get_segmentations(voxel_size=20.0)
        assert len(target_segs_20) == 0, "20.0 voxel spacing should not be synchronized"

    def test_sync_segmentations_with_name_mapping(self, source_target_configs, runner):
        """Test segmentations synchronization with name mapping via CLI."""
        source_config = source_target_configs["source_config"]
        target_config = source_target_configs["target_config"]
        source_root = source_target_configs["source_root"]

        # Add test segmentation
        runs = list(source_root.runs)
        if not runs:
            test_run = source_root.new_run("source_run", exist_ok=True)
            runs = [test_run]

        source_run = runs[0]

        segmentation = source_run.new_segmentation(
            name="source-segmentation",
            user_id="source-user",
            session_id="test-session",
            voxel_size=10.0,
            is_multilabel=True,  # Use multilabel to avoid needing pickable object
            exist_ok=True,
        )
        test_data = np.random.randint(0, 3, (8, 8, 8), dtype=np.uint8)
        segmentation.from_numpy(test_data)

        # Run sync with mapping
        result = runner.invoke(
            sync,
            [
                "segmentations",
                "--config",
                source_config,
                "--target-config",
                target_config,
                "--source-runs",
                source_run.name,
                "--target-runs",
                f"{source_run.name}:target_run",
                "--source-names",
                "source-segmentation",
                "--target-names",
                "source-segmentation:target-segmentation",
                "--source-users",
                "source-user",
                "--target-users",
                "source-user:target-user",
                "--log",
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify with mapped names
        target_root = CopickRootFSSpec.from_file(target_config)
        target_run = target_root.get_run("target_run")
        assert target_run is not None, "Target run should be created with mapped name"

        target_segmentations = target_run.get_segmentations(
            name="target-segmentation",
            user_id="target-user",
            session_id="test-session",
            voxel_size=10.0,
        )
        assert len(target_segmentations) > 0, "Target segmentation should be created with mapped names"


class TestSyncTomogramsCLI:
    """Test cases for the sync tomograms CLI command."""

    def test_sync_tomograms_basic(self, source_target_configs, runner):
        """Test basic tomograms synchronization via CLI."""
        source_config = source_target_configs["source_config"]
        target_config = source_target_configs["target_config"]
        source_root = source_target_configs["source_root"]

        # Check if we have existing tomograms to sync
        runs = list(source_root.runs)
        if not runs:
            pytest.skip("No runs available for testing")

        source_run = runs[0]
        voxel_spacings = list(source_run.voxel_spacings)
        if not voxel_spacings:
            pytest.skip("No voxel spacings available for testing")

        source_vs = voxel_spacings[0]
        tomograms = source_vs.tomograms
        if not tomograms:
            pytest.skip("No tomograms available for testing")

        # Run sync command
        result = runner.invoke(
            sync,
            [
                "tomograms",
                "--config",
                source_config,
                "--target-config",
                target_config,
                "--log",
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"
        assert "completed successfully" in result.output

        # Verify tomogram was synchronized
        target_root = CopickRootFSSpec.from_file(target_config)
        target_run = target_root.get_run(source_run.name)
        assert target_run is not None, "Target run should be created"

        target_vs = target_run.get_voxel_spacing(source_vs.voxel_size)
        assert target_vs is not None, "Target voxel spacing should be created"

    def test_sync_tomograms_with_type_mapping(self, source_target_configs, runner):
        """Test tomograms synchronization with type mapping via CLI."""
        source_config = source_target_configs["source_config"]
        target_config = source_target_configs["target_config"]
        source_root = source_target_configs["source_root"]

        # Check for existing tomograms
        runs = list(source_root.runs)
        if not runs:
            pytest.skip("No runs available for testing")

        source_run = runs[0]
        voxel_spacings = list(source_run.voxel_spacings)
        if not voxel_spacings:
            pytest.skip("No voxel spacings available for testing")

        source_vs = voxel_spacings[0]
        tomograms = source_vs.tomograms
        if not tomograms:
            pytest.skip("No tomograms available for testing")

        source_tomo_type = tomograms[0].tomo_type

        # Run sync with type mapping
        result = runner.invoke(
            sync,
            [
                "tomograms",
                "--config",
                source_config,
                "--target-config",
                target_config,
                "--source-runs",
                source_run.name,
                "--target-runs",
                f"{source_run.name}:target_run",
                "--source-tomo-types",
                source_tomo_type,
                "--target-tomo-types",
                f"{source_tomo_type}:mapped-type",
                "--log",
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify with mapped names
        target_root = CopickRootFSSpec.from_file(target_config)
        target_run = target_root.get_run("target_run")
        assert target_run is not None, "Target run should be created with mapped name"

        target_vs = target_run.get_voxel_spacing(source_vs.voxel_size)
        assert target_vs is not None, "Target voxel spacing should be created"

        target_tomos = target_vs.get_tomograms("mapped-type")
        assert len(target_tomos) > 0, "Target tomogram should be created with mapped type"

    def test_sync_tomograms_with_voxel_filtering(self, source_target_configs, runner):
        """Test tomograms synchronization with voxel spacing filtering via CLI."""
        source_config = source_target_configs["source_config"]
        target_config = source_target_configs["target_config"]
        source_root = source_target_configs["source_root"]

        # Check for existing tomograms at different voxel spacings
        runs = list(source_root.runs)
        if not runs:
            pytest.skip("No runs available for testing")

        source_run = runs[0]
        voxel_spacings = list(source_run.voxel_spacings)
        if len(voxel_spacings) < 1:
            pytest.skip("Need at least one voxel spacing for testing")

        # Use the first voxel spacing for filtering
        target_voxel_size = voxel_spacings[0].voxel_size

        # Run sync with voxel spacing filtering
        result = runner.invoke(
            sync,
            [
                "tomograms",
                "--config",
                source_config,
                "--target-config",
                target_config,
                "--voxel-spacings",
                str(target_voxel_size),
                "--log",
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify only the specified voxel spacing was synchronized
        target_root = CopickRootFSSpec.from_file(target_config)
        target_run = target_root.get_run(source_run.name)
        target_vs = target_run.get_voxel_spacing(target_voxel_size)
        assert target_vs is not None, f"Target voxel spacing {target_voxel_size} should be created"


class TestSyncCLIIntegration:
    """Integration tests for sync CLI commands."""

    def test_sync_all_data_types_cli(self, source_target_configs, runner):
        """Test syncing all data types via CLI commands."""
        source_config = source_target_configs["source_config"]
        target_config = source_target_configs["target_config"]
        source_root = source_target_configs["source_root"]

        # Add test data to source
        runs = list(source_root.runs)
        if not runs:
            test_run = source_root.new_run("test_run", exist_ok=True)
            runs = [test_run]

        source_run = runs[0]
        objects = list(source_root.pickable_objects)
        if not objects:
            pytest.skip("No pickable objects available for testing")

        source_obj = objects[0]

        # Add picks
        picks = source_run.new_picks(
            object_name=source_obj.name,
            user_id="test-user",
            session_id="test-session",
            exist_ok=True,
        )
        picks.from_numpy(np.array([[10, 20, 30]]))
        picks.store()

        # Add mesh
        mesh = source_run.new_mesh(
            object_name=source_obj.name,
            user_id="test-user",
            session_id="test-session",
            exist_ok=True,
        )
        vertices = np.array([[0, 0, 0]], dtype=np.float32)
        faces = np.array([[0]], dtype=np.uint32)
        mesh.mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
        mesh.store()

        # Add segmentation
        segmentation = source_run.new_segmentation(
            name="test-segmentation",
            user_id="test-user",
            session_id="test-session",
            voxel_size=10.0,
            is_multilabel=True,  # Use multilabel to avoid needing pickable object
            exist_ok=True,
        )
        test_data = np.random.randint(0, 3, (8, 8, 8), dtype=np.uint8)
        segmentation.from_numpy(test_data)

        # Sync picks
        result1 = runner.invoke(
            sync,
            [
                "picks",
                "--config",
                source_config,
                "--target-config",
                target_config,
                "--log",
            ],
        )
        assert result1.exit_code == 0, f"Picks sync failed: {result1.output}"

        # Sync meshes
        result2 = runner.invoke(
            sync,
            [
                "meshes",
                "--config",
                source_config,
                "--target-config",
                target_config,
                "--log",
            ],
        )
        assert result2.exit_code == 0, f"Meshes sync failed: {result2.output}"

        # Sync segmentations
        result3 = runner.invoke(
            sync,
            [
                "segmentations",
                "--config",
                source_config,
                "--target-config",
                target_config,
                "--log",
            ],
        )
        assert result3.exit_code == 0, f"Segmentations sync failed: {result3.output}"

        # Verify all data types were synchronized
        target_root = CopickRootFSSpec.from_file(target_config)
        target_run = target_root.get_run(source_run.name)
        assert target_run is not None, "Target run should be created"

        # Check picks
        target_picks = target_run.get_picks(
            object_name=source_obj.name,
            user_id="test-user",
            session_id="test-session",
        )
        assert len(target_picks) > 0, "Target picks should be created"

        # Check meshes
        target_meshes = target_run.get_meshes(
            object_name=source_obj.name,
            user_id="test-user",
            session_id="test-session",
        )
        assert len(target_meshes) > 0, "Target meshes should be created"

        # Check segmentations
        target_segmentations = target_run.get_segmentations(
            name="test-segmentation",
            user_id="test-user",
            session_id="test-session",
            voxel_size=10.0,
        )
        assert len(target_segmentations) > 0, "Target segmentations should be created"

    def test_sync_cli_help_commands(self, runner):
        """Test help output for sync CLI commands."""
        # Test main sync help
        result = runner.invoke(sync, ["--help"])
        assert result.exit_code == 0
        assert "Synchronize data between Copick projects" in result.output

        # Test picks help
        result = runner.invoke(sync, ["picks", "--help"])
        assert result.exit_code == 0
        assert "Synchronize picks between two Copick projects" in result.output

        # Test meshes help
        result = runner.invoke(sync, ["meshes", "--help"])
        assert result.exit_code == 0
        assert "Synchronize meshes between two Copick projects" in result.output

        # Test segmentations help
        result = runner.invoke(sync, ["segmentations", "--help"])
        assert result.exit_code == 0
        assert "Synchronize segmentations between two Copick projects" in result.output

        # Test tomograms help
        result = runner.invoke(sync, ["tomograms", "--help"])
        assert result.exit_code == 0
        assert "Synchronize tomograms between two Copick projects" in result.output

    def test_sync_cli_debug_mode(self, source_target_configs, runner):
        """Test sync CLI commands with debug mode enabled."""
        source_config = source_target_configs["source_config"]
        target_config = source_target_configs["target_config"]
        source_root = source_target_configs["source_root"]

        # Add minimal test data
        runs = list(source_root.runs)
        if not runs:
            test_run = source_root.new_run("test_run", exist_ok=True)
            runs = [test_run]

        # Run sync with debug mode
        result = runner.invoke(
            sync,
            [
                "picks",
                "--config",
                source_config,
                "--target-config",
                target_config,
                "--debug",
                "--log",
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"
        # Debug mode should still complete successfully
