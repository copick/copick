"""Tests for the sync operations module."""

import json
import tempfile
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pytest
import trimesh
from copick.impl.filesystem import CopickRootFSSpec
from copick.ops.sync import sync_meshes, sync_picks, sync_segmentations, sync_tomograms


@pytest.fixture(params=pytest.common_cases)
def test_payload(request) -> Dict[str, Any]:
    payload = request.getfixturevalue(request.param)
    payload["root"] = CopickRootFSSpec.from_file(payload["cfg_file"])
    return payload


@pytest.fixture
def source_target_configs(test_payload):
    """Create source and target configurations for sync tests."""
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


class TestSyncPicks:
    """Test cases for picks synchronization."""

    def test_sync_picks_basic(self, source_target_configs):
        """Test basic picks synchronization."""
        source_root = source_target_configs["source_root"]
        target_root = source_target_configs["target_root"]

        # Add some test picks to the source
        runs = list(source_root.runs)
        if not runs:
            # Create a test run if none exist
            test_run = source_root.new_run("test_run", exist_ok=True)
            runs = [test_run]

        source_run = runs[0]

        # Get a pickable object
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

        # Perform synchronization
        sync_picks(
            source_root=source_root,
            target_root=target_root,
            log=True,
        )

        # Verify picks were synchronized
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

    def test_sync_picks_with_name_mapping(self, source_target_configs):
        """Test picks synchronization with name mapping."""
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

        # Ensure the target object exists
        target_root.new_object(
            name="target-object",
            is_particle=source_obj.is_particle,
            exist_ok=True,
        )

        # Perform synchronization with mapping
        sync_picks(
            source_root=source_root,
            target_root=target_root,
            source_runs=[source_run.name],
            target_runs={source_run.name: "target_run"},
            source_objects=[source_obj.name],
            target_objects={source_obj.name: "target-object"},
            source_users=["source-user"],
            target_users={"source-user": "target-user"},
            log=True,
        )

        # Verify with mapped names
        target_run = target_root.get_run("target_run")
        assert target_run is not None, "Target run should be created with mapped name"

        target_picks_list = target_run.get_picks(
            object_name="target-object",
            user_id="target-user",
            session_id="test-session",
        )
        assert len(target_picks_list) > 0, "Target picks should be created with mapped names"

    def test_sync_picks_with_user_filtering(self, source_target_configs):
        """Test picks synchronization with user filtering."""
        source_root = source_target_configs["source_root"]
        target_root = source_target_configs["target_root"]

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
        sync_picks(
            source_root=source_root,
            target_root=target_root,
            source_users=["user1"],
            log=True,
        )

        # Verify only user1's picks were synchronized
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

    def test_sync_picks_exist_ok(self, source_target_configs):
        """Test picks synchronization with exist_ok flag."""
        source_root = source_target_configs["source_root"]
        target_root = source_target_configs["target_root"]

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

        # Create initial picks
        picks = source_run.new_picks(
            object_name=source_obj.name,
            user_id="test-user",
            session_id="test-session",
            exist_ok=True,
        )
        picks.from_numpy(np.array([[10, 20, 30]]))
        picks.store()

        # First sync
        sync_picks(
            source_root=source_root,
            target_root=target_root,
            log=True,
        )

        # Modify source picks
        picks.from_numpy(np.array([[10, 20, 30], [70, 80, 90]]))
        picks.store()

        # Second sync with exist_ok=True
        sync_picks(
            source_root=source_root,
            target_root=target_root,
            exist_ok=True,
            log=True,
        )

        # Verify updated picks
        target_run = target_root.get_run(source_run.name)
        target_picks_list = target_run.get_picks(
            object_name=source_obj.name,
            user_id="test-user",
            session_id="test-session",
        )
        target_picks = target_picks_list[0]
        assert len(target_picks.points) == 2, "Target picks should be updated"


