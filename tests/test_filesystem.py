from typing import Any, Dict

import numpy as np
import pytest
import zarr
from copick.impl.filesystem import CopickRootFSSpec
from copick.models import CopickPicksFile
from copick.util.ome import write_ome_zarr_3d
from scipy.spatial.transform import Rotation
from trimesh.parent import Geometry

NUMERICAL_PRECISION = 1e-8


@pytest.fixture(params=pytest.common_cases)
def test_payload(request) -> Dict[str, Any]:
    payload = request.getfixturevalue(request.param)
    payload["root"] = CopickRootFSSpec.from_file(payload["cfg_file"])
    return payload


def test_root_lazy(test_payload: Dict[str, Any]):
    copick_root = test_payload["root"]

    # Check that the root is not populated
    assert copick_root._runs is None, "Runs should not be populated"
    assert copick_root._objects is None, "Objects should not be populated"

    # Access the runs and confirm query
    runs = copick_root.runs
    rnames = [r.name for r in runs]

    assert copick_root._runs is not None, "Runs should be populated"
    assert len(runs) == 3, "Incorrect number of runs"
    assert set(rnames) == {"TS_001", "TS_002", "TS_003"}, "Incorrect runs"

    # Access the objects and confirm query
    objects = copick_root.pickable_objects
    onames = [o.name for o in objects]

    assert copick_root._objects is not None, "Objects should be populated"
    assert len(objects) == 3, "Incorrect number of objects"
    assert set(onames) == {"proteasome", "ribosome", "membrane"}, "Incorrect objects"


def test_root_metadata(test_payload: Dict[str, Any]):
    copick_root = test_payload["root"]

    assert copick_root.config.name == "test", "Incorrect name"
    assert copick_root.config.description == "A test project.", "Incorrect description"

    assert copick_root.user_id is None, "Incorrect user_id"
    assert copick_root.session_id is None, "Incorrect description"

    copick_root.user_id = "test.user"
    copick_root.session_id = "0"

    assert copick_root.user_id == "test.user", "Incorrect user_id after setting"
    assert copick_root.session_id == "0", "Incorrect session_id after setting"


def test_root_get_object(test_payload: Dict[str, Any]):
    copick_root = test_payload["root"]

    objs = ["proteasome", "ribosome", "membrane"]

    for obj in objs:
        assert copick_root.get_object(obj) is not None, f"Object {obj} not found"
        assert copick_root.get_object(obj).name == obj, f"Object {obj} not found"

    assert copick_root.get_object("nucleus") is None, "Object nucleus should not be found"


def test_root_get_run(test_payload: Dict[str, Any]):
    copick_root = test_payload["root"]

    runs = ["TS_001", "TS_002", "TS_003"]

    for run in runs:
        assert copick_root.get_run(run) is not None, f"Run {run} not found"
        assert copick_root.get_run(run).name == run, f"Run {run} not found"
        assert copick_root._runs is None, f"Random access for run {run} should not populate runs index"

    assert copick_root.get_run("TS_004") is None, "Run TS_004 should not be found"


def test_root_refresh(test_payload: Dict[str, Any]):
    copick_root = test_payload["root"]

    # Check that the root is not populated
    assert copick_root._runs is None, "Runs should not be populated"

    copick_root.refresh()

    assert copick_root._runs is not None, "Runs should be populated"
    rnames = [r.name for r in copick_root.runs]
    assert len(copick_root.runs) == 3, "Incorrect number of runs"
    assert set(rnames) == {"TS_001", "TS_002", "TS_003"}, "Incorrect runs"


def test_root_new_run(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]
    overlay_fs = test_payload["testfs_overlay"]
    overlay_loc = test_payload["testpath_overlay"]

    only_overlay = True
    static_fs = None
    static_loc = None
    if test_payload["testfs_static"] is not None:
        static_fs = test_payload["testfs_static"]
        static_loc = test_payload["testpath_static"]
        only_overlay = False

    # Check that the root is not populated
    assert copick_root._runs is None, "Runs should not be populated"

    # Adding a run with the same name as an existing one raises an error
    with pytest.raises(ValueError):
        copick_root.new_run("TS_001")

    # Adding the first run inits the _runs attribute as list of runs
    run4 = copick_root.new_run("TS_004")
    assert copick_root._runs is not None, "Runs should be populated"
    assert run4 in copick_root.runs, "Run not added to runs"

    # Adding another run appends to the list
    run5 = copick_root.new_run("TS_005")
    assert run5 in copick_root.runs, "Run not added to runs"

    # Total number of runs should be 5 now
    copick_root.refresh()
    assert len(copick_root.runs) == 5, "Incorrect number of runs"

    # Check filesystem for existing runs
    if only_overlay:
        run_path = str(overlay_loc / "ExperimentRuns") + "/"
        for run in ["TS_001", "TS_002", "TS_003", "TS_004", "TS_005"]:
            assert overlay_fs.exists(run_path + run), f"{run} not found in overlay"
    else:
        run_path_overlay = str(overlay_loc / "ExperimentRuns") + "/"
        run_path_static = str(static_loc / "ExperimentRuns") + "/"

        for run in ["TS_001", "TS_002", "TS_003"]:
            assert static_fs.exists(run_path_static + run), f"{run} not found in static"

        for run in ["TS_004", "TS_005"]:
            assert overlay_fs.exists(run_path_overlay + run), f"{run} not found in overlay"


def test_object_meta(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]

    # Check metadata for proteasome object
    copick_object = copick_root.get_object("proteasome")
    assert copick_object.name == "proteasome", "Incorrect name"
    assert copick_object.is_particle is True, "Incorrect is_particle"
    assert copick_object.label == 1, "Incorrect label"
    assert copick_object.color == (255, 0, 0, 255), "Incorrect color"
    assert copick_object.radius == 60, "Incorrect radius"
    assert copick_object.map_threshold == pytest.approx(0.0418, abs=NUMERICAL_PRECISION), "Incorrect threshold"


def test_object_zarr(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]

    # Check metadata for proteasome object
    copick_object = copick_root.get_object("proteasome")

    # Check zarr is readable
    arrays = list(zarr.open(copick_object.zarr(), "r").arrays())
    _, array = arrays[0]
    assert array.shape == (42, 36, 36), "Error reading Zarr, (incorrect shape)"
    assert np.sum(array) == pytest.approx(
        1029.2904052734375,
        abs=1e-3,
    ), "Error reading Zarr (incorrect sum)."

    # Assert no zarr for non-particle object
    copick_object = copick_root.get_object("membrane")
    assert copick_object.zarr() is None, "Zarr should not exist for non-particle object"


def test_object_read_numpy(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]

    # Check metadata for proteasome object
    copick_object = copick_root.get_object("proteasome")

    # Check numpy is readable
    array = copick_object.numpy()

    # Full size
    assert array.shape == (42, 36, 36), "Error getting numpy array, (incorrect shape)"
    assert np.sum(array) == pytest.approx(
        1029.2904052734375,
        abs=1e-3,
    ), "Error getting numpy array (incorrect sum)."

    # Subregion
    array = copick_object.numpy(x=slice(10, 20), y=slice(10, 20), z=slice(10, 20))
    assert array.shape == (10, 10, 10), "Error getting numpy array, (incorrect shape)"
    assert np.sum(array) == pytest.approx(
        168.116912842,
        abs=NUMERICAL_PRECISION,
    ), "Error getting numpy array (incorrect sum)."


def test_run_meta(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]

    # Check metadata for TS_001 run
    copick_run = copick_root.get_run("TS_001")

    # Name
    assert copick_run.name == "TS_001", "Incorrect name"
    copick_run.name = "TS_001_new"
    assert copick_run.name == "TS_001_new", "Incorrect name after setting"


