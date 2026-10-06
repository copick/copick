"""Offline tests for the Embrella backend.

A stdlib HTTP server plays both roles of the real deployment: the Embrella projects
API (``/copick/v1/projects/``) and the cluster file server (Caddy), including Caddy's
JSON directory listings (``Accept: application/json``) with an HTML fallback.
"""

import json
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import copick
import numpy as np
import pytest
import zarr
from copick.impl.embrella import (
    CopickConfigEmbrella,
    CopickRootEmbrella,
    EmbrellaTomoSelection,
    _join_path,
    _positions_from_listing,
)
from copick.models import PickableObject
from zarr.storage import LocalStore

DCTF_VS = 5.0015426674967864  # rounds to 5.002
SART_VS = 10.003085334993573  # rounds to 10.003


def _write_tomo_zarr(path: Path, voxel_size: float, shape=(8, 8, 8), with_scale: bool = True) -> np.ndarray:
    """Write a tiny Zarr v2 / NGFF 0.4 tomogram like zarrczar does."""
    path.parent.mkdir(parents=True, exist_ok=True)
    group = zarr.group(store=LocalStore(str(path)), zarr_format=2)
    data = np.arange(np.prod(shape), dtype=np.float32).reshape(shape)
    array = group.create_array(
        "0",
        shape=shape,
        chunks=shape,
        dtype="float32",
        chunk_key_encoding={"name": "v2", "separator": "/"},
    )
    array[:] = data

    dataset = {"path": "0"}
    if with_scale:
        dataset["coordinateTransformations"] = [{"type": "scale", "scale": [voxel_size] * 3}]
    group.attrs["multiscales"] = [
        {
            "version": "0.4",
            "axes": [{"name": n, "type": "space", "unit": "angstrom"} for n in "zyx"],
            "datasets": [dataset],
        },
    ]
    return data


def _write_overlay_project(root: Path, posix_root: str, pickable_objects=None) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "ExperimentRuns").mkdir(exist_ok=True)
    config = {
        "config_type": "filesystem",
        "name": "embrella overlay",
        "description": "",
        "version": "1.23.3",
        "pickable_objects": pickable_objects or [],
        "overlay_root": f"local://{posix_root}",
        "overlay_fs_args": {"auto_mkdir": True},
    }
    (root / "config.json").write_text(json.dumps(config))


@pytest.fixture
def tree(tmp_path):
    """Build a processing tree with two sessions and their overlay projects."""
    base = tmp_path / "tree"
    proc = base / "krios1.processing"

    # Session 25aug25a: AreTomo3 run003 (dctf + sart), DenoisET run001.
    vol1 = proc / "aretomo3" / "25aug25a" / "run003" / "vol001"
    vol3 = proc / "aretomo3" / "25aug25a" / "run003" / "vol003"
    for pos in ("Position_1", "Position_2"):
        _write_tomo_zarr(vol1 / f"{pos}_Vol.zarr", DCTF_VS)
        _write_tomo_zarr(vol3 / f"{pos}_Vol.zarr", SART_VS)
        (vol1 / f"{pos}_Vol.mrc").write_bytes(b"MRC")
    # Even/odd half-reconstruction decoys (stem exclusion).
    _write_tomo_zarr(vol1 / "Position_9_EVN_Vol.zarr", DCTF_VS)
    _write_tomo_zarr(vol1 / "Position_9_ODD_Vol.zarr", DCTF_VS)
    # Denoised run (no vol subdirectory).
    _write_tomo_zarr(proc / "denoise" / "25aug25a" / "run001" / "Position_1_Vol.zarr", SART_VS)

    # Session 25aug22b: AreTomo3 run001 (dctf only), messy stem, one zarr without scale.
    vol1b = proc / "aretomo3" / "25aug22b" / "run001" / "vol001"
    _write_tomo_zarr(vol1b / "L2_Series3A_Pos1.mrc_Vol.zarr", DCTF_VS)

    # Overlay projects.
    ovl_a = proc / "copick" / "25aug25a" / "run002"
    _write_overlay_project(
        ovl_a,
        str(ovl_a),
        pickable_objects=[
            {"name": "ribosome", "is_particle": True, "label": 1, "color": [0, 117, 220, 255], "radius": 150.0},
            {"name": "membrane", "is_particle": False, "label": 2, "color": [255, 0, 0, 255], "radius": 50.0},
        ],
    )
    # Pre-existing duplicated import (plain tomo_type) and a pick, like Embrella creates.
    run_dir = ovl_a / "ExperimentRuns" / "25aug25a_Position_1"
    _write_tomo_zarr(run_dir / "VoxelSpacing10.003" / "sart.zarr", SART_VS)
    (run_dir / "Picks").mkdir(parents=True)
    (run_dir / "Picks" / "alice_1_ribosome.json").write_text(
        json.dumps(
            {
                "pickable_object_name": "ribosome",
                "user_id": "alice",
                "session_id": "1",
                "run_name": "25aug25a_Position_1",
                "points": [],
            },
        ),
    )

    ovl_b = proc / "copick" / "25aug22b" / "run001"
    _write_overlay_project(
        ovl_b,
        str(ovl_b),
        pickable_objects=[
            {"name": "ribosome", "is_particle": True, "label": 7, "color": [1, 2, 3, 255], "radius": 150.0},
        ],
    )

    return base