class TestSyncMeshes:
    """Test cases for meshes synchronization."""

    def test_sync_meshes_basic(self, source_target_configs):
        """Test basic meshes synchronization."""
        source_root = source_target_configs["source_root"]
        target_root = source_target_configs["target_root"]

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

        # Create simple mesh data (triangle)
        vertices = np.array(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [0.5, 1.0, 0.0],
            ],
            dtype=np.float32,
        )

        faces = np.array(
            [
                [0, 1, 2],
            ],
            dtype=np.uint32,
        )

        mesh.mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
        mesh.store()

        # Perform synchronization
        sync_meshes(
            source_root=source_root,
            target_root=target_root,
            log=True,
        )

        # Verify mesh was synchronized
        target_run = target_root.get_run(source_run.name)
        assert target_run is not None, "Target run should be created"

        target_meshes = target_run.get_meshes(
            object_name=source_obj.name,
            user_id="test-user",
            session_id="test-session",
        )
        assert len(target_meshes) > 0, "Target mesh should be created"

        target_mesh = target_meshes[0]
        assert target_mesh.mesh is not None, "Target mesh should have data"
        assert hasattr(target_mesh.mesh, "vertices"), "Target mesh should have vertices"
        assert hasattr(target_mesh.mesh, "faces"), "Target mesh should have faces"

    def test_sync_meshes_with_mapping(self, source_target_configs):
        """Test meshes synchronization with name mapping."""
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

        # Create test mesh
        mesh = source_run.new_mesh(
            object_name=source_obj.name,
            user_id="source-user",
            session_id="test-session",
            exist_ok=True,
        )
        mesh.mesh = trimesh.Trimesh(
            vertices=np.array([[0, 0, 0]], dtype=np.float32),
            faces=np.array([[0]], dtype=np.uint32),
        )
        mesh.store()

        # Ensure target object exists
        target_root.new_object(
            name="target-object",
            is_particle=source_obj.is_particle,
            exist_ok=True,
        )

        # Perform synchronization with mapping
        sync_meshes(
            source_root=source_root,
            target_root=target_root,
            source_runs=[source_run.name],
            target_runs={source_run.name: "target_run"},
            source_objects=[source_obj.name],
            target_objects={source_obj.name: "target-object"},
            source_users=["source-user"],
            target_users={"source-user": "target-user"},
            log=True,
        )

        # Verify with mapped names
        target_run = target_root.get_run("target_run")
        assert target_run is not None, "Target run should be created with mapped name"

        target_meshes = target_run.get_meshes(
            object_name="target-object",
            user_id="target-user",
            session_id="test-session",
        )
        assert len(target_meshes) > 0, "Target mesh should be created with mapped names"


class TestSyncSegmentations:
    """Test cases for segmentations synchronization."""

    def test_sync_segmentations_basic(self, source_target_configs):
        """Test basic segmentations synchronization."""
        source_root = source_target_configs["source_root"]
        target_root = source_target_configs["target_root"]

        # Add test segmentation to source
        runs = list(source_root.runs)
        if not runs:
            test_run = source_root.new_run("test_run", exist_ok=True)
            runs = [test_run]

        source_run = runs[0]

        # Create test segmentation (multilabel to avoid pickable object requirement)
        segmentation = source_run.new_segmentation(
            name="test-segmentation",
            user_id="test-user",
            session_id="test-session",
            voxel_size=10.0,
            is_multilabel=True,
            exist_ok=True,
        )

        # Add test data
        test_data = np.random.randint(0, 3, (32, 32, 32), dtype=np.uint8)
        segmentation.from_numpy(test_data)

        # Perform synchronization
        sync_segmentations(
            source_root=source_root,
            target_root=target_root,
            log=True,
        )

        # Verify segmentation was synchronized
        target_run = target_root.get_run(source_run.name)
        assert target_run is not None, "Target run should be created"

        target_segmentations = target_run.get_segmentations(
            name="test-segmentation",
            user_id="test-user",
            session_id="test-session",
            voxel_size=10.0,
        )
        assert len(target_segmentations) > 0, "Target segmentation should be created"

    def test_sync_segmentations_with_voxel_filtering(self, source_target_configs):
        """Test segmentations synchronization with voxel spacing filtering."""
        source_root = source_target_configs["source_root"]
        target_root = source_target_configs["target_root"]

        # Add test segmentations at different voxel spacings
        # Create a unique run for this test to avoid conflicts with existing data
        source_run = source_root.new_run("voxel-filter-test-run", exist_ok=True)

        # Create segmentations at different voxel sizes
        seg1 = source_run.new_segmentation(
            name="test-seg-10",
            user_id="test-user",
            session_id="test-session",
            voxel_size=10.0,
            is_multilabel=True,
            exist_ok=True,
        )
        test_data = np.random.randint(0, 3, (16, 16, 16), dtype=np.uint8)
        seg1.from_numpy(test_data)

        seg2 = source_run.new_segmentation(
            name="test-seg-20",
            user_id="test-user",
            session_id="test-session",
            voxel_size=20.0,
            is_multilabel=True,
            exist_ok=True,
        )
        seg2.from_numpy(test_data)

        # Sync only 10.0 voxel spacing
        sync_segmentations(
            source_root=source_root,
            target_root=target_root,
            voxel_spacings=[10.0],
            log=True,
        )

        # Verify only 10.0 spacing was synchronized
        target_run = target_root.get_run(source_run.name)

        target_segs_10 = target_run.get_segmentations(voxel_size=10.0)
        assert len(target_segs_10) > 0, "10.0 voxel spacing should be synchronized"

        target_segs_20 = target_run.get_segmentations(voxel_size=20.0)
        assert len(target_segs_20) == 0, "20.0 voxel spacing should not be synchronized"

    def test_sync_segmentations_with_name_mapping(self, source_target_configs):
        """Test segmentations synchronization with name mapping."""
        source_root = source_target_configs["source_root"]
        target_root = source_target_configs["target_root"]

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
            is_multilabel=True,
            exist_ok=True,
        )
        test_data = np.random.randint(0, 3, (16, 16, 16), dtype=np.uint8)
        segmentation.from_numpy(test_data)

        # Perform synchronization with mapping
        sync_segmentations(
            source_root=source_root,
            target_root=target_root,
            source_runs=[source_run.name],
            target_runs={source_run.name: "target_run"},
            source_names=["source-segmentation"],
            target_names={"source-segmentation": "target-segmentation"},
            source_users=["source-user"],
            target_users={"source-user": "target-user"},
            log=True,
        )

        # Verify with mapped names
        target_run = target_root.get_run("target_run")
        assert target_run is not None, "Target run should be created with mapped name"

        target_segmentations = target_run.get_segmentations(
            name="target-segmentation",
            user_id="target-user",
            session_id="test-session",
            voxel_size=10.0,
        )
        assert len(target_segmentations) > 0, "Target segmentation should be created with mapped names"