def test_run_lazy(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]

    # Check that the run is not populated
    copick_run = copick_root.get_run("TS_001")
    assert copick_run._voxel_spacings is None, "Voxel spacings should not be populated"
    assert copick_run._picks is None, "Picks should not be populated"
    assert copick_run._meshes is None, "Meshes should not be populated"
    assert copick_run._segmentations is None, "Segmentations should not be populated"

    # Access the voxel spacings and confirm query
    voxel_spacings = copick_run.voxel_spacings
    vs = [v.voxel_size for v in voxel_spacings]
    assert copick_run._voxel_spacings is not None, "Voxel spacings should be populated"
    assert len(vs) == 2, "Incorrect number of voxel spacings"
    assert set(vs) == {10.000, 20.000}, "Incorrect voxel spacings"

    # Access the picks and confirm query
    picks = copick_run.picks

    assert copick_run._picks is not None, "Picks should be populated"
    assert len(picks) == 5, "Incorrect number of picks"

    # Access the meshes and confirm query
    meshes = copick_run.meshes

    assert copick_run._meshes is not None, "Meshes should be populated"
    assert len(meshes) == 3, "Incorrect number of meshes"

    # Access the segmentations and confirm query
    segmentations = copick_run.segmentations

    assert copick_run._segmentations is not None, "Segmentations should be populated"
    assert len(segmentations) == 3, "Incorrect segmentations"


def test_run_get_voxel_spacing(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]

    # Get run
    copick_run = copick_root.get_run("TS_001")

    # Non-existing voxel spacing
    assert copick_run.get_voxel_spacing(30.000) is None, "Voxel spacing should not exist"

    # Get voxel spacing
    vs = copick_run.get_voxel_spacing(10.000)
    assert vs is not None, "Voxel spacing not found"
    assert vs.voxel_size == 10.000, "Incorrect voxel size"
    assert (
        copick_run._voxel_spacings is None
    ), "Random access for voxel spacing should not populate voxel spacings index"

    vs = copick_run.get_voxel_spacing(20.000)
    assert vs is not None, "Voxel spacing not found"
    assert vs.voxel_size == 20.000, "Incorrect voxel size"


def test_run_entity_types(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]

    # Get run
    copick_run = copick_root.get_run("TS_001")

    # Check pick types
    tool_picks = copick_run.tool_picks()
    assert len(tool_picks) == 2, "Incorrect number of tool picks"

    user_picks = copick_run.user_picks()
    assert len(user_picks) == 3, "Incorrect number of user picks"

    # Check mesh types
    tool_meshes = copick_run.tool_meshes()
    assert len(tool_meshes) == 2, "Incorrect number of tool meshes"

    user_meshes = copick_run.user_meshes()
    assert len(user_meshes) == 1, "Incorrect number of user meshes"

    # Check segmentation types
    tool_segmentations = copick_run.tool_segmentations()
    assert len(tool_segmentations) == 2, "Incorrect number of tool segmentations"

    user_segmentations = copick_run.user_segmentations()
    assert len(user_segmentations) == 1, "Incorrect number of user segmentations"

    # Check with user_id set
    copick_root.config.user_id = "test.user"
    user_picks = copick_run.user_picks()
    assert len(user_picks) == 2, "Incorrect number of user picks"

    user_meshes = copick_run.user_meshes()
    assert len(user_meshes) == 0, "Incorrect number of user meshes"

    user_segmentations = copick_run.user_segmentations()
    assert len(user_segmentations) == 1, "Incorrect number of user segmentations"


def test_run_get_picks(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]

    # Get run
    copick_run = copick_root.get_run("TS_001")

    # Get picks
    picks = copick_run.get_picks()
    assert len(picks) == 5, "Incorrect number of picks"

    # Get picks by object
    picks = copick_run.get_picks(object_name="proteasome")
    assert len(picks) == 3, "Incorrect number of picks"

    # Get picks by object and user_id
    picks = copick_run.get_picks(object_name="proteasome", user_id="ArtiaX")
    assert len(picks) == 1, "Incorrect number of picks"
    assert picks[0].pickable_object_name == "proteasome", "Incorrect object"

    # Get picks by object, user_id and session_id
    picks = copick_run.get_picks(object_name="ribosome", user_id="gapstop", session_id="0")
    assert len(picks) == 1, "Incorrect number of picks"
    assert picks[0].pickable_object_name == "ribosome", "Incorrect object"
    assert picks[0].user_id == "gapstop", "Incorrect user_id"
    assert picks[0].session_id == "0", "Incorrect session_id"


@pytest.fixture
def ts_001_ribosome_gapstop_points():
    return np.array(
        [
            [13.109512186388912, 74.71185201921038, 202.47507943202584],
            [631.4709314294199, 216.35459177569777, 153.51979459358296],
            [13.269106483949642, 493.1507625056122, 191.96928603555477],
            [295.3857864878723, 48.00127558957804, 12.379751870875282],
            [204.07695344548807, 363.70538811345045, 421.5631049171766],
            [341.5641484136662, 583.1178654724652, 265.92234830389776],
            [595.6901903739324, 152.54150479358174, 269.050095901217],
            [414.749742830462, 33.87702343343186, 149.04501288274474],
            [230.77112217392795, 158.07881774104047, 33.889195589406285],
            [205.03836780107628, 191.17304087417068, 17.748902885347206],
        ],
    )


@pytest.fixture
def ts_001_ribosome_gapstop_transformations():
    return np.array(
        [
            [
                [0.91082157, 0.41183225, 0.02825357, 2.04080334],
                [0.39883888, -0.86030307, -0.31749989, -1.22192711],
                [-0.10645006, 0.30045437, -0.9478373, -4.95620327],
                [0.0, 0.0, 0.0, 1.0],
            ],
            [
                [0.25494658, -0.930823, 0.26186024, -4.15673036],
                [0.07354863, 0.28869173, 0.95459294, 1.73078736],
                [-0.96415395, -0.22411074, 0.14206172, -0.88387753],
                [0.0, 0.0, 0.0, 1.0],
            ],
            [
                [0.97406863, -0.12313085, -0.18981335, -1.54048992],
                [0.10487541, 0.98909245, -0.10342766, -4.39372889],
                [0.20047809, 0.08083889, 0.97635732, -1.8710075],
                [0.0, 0.0, 0.0, 1.0],
            ],
            [
                [0.63125354, 0.05558002, -0.77358247, -0.27267958],
                [0.26806113, 0.92032357, 0.28486444, 1.45023474],
                [0.72777895, -0.38718908, 0.56605867, -1.47745371],
                [0.0, 0.0, 0.0, 1.0],
            ],
            [
                [-0.16909497, -0.31483618, -0.93396203, 3.25622553],
                [0.98550232, -0.04068504, -0.16471158, 3.51267799],
                [0.01385888, -0.94827365, 0.31715142, -0.50734273],
                [0.0, 0.0, 0.0, 1.0],
            ],
            [
                [-0.46587729, 0.80999162, 0.35619085, 2.20399113],
                [0.87365849, 0.48488946, 0.04003821, -4.95970857],
                [-0.14028257, 0.32984205, -0.93355504, 2.89001954],
                [0.0, 0.0, 0.0, 1.0],
            ],
            [
                [-0.12243006, 0.91735533, 0.37877445, 2.32553322],
                [-0.77156017, -0.32802754, 0.54506223, 3.06393629],
                [0.62426419, -0.22551528, 0.74795526, -2.55255873],
                [0.0, 0.0, 0.0, 1.0],
            ],
            [
                [0.704833, -0.70612128, -0.06784677, -1.28122836],
                [0.70160862, 0.70803464, -0.08020155, -1.33420528],
                [0.10466989, 0.00892682, 0.99446696, -2.85401946],
                [0.0, 0.0, 0.0, 1.0],
            ],
            [
                [0.19161049, 0.75988339, -0.62117843, -4.11172068],
                [-0.57053738, -0.42874731, -0.7004733, -2.50187213],
                [-0.79860661, 0.48862355, 0.3513894, 3.90473263],
                [0.0, 0.0, 0.0, 1.0],
            ],
            [
                [0.40646443, 0.88858526, 0.21260974, 2.53815537],
                [-0.66079699, 0.44660241, -0.60323597, 4.90033419],
                [-0.63097861, 0.10470209, 0.76870246, -4.43535779],
                [0.0, 0.0, 0.0, 1.0],
            ],
        ],
    )