class _EmbrellaHandler(SimpleHTTPRequestHandler):
    """Serves the Embrella projects API and Caddy-style file listings from a tree."""

    projects: dict = {}

    def log_message(self, format, *args):  # noqa: A002
        pass

    def _send_json(self, payload) -> None:
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path.rstrip("/") == "/copick/v1/projects":
            query = urllib.parse.parse_qs(parsed.query)
            session = query.get("session_id", [None])[0]
            self._send_json({"success": True, "projects": self.projects.get(session, [])})
            return

        if "application/json" in (self.headers.get("Accept") or ""):
            local = Path(self.directory) / urllib.parse.unquote(parsed.path).lstrip("/")
            if local.is_dir():
                entries = [
                    {"name": p.name + ("/" if p.is_dir() else ""), "is_dir": p.is_dir()}
                    for p in sorted(local.iterdir())
                ]
                self._send_json(entries)
                return

        super().do_GET()


@pytest.fixture
def server(tree):
    """Serve the tree; yields the base URL (Embrella API and file server in one)."""

    class Handler(_EmbrellaHandler):
        projects = {}

        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(tree), **kwargs)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{httpd.server_port}"

    Handler.projects = {
        "25aug25a": [
            {
                "session_name": "25aug25a",
                "run_name": "run001",
                "cluster_id": "test",
                "scope": "krios1",
                "root_url": f"{base_url}/krios1.processing/copick/25aug25a/run001/",
                "config_url": f"{base_url}/krios1.processing/copick/25aug25a/run001/config.json",
                "data_url": f"{base_url}/krios1.processing/copick/25aug25a/run001/",
                "status": "failed",
                "created_at": "2026-08-01T00:00:00+00:00",
                "proc_run_id": 1,
            },
            {
                "session_name": "25aug25a",
                "run_name": "run002",
                "cluster_id": "test",
                "scope": "krios1",
                "root_url": f"{base_url}/krios1.processing/copick/25aug25a/run002/",
                "config_url": f"{base_url}/krios1.processing/copick/25aug25a/run002/config.json",
                "data_url": f"{base_url}/krios1.processing/copick/25aug25a/run002/",
                "status": "completed",
                "created_at": "2026-08-02T00:00:00+00:00",
                "proc_run_id": 2,
            },
        ],
        "25aug22b": [
            {
                "session_name": "25aug22b",
                "run_name": "run001",
                "cluster_id": "test",
                "scope": "krios1",
                "root_url": f"{base_url}/krios1.processing/copick/25aug22b/run001/",
                "config_url": f"{base_url}/krios1.processing/copick/25aug22b/run001/config.json",
                "data_url": f"{base_url}/krios1.processing/copick/25aug22b/run001/",
                "status": "completed",
                "created_at": "2026-08-03T00:00:00+00:00",
                "proc_run_id": 3,
            },
        ],
    }

    yield base_url

    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=5)


