"""Tests for the mlcroissant copick backend and its exporter."""

import json
import shutil
from pathlib import Path

import pytest


@pytest.fixture
def tiny_filesystem_project(tmp_path):
    """Build a minimal on-disk copick filesystem project for exporter tests."""
    proj = tmp_path / "proj"
    (proj / "ExperimentRuns" / "run_001" / "Picks").mkdir(parents=True)
    (proj / "ExperimentRuns" / "run_001" / "Meshes").mkdir(parents=True)

    pick = {
        "pickable_object_name": "ribosome",
        "user_id": "alice",
        "session_id": "42",
        "run_name": "run_001",
        "voxel_spacing": 10.0,
        "unit": "angstrom",
        "points": [{"location": {"x": 1.0, "y": 2.0, "z": 3.0}}],
        "trust_orientation": False,
    }
    (proj / "ExperimentRuns" / "run_001" / "Picks" / "alice_42_ribosome.json").write_text(json.dumps(pick))

    config = {
        "config_type": "filesystem",
        "name": "tiny",
        "version": "1.0.0",
        "user_id": "alice",
        "session_id": "42",
        "pickable_objects": [
            {"name": "ribosome", "is_particle": True, "label": 1, "color": [200, 100, 100, 255]},
        ],
        "overlay_root": f"local://{proj}",
        "overlay_fs_args": {"auto_mkdir": True},
    }
    (proj / "filesystem.json").write_text(json.dumps(config))
    return proj


def test_export_and_validate(tiny_filesystem_project):
    """export_croissant produces a validator-clean manifest + CSV sidecars."""
    import copick
    from copick.ops.croissant import export_croissant

    proj = tiny_filesystem_project
    root = copick.from_file(str(proj / "filesystem.json"))
    metadata_path = export_croissant(
        root,
        project_root=str(proj),
        base_url=f"file://{proj}",
        dataset_name="tiny-test",
    )
    assert Path(metadata_path).exists()

    # 8 CSVs present
    expected = {
        "runs.csv",
        "voxel_spacings.csv",
        "tomograms.csv",
        "features.csv",
        "picks.csv",
        "meshes.csv",
        "segmentations.csv",
        "objects.csv",
    }
    assert expected.issubset({p.name for p in (proj / "Croissant").iterdir()})

    # Validator: 0 errors
    import mlcroissant as mlc

    ds = mlc.Dataset(jsonld=metadata_path)
    errors = list(ds.metadata.ctx.issues.errors)
    assert errors == [], f"validator errors: {errors}"


def test_round_trip_read(tiny_filesystem_project):
    """Export then reload via from_croissant; walk returns same artifacts."""
    import copick
    from copick.ops.croissant import export_croissant

    proj = tiny_filesystem_project
    root = copick.from_file(str(proj / "filesystem.json"))
    export_croissant(root, project_root=str(proj), base_url=f"file://{proj}")

    root2 = copick.from_croissant(str(proj / "Croissant" / "metadata.json"))
    assert root2.config.name == "tiny"
    assert root2.mode == "A"
    assert [r.name for r in root2.runs] == ["run_001"]
    run = root2.get_run("run_001")
    assert len(run.picks) == 1
    p = run.picks[0]
    assert p.user_id == "alice"
    assert p.session_id == "42"
    assert p.pickable_object_name == "ribosome"
    # Points load correctly through the Croissant-resolved URL
    assert len(p.points) == 1
    assert p.points[0].location.x == 1.0


def test_mode_a_auto_sync(tiny_filesystem_project):
    """Writing a new pick auto-appends to picks.csv + refreshes metadata sha256."""
    import copick
    from copick.models import CopickLocation, CopickPoint
    from copick.ops.croissant import export_croissant

    proj = tiny_filesystem_project
    root = copick.from_file(str(proj / "filesystem.json"))
    export_croissant(root, project_root=str(proj), base_url=f"file://{proj}")

    r2 = copick.from_croissant(str(proj / "Croissant" / "metadata.json"))
    run = r2.get_run("run_001")
    np = run.new_picks(object_name="ribosome", user_id="bob", session_id="99")
    np.points = [CopickPoint(location=CopickLocation(x=10.0, y=20.0, z=30.0))]
    np.store()

    # The CSV now has 2 rows
    picks_csv = (proj / "Croissant" / "picks.csv").read_text().splitlines()
    assert len(picks_csv) == 3  # header + 2 rows
    assert any("bob,99,ribosome" in line for line in picks_csv)

    # metadata.json has updated sha256 for picks-csv
    doc = json.loads((proj / "Croissant" / "metadata.json").read_text())
    picks_fo = next(e for e in doc["distribution"] if e.get("@id") == "picks-csv")
    assert picks_fo["sha256"]  # non-empty

    # Fresh reload sees the new pick
    r3 = copick.from_croissant(str(proj / "Croissant" / "metadata.json"))
    run3 = r3.get_run("run_001")
    users = sorted({p.user_id for p in run3.picks})
    assert users == ["alice", "bob"]


