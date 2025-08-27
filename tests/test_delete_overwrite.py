from typing import Any, Dict

import pytest
import zarr
from copick.impl.filesystem import CopickRootFSSpec


@pytest.fixture(params=pytest.common_cases)
def test_payload(request) -> Dict[str, Any]:
    payload = request.getfixturevalue(request.param)
    payload["root"] = CopickRootFSSpec.from_file(payload["cfg_file"])
    return payload


def test_delete_run(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]
    overlay_fs = test_payload["testfs_overlay"]
    overlay_loc = test_payload["testpath_overlay"]

    # Create a new run to delete
    run_name = "TS_DELETE"
    run = copick_root.new_run(run_name)
    assert run in copick_root.runs, "Run not added to runs"

    # Check that run exists in filesystem
    run_path_overlay = str(overlay_loc / "ExperimentRuns" / run_name)
    assert overlay_fs.exists(run_path_overlay), f"{run_name} not found in overlay"

    # Delete the run
    copick_root.delete_run(run_name)

    # Verify run is removed from runs list
    assert run not in copick_root.runs, "Run still in runs list"

    # Verify run is removed from filesystem
    assert not overlay_fs.exists(run_path_overlay), f"{run_name} still exists in overlay"

    # TODO: decide what to do in this case
    # Trying to delete a non-existent run should raise an error
    # with pytest.raises(FileNotFoundError):
    #     copick_root.delete_run(run_name)


def test_delete_voxel_spacing(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]
    copick_run = copick_root.get_run("TS_001")
    overlay_fs = test_payload["testfs_overlay"]
    overlay_loc = test_payload["testpath_overlay"]

    # Create a new voxel spacing to delete
    vs_size = 15.000
    vs = copick_run.new_voxel_spacing(vs_size)
    assert vs in copick_run.voxel_spacings, "Voxel spacing not added to voxel_spacings"

    # Check that voxel spacing exists in filesystem
    vs_path_overlay = str(overlay_loc / "ExperimentRuns" / "TS_001" / f"VoxelSpacing{vs_size:.3f}")
    assert overlay_fs.exists(vs_path_overlay), f"VoxelSpacing{vs_size:.3f} not found in overlay"

    # Delete the voxel spacing
    copick_run.delete_voxel_spacings(vs_size)

    # Verify voxel spacing is removed from voxel_spacings list
    assert vs not in copick_run.voxel_spacings, "Voxel spacing still in voxel_spacings list"

    # Verify voxel spacing is removed from filesystem
    assert not overlay_fs.exists(vs_path_overlay), f"VoxelSpacing{vs_size:.3f} still exists in overlay"

    # Trying to delete a non-existent voxel spacing should raise an error
    # with pytest.raises(FileNotFoundError):
    #     vs.delete()


def test_delete_tomogram(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]
    copick_run = copick_root.get_run("TS_001")
    vs = copick_run.get_voxel_spacing(10.000)
    overlay_fs = test_payload["testfs_overlay"]
    overlay_loc = test_payload["testpath_overlay"]

    # Create a new tomogram to delete
    tomo_type = "delete-test"
    tomogram = vs.new_tomogram(tomo_type=tomo_type)
    zarr.create((5, 5, 5), store=tomogram.zarr())
    assert tomogram in vs.tomograms, "Tomogram not added to tomograms"

    # Check that tomogram exists in filesystem
    tomo_path_overlay = str(
        overlay_loc / "ExperimentRuns" / "TS_001" / f"VoxelSpacing{vs.voxel_size:.3f}" / f"{tomo_type}.zarr",
    )
    assert overlay_fs.exists(tomo_path_overlay), f"{tomo_type}.zarr not found in overlay"

    # Delete the tomogram
    tomogram.delete()

    # Verify tomogram is removed from tomograms list
    vs.refresh_tomograms()
    assert tomogram not in vs.tomograms, "Tomogram still in tomograms list"

    # Verify tomogram is removed from filesystem
    assert not overlay_fs.exists(tomo_path_overlay), f"{tomo_type}.zarr still exists in overlay"

    # Trying to delete a non-existent tomogram should raise an error
    # with pytest.raises(FileNotFoundError):
    #     tomogram._delete_data()