def _config_dict(tree, base_url, **overrides):
    config = {
        "config_type": "embrella",
        "name": "embrella test project",
        "pickable_objects": [
            {"name": "ribosome", "is_particle": True, "label": 1, "color": [0, 117, 220, 255], "radius": 150.0},
        ],
        "embrella_base_url": base_url,
        "clusters": {"test": {"http_base": f"{base_url}/", "posix_base": str(tree)}},
        "default_data_cluster": "test",
        "scope": "krios1",
        "sessions": [
            {
                "name": "25aug25a",
                "tomograms": [
                    {"proc_run": "run003", "recon_type": "dctf"},
                    {"proc_run": "run003", "recon_type": "sart"},
                    {"proc_run": "run001", "recon_type": "denoise"},
                ],
                "overlay_run": "run002",
            },
            {
                "name": "25aug22b",
                "tomograms": [{"proc_run": "run001", "recon_type": "dctf"}],
            },
        ],
        "overlay_mode": "local",
        "static_mode": "http",
    }
    config.update(overrides)
    return config


@pytest.fixture
def root(tree, server) -> CopickRootEmbrella:
    return copick.from_string(json.dumps(_config_dict(tree, server)))


# --------------------------------------------------------------------------------------
# Config validation
# --------------------------------------------------------------------------------------


def test_wbp_is_rejected():
    with pytest.raises(ValueError, match="MRC only"):
        EmbrellaTomoSelection(proc_run="run001", recon_type="wbp")


def test_underscore_proc_run_is_rejected():
    with pytest.raises(ValueError, match="underscore"):
        EmbrellaTomoSelection(proc_run="run_001", recon_type="dctf")


def test_tomo_type_derivation():
    sel = EmbrellaTomoSelection(proc_run="run003", recon_type="DCTF")
    assert sel.tomo_type == "run003-dctf"


def test_positions_from_listing_excludes_half_reconstructions():
    entries = [
        {"name": "Position_1_Vol.zarr", "is_dir": True},
        {"name": "Position_1_EVN_Vol.zarr", "is_dir": True},
        {"name": "Position_1_ODD_Vol.zarr", "is_dir": True},
        {"name": "Position_1_Vol.mrc", "is_dir": False},
        {"name": "L2_Series3A_Pos1.mrc_Vol.zarr", "is_dir": True},
    ]
    assert _positions_from_listing(entries) == ["L2_Series3A_Pos1.mrc", "Position_1"]


def test_join_path_collapses_empty_segments():
    assert _join_path("http://x/", "a.processing", "denoise", "s", "r", None) == "http://x/a.processing/denoise/s/r"


# --------------------------------------------------------------------------------------
# Index building
# --------------------------------------------------------------------------------------


def test_index_build(root):
    index = root.index
    assert set(index.sessions) == {"25aug25a", "25aug22b"}

    # Pinned overlay project wins over the newest one.
    assert index.sessions["25aug25a"].overlay_run == "run002"
    # Unpinned: newest completed project.
    assert index.sessions["25aug22b"].overlay_run == "run001"

    assert set(index.runs) == {
        "25aug25a_Position_1",
        "25aug25a_Position_2",
        "25aug22b_L2_Series3A_Pos1.mrc",
    }

    # Position_1 has dctf, sart and denoise; Position_2 only dctf and sart.
    types_p1 = {r.tomo_type for r in index.tomos_by_run["25aug25a_Position_1"]}
    assert types_p1 == {"run003-dctf", "run003-sart", "run001-denoise"}
    types_p2 = {r.tomo_type for r in index.tomos_by_run["25aug25a_Position_2"]}
    assert types_p2 == {"run003-dctf", "run003-sart"}


def test_voxel_size_sniffed_and_rounded(root):
    records = root.index.tomos_by_run["25aug25a_Position_1"]
    by_type = {r.tomo_type: r for r in records}
    assert by_type["run003-dctf"].voxel_size == 5.002
    assert by_type["run003-sart"].voxel_size == 10.003


def test_denoise_url_has_no_vol_segment_and_no_double_slash(root):
    record = next(r for r in root.index.tomos_by_run["25aug25a_Position_1"] if r.recon_type == "denoise")
    assert record.static_url.endswith("/krios1.processing/denoise/25aug25a/run001/Position_1_Vol.zarr")
    assert "//" not in record.static_url.split("://", 1)[1]