@pytest.fixture
def ts_001_ribosome_gapstop_csv_data():
    return """\
,rlnCoordinateX,rlnCoordinateY,rlnCoordinateZ,rlnAngleRot,rlnAngleTilt,rlnAnglePsi,rlnCenteredCoordinateXAngst,rlnCenteredCoordinateYAngst,rlnCenteredCoordinateZAngst
0,1.515031552638891,7.348992490921039,19.751887616202584,109.50907985667635,161.4123797256452,-95.08522231005571,-304.8496844736111,-246.5100750907896,-122.48112383797417
1,62.731420106942,21.808537913569776,15.263591706358294,-166.9143709708248,81.83283311460454,105.33981666736783,307.31420106941994,-101.91462086430224,-167.36408293641705
2,1.172861656394964,48.87570336156122,19.00982785355548,21.960797348335795,12.483759659271382,-28.58558629047773,-308.27138343605037,168.75703361561222,-129.90172146444522
3,29.51131069078723,4.945151032957805,1.0902298160875281,-28.013632548828017,55.52416048823932,20.215753506264058,-24.886893092127707,-270.548489670422,-309.09770183912474
4,20.733317897548808,36.72180661034504,42.10557621871766,-89.16269015143828,71.50925798264286,-10.001718002075961,-112.66682102451193,47.21806610345044,101.05576218717658
5,34.376813954366625,57.81581569024652,26.881236784389777,113.04015943122353,158.99594224139992,173.58649629583556,23.768139543666223,258.1581569024652,-51.18763215610221
6,59.80157235939324,15.560544108358172,26.6497537171217,-19.86224078837036,41.586434365506726,124.79619591385287,278.0157235939324,-164.39455891641828,-53.502462828782996
7,41.346851447046205,3.254281815343186,14.619099342274476,4.874701253810245,6.030039292898939,-49.7703366694967,93.46851447046203,-287.4571818465681,-173.80900657725525
8,22.665940149392796,15.557694561104046,3.779392821940628,148.5398245381037,69.42767947620969,-48.43344726285531,-93.34059850607204,-164.42305438895954,-282.20607178059373
9,20.757652317107627,19.607337506417068,1.3313545095347206,170.5784132938702,39.762486837924975,-109.41494035897404,-112.42347682892373,-123.92662493582932,-306.6864549046528
"""


def test_picks_read_numpy(
    test_payload: Dict[str, Any],
    ts_001_ribosome_gapstop_points,
    ts_001_ribosome_gapstop_transformations,
):
    # Setup
    copick_root = test_payload["root"]

    # Get run
    copick_run = copick_root.get_run("TS_001")

    # Get picks by object, user_id and session_id
    picks = copick_run.get_picks(object_name="ribosome", user_id="gapstop", session_id="0")

    pos, ori = picks[0].numpy()
    assert np.allclose(
        pos,
        ts_001_ribosome_gapstop_points,
        atol=NUMERICAL_PRECISION,
    ), "Error getting numpy array (incorrect positions)."
    assert np.allclose(
        ori,
        ts_001_ribosome_gapstop_transformations,
        atol=NUMERICAL_PRECISION,
    ), "Error getting numpy array (incorrect orientations)."


def test_picks_read_relion_df(
    test_payload: Dict[str, Any],
    ts_001_ribosome_gapstop_points,
    ts_001_ribosome_gapstop_transformations,
):
    SMALLEST_VOXEL_SIZE = 10.0
    copick_root = test_payload["root"]
    copick_run = copick_root.get_run("TS_001")
    picks = copick_run.get_picks(object_name="ribosome", user_id="gapstop", session_id="0")

    ts_001_ribosome_gapstop_orientations = ts_001_ribosome_gapstop_transformations[:, :3, :3]
    ts_001_ribosome_gapstop_translations = ts_001_ribosome_gapstop_transformations[:, :3, 3]
    ts_001_ribosome_gapstop_translated_points = ts_001_ribosome_gapstop_points + ts_001_ribosome_gapstop_translations

    df = picks[0].df()
    df_points_px = df[["rlnCoordinateX", "rlnCoordinateY", "rlnCoordinateZ"]].to_numpy() * SMALLEST_VOXEL_SIZE
    assert np.allclose(
        df_points_px,
        ts_001_ribosome_gapstop_translated_points,
        atol=NUMERICAL_PRECISION,
    ), "Error getting pixel coordinates from DataFrame."

    df_eulers = df[["rlnAngleRot", "rlnAngleTilt", "rlnAnglePsi"]].to_numpy()
    df_orientations = Rotation.from_euler("ZYZ", df_eulers, degrees=True).inv().as_matrix()

    assert np.allclose(
        df_orientations,
        ts_001_ribosome_gapstop_orientations,
        atol=NUMERICAL_PRECISION,
    ), "Error getting orientations from DataFrame."


def test_picks_write_numpy(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]

    # Get run
    copick_run = copick_root.get_run("TS_001")

    # Get picks by object, user_id and session_id
    picks = copick_run.new_picks(object_name="ribosome", user_id="gapstop", session_id="1")

    POINTS = np.array(
        [
            [1, 2, 3],
            [4, 5, 6],
        ],
    )

    POINTS_err = np.array(
        [
            [1, 2, 3],
            [4, 5, 6],
            [7, 8, 9],
        ],
    )

    ORIENTATIONS = np.array(
        [
            [
                [0.055084832105785964, 0.8464969771473587, 0.9890811615793559, 0.0],
                [0.05411530447521384, 0.9796933083190055, 0.7672162846141741, 0.0],
                [0.47825664023283687, 0.9155030040986599, 0.35583007986260196, 0.0],
                [0.0, 0.0, 0.0, 1.0],
            ],
            [
                [0.07837980771565989, 0.9521754802942424, 0.7061476278277338, 0.0],
                [0.8144408709150506, 0.19072161285288602, 0.1759034817259575, 0.0],
                [0.29103797580332835, 0.7906135259730082, 0.17079014782816504, 0.0],
                [0.0, 0.0, 0.0, 1.0],
            ],
        ],
    )

    # Write picks
    picks.from_numpy(POINTS, ORIENTATIONS)
    del picks

    # Compare with file contents
    picks = copick_run.get_picks(object_name="ribosome", user_id="gapstop", session_id="1")[0]

    assert len(picks.points) == 2, "Incorrect number of points."

    for i, p in enumerate(picks.points):
        assert p.transformation == pytest.approx(
            ORIENTATIONS[i, :, :],
            abs=NUMERICAL_PRECISION,
        ), f"Incorrect position for point {i}."

        assert [p.location.x, p.location.y, p.location.z] == pytest.approx(
            POINTS[i, :],
            abs=NUMERICAL_PRECISION,
        ), f"Incorrect orientation for point {i}."

    with pytest.raises(ValueError):
        picks.from_numpy(POINTS_err, ORIENTATIONS)