def test_delete_features(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]
    copick_run = copick_root.get_run("TS_001")
    vs = copick_run.get_voxel_spacing(10.000)
    tomogram = vs.get_tomogram(tomo_type="wbp")
    overlay_fs = test_payload["testfs_overlay"]
    overlay_loc = test_payload["testpath_overlay"]

    # Create a new feature to delete
    feature_type = "delete-test"
    feature = tomogram.new_features(feature_type=feature_type)
    zarr.create((5, 5, 5), store=feature.zarr())
    assert feature in tomogram.features, "Feature not added to features"

    # Check that feature exists in filesystem
    feature_path_overlay = str(
        overlay_loc
        / "ExperimentRuns"
        / "TS_001"
        / f"VoxelSpacing{vs.voxel_size:.3f}"
        / f"{tomogram.tomo_type}_{feature_type}_features.zarr",
    )
    assert overlay_fs.exists(
        feature_path_overlay,
    ), f"{tomogram.tomo_type}_{feature_type}_features.zarr not found in overlay"

    # Delete the feature
    feature.delete()

    # Verify feature is removed from features list
    tomogram.refresh_features()
    assert feature not in tomogram.features, "Feature still in features list"

    # Verify feature is removed from filesystem
    assert not overlay_fs.exists(
        feature_path_overlay,
    ), f"{tomogram.tomo_type}_{feature_type}_features.zarr still exists in overlay"

    # Trying to delete a non-existent feature should raise an error
    # with pytest.raises(FileNotFoundError):
    #     feature._delete_data()


def test_delete_picks(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]
    copick_run = copick_root.get_run("TS_001")
    overlay_fs = test_payload["testfs_overlay"]
    overlay_loc = test_payload["testpath_overlay"]

    # Create a new pick to delete
    user_id = "delete-test"
    session_id = "12345"
    object_name = "proteasome"
    picks = copick_run.new_picks(object_name=object_name, session_id=session_id, user_id=user_id)
    picks.store()
    assert picks in copick_run.picks, "Pick not added to picks"

    # Check that pick exists in filesystem
    pick_path_overlay = str(
        overlay_loc / "ExperimentRuns" / "TS_001" / "Picks" / f"{user_id}_{session_id}_{object_name}.json",
    )
    assert overlay_fs.exists(pick_path_overlay), f"{user_id}_{session_id}_{object_name}.json not found in overlay"

    # Delete the pick
    picks.delete()

    # Verify pick is removed from picks list
    copick_run.refresh_picks()
    assert picks not in copick_run.picks, "Pick still in picks list"

    # Verify pick is removed from filesystem
    assert not overlay_fs.exists(
        pick_path_overlay,
    ), f"{user_id}_{session_id}_{object_name}.json still exists in overlay"

    # Trying to delete a non-existent pick should raise an error
    # with pytest.raises(FileNotFoundError):
    #     picks._delete_data()


def test_delete_mesh(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]
    copick_run = copick_root.get_run("TS_001")
    overlay_fs = test_payload["testfs_overlay"]
    overlay_loc = test_payload["testpath_overlay"]

    # Create a new mesh to delete
    user_id = "delete-test"
    session_id = "12345"
    object_name = "proteasome"
    mesh = copick_run.new_mesh(object_name=object_name, session_id=session_id, user_id=user_id)
    # We don't actually need to store a real mesh for this test
    assert mesh in copick_run.meshes, "Mesh not added to meshes"

    # Check that mesh exists in filesystem (directory is created)
    mesh_dir_overlay = str(overlay_loc / "ExperimentRuns" / "TS_001" / "Meshes")
    assert overlay_fs.exists(mesh_dir_overlay), "Meshes directory not found in overlay"

    # Delete the mesh
    # This will fail since we didn't actually create a file, but that's expected
    # with pytest.raises(FileNotFoundError):
    #     mesh.delete()


def test_delete_segmentation(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]
    copick_run = copick_root.get_run("TS_001")
    overlay_fs = test_payload["testfs_overlay"]
    overlay_loc = test_payload["testpath_overlay"]

    # Create a new segmentation to delete
    user_id = "delete-test"
    session_id = "12345"
    name = "delete-seg"
    is_multilabel = True
    voxel_size = 10.000
    segmentation = copick_run.new_segmentation(
        voxel_size=voxel_size,
        user_id=user_id,
        session_id=session_id,
        name=name,
        is_multilabel=is_multilabel,
    )
    zarr.create((5, 5, 5), store=segmentation.zarr())
    assert segmentation in copick_run.segmentations, "Segmentation not added to segmentations"

    # Check that segmentation exists in filesystem
    seg_file = f"{voxel_size:.3f}_{user_id}_{session_id}_{name}-multilabel.zarr"
    seg_path_overlay = str(overlay_loc / "ExperimentRuns" / "TS_001" / "Segmentations" / seg_file)
    assert overlay_fs.exists(seg_path_overlay), f"{seg_file} not found in overlay"

    # Delete the segmentation
    segmentation.delete()

    # Verify segmentation is removed from segmentations list
    copick_run.refresh_segmentations()
    assert segmentation not in copick_run.segmentations, "Segmentation still in segmentations list"

    # Verify segmentation is removed from filesystem
    assert not overlay_fs.exists(seg_path_overlay), f"{seg_file} still exists in overlay"

    # Trying to delete a non-existent segmentation should raise an error
    # with pytest.raises(FileNotFoundError):
    #     segmentation._delete_data()