class TestSyncTomograms:
    """Test cases for tomograms synchronization."""

    def test_sync_tomograms_basic(self, source_target_configs):
        """Test basic tomograms synchronization."""
        source_root = source_target_configs["source_root"]
        target_root = source_target_configs["target_root"]

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

        # Perform synchronization
        sync_tomograms(
            source_root=source_root,
            target_root=target_root,
            log=True,
        )

        # Verify tomogram was synchronized
        target_run = target_root.get_run(source_run.name)
        assert target_run is not None, "Target run should be created"

        target_vs = target_run.get_voxel_spacing(source_vs.voxel_size)
        assert target_vs is not None, "Target voxel spacing should be created"

        source_tomo_types = [tomo.tomo_type for tomo in tomograms]
        target_tomos = []
        for tomo_type in source_tomo_types:
            tomos = target_vs.get_tomograms(tomo_type)
            target_tomos.extend(tomos)

        assert len(target_tomos) > 0, "Target tomograms should be created"

    def test_sync_tomograms_with_type_mapping(self, source_target_configs):
        """Test tomograms synchronization with type mapping."""
        source_root = source_target_configs["source_root"]
        target_root = source_target_configs["target_root"]

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

        # Perform synchronization with type mapping
        sync_tomograms(
            source_root=source_root,
            target_root=target_root,
            source_runs=[source_run.name],
            target_runs={source_run.name: "target_run"},
            source_tomo_types=[source_tomo_type],
            target_tomo_types={source_tomo_type: "mapped-type"},
            log=True,
        )

        # Verify with mapped names
        target_run = target_root.get_run("target_run")
        assert target_run is not None, "Target run should be created with mapped name"

        target_vs = target_run.get_voxel_spacing(source_vs.voxel_size)
        assert target_vs is not None, "Target voxel spacing should be created"

        target_tomos = target_vs.get_tomograms("mapped-type")
        assert len(target_tomos) > 0, "Target tomogram should be created with mapped type"

    def test_sync_tomograms_with_voxel_filtering(self, source_target_configs):
        """Test tomograms synchronization with voxel spacing filtering."""
        source_root = source_target_configs["source_root"]
        target_root = source_target_configs["target_root"]

        # Check for existing tomograms at different voxel spacings
        # Create a unique run for this test to avoid conflicts with existing data
        source_run = source_root.new_run("voxel-filter-test-run", exist_ok=True)
        source_run.new_voxel_spacing(12.0, exist_ok=True)

        voxel_spacings = list(source_run.voxel_spacings)

        # Use the first voxel spacing for filtering
        target_voxel_size = voxel_spacings[0].voxel_size

        # Sync only specific voxel spacing
        sync_tomograms(
            source_root=source_root,
            target_root=target_root,
            voxel_spacings=[target_voxel_size],
            log=True,
        )

        # Verify only the specified voxel spacing was synchronized
        target_run = target_root.get_run(source_run.name)
        target_vs = target_run.get_voxel_spacing(target_voxel_size)
        assert target_vs is not None, f"Target voxel spacing {target_voxel_size} should be created"

        # Check that other voxel spacings were not synchronized
        for vs in voxel_spacings[1:]:
            other_target_vs = target_run.get_voxel_spacing(vs.voxel_size)
            if other_target_vs is not None:
                assert (
                    len(other_target_vs.tomograms) == 0
                ), f"Other voxel spacing {vs.voxel_size} should not have tomograms"