def test_picks_write_relion_df(
    test_payload: Dict[str, Any],
    ts_001_ribosome_gapstop_points,
    ts_001_ribosome_gapstop_transformations,
    ts_001_ribosome_gapstop_csv_data,
):
    from io import StringIO

    import pandas as pd

    copick_root = test_payload["root"]
    copick_run = copick_root.get_run("TS_001")

    df = pd.read_csv(StringIO(ts_001_ribosome_gapstop_csv_data))

    new_picks_relion_4 = copick_run.new_picks(object_name="ribosome", user_id="relion4", session_id="0")
    new_picks_relion_4.from_df(df)

    # Remove RELION 4 columns, so must rely on RELION 5 columns
    df.drop(columns=["rlnCoordinateX", "rlnCoordinateY", "rlnCoordinateZ"], inplace=True)

    new_picks_relion_5 = copick_run.new_picks(object_name="ribosome", user_id="relion5", session_id="0")
    new_picks_relion_5.from_df(df)

    new_picks_relion_4_points, new_picks_relion_4_transformations = new_picks_relion_4.numpy()
    new_picks_relion_5_points, new_picks_relion_5_transformations = new_picks_relion_5.numpy()

    # Add translational offset stored in transformation to original points
    ts_001_ribosome_gapstop_translations = ts_001_ribosome_gapstop_transformations[:, :3, 3]
    ts_001_ribosome_gapstop_translated_points = ts_001_ribosome_gapstop_points + ts_001_ribosome_gapstop_translations

    assert np.allclose(
        new_picks_relion_4_points,
        ts_001_ribosome_gapstop_translated_points,
        atol=NUMERICAL_PRECISION,
    ), "RELION 4 points do not match expected values."
    assert np.allclose(
        new_picks_relion_5_points,
        ts_001_ribosome_gapstop_translated_points,
        atol=NUMERICAL_PRECISION,
    ), "RELION 5 points do not match expected values."

    ts_001_ribosome_gapstop_orientations = ts_001_ribosome_gapstop_transformations.copy()
    ts_001_ribosome_gapstop_orientations[:, :3, 3] = 0

    # Checking that the orientations should match, the translations should be 0, the bottom row should be [0, 0, 0, 1]
    assert np.allclose(
        new_picks_relion_4_transformations,
        ts_001_ribosome_gapstop_orientations,
        atol=NUMERICAL_PRECISION,
    ), "RELION 4 orientations do not match expected values."
    assert np.allclose(
        new_picks_relion_5_transformations,
        ts_001_ribosome_gapstop_orientations,
        atol=NUMERICAL_PRECISION,
    ), "RELION 5 orientations do not match expected values."

    new_picks_relion_subtomogram_orientations = copick_run.new_picks(
        object_name="ribosome",
        user_id="relion_sub_orientations",
        session_id="0",
    )

    df = pd.read_csv(StringIO(ts_001_ribosome_gapstop_csv_data))
    df.rename(
        columns={
            "rlnAngleRot": "rlnTomoSubtomogramRot",
            "rlnAngleTilt": "rlnTomoSubtomogramTilt",
            "rlnAnglePsi": "rlnTomoSubtomogramPsi",
        },
        inplace=True,
    )
    df["rlnAngleRot"] = 0
    df["rlnAngleTilt"] = 0
    df["rlnAnglePsi"] = 0

    new_picks_relion_subtomogram_orientations.from_df(df)
    (
        new_picks_relion_subtomogram_orientations_points,
        new_picks_relion_subtomogram_orientations_transformations,
    ) = new_picks_relion_subtomogram_orientations.numpy()

    assert np.allclose(
        new_picks_relion_subtomogram_orientations_points,
        ts_001_ribosome_gapstop_translated_points,
        atol=NUMERICAL_PRECISION,
    ), "RELION 3D subtomogram points do not match expected values."
    assert np.allclose(
        new_picks_relion_subtomogram_orientations_transformations,
        ts_001_ribosome_gapstop_orientations,
        atol=NUMERICAL_PRECISION,
    ), "RELION 3D subtomogram orientations do not match expected values."

    new_picks_relion_offsets = copick_run.new_picks(object_name="ribosome", user_id="relion_offsets", session_id="0")
    # Subtract an arbitrary value from the coordinates and add it to the "rlnOriginX/Y/ZAngst" columns
    df = pd.read_csv(StringIO(ts_001_ribosome_gapstop_csv_data))
    X_OFFSET_VALUE = 4.2
    Y_OFFSET_VALUE = -0.5
    Z_OFFSET_VALUE = 1.337

    # use RELION 5 values only, so don't have to update RELION 4 values
    df.drop(columns=["rlnCoordinateX", "rlnCoordinateY", "rlnCoordinateZ"], inplace=True)
    df["rlnOriginXAngst"] = X_OFFSET_VALUE
    df["rlnOriginYAngst"] = Y_OFFSET_VALUE
    df["rlnOriginZAngst"] = Z_OFFSET_VALUE
    # Add since the offset is subtracted from the original value in RELION code (a bit unintuitive)
    df["rlnCenteredCoordinateXAngst"] += X_OFFSET_VALUE
    df["rlnCenteredCoordinateYAngst"] += Y_OFFSET_VALUE
    df["rlnCenteredCoordinateZAngst"] += Z_OFFSET_VALUE

    new_picks_relion_offsets.from_df(df)
    new_picks_relion_offsets_points, new_picks_relion_offsets_transformations = new_picks_relion_offsets.numpy()

    assert np.allclose(
        new_picks_relion_offsets_points,
        ts_001_ribosome_gapstop_translated_points,
        atol=NUMERICAL_PRECISION,
    ), "RELION offsets points do not match expected values."
    assert np.allclose(
        new_picks_relion_offsets_transformations,
        ts_001_ribosome_gapstop_orientations,
        atol=NUMERICAL_PRECISION,
    ), "RELION offsets orientations do not match expected values."


def test_run_get_meshes(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]

    # Get run
    copick_run = copick_root.get_run("TS_001")

    # Get meshes
    meshes = copick_run.get_meshes()
    assert len(meshes) == 3, "Incorrect number of meshes"

    # Get meshes by object
    meshes = copick_run.get_meshes(object_name="proteasome")
    assert len(meshes) == 1, "Incorrect number of meshes"
    assert meshes[0].pickable_object_name == "proteasome", "Incorrect mesh"

    # Get meshes by user_id
    meshes = copick_run.get_meshes(user_id="user.test")
    assert len(meshes) == 1, "Incorrect number of meshes"
    assert meshes[0].user_id == "user.test", "Incorrect mesh"

    # Get meshes by session_id
    meshes = copick_run.get_meshes(session_id="321")
    assert len(meshes) == 1, "Incorrect number of meshes"
    assert meshes[0].session_id == "321", "Incorrect mesh"


def test_run_get_segmentations(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]

    # Get run
    copick_run = copick_root.get_run("TS_001")

    # Get segmentations
    segmentations = copick_run.get_segmentations()
    assert len(segmentations) == 3, "Incorrect number of segmentations"

    # Get segmentations by voxel spacing
    segmentations = copick_run.get_segmentations(voxel_size=10.000)
    snames = [s.name for s in segmentations]
    assert len(segmentations) == 2, "Incorrect number of segmentations"
    assert "prediction" in snames, "Segmentation not found"
    assert "painting" in snames, "Segmentation not found"

    # Get segmentations by object
    segmentations = copick_run.get_segmentations(name="membrane")
    assert len(segmentations) == 1, "Incorrect number of segmentations"
    assert segmentations[0].name == "membrane", "Incorrect segmentation"

    # Get segmentations by user_id
    segmentations = copick_run.get_segmentations(user_id="membrain")
    assert len(segmentations) == 1, "Incorrect number of segmentations"
    assert segmentations[0].user_id == "membrain", "Incorrect segmentation"

    # Get segmentations by multilabel and session_id
    segmentations = copick_run.get_segmentations(is_multilabel=True, session_id="123")
    assert len(segmentations) == 1, "Incorrect number of segmentations"
    assert segmentations[0].is_multilabel is True, "Incorrect segmentation"
    assert segmentations[0].session_id == "123", "Incorrect segmentation"


def test_segmentation_zarr(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]

    # Get run
    copick_run = copick_root.get_run("TS_001")

    # Get segmentations by object
    segmentation = copick_run.get_segmentations(name="membrane")[0]

    # Check zarr is readable
    arrays = list(zarr.open(segmentation.zarr(), "r").arrays())
    _, array = arrays[0]
    assert array.shape == (64, 64, 64), "Error reading Zarr, (incorrect shape)"
    assert np.sum(array) == pytest.approx(
        24576,
        abs=NUMERICAL_PRECISION,
    ), "Error reading Zarr (incorrect sum)."


def test_segmentation_read_numpy(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]

    # Get run
    copick_run = copick_root.get_run("TS_001")

    # Get segmentations by object
    segmentation = copick_run.get_segmentations(name="membrane")[0]

    # Full volume
    array = segmentation.numpy()
    assert array.shape == (64, 64, 64), "Error getting numpy array, (incorrect shape)"
    assert np.sum(array) == pytest.approx(
        24576,
        abs=NUMERICAL_PRECISION,
    ), "Error getting numpy array (incorrect sum)."

    # Subregion
    array = segmentation.numpy(x=slice(20, 40), y=slice(20, 40), z=slice(20, 40))
    assert array.shape == (20, 20, 20), "Error getting numpy array, (incorrect shape)"
    assert np.sum(array) == pytest.approx(
        426,
        abs=NUMERICAL_PRECISION,
    ), "Error getting numpy array (incorrect sum)."