def test_voxel_size_override(tree, server):
    config = _config_dict(tree, server)
    config["sessions"] = [
        {
            "name": "25aug25a",
            "tomograms": [{"proc_run": "run003", "recon_type": "dctf", "voxel_size": 5.0}],
            "overlay_run": "run002",
        },
    ]
    root = copick.from_string(json.dumps(config))
    assert all(r.voxel_size == 5.0 for r in root.index.tomos_by_run["25aug25a_Position_1"])


def test_missing_scale_metadata_raises_actionable_error(tree, server):
    _write_tomo_zarr(
        tree / "krios1.processing" / "aretomo3" / "25aug25a" / "run005" / "vol001" / "Position_1_Vol.zarr",
        DCTF_VS,
        with_scale=False,
    )
    config = _config_dict(tree, server)
    config["sessions"] = [
        {
            "name": "25aug25a",
            "tomograms": [{"proc_run": "run005", "recon_type": "dctf"}],
            "overlay_run": "run002",
        },
    ]
    with pytest.raises(ValueError, match="voxel_size"):
        copick.from_string(json.dumps(config))


def test_pinned_positions_skip_listing(tree, server):
    config = _config_dict(tree, server)
    config["sessions"] = [
        {
            "name": "25aug25a",
            "tomograms": [{"proc_run": "run003", "recon_type": "dctf", "positions": ["Position_1"]}],
            "overlay_run": "run002",
        },
    ]
    root = copick.from_string(json.dumps(config))
    assert set(root.index.runs) == {"25aug25a_Position_1"}


def test_unknown_cluster_raises(tree, server):
    config = _config_dict(tree, server)
    config["sessions"][0]["tomograms"] = [{"proc_run": "run003", "recon_type": "dctf", "cluster": "nope"}]
    with pytest.raises(ValueError, match="Unknown cluster 'nope'"):
        copick.from_string(json.dumps(config))


# --------------------------------------------------------------------------------------
# Runs, voxel spacings, tomograms
# --------------------------------------------------------------------------------------


def test_query_runs_union_with_overlay_only_runs(tree, root):
    extra = tree / "krios1.processing" / "copick" / "25aug25a" / "run002" / "ExperimentRuns" / "25aug25a_Position_99"
    extra.mkdir(parents=True)

    names = [r.name for r in root.runs]
    assert "25aug25a_Position_99" in names
    assert "25aug25a_Position_1" in names
    assert "25aug22b_L2_Series3A_Pos1.mrc" in names

    overlay_only = root.get_run("25aug25a_Position_99")
    assert overlay_only.embrella_session == "25aug25a"
    assert overlay_only.voxel_spacings == []


def test_get_run_random_access(root):
    # _runs is None until the runs property is touched -> random access path.
    assert root._runs is None
    run = root.get_run("25aug25a_Position_1")
    assert run is not None
    assert run.embrella_session == "25aug25a"
    assert run.embrella_position == "Position_1"
    assert root.get_run("25aug25a_Position_nope") is None
    assert root.get_run("unrelated_run") is None


def test_voxel_spacings_deduped_between_static_and_overlay(root):
    run = root.get_run("25aug25a_Position_1")
    spacings = run.voxel_spacings
    sizes = sorted(vs.voxel_size for vs in spacings)
    # 5.002 (static dctf) and 10.003 (static sart/denoise + overlay dir, deduped).
    assert sizes == [5.002, 10.003]


def test_static_tomograms_read_only(root):
    run = root.get_run("25aug25a_Position_1")
    vs = run.get_voxel_spacing(5.002)
    tomos = vs.get_tomograms("run003-dctf")
    assert len(tomos) == 1
    tomo = tomos[0]
    assert tomo.read_only is True
    assert tomo.meta.embrella_proc_run == "run003"
    assert tomo.meta.embrella_recon_type == "dctf"
    store = tomo.zarr()
    assert store.read_only is True
    with pytest.raises(PermissionError):
        tomo.delete()


def test_tomogram_numpy_over_http(root):
    run = root.get_run("25aug25a_Position_1")
    vs = run.get_voxel_spacing(5.002)
    tomo = vs.get_tomograms("run003-dctf")[0]
    data = tomo.numpy()
    expected = np.arange(8 * 8 * 8, dtype=np.float32).reshape(8, 8, 8)
    np.testing.assert_array_equal(data, expected)