def test_exist_ok_run(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]

    # Create a new run
    run_name = "TS_EXIST_OK"
    run1 = copick_root.new_run(run_name)

    # Attempt to create the same run without exist_ok
    with pytest.raises(ValueError):
        copick_root.new_run(run_name)

    # Create the same run with exist_ok=True
    run2 = copick_root.new_run(run_name, exist_ok=True)

    # Verify it's the same run object
    assert run1 == run2, "Run objects should be the same when using exist_ok=True"


def test_exist_ok_voxel_spacing(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]
    copick_run = copick_root.get_run("TS_001")

    # Create a new voxel spacing
    vs_size = 25.000
    vs1 = copick_run.new_voxel_spacing(vs_size)

    # Attempt to create the same voxel spacing without exist_ok
    with pytest.raises(ValueError):
        copick_run.new_voxel_spacing(vs_size)

    # Create the same voxel spacing with exist_ok=True
    vs2 = copick_run.new_voxel_spacing(vs_size, exist_ok=True)

    # Verify it's the same voxel spacing object
    assert vs1 == vs2, "Voxel spacing objects should be the same when using exist_ok=True"


def test_exist_ok_tomogram(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]
    copick_run = copick_root.get_run("TS_001")
    vs = copick_run.get_voxel_spacing(10.000)

    # Create a new tomogram
    tomo_type = "exist-ok-test"
    tomo1 = vs.new_tomogram(tomo_type=tomo_type)
    zarr.create((5, 5, 5), store=tomo1.zarr())

    # Attempt to create the same tomogram without exist_ok
    with pytest.raises(ValueError):
        vs.new_tomogram(tomo_type=tomo_type)

    # Create the same tomogram with exist_ok=True
    tomo2 = vs.new_tomogram(tomo_type=tomo_type, exist_ok=True)

    # Verify it's the same tomogram object
    assert tomo1 == tomo2, "Tomogram objects should be the same when using exist_ok=True"


def test_exist_ok_features(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]
    copick_run = copick_root.get_run("TS_001")
    vs = copick_run.get_voxel_spacing(10.000)
    tomogram = vs.get_tomogram(tomo_type="wbp")

    # Create a new feature
    feature_type = "exist-ok-test"
    feature1 = tomogram.new_features(feature_type=feature_type)
    zarr.create((5, 5, 5), store=feature1.zarr())

    # Attempt to create the same feature without exist_ok
    with pytest.raises(ValueError):
        tomogram.new_features(feature_type=feature_type)

    # Create the same feature with exist_ok=True
    feature2 = tomogram.new_features(feature_type=feature_type, exist_ok=True)

    # Verify it's the same feature object
    assert feature1 == feature2, "Feature objects should be the same when using exist_ok=True"


def test_exist_ok_picks(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]
    copick_run = copick_root.get_run("TS_001")

    # Create a new pick
    user_id = "exist-ok-test"
    session_id = "12345"
    object_name = "proteasome"
    pick1 = copick_run.new_picks(object_name=object_name, session_id=session_id, user_id=user_id)
    pick1.store()

    # Attempt to create the same pick without exist_ok
    with pytest.raises(ValueError):
        copick_run.new_picks(object_name=object_name, session_id=session_id, user_id=user_id)

    # Create the same pick with exist_ok=True
    pick2 = copick_run.new_picks(object_name=object_name, session_id=session_id, user_id=user_id, exist_ok=True)

    # Verify it references the same pick
    assert pick1.path == pick2.path, "Pick objects should reference the same file when using exist_ok=True"


def test_exist_ok_mesh(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]
    copick_run = copick_root.get_run("TS_001")

    # Create a new mesh
    user_id = "exist-ok-test"
    session_id = "12345"
    object_name = "proteasome"
    mesh1 = copick_run.new_mesh(object_name=object_name, session_id=session_id, user_id=user_id)

    # Attempt to create the same mesh without exist_ok
    with pytest.raises(ValueError):
        copick_run.new_mesh(object_name=object_name, session_id=session_id, user_id=user_id)

    # Create the same mesh with exist_ok=True
    mesh2 = copick_run.new_mesh(object_name=object_name, session_id=session_id, user_id=user_id, exist_ok=True)

    # Verify it references the same mesh
    assert mesh1.path == mesh2.path, "Mesh objects should reference the same file when using exist_ok=True"