def test_mode_a_batch_defers_commits(tiny_filesystem_project):
    """batch() context manager writes metadata.json once, not per call."""
    import copick
    from copick.models import CopickLocation, CopickPoint
    from copick.ops.croissant import export_croissant

    proj = tiny_filesystem_project
    root = copick.from_file(str(proj / "filesystem.json"))
    export_croissant(root, project_root=str(proj), base_url=f"file://{proj}")

    r = copick.from_croissant(str(proj / "Croissant" / "metadata.json"))
    run = r.get_run("run_001")

    # Track mtime of metadata.json
    md_path = proj / "Croissant" / "metadata.json"
    t_before = md_path.stat().st_mtime_ns

    import time

    time.sleep(0.01)  # mtime granularity

    with r.batch():
        for i in range(3):
            np = run.new_picks(object_name="ribosome", user_id=f"user{i}", session_id="1")
            np.points = [CopickPoint(location=CopickLocation(x=float(i), y=0.0, z=0.0))]
            np.store()
        # Still only initial metadata.json on disk (no commits yet)
        t_mid = md_path.stat().st_mtime_ns
        assert t_mid == t_before

    # After exiting batch, exactly one commit happened
    t_after = md_path.stat().st_mtime_ns
    assert t_after > t_before

    # All 4 picks present
    r2 = copick.from_croissant(str(md_path))
    run2 = r2.get_run("run_001")
    assert len(run2.picks) == 4


def test_base_url_override(tiny_filesystem_project, tmp_path):
    """croissant_base_url at load time relocates the reference base URL."""
    import copick
    from copick.ops.croissant import export_croissant

    proj = tiny_filesystem_project
    root = copick.from_file(str(proj / "filesystem.json"))
    export_croissant(root, project_root=str(proj), base_url="https://original.example.org/proj")

    # With default: absolute URL would be unreachable. Override to file:// tmp_path.
    # First copy data into a fresh location to simulate a move.
    new_loc = tmp_path / "moved"
    shutil.copytree(proj, new_loc)
    root2 = copick.from_croissant(
        str(new_loc / "Croissant" / "metadata.json"),
        croissant_base_url=f"file://{new_loc}",
    )
    run = root2.get_run("run_001")
    # Load the pick file: if the override didn't work, this FileNotFoundError
    p = run.picks[0]
    _ = p.points  # Forces _load() via base URL resolution
    assert p.points[0].location.x == 1.0


def test_mode_b_write_to_overlay(tiny_filesystem_project, tmp_path):
    """With overlay_root set, writes go to overlay and Croissant is untouched."""
    import copick
    from copick.models import CopickLocation, CopickPoint
    from copick.ops.croissant import export_croissant

    proj = tiny_filesystem_project
    root = copick.from_file(str(proj / "filesystem.json"))
    export_croissant(root, project_root=str(proj), base_url=f"file://{proj}")

    overlay = tmp_path / "overlay"
    overlay.mkdir()

    r = copick.from_croissant(
        str(proj / "Croissant" / "metadata.json"),
        overlay_root=f"local://{overlay}",
    )
    assert r.mode == "B"

    run = r.get_run("run_001")
    np = run.new_picks(object_name="ribosome", user_id="carol", session_id="7")
    np.points = [CopickPoint(location=CopickLocation(x=5.0, y=5.0, z=5.0))]
    np.store()

    # Croissant is unchanged
    picks_csv_rows = (proj / "Croissant" / "picks.csv").read_text().splitlines()
    assert len(picks_csv_rows) == 2  # header + 1 original row

    # Overlay has the new pick
    expected_overlay = overlay / "ExperimentRuns" / "run_001" / "Picks" / "carol_7_ribosome.json"
    assert expected_overlay.exists()