def test_segmentation_write_numpy(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]

    # Get run
    copick_run = copick_root.get_run("TS_001")

    # Get new segmentation
    segmentation = copick_run.new_segmentation(
        name="ribosome",
        user_id="pytom",
        session_id="10",
        is_multilabel=False,
        voxel_size=10.000,
    )

    # Write numpy array
    array = np.random.randint(low=0, high=50, size=(64, 64, 64)).astype(np.uint8)
    segmentation.from_numpy(array)

    # Check zarr contents
    arrays = list(zarr.open(segmentation.zarr(), "r").arrays())
    _, array2 = arrays[0]
    assert np.allclose(array, array2), "Error writing numpy array"

    # Write subregion
    sub_array = np.random.rand(30, 30, 30).astype(np.uint8)
    franken_array = array
    franken_array[10:40, 10:40, 10:40] = sub_array
    segmentation.set_region(sub_array, x=slice(10, 40), y=slice(10, 40), z=slice(10, 40))

    # Check zarr contents
    arrays = list(zarr.open(segmentation.zarr(), "r").arrays())
    _, array2 = arrays[0]
    assert np.allclose(franken_array, array2), "Error writing numpy array subregion"


def test_run_new_voxel_spacing(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]
    copick_run = copick_root.get_run("TS_001")

    # Adding a voxel spacing with the same size as an existing one raises an error
    with pytest.raises(ValueError):
        copick_run.new_voxel_spacing(10.000)

    # Adding the first voxel spacing inits the _voxel_spacings attribute as list of voxel spacings
    vs3 = copick_run.new_voxel_spacing(30.000)

    assert copick_run._voxel_spacings is not None, "Voxel spacings should be populated"
    assert vs3 in copick_run.voxel_spacings, "Voxel spacing not added to voxel spacings"

    # Adding another voxel spacing appends to the list
    vs4 = copick_run.new_voxel_spacing(40.000)
    assert vs4 in copick_run.voxel_spacings, "Voxel spacing not added to voxel spacings"

    # Total number of voxel spacings should be 4 now
    copick_run.refresh_voxel_spacings()
    assert len(copick_run.voxel_spacings) == 4, "Incorrect number of voxel spacings"


def test_run_new_picks(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]
    copick_run = copick_root.get_run("TS_001")

    overlay_fs = test_payload["testfs_overlay"]
    overlay_loc = test_payload["testpath_overlay"]

    only_overlay = True
    static_fs = None
    static_loc = None
    if test_payload["testfs_static"] is not None:
        static_fs = test_payload["testfs_static"]
        static_loc = test_payload["testpath_static"]
        only_overlay = False

    # Check that picks are not populated
    assert copick_run._picks is None, "Picks should not be populated"

    # Adding a pick with the same name as an existing one raises an error
    with pytest.raises(ValueError):
        copick_run.new_picks(object_name="proteasome", session_id="0", user_id="pytom")

    # Add pick with object that does not exist
    with pytest.raises(ValueError):
        copick_run.new_picks(object_name="nucleus", session_id="0", user_id="pytom")

    # Adding the first pick inits the _picks attribute as list of picks
    pick6 = copick_run.new_picks(object_name="ribosome", session_id="0", user_id="ArtiaX")

    assert copick_run._picks is not None, "Picks should be populated"
    assert pick6 in copick_run.picks, "Pick not added to picks"

    # Adding another pick appends to the list after setting user id
    copick_root.config.user_id = "user.test"
    pick7 = copick_run.new_picks(object_name="ribosome", session_id="1234")

    assert pick7 in copick_run.picks, "Pick not added to picks"
    assert (
        pick7 == copick_run.get_picks(object_name="ribosome", session_id="1234", user_id="user.test")[0]
    ), "Pick not found"

    # Total number of picks should be 7 now
    copick_run.refresh_picks()
    assert len(copick_run.picks) == 7, "Incorrect number of picks"

    # Check filesystem for existing picks
    st = [
        "pytom_0_proteasome.json",
        "test.user_1234_ribosome.json",
        "gapstop_0_ribosome.json",
        "test.user_1234_proteasome.json",
        "ArtiaX_19_proteasome.json",
    ]

    ov = [
        "ArtiaX_0_ribosome.json",
        "user.test_1234_ribosome.json",
    ]
    if only_overlay:
        pick_path = str(overlay_loc / "ExperimentRuns" / "TS_001" / "Picks") + "/"
        for pick in ov + st:
            assert overlay_fs.exists(pick_path + pick), f"{pick} not found in overlay"
    else:
        pick_path_overlay = str(overlay_loc / "ExperimentRuns" / "TS_001" / "Picks") + "/"
        pick_path_static = str(static_loc / "ExperimentRuns" / "TS_001" / "Picks") + "/"

        for pick in st:
            assert static_fs.exists(pick_path_static + pick), f"{pick} not found in static"

        for pick in ov:
            assert overlay_fs.exists(pick_path_overlay + pick), f"{pick} not found in overlay"


def test_run_new_meshes(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]
    copick_run = copick_root.get_run("TS_001")

    overlay_fs = test_payload["testfs_overlay"]
    overlay_loc = test_payload["testpath_overlay"]

    only_overlay = True
    static_fs = None
    static_loc = None
    if test_payload["testfs_static"] is not None:
        static_fs = test_payload["testfs_static"]
        static_loc = test_payload["testpath_static"]
        only_overlay = False

    # Check that the meshes are not populated
    assert copick_run._meshes is None, "Meshes should not be populated"

    # Adding a mesh with the same name as an existing one raises an error
    with pytest.raises(ValueError):
        copick_run.new_mesh(object_name="membrane", session_id="0", user_id="membrain")

    # Add mesh with object that does not exist
    with pytest.raises(ValueError):
        copick_run.new_mesh(object_name="nucleus", session_id="0", user_id="pytom")

    # Adding the first mesh inits the _meshes attribute as list of meshes
    mesh2 = copick_run.new_mesh(object_name="membrane", session_id="0", user_id="ArtiaX")

    assert copick_run._meshes is not None, "Meshes should be populated"
    assert mesh2 in copick_run.meshes, "Mesh not added to meshes"

    # Adding another mesh appends to the list after setting user id
    copick_root.config.user_id = "user.test"
    mesh3 = copick_run.new_mesh(object_name="membrane", session_id="1234")

    assert mesh3 in copick_run.meshes, "Mesh not added to meshes"
    assert (
        mesh3 == copick_run.get_meshes(object_name="membrane", session_id="1234", user_id="user.test")[0]
    ), "Mesh not found"

    # Total number of meshes should be 5 now
    copick_run.refresh_meshes()
    assert len(copick_run.meshes) == 5, "Incorrect number of meshes"

    # Check filesystem for existing meshes
    st = [
        "membrain_0_membrane.glb",
        "user.test_321_proteasome.glb",
        "gapstop_0_ribosome.glb",
    ]

    ov = [
        "ArtiaX_0_membrane.glb",
        "user.test_1234_membrane.glb",
    ]

    if only_overlay:
        mesh_path = str(overlay_loc / "ExperimentRuns" / "TS_001" / "Meshes") + "/"
        for mesh in ov + st:
            assert overlay_fs.exists(mesh_path + mesh), f"{mesh} not found in overlay"
    else:
        mesh_path_overlay = str(overlay_loc / "ExperimentRuns" / "TS_001" / "Meshes") + "/"
        mesh_path_static = str(static_loc / "ExperimentRuns" / "TS_001" / "Meshes") + "/"

        for mesh in st:
            assert static_fs.exists(mesh_path_static + mesh), f"{mesh} not found in static"

        for mesh in ov:
            assert overlay_fs.exists(mesh_path_overlay + mesh), f"{mesh} not found in overlay"