def test_overlay_tomogram_listed_alongside_static(root):
    run = root.get_run("25aug25a_Position_1")
    vs = run.get_voxel_spacing(10.003)
    types = {t.tomo_type for t in vs.tomograms}
    # Static sart/denoise plus the legacy duplicated plain "sart" import.
    assert types == {"run003-sart", "run001-denoise", "sart"}


def test_exclude_overlay_tomo_types(tree, server):
    config = _config_dict(tree, server, exclude_overlay_tomo_types=["sart"])
    root = copick.from_string(json.dumps(config))
    run = root.get_run("25aug25a_Position_1")
    vs = run.get_voxel_spacing(10.003)
    types = {t.tomo_type for t in vs.tomograms}
    assert types == {"run003-sart", "run001-denoise"}


def test_overlay_features_glob(tree, root):
    feat = (
        tree
        / "krios1.processing"
        / "copick"
        / "25aug25a"
        / "run002"
        / "ExperimentRuns"
        / "25aug25a_Position_1"
        / "VoxelSpacing5.002"
        / "run003-dctf_sobel_features.zarr"
    )
    feat.mkdir(parents=True)

    run = root.get_run("25aug25a_Position_1")
    tomo = run.get_voxel_spacing(5.002).get_tomograms("run003-dctf")[0]
    features = tomo.features
    assert len(features) == 1
    assert features[0].feature_type == "sobel"
    assert features[0].read_only is False


# --------------------------------------------------------------------------------------
# Annotations: overlay routing and read-only modes
# --------------------------------------------------------------------------------------


def test_existing_overlay_picks_are_discovered(root):
    run = root.get_run("25aug25a_Position_1")
    picks = run.get_picks(object_name="ribosome")
    assert len(picks) == 1
    assert picks[0].user_id == "alice"
    assert picks[0].read_only is False


def test_picks_write_routed_to_owning_session_overlay(tree, root):
    run_a = root.get_run("25aug25a_Position_2")
    picks = run_a.new_picks("ribosome", session_id="7", user_id="tester")
    picks.store()
    expected_a = (
        tree
        / "krios1.processing"
        / "copick"
        / "25aug25a"
        / "run002"
        / "ExperimentRuns"
        / "25aug25a_Position_2"
        / "Picks"
        / "tester_7_ribosome.json"
    )
    assert expected_a.exists()

    run_b = root.get_run("25aug22b_L2_Series3A_Pos1.mrc")
    picks_b = run_b.new_picks("ribosome", session_id="7", user_id="tester")
    picks_b.store()
    expected_b = (
        tree
        / "krios1.processing"
        / "copick"
        / "25aug22b"
        / "run001"
        / "ExperimentRuns"
        / "25aug22b_L2_Series3A_Pos1.mrc"
        / "Picks"
        / "tester_7_ribosome.json"
    )
    assert expected_b.exists()


def test_overlay_http_mode_is_read_only(tree, server):
    config = _config_dict(tree, server, overlay_mode="http")
    root = copick.from_string(json.dumps(config))

    run = root.get_run("25aug25a_Position_1")
    assert run.overlay_read_only is True

    picks = run.get_picks(object_name="ribosome")
    assert len(picks) == 1
    assert picks[0].read_only is True
    with pytest.raises(PermissionError):
        picks[0].store()

    with pytest.raises(PermissionError):
        root.new_run("25aug25a_Position_50")


def test_new_run_with_unconfigured_prefix_raises(root):
    with pytest.raises(ValueError, match="does not belong to any configured"):
        root.new_run("othersession_Position_1")


def test_new_run_creates_overlay_directory(tree, root):
    run = root.new_run("25aug25a_Position_42")
    assert run is not None
    run_dir = tree / "krios1.processing" / "copick" / "25aug25a" / "run002" / "ExperimentRuns" / "25aug25a_Position_42"
    assert run_dir.is_dir()