# -----------------------------------------------------------------------------
# Subset / filter-export tests
# -----------------------------------------------------------------------------


@pytest.fixture
def multi_run_filesystem_project(tmp_path):
    """A fixture with 2 runs × 2 voxel spacings × 2 tomo types + multiple picks.

    Used to exercise subset-filter behavior on runs / tomograms / picks /
    segmentations.
    """
    proj = tmp_path / "proj"

    pickable_objects = [
        {"name": "ribosome", "is_particle": True, "label": 1, "color": [200, 100, 100, 255]},
        {"name": "proteasome", "is_particle": True, "label": 2, "color": [100, 200, 100, 255]},
        {"name": "membrane", "is_particle": False, "label": 3, "color": [100, 100, 200, 255]},
    ]

    # Scaffold run directories + a handful of pick files
    for run_name, users in [
        ("TS_001", [("alice", "1", "ribosome"), ("alice", "1", "proteasome"), ("bob", "2", "ribosome")]),
        ("TS_002", [("alice", "1", "ribosome")]),
    ]:
        (proj / "ExperimentRuns" / run_name / "Picks").mkdir(parents=True)
        for user, session, obj in users:
            (proj / "ExperimentRuns" / run_name / "Picks" / f"{user}_{session}_{obj}.json").write_text(
                json.dumps(
                    {
                        "pickable_object_name": obj,
                        "user_id": user,
                        "session_id": session,
                        "run_name": run_name,
                        "voxel_spacing": 10.0,
                        "unit": "angstrom",
                        "points": [{"location": {"x": 1.0, "y": 2.0, "z": 3.0}}],
                        "trust_orientation": False,
                    },
                ),
            )

    config = {
        "config_type": "filesystem",
        "name": "multi-run",
        "version": "1.0.0",
        "user_id": "alice",
        "session_id": "1",
        "pickable_objects": pickable_objects,
        "overlay_root": f"local://{proj}",
        "overlay_fs_args": {"auto_mkdir": True},
    }
    (proj / "filesystem.json").write_text(json.dumps(config))
    return proj


def _read_csv(csv_path):
    import csv as _csv

    with open(csv_path) as f:
        return list(_csv.DictReader(f))


def test_export_filter_runs(multi_run_filesystem_project):
    """runs filter restricts every per-run CSV to the named subset."""
    import copick
    from copick.ops.croissant import export_croissant

    proj = multi_run_filesystem_project
    root = copick.from_file(str(proj / "filesystem.json"))
    export_croissant(
        root,
        project_root=str(proj),
        base_url=f"file://{proj}",
        runs=["TS_001"],
    )

    runs_rows = _read_csv(proj / "Croissant" / "runs.csv")
    assert [r["name"] for r in runs_rows] == ["TS_001"]

    picks_rows = _read_csv(proj / "Croissant" / "picks.csv")
    assert all(r["run"] == "TS_001" for r in picks_rows)
    assert len(picks_rows) == 3  # 3 picks in TS_001


def test_export_filter_picks_uri(multi_run_filesystem_project):
    """picks URI filter restricts only picks.csv; runs/voxel_spacings unaffected."""
    import copick
    from copick.ops.croissant import export_croissant

    proj = multi_run_filesystem_project
    root = copick.from_file(str(proj / "filesystem.json"))
    export_croissant(
        root,
        project_root=str(proj),
        base_url=f"file://{proj}",
        picks=["ribosome:*/*"],
    )

    picks_rows = _read_csv(proj / "Croissant" / "picks.csv")
    assert all(r["object_name"] == "ribosome" for r in picks_rows)
    assert {(r["run"], r["user_id"]) for r in picks_rows} == {
        ("TS_001", "alice"),
        ("TS_001", "bob"),
        ("TS_002", "alice"),
    }
    runs_rows = _read_csv(proj / "Croissant" / "runs.csv")
    assert {r["name"] for r in runs_rows} == {"TS_001", "TS_002"}