def test_run_new_segmentations(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]
    copick_run = copick_root.get_run("TS_001")

    overlay_fs = test_payload["testfs_overlay"]
    overlay_loc = test_payload["testpath_overlay"]

    only_overlay = True
    static_fs = None
    static_loc = None
    if test_payload["testfs_static"] is not None:
        static_fs = test_payload["testfs_static"]
        static_loc = test_payload["testpath_static"]
        only_overlay = False

    # Check that segmentations are not populated
    assert copick_run._segmentations is None, "Segmentations should not be populated"

    # Adding a segmentation with the same name as an existing one raises an error
    with pytest.raises(ValueError):
        copick_run.new_segmentation(
            voxel_size=10.000,
            user_id="cellcanvas",
            session_id="0",
            name="prediction",
            is_multilabel=True,
        )

    # Add segmentation with object that does not exist
    with pytest.raises(ValueError):
        copick_run.new_segmentation(
            voxel_size=10.000,
            user_id="cellcanvas",
            session_id="0",
            name="nucleus",
            is_multilabel=False,
        )

    # Adding the first segmentation inits the _segmentations attribute as list of segmentations
    # For object stores we actually need to write to the zarr to create the "directory"
    seg4 = copick_run.new_segmentation(
        voxel_size=10.000,
        user_id="test.user",
        session_id="0",
        name="ribosome",
        is_multilabel=False,
    )
    zarr.create((5, 5, 5), store=seg4.zarr())
    assert copick_run._segmentations is not None, "Segmentations should be populated"
    assert seg4 in copick_run.segmentations, "Segmentation not added to segmentations"

    # Adding another segmentation appends to the list after setting user id
    # For object stores we actually need to write to the zarr to create the "directory"
    copick_root.config.user_id = "user.test"
    seg5 = copick_run.new_segmentation(
        voxel_size=10.000,
        session_id="1234",
        name="location",
        is_multilabel=True,
    )
    zarr.create((5, 5, 5), store=seg5.zarr())
    assert seg5 in copick_run.segmentations, "Segmentation not added to segmentations"
    assert (
        seg5
        == copick_run.get_segmentations(
            voxel_size=10.000,
            name="location",
            session_id="1234",
            user_id="user.test",
            is_multilabel=True,
        )[0]
    ), "Segmentation not found"

    # Total number of segmentations should be 5 now
    copick_run.refresh_segmentations()
    assert len(copick_run.segmentations) == 5, "Incorrect number of segmentations"

    # Check filesystem for existing segmentations
    st = [
        "10.000_cellcanvas_0_prediction-multilabel.zarr",
        "10.000_test.user_123_painting-multilabel.zarr",
        "20.000_membrain_0_membrane.zarr",
    ]

    ov = [
        "10.000_user.test_1234_location-multilabel.zarr",
        "10.000_test.user_0_ribosome.zarr",
    ]

    if only_overlay:
        seg_path = str(overlay_loc / "ExperimentRuns" / "TS_001" / "Segmentations") + "/"
        for seg in ov + st:
            assert overlay_fs.exists(seg_path + seg), f"{seg} not found in overlay"
    else:
        seg_path_overlay = str(overlay_loc / "ExperimentRuns" / "TS_001" / "Segmentations") + "/"
        seg_path_static = str(static_loc / "ExperimentRuns" / "TS_001" / "Segmentations") + "/"

        for seg in st:
            assert static_fs.exists(seg_path_static + seg), f"{seg} not found in static"

        for seg in ov:
            assert overlay_fs.exists(seg_path_overlay + seg), f"{seg} not found in overlay"


def test_run_refresh(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]
    copick_run = copick_root.get_run("TS_001")

    # Check that the run is not populated
    assert copick_run._voxel_spacings is None, "Voxel spacings should not be populated"
    assert copick_run._picks is None, "Picks should not be populated"
    assert copick_run._meshes is None, "Meshes should not be populated"
    assert copick_run._segmentations is None, "Segmentations should not be populated"

    copick_run.refresh()

    assert copick_run._voxel_spacings is not None, "Voxel spacings should be populated"
    assert copick_run._picks is not None, "Picks should be populated"
    assert copick_run._meshes is not None, "Meshes should be populated"
    assert copick_run._segmentations is not None, "Segmentations should be populated"

    assert len(copick_run.voxel_spacings) == 2, "Incorrect number of voxel spacings"
    assert len(copick_run.picks) == 5, "Incorrect number of picks"
    assert len(copick_run.meshes) == 3, "Incorrect number of meshes"
    assert len(copick_run.segmentations) == 3, "Incorrect number of segmentations"


def test_vs_meta(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]
    copick_run = copick_root.get_run("TS_001")
    vs = copick_run.get_voxel_spacing(10.000)

    # Check metadata for voxel spacing
    assert vs.voxel_size == 10.000, "Incorrect voxel size"


def test_vs_lazy(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]
    copick_run = copick_root.get_run("TS_001")
    vs = copick_run.get_voxel_spacing(10.000)

    # Check that the voxel spacing is not populated
    assert vs._tomograms is None, "Voxel size should not be populated"

    # Access the tomograms and confirm query
    tomograms = vs.tomograms
    ttype = [t.tomo_type for t in tomograms]

    assert len(tomograms) == 2, "Incorrect number of tomograms"
    assert "denoised" in ttype, "Expected tomogram not found"
    assert "wbp" in ttype, "Expected tomogram not found"


def test_vs_get_tomogram(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]
    copick_run = copick_root.get_run("TS_001")
    vs = copick_run.get_voxel_spacing(10.000)

    # Get tomogram
    tomogram = vs.get_tomogram(tomo_type="denoised")
    assert tomogram is not None, "Tomogram not found"
    assert tomogram.tomo_type == "denoised", "Wrong tomogram found"

    # Non-existing tomogram
    tomogram = vs.get_tomogram(tomo_type="SIRT")
    assert tomogram is None, "Tomogram should not be found"


def test_vs_new_tomogram(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]
    copick_run = copick_root.get_run("TS_001")
    vs = copick_run.get_voxel_spacing(10.000)

    overlay_fs = test_payload["testfs_overlay"]
    overlay_loc = test_payload["testpath_overlay"]

    only_overlay = True
    static_fs = None
    static_loc = None
    if test_payload["testfs_static"] is not None:
        static_fs = test_payload["testfs_static"]
        static_loc = test_payload["testpath_static"]
        only_overlay = False

    # Check that the voxel spacing is not populated
    assert vs._tomograms is None, "Tomograms should not be populated"

    # Adding a tomogram with the same name as an existing one raises an error
    with pytest.raises(ValueError):
        vs.new_tomogram(tomo_type="denoised")

    # Adding the first tomogram inits the _tomograms attribute as list of tomograms
    # For object stores we actually need to write to the zarr to create the "directory"
    tomogram = vs.new_tomogram(tomo_type="isonet")
    zarr.create((5, 5, 5), store=tomogram.zarr())

    assert vs._tomograms is not None, "Tomograms should be populated"
    assert tomogram in vs.tomograms, "Tomogram not added to tomograms"

    # Adding another tomogram appends to the list
    # For object stores we actually need to write to the zarr to create the "directory"
    tomogram = vs.new_tomogram(tomo_type="SIRT")
    zarr.create((5, 5, 5), store=tomogram.zarr())

    assert tomogram in vs.tomograms, "Tomogram not added to tomograms"
    assert tomogram == vs.get_tomogram(tomo_type="SIRT"), "Tomogram not found"

    # Total number of tomograms should be 3 now
    vs.refresh_tomograms()
    assert len(vs.tomograms) == 4, "Incorrect number of tomograms"

    # Check filesystem for existing tomograms
    st = [
        "denoised.zarr",
        "wbp.zarr",
    ]

    ov = [
        "isonet.zarr",
        "SIRT.zarr",
    ]

    if only_overlay:
        tomogram_path = str(overlay_loc / "ExperimentRuns" / "TS_001" / "VoxelSpacing10.000") + "/"
        for tomogram in ov + st:
            assert overlay_fs.exists(tomogram_path + tomogram), f"{tomogram} not found in overlay"
    else:
        tomogram_path_overlay = str(overlay_loc / "ExperimentRuns" / "TS_001" / "VoxelSpacing10.000") + "/"
        tomogram_path_static = str(static_loc / "ExperimentRuns" / "TS_001" / "VoxelSpacing10.000") + "/"

        for tomogram in st:
            assert static_fs.exists(tomogram_path_static + tomogram), f"{tomogram} not found in static"

        for tomogram in ov:
            assert overlay_fs.exists(tomogram_path_overlay + tomogram), f"{tomogram} not found in overlay"


def test_vs_refresh(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]
    copick_run = copick_root.get_run("TS_001")
    vs = copick_run.get_voxel_spacing(10.000)

    # Check that the voxel spacing is not populated
    assert vs._tomograms is None, "Tomograms should not be populated"

    vs.refresh()

    assert vs._tomograms is not None, "Tomograms should be populated"
    assert len(vs.tomograms) == 2, "Incorrect number of tomograms"