class TestSyncIntegration:
    """Integration tests for sync operations."""

    def test_sync_all_data_types(self, source_target_configs):
        """Test synchronizing all data types together."""
        source_root = source_target_configs["source_root"]
        target_root = source_target_configs["target_root"]

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
        mesh.mesh = trimesh.Trimesh(
            vertices=np.array([[0, 0, 0]], dtype=np.float32),
            faces=np.array([[0]], dtype=np.uint32),
        )
        mesh.store()

        # Add segmentation
        segmentation = source_run.new_segmentation(
            name="test-segmentation",
            user_id="test-user",
            session_id="test-session",
            voxel_size=10.0,
            is_multilabel=True,
            exist_ok=True,
        )
        test_data = np.random.randint(0, 3, (16, 16, 16), dtype=np.uint8)
        segmentation.from_numpy(test_data)

        # Sync all data types
        sync_picks(source_root=source_root, target_root=target_root, log=True)
        sync_meshes(source_root=source_root, target_root=target_root, log=True)
        sync_segmentations(source_root=source_root, target_root=target_root, log=True)

        # Sync tomograms if they exist
        voxel_spacings = list(source_run.voxel_spacings)
        if voxel_spacings and voxel_spacings[0].tomograms:
            sync_tomograms(source_root=source_root, target_root=target_root, log=True)

        # Verify all data types were synchronized
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

    def test_sync_with_parallel_workers(self, source_target_configs):
        """Test synchronization with multiple parallel workers."""
        source_root = source_target_configs["source_root"]
        target_root = source_target_configs["target_root"]

        # Add test data to multiple runs
        test_runs = []
        for i in range(3):
            run_name = f"test_run_{i}"
            test_run = source_root.new_run(run_name, exist_ok=True)
            test_runs.append(test_run)

            objects = list(source_root.pickable_objects)
            if objects:
                source_obj = objects[0]
                picks = test_run.new_picks(
                    object_name=source_obj.name,
                    user_id="test-user",
                    session_id="test-session",
                    exist_ok=True,
                )
                picks.from_numpy(np.array([[i * 10, i * 20, i * 30]]))
                picks.store()

        # Sync with multiple workers
        sync_picks(
            source_root=source_root,
            target_root=target_root,
            max_workers=3,
            log=True,
        )

        # Verify all runs were synchronized
        for test_run in test_runs:
            target_run = target_root.get_run(test_run.name)
            assert target_run is not None, f"Target run {test_run.name} should be created"

    def test_sync_error_handling(self, source_target_configs):
        """Test sync error handling for missing objects."""
        source_root = source_target_configs["source_root"]
        target_root = source_target_configs["target_root"]

        # Add test picks with an object that won't exist in target
        runs = list(source_root.runs)
        if not runs:
            test_run = source_root.new_run("test_run", exist_ok=True)
            runs = [test_run]

        source_run = runs[0]

        # Create a temporary object in source
        source_root.new_object(
            name="temp-object",
            is_particle=True,
            exist_ok=True,
        )

        picks = source_run.new_picks(
            object_name="temp-object",
            user_id="test-user",
            session_id="test-session",
            exist_ok=True,
        )
        picks.from_numpy(np.array([[10, 20, 30]]))
        picks.store()

        # Remove object from target (or don't create it)
        # Sync should handle missing target object gracefully
        sync_picks(
            source_root=source_root,
            target_root=target_root,
            source_objects=["temp-object"],
            log=True,
        )

        # The sync should complete without raising exceptions
        # but the specific pick may not be created due to missing target object
        target_run = target_root.get_run(source_run.name)
        assert target_run is not None, "Target run should still be created"