def test_exist_ok_segmentation(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]
    copick_run = copick_root.get_run("TS_001")

    # Create a new segmentation
    user_id = "exist-ok-test"
    session_id = "12345"
    name = "exist-ok-seg"
    is_multilabel = True
    voxel_size = 10.000
    seg1 = copick_run.new_segmentation(
        voxel_size=voxel_size,
        user_id=user_id,
        session_id=session_id,
        name=name,
        is_multilabel=is_multilabel,
    )
    zarr.create((5, 5, 5), store=seg1.zarr())

    # Attempt to create the same segmentation without exist_ok
    with pytest.raises(ValueError):
        copick_run.new_segmentation(
            voxel_size=voxel_size,
            user_id=user_id,
            session_id=session_id,
            name=name,
            is_multilabel=is_multilabel,
        )

    # Create the same segmentation with exist_ok=True
    seg2 = copick_run.new_segmentation(
        voxel_size=voxel_size,
        user_id=user_id,
        session_id=session_id,
        name=name,
        is_multilabel=is_multilabel,
        exist_ok=True,
    )

    # Verify it references the same segmentation
    assert seg1.path == seg2.path, "Segmentation objects should reference the same file when using exist_ok=True"


def test_delete_collections(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]
    copick_run = copick_root.get_run("TS_001")
    overlay_fs = test_payload["testfs_overlay"]
    overlay_loc = test_payload["testpath_overlay"]

    # Create multiple entities to test batch deletion
    user_id = "delete-batch"

    # Create multiple picks (proteasome and ribosome)
    picks1 = copick_run.new_picks(object_name="proteasome", session_id="batch1", user_id=user_id)
    picks1.store()
    picks2 = copick_run.new_picks(object_name="ribosome", session_id="batch1", user_id=user_id)
    picks2.store()
    picks3 = copick_run.new_picks(object_name="proteasome", session_id="batch2", user_id=user_id)
    picks3.store()

    # Create multiple meshes
    copick_run.new_mesh(object_name="proteasome", session_id="batch1", user_id=user_id)
    copick_run.new_mesh(object_name="membrane", session_id="batch1", user_id=user_id)

    # Create multiple segmentations
    seg1 = copick_run.new_segmentation(
        voxel_size=10.000,
        user_id=user_id,
        session_id="batch1",
        name="ribosome",
        is_multilabel=False,
    )
    zarr.create((5, 5, 5), store=seg1.zarr())

    seg2 = copick_run.new_segmentation(
        voxel_size=10.000,
        user_id=user_id,
        session_id="batch2",
        name="segment2",
        is_multilabel=True,
    )
    zarr.create((5, 5, 5), store=seg2.zarr())

    # Refresh to ensure all entities are tracked
    copick_run.refresh()

    # Test deleting picks by user_id
    copick_run.delete_picks(user_id=user_id, session_id="batch1")
    copick_run.refresh_picks()

    # Verify picks1 and picks2 are deleted, but picks3 remains
    pick_path1 = str(overlay_loc / "ExperimentRuns" / "TS_001" / "Picks" / f"{user_id}_batch1_proteasome.json")
    pick_path2 = str(overlay_loc / "ExperimentRuns" / "TS_001" / "Picks" / f"{user_id}_batch1_ribosome.json")
    pick_path3 = str(overlay_loc / "ExperimentRuns" / "TS_001" / "Picks" / f"{user_id}_batch2_proteasome.json")

    assert not overlay_fs.exists(pick_path1), "Pick1 still exists"
    assert not overlay_fs.exists(pick_path2), "Pick2 still exists"
    assert overlay_fs.exists(pick_path3), "Pick3 should still exist"

    # Test deleting all meshes by user_id
    copick_run.delete_meshes(user_id=user_id)
    copick_run.refresh_meshes()

    # Test deleting segmentations by multiple criteria
    copick_run.delete_segmentations(user_id=user_id, is_multilabel=True)
    copick_run.refresh_segmentations()

    # Verify seg2 is deleted but seg1 remains
    seg_path1 = str(
        overlay_loc / "ExperimentRuns" / "TS_001" / "Segmentations" / f"10.000_{user_id}_batch1_ribosome.zarr",
    )
    seg_path2 = str(
        overlay_loc
        / "ExperimentRuns"
        / "TS_001"
        / "Segmentations"
        / f"10.000_{user_id}_batch2_segment2-multilabel.zarr",
    )

    assert overlay_fs.exists(seg_path1), "Seg1 should still exist"
    assert not overlay_fs.exists(seg_path2), "Seg2 still exists"