def test_session_without_overlay_project_is_static_only(tree, server):
    config = _config_dict(tree, server)
    config["sessions"] = [
        {
            "name": "25aug25a",
            "tomograms": [{"proc_run": "run003", "recon_type": "dctf"}],
            "overlay_run": "run042",  # does not exist
        },
    ]
    root = copick.from_string(json.dumps(config))

    run = root.get_run("25aug25a_Position_1")
    assert run.fs_overlay is None
    assert run.overlay_read_only is True

    # Static tomograms are still served.
    tomo = run.get_voxel_spacing(5.002).get_tomograms("run003-dctf")[0]
    assert tomo.read_only is True

    # new_picks stores immediately, so the write rejection surfaces there.
    with pytest.raises(PermissionError):
        run.new_picks("ribosome", session_id="7", user_id="tester")


# --------------------------------------------------------------------------------------
# Objects
# --------------------------------------------------------------------------------------


def test_objects_config_only_without_project_overlay(root):
    obj = root.get_object("ribosome")
    assert obj.read_only is True
    assert obj.has_density_map() is False
    assert obj.zarr() is None


def test_objects_writable_with_project_overlay(tree, server, tmp_path):
    objects_root = tmp_path / "project_overlay"
    config = _config_dict(tree, server, overlay_root=f"local://{objects_root}")
    root = copick.from_string(json.dumps(config))

    obj = root.get_object("ribosome")
    assert obj.read_only is False
    assert obj.has_density_map() is False
    store = obj.zarr()
    assert store is not None
    assert store.read_only is False


def test_overlay_pickable_objects_deduplicated(root):
    objects = root.overlay_pickable_objects()
    by_name = {o.name: o for o in objects}
    assert set(by_name) == {"ribosome", "membrane"}
    # First session's definition wins over 25aug22b's conflicting one.
    assert by_name["ribosome"].label == 1


# --------------------------------------------------------------------------------------
# Static local mode
# --------------------------------------------------------------------------------------


def test_static_mode_local(tree, server):
    config = _config_dict(tree, server, static_mode="local")
    root = copick.from_string(json.dumps(config))

    run = root.get_run("25aug25a_Position_1")
    tomo = run.get_voxel_spacing(5.002).get_tomograms("run003-dctf")[0]
    data = tomo.numpy()
    expected = np.arange(8 * 8 * 8, dtype=np.float32).reshape(8, 8, 8)
    np.testing.assert_array_equal(data, expected)


# --------------------------------------------------------------------------------------
# Offline harness (no projects API)
# --------------------------------------------------------------------------------------


def test_offline_index_via_monkeypatched_fetch(tree, monkeypatch):
    ovl = tree / "krios1.processing" / "copick" / "25aug25a" / "run002"
    payload = {
        "sessions": [
            {
                "session": "25aug25a",
                "scope": "krios1",
                "overlay_run": "run002",
                "cluster_id": "test",
                "overlay_url": None,
                "overlay_posix": str(ovl),
                "read_only": False,
                "pickable_objects": [],
                "selections": [
                    {
                        "proc_run": "run003",
                        "recon_type": "dctf",
                        "positions": ["Position_1", "Position_2"],
                        "voxel_size": 5.002,
                        "data_url": "http://unused/krios1.processing/aretomo3/25aug25a/run003/vol001",
                        "data_posix": str(tree / "krios1.processing" / "aretomo3" / "25aug25a" / "run003" / "vol001"),
                    },
                ],
            },
        ],
    }
    monkeypatch.setattr(CopickRootEmbrella, "_fetch_index_data", lambda self: payload)

    config = CopickConfigEmbrella(
        name="offline",
        pickable_objects=[PickableObject(name="ribosome", is_particle=True, label=1, radius=150.0)],
        embrella_base_url="http://unused",
        clusters={"test": {"http_base": "http://unused/", "posix_base": str(tree)}},
        default_data_cluster="test",
        sessions=[
            {
                "name": "25aug25a",
                "tomograms": [{"proc_run": "run003", "recon_type": "dctf"}],
                "overlay_run": "run002",
            },
        ],
        overlay_mode="local",
        static_mode="local",
    )
    root = CopickRootEmbrella(config)

    assert set(root.index.runs) == {"25aug25a_Position_1", "25aug25a_Position_2"}
    tomo = root.get_run("25aug25a_Position_1").get_voxel_spacing(5.002).get_tomograms("run003-dctf")[0]
    np.testing.assert_array_equal(tomo.numpy(), np.arange(8 * 8 * 8, dtype=np.float32).reshape(8, 8, 8))