def test_tomogram_meta(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]
    copick_run = copick_root.get_run("TS_001")
    vs = copick_run.get_voxel_spacing(10.000)
    tomogram = vs.get_tomogram(tomo_type="denoised")

    # Check metadata for tomogram
    assert tomogram.tomo_type == "denoised", "Incorrect tomogram type"


def test_tomogram_lazy(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]
    copick_run = copick_root.get_run("TS_001")
    vs = copick_run.get_voxel_spacing(10.000)
    tomogram = vs.get_tomogram(tomo_type="wbp")

    # Check that the features are not populated
    assert tomogram._features is None, "features should not be populated"

    # Access the features and confirm query
    features = tomogram.features
    ftype = [f.feature_type for f in features]

    assert len(features) == 2, "Incorrect number of features"
    assert "sobel" in ftype, "Expected feature not found"
    assert "edge" in ftype, "Expected feature not found"


def test_tomogram_get_features(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]
    copick_run = copick_root.get_run("TS_001")
    vs = copick_run.get_voxel_spacing(10.000)
    tomogram = vs.get_tomogram(tomo_type="wbp")

    # Get features by type
    features = tomogram.get_features(feature_type="sobel")
    assert features is not None, "Incorrect number of features"

    # Non-existing feature
    features = tomogram.get_features(feature_type="sift")
    assert features is None, "Incorrect number of features"


def test_tomogram_new_features(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]
    copick_run = copick_root.get_run("TS_001")
    vs = copick_run.get_voxel_spacing(10.000)
    tomogram = vs.get_tomogram(tomo_type="wbp")

    overlay_fs = test_payload["testfs_overlay"]
    overlay_loc = test_payload["testpath_overlay"]

    only_overlay = True
    static_fs = None
    static_loc = None
    if test_payload["testfs_static"] is not None:
        static_fs = test_payload["testfs_static"]
        static_loc = test_payload["testpath_static"]
        only_overlay = False

    # Check that the tomogram is not populated
    assert tomogram._features is None, "Features should not be populated"

    # Adding a feature with the same name as an existing one raises an error
    with pytest.raises(ValueError):
        tomogram.new_features(feature_type="sobel")

    # Adding the first feature inits the _features attribute as list of features
    # For object stores we actually need to write to the zarr to create the "directory"
    feature = tomogram.new_features(feature_type="sift")
    zarr.create((5, 5, 5), store=feature.zarr())

    assert tomogram._features is not None, "Features should be populated"
    assert feature in tomogram.features, "Feature not added to features"

    # Adding another feature appends to the list
    # For object stores we actually need to write to the zarr to create the "directory"
    feature = tomogram.new_features(feature_type="tomotwin")
    zarr.create((5, 5, 5), store=feature.zarr())

    assert feature in tomogram.features, "Feature not added to features"
    assert feature == tomogram.get_features(feature_type="tomotwin"), "Feature not found"

    # Total number of features should be 3 now
    tomogram.refresh_features()
    assert len(tomogram.features) == 4, "Incorrect number of features"

    # Check filesystem for existing features
    st = [
        "wbp_sobel_features.zarr",
        "wbp_edge_features.zarr",
    ]

    ov = [
        "wbp_sift_features.zarr",
        "wbp_tomotwin_features.zarr",
    ]

    if only_overlay:
        feature_path = str(overlay_loc / "ExperimentRuns" / "TS_001" / "VoxelSpacing10.000") + "/"
        for feature in ov + st:
            assert overlay_fs.exists(feature_path + feature), f"{feature} not found in overlay"
    else:
        feature_path_overlay = str(overlay_loc / "ExperimentRuns" / "TS_001" / "VoxelSpacing10.000") + "/"
        feature_path_static = str(static_loc / "ExperimentRuns" / "TS_001" / "VoxelSpacing10.000") + "/"

        for feature in st:
            assert static_fs.exists(feature_path_static + feature), f"{feature} not found in static"

        for feature in ov:
            assert overlay_fs.exists(feature_path_overlay + feature), f"{feature} not found in overlay"


def test_tomogram_refresh(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]
    copick_run = copick_root.get_run("TS_001")
    vs = copick_run.get_voxel_spacing(10.000)
    tomogram = vs.get_tomogram(tomo_type="wbp")

    # Check that the tomogram is not populated
    assert tomogram._features is None, "Features should not be populated"

    tomogram.refresh()

    assert tomogram._features is not None, "Features should be populated"
    assert len(tomogram.features) == 2, "Incorrect number of features"


def test_tomogram_zarr(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]
    copick_run = copick_root.get_run("TS_001")
    vs = copick_run.get_voxel_spacing(10.000)
    tomogram = vs.get_tomogram(tomo_type="denoised")

    # Check zarr is readable
    arrays = list(zarr.open(tomogram.zarr(), "r").arrays())
    _, array = arrays[0]
    assert array.shape == (64, 64, 64), "Error reading Zarr, (incorrect shape)"
    assert np.sum(array) == pytest.approx(
        8192.0,
        abs=NUMERICAL_PRECISION,
    ), "Error reading Zarr (incorrect sum)."

    # Check zarr is writable
    tomo = vs.new_tomogram(tomo_type="test")
    zarr.array(np.random.rand(64, 64, 64), store=tomo.zarr(), chunks=(32, 32, 32))


def test_tomogram_read_numpy(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]
    copick_run = copick_root.get_run("TS_001")
    vs = copick_run.get_voxel_spacing(10.000)
    tomogram = vs.get_tomogram(tomo_type="denoised")

    # Full array
    array = tomogram.numpy()
    assert array.shape == (64, 64, 64), "Error getting numpy array, (incorrect shape)"
    assert np.sum(array) == pytest.approx(
        8192.0,
        abs=NUMERICAL_PRECISION,
    ), "Error getting numpy array (incorrect sum)."

    # Subregion
    array = tomogram.numpy(x=slice(0, 30), y=slice(50, 60), z=slice(10, 40))
    assert array.shape == (30, 10, 30), "Error getting numpy array, (incorrect shape)"
    assert np.sum(array) == pytest.approx(
        30.0,
        abs=NUMERICAL_PRECISION,
    ), "Error getting numpy array (incorrect sum)."


def test_tomogram_write_numpy(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]
    copick_run = copick_root.get_run("TS_001")
    vs = copick_run.get_voxel_spacing(10.000)
    tomogram = vs.new_tomogram(tomo_type="test")

    # Write numpy array
    array = np.random.rand(64, 64, 64)
    tomogram.from_numpy(array)

    # Check zarr contents
    arrays = list(zarr.open(tomogram.zarr(), "r").arrays())
    _, array2 = arrays[0]
    assert np.allclose(array, array2), "Error writing numpy array"

    # Write subregion
    sub_array = np.random.rand(30, 30, 30)
    franken_array = array
    franken_array[10:40, 10:40, 10:40] = sub_array
    tomogram.set_region(sub_array, x=slice(10, 40), y=slice(10, 40), z=slice(10, 40))

    # Check zarr contents
    arrays = list(zarr.open(tomogram.zarr(), "r").arrays())
    _, array2 = arrays[0]
    assert np.allclose(franken_array, array2), "Error writing numpy array subregion"


def test_feature_meta(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]
    copick_run = copick_root.get_run("TS_001")
    vs = copick_run.get_voxel_spacing(10.000)
    tomogram = vs.get_tomogram(tomo_type="wbp")
    feature = tomogram.get_features(feature_type="sobel")

    # Check metadata for feature
    assert feature.feature_type == "sobel", "Incorrect feature type"
    assert feature.tomo_type == "wbp", "Incorrect feature name"


def test_feature_zarr(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]
    copick_run = copick_root.get_run("TS_001")
    vs = copick_run.get_voxel_spacing(10.000)
    tomogram = vs.get_tomogram(tomo_type="wbp")
    feature = tomogram.get_features(feature_type="sobel")

    # Check zarr is readable
    arrays = list(zarr.open(feature.zarr(), "r").arrays())
    _, array = arrays[0]
    assert array.shape == (64, 64, 64), "Error reading Zarr, (incorrect shape)"
    assert np.sum(array) == pytest.approx(
        20619.8125,
        abs=NUMERICAL_PRECISION,
    ), "Error reading Zarr (incorrect sum)."

    # Check zarr is writable
    feat = tomogram.new_features(feature_type="test")
    zarr.array(np.random.rand(64, 64, 64), store=feat.zarr(), chunks=(32, 32, 32))