def test_export_filter_combined(multi_run_filesystem_project):
    """runs + picks URI filters intersect as expected."""
    import copick
    from copick.ops.croissant import export_croissant

    proj = multi_run_filesystem_project
    root = copick.from_file(str(proj / "filesystem.json"))
    export_croissant(
        root,
        project_root=str(proj),
        base_url=f"file://{proj}",
        runs=["TS_001"],
        picks=["ribosome:alice/*"],
    )

    runs_rows = _read_csv(proj / "Croissant" / "runs.csv")
    assert [r["name"] for r in runs_rows] == ["TS_001"]

    picks_rows = _read_csv(proj / "Croissant" / "picks.csv")
    assert len(picks_rows) == 1
    assert picks_rows[0]["user_id"] == "alice"
    assert picks_rows[0]["object_name"] == "ribosome"


def test_export_filter_nonexistent_run(multi_run_filesystem_project):
    """Non-existent run names are silently skipped; CSVs come out empty."""
    import copick
    from copick.ops.croissant import export_croissant

    proj = multi_run_filesystem_project
    root = copick.from_file(str(proj / "filesystem.json"))
    metadata_path = export_croissant(
        root,
        project_root=str(proj),
        base_url=f"file://{proj}",
        runs=["TS_nonexistent"],
    )
    # Validator still accepts the manifest
    import mlcroissant as mlc

    ds = mlc.Dataset(jsonld=metadata_path)
    assert list(ds.metadata.ctx.issues.errors) == []

    runs_rows = _read_csv(proj / "Croissant" / "runs.csv")
    assert runs_rows == []


def test_export_filter_objects(multi_run_filesystem_project):
    """objects filter restricts only the objects CSV; config pickable_objects stays complete."""
    import copick
    from copick.ops.croissant import export_croissant

    proj = multi_run_filesystem_project
    root = copick.from_file(str(proj / "filesystem.json"))
    # The sample has no actual density-map zarrs under Objects/, so the
    # objects CSV is expected to be empty whether or not filter is given.
    # Here we verify the flag plumbing reaches the export and the overall
    # manifest stays valid — picks for proteasome remain emitted even when
    # objects=["ribosome"] is passed (filter applies to density maps only).
    metadata_path = export_croissant(
        root,
        project_root=str(proj),
        base_url=f"file://{proj}",
        objects=["ribosome"],
    )
    import mlcroissant as mlc

    ds = mlc.Dataset(jsonld=metadata_path)
    assert list(ds.metadata.ctx.issues.errors) == []

    # Proteasome picks should still appear — --objects doesn't filter picks.
    picks_rows = _read_csv(proj / "Croissant" / "picks.csv")
    assert any(r["object_name"] == "proteasome" for r in picks_rows)


def test_export_filter_validator_clean(multi_run_filesystem_project):
    """Every subset export still round-trips through the Croissant validator."""
    import copick
    import mlcroissant as mlc
    from copick.ops.croissant import export_croissant

    proj = multi_run_filesystem_project
    root = copick.from_file(str(proj / "filesystem.json"))
    metadata_path = export_croissant(
        root,
        project_root=str(proj),
        base_url=f"file://{proj}",
        runs=["TS_001"],
        picks=["ribosome:*/*", "proteasome:alice/*"],
    )
    ds = mlc.Dataset(jsonld=metadata_path)
    assert list(ds.metadata.ctx.issues.errors) == []


def test_export_filter_cli(multi_run_filesystem_project):
    """End-to-end CLI invocation with --runs + --picks filters."""
    from click.testing import CliRunner
    from copick.cli.config import config

    proj = multi_run_filesystem_project
    runner = CliRunner()
    r = runner.invoke(
        config,
        [
            "export-croissant",
            "--config",
            str(proj / "filesystem.json"),
            "--project-root",
            str(proj),
            "--base-url",
            f"file://{proj}",
            "--runs",
            "TS_001",
            "--picks",
            "ribosome:*/*",
        ],
    )
    assert r.exit_code == 0, r.output

    runs_rows = _read_csv(proj / "Croissant" / "runs.csv")
    assert [r["name"] for r in runs_rows] == ["TS_001"]

    picks_rows = _read_csv(proj / "Croissant" / "picks.csv")
    assert all(r["object_name"] == "ribosome" and r["run"] == "TS_001" for r in picks_rows)
    assert len(picks_rows) == 2  # alice + bob, both ribosome in TS_001