def test_feature_read_numpy(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]
    copick_run = copick_root.get_run("TS_001")
    vs = copick_run.get_voxel_spacing(10.000)
    tomogram = vs.get_tomogram(tomo_type="wbp")
    feature = tomogram.get_features(feature_type="sobel")

    # Full volume
    array = feature.numpy()
    assert array.shape == (64, 64, 64), "Error getting numpy array, (incorrect shape)"
    assert np.sum(array) == pytest.approx(
        20619.8125,
        abs=NUMERICAL_PRECISION,
    ), "Error getting numpy array (incorrect sum)."

    # Subregion
    array = feature.numpy(slices=(slice(20, 40), slice(20, 40), slice(20, 40)))
    assert array.shape == (20, 20, 20), "Error getting numpy array, (incorrect shape)"
    assert np.sum(array) == pytest.approx(
        563.36730957,
        abs=NUMERICAL_PRECISION,
    ), "Error getting numpy array (incorrect sum)."


def test_feature_write_numpy(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]
    copick_run = copick_root.get_run("TS_001")
    vs = copick_run.get_voxel_spacing(10.000)
    tomogram = vs.get_tomogram(tomo_type="wbp")
    feat = tomogram.new_features(feature_type="test")

    # Write zarr
    array = np.random.rand(64, 64, 64)
    pyramid = {10.000: array}
    write_ome_zarr_3d(feat.zarr(), pyramid, (32, 32, 32))

    # Write subregion
    sub_array = np.random.rand(30, 30, 30)
    franken_array = array
    franken_array[10:40, 10:40, 10:40] = sub_array
    feat.set_region(sub_array, slices=(slice(10, 40), slice(10, 40), slice(10, 40)))

    # Check zarr contents
    arrays = list(zarr.open(feat.zarr(), "r").arrays())
    _, array2 = arrays[0]
    assert np.allclose(franken_array, array2), "Error writing numpy array subregion"


def test_mesh_meta(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]
    copick_run = copick_root.get_run("TS_001")
    mesh = copick_run.get_meshes(object_name="membrane", session_id="0", user_id="membrain")[0]

    # Check metadata for mesh
    assert mesh.pickable_object_name == "membrane", "Incorrect object name"
    assert mesh.session_id == "0", "Incorrect session id"
    assert mesh.user_id == "membrain", "Incorrect user id"
    assert mesh.from_tool is True, "Incorrect from_tool"


def test_mesh_io(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]
    copick_run = copick_root.get_run("TS_001")
    mesh = copick_run.get_meshes(object_name="membrane", session_id="0", user_id="membrain")[0]

    only_overlay = True
    if test_payload["testfs_static"] is not None:
        only_overlay = False

    # Mesh not initialized
    assert mesh._mesh is None, "Mesh should not be initialized"

    # Check mesh is readable
    msh = mesh.load()
    assert isinstance(msh, Geometry), "Error reading mesh"

    # Check mesh is initialized
    assert mesh._mesh is not None, "Mesh should be initialized"
    assert msh == mesh.mesh, "Mesh should be initialized"

    # Check static mesh not writable
    if not only_overlay:
        with pytest.raises(PermissionError):
            mesh.store()

    # Check mesh is writable
    msh2 = copick_run.new_mesh(object_name="proteasome", session_id="0", user_id="deepfinder")
    msh2.store()


def test_picks_meta(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]
    copick_run = copick_root.get_run("TS_001")
    pick = copick_run.get_picks(object_name="proteasome", session_id="0", user_id="pytom")[0]

    # Check metadata for pick
    assert pick.pickable_object_name == "proteasome", "Incorrect object name"
    assert pick.session_id == "0", "Incorrect session id"
    assert pick.user_id == "pytom", "Incorrect user id"
    assert pick.from_tool is True, "Incorrect from_tool"
    assert pick.trust_orientation is True, "Incorrect trust_orientation"
    assert pick.color == (255, 0, 0, 255), "Incorrect color"


def test_pick_io(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]
    copick_run = copick_root.get_run("TS_001")
    picks = copick_run.get_picks(object_name="proteasome", session_id="0", user_id="pytom")[0]

    only_overlay = True
    if test_payload["testfs_static"] is not None:
        only_overlay = False

    # Check picks is readable
    pck = picks.load()
    assert isinstance(pck, CopickPicksFile), "Error reading pick"

    # Check static picks not writable
    if not only_overlay:
        with pytest.raises(PermissionError):
            picks.store()

    # Check pick is writable
    pck2 = copick_run.new_picks(object_name="ribosome", session_id="0", user_id="pytom")
    pck2.store()


def test_root_new_object(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]

    # Test creating a new object
    new_obj = copick_root.new_object(
        name="test-object",
        is_particle=True,
        label=50,
        color=(128, 64, 192, 255),
        radius=75.0,
    )

    assert new_obj.name == "test-object"
    assert new_obj.is_particle is True
    assert new_obj.label == 50
    assert new_obj.color == (128, 64, 192, 255)
    assert new_obj.radius == 75.0

    # Test that object is accessible from root
    retrieved_obj = copick_root.get_object("test-object")
    assert retrieved_obj is not None
    assert retrieved_obj.name == "test-object"

    # Test auto label assignment
    auto_obj = copick_root.new_object(name="auto-label-object", is_particle=False)
    assert auto_obj.label > 0
    assert auto_obj.label != new_obj.label

    # Test duplicate name handling
    with pytest.raises(ValueError, match="already exists"):
        copick_root.new_object(name="test-object", is_particle=True)

    # Test exist_ok=True
    existing_obj = copick_root.new_object(name="test-object", is_particle=False, exist_ok=True)  # Different type
    # Should update the existing object
    assert existing_obj.name == "test-object"
    assert existing_obj.is_particle is False  # Should be updated


def test_root_save_config(test_payload: Dict[str, Any], tmp_path):
    # Setup
    copick_root = test_payload["root"]

    # Add a new object
    copick_root.new_object(name="test-save-object", is_particle=True, label=99)

    # Save config
    config_path = tmp_path / "test_config.json"
    copick_root.save_config(str(config_path))

    # Verify file was created
    assert config_path.exists()

    # Load config and verify object was saved
    from copick.impl.filesystem import CopickRootFSSpec

    new_root = CopickRootFSSpec.from_file(str(config_path))
    saved_obj = new_root.get_object("test-save-object")
    assert saved_obj is not None
    assert saved_obj.name == "test-save-object"
    assert saved_obj.label == 99


def test_object_write_readonly_behavior(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]

    # Test that we can create writable objects
    writable_obj = copick_root.new_object(name="writable-test", is_particle=True)

    # For filesystem backend, newly created objects should be writable
    if hasattr(writable_obj, "read_only"):
        assert writable_obj.read_only is False

    # Test writing to object (should work for writable objects)
    if writable_obj.is_particle:
        import numpy as np

        volume_data = np.random.randn(16, 16, 16).astype(np.float32)
        try:
            writable_obj.from_numpy(volume_data, 10.0)
            # If we get here, the object is writable
            assert writable_obj.zarr() is not None
        except ValueError as e:
            if "read-only" in str(e):
                # This object is read-only, which is also valid
                pass
            else:
                # Some other error, re-raise
                raise


def test_repr(test_payload: Dict[str, Any]):
    # Setup
    copick_root = test_payload["root"]
    copick_run = copick_root.get_run("TS_001")
    vs = copick_run.get_voxel_spacing(10.000)
    tomogram = vs.get_tomogram(tomo_type="wbp")
    feature = tomogram.get_features(feature_type="sobel")
    mesh = copick_run.get_meshes(object_name="membrane", session_id="0", user_id="membrain")[0]
    pick = copick_run.get_picks(object_name="proteasome", session_id="0", user_id="pytom")[0]
    seg = copick_run.get_segmentations(name="membrane")[0]
    co = copick_root.pickable_objects[0]

    repr(copick_run)
    repr(vs)
    repr(tomogram)
    repr(feature)
    repr(mesh)
    repr(pick)
    repr(seg)
    repr(co)
