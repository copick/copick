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


# -----------------------------------------------------------------------------
# Reshape tests (remap + templates) — filesystem source, no CDP required.
# -----------------------------------------------------------------------------


def test_export_object_name_map_rewrites_csv(multi_run_filesystem_project):
    """object_name_map rewrites picks.csv and copick:config.pickable_objects."""
    import copick
    from copick.ops.croissant import export_croissant

    proj = multi_run_filesystem_project
    root = copick.from_file(str(proj / "filesystem.json"))
    export_croissant(
        root,
        project_root=str(proj),
        base_url=f"file://{proj}",
        object_name_map={"ribosome": "rib", "proteasome": "proteasome"},
    )

    picks_rows = _read_csv(proj / "Croissant" / "picks.csv")
    names = {r["object_name"] for r in picks_rows}
    assert "rib" in names
    assert "ribosome" not in names  # all ribosome entries renamed
    # portal_object_name should stay blank for non-CDP sources
    assert all(r.get("portal_object_name", "") == "" for r in picks_rows)

    doc = json.loads((proj / "Croissant" / "metadata.json").read_text())
    cfg = doc["copick:config"]
    po_names = {po["name"] for po in cfg["pickable_objects"]}
    assert "rib" in po_names
    assert "ribosome" not in po_names
    rib_entry = next(po for po in cfg["pickable_objects"] if po["name"] == "rib")
    assert rib_entry.get("metadata", {}).get("portal_original_name") == "ribosome"


def test_export_session_id_template_non_cdp_raises(tiny_filesystem_project):
    """Non-CDP + session_id_template must raise ValueError at entry."""
    import copick
    from copick.ops.croissant import export_croissant

    proj = tiny_filesystem_project
    root = copick.from_file(str(proj / "filesystem.json"))
    with pytest.raises(ValueError, match="CryoET Data Portal source"):
        export_croissant(
            root,
            project_root=str(proj),
            base_url=f"file://{proj}",
            session_id_template="{method_type}",
        )


def test_export_cdp_only_flags_non_cdp_raise(tiny_filesystem_project):
    """All CDP-only flags raise on non-CDP sources."""
    import copick
    from copick.ops.croissant import export_croissant

    proj = tiny_filesystem_project
    root = copick.from_file(str(proj / "filesystem.json"))
    with pytest.raises(ValueError, match="CryoET Data Portal source"):
        export_croissant(
            root,
            project_root=str(proj),
            base_url=f"file://{proj}",
            picks_portal_meta={"ground_truth_status": "true"},
        )


# -----------------------------------------------------------------------------
# --force behaviour
# -----------------------------------------------------------------------------


def test_export_refuses_existing_without_force(tiny_filesystem_project):
    """Running export twice without --force raises FileExistsError."""
    import copick
    from copick.ops.croissant import export_croissant

    proj = tiny_filesystem_project
    root = copick.from_file(str(proj / "filesystem.json"))
    export_croissant(root, project_root=str(proj), base_url=f"file://{proj}")
    with pytest.raises(FileExistsError, match="already exists"):
        export_croissant(root, project_root=str(proj), base_url=f"file://{proj}")


def test_export_force_overwrites(tiny_filesystem_project):
    """--force bypasses the FileExistsError guard."""
    import copick
    from copick.ops.croissant import export_croissant

    proj = tiny_filesystem_project
    root = copick.from_file(str(proj / "filesystem.json"))
    export_croissant(root, project_root=str(proj), base_url=f"file://{proj}")
    # No exception with force=True
    export_croissant(
        root,
        project_root=str(proj),
        base_url=f"file://{proj}",
        force=True,
        dataset_name="overwritten",
    )
    doc = json.loads((proj / "Croissant" / "metadata.json").read_text())
    assert doc["name"] == "overwritten"


# -----------------------------------------------------------------------------
# Append tests — filesystem source, no CDP required.
# -----------------------------------------------------------------------------


def test_append_adds_new_picks(multi_run_filesystem_project):
    """Export a subset, then append a different subset; final CSV unions both."""
    import copick
    from copick.ops.croissant import append_croissant, export_croissant

    proj = multi_run_filesystem_project
    root = copick.from_file(str(proj / "filesystem.json"))

    # Step 1: export ribosome picks only
    export_croissant(
        root,
        project_root=str(proj),
        base_url=f"file://{proj}",
        picks=["ribosome:*/*"],
    )
    picks_rows = _read_csv(proj / "Croissant" / "picks.csv")
    assert {r["object_name"] for r in picks_rows} == {"ribosome"}

    # Step 2: append proteasome picks
    append_croissant(
        str(proj / "Croissant" / "metadata.json"),
        root,
        picks=["proteasome:*/*"],
    )
    picks_rows = _read_csv(proj / "Croissant" / "picks.csv")
    assert {r["object_name"] for r in picks_rows} == {"ribosome", "proteasome"}


def test_append_validator_clean(multi_run_filesystem_project):
    """After append, Croissant still validates with 0 errors."""
    import copick
    import mlcroissant as mlc
    from copick.ops.croissant import append_croissant, export_croissant

    proj = multi_run_filesystem_project
    root = copick.from_file(str(proj / "filesystem.json"))
    export_croissant(
        root,
        project_root=str(proj),
        base_url=f"file://{proj}",
        picks=["ribosome:*/*"],
    )
    metadata_path = append_croissant(
        str(proj / "Croissant" / "metadata.json"),
        root,
        picks=["proteasome:*/*"],
    )

    ds = mlc.Dataset(jsonld=metadata_path)
    errors = list(ds.metadata.ctx.issues.errors)
    assert errors == [], f"validator errors after append: {errors}"


def test_append_replaces_on_key_collision(multi_run_filesystem_project):
    """Re-append the same row with a transformed field; final row reflects last append."""
    import copick
    from copick.ops.croissant import append_croissant, export_croissant

    proj = multi_run_filesystem_project
    root = copick.from_file(str(proj / "filesystem.json"))
    export_croissant(
        root,
        project_root=str(proj),
        base_url=f"file://{proj}",
        picks=["ribosome:*/*"],
    )
    picks_before = _read_csv(proj / "Croissant" / "picks.csv")
    n_before = len(picks_before)

    # Re-append the same rows — should replace in place (same count, no duplication).
    append_croissant(
        str(proj / "Croissant" / "metadata.json"),
        root,
        picks=["ribosome:*/*"],
    )
    picks_after = _read_csv(proj / "Croissant" / "picks.csv")
    assert len(picks_after) == n_before


def test_append_unions_pickable_objects(tmp_path):
    """Appending from a source with extra pickable objects grows dest config."""
    import copick
    from copick.ops.croissant import append_croissant, export_croissant

    # Destination project: just ribosome.
    dest = tmp_path / "dest"
    (dest / "ExperimentRuns" / "run_001" / "Picks").mkdir(parents=True)
    (dest / "filesystem.json").write_text(
        json.dumps(
            {
                "config_type": "filesystem",
                "name": "dest",
                "version": "1.0.0",
                "user_id": "u",
                "session_id": "s",
                "pickable_objects": [
                    {"name": "ribosome", "is_particle": True, "label": 1, "color": [200, 100, 100, 255]},
                ],
                "overlay_root": f"local://{dest}",
                "overlay_fs_args": {"auto_mkdir": True},
            },
        ),
    )
    dest_root = copick.from_file(str(dest / "filesystem.json"))
    export_croissant(dest_root, project_root=str(dest), base_url=f"file://{dest}")

    # Source project: has ribosome + proteasome.
    src = tmp_path / "src"
    (src / "ExperimentRuns" / "run_001" / "Picks").mkdir(parents=True)
    (src / "filesystem.json").write_text(
        json.dumps(
            {
                "config_type": "filesystem",
                "name": "src",
                "version": "1.0.0",
                "user_id": "u",
                "session_id": "s",
                "pickable_objects": [
                    {"name": "ribosome", "is_particle": True, "label": 1, "color": [200, 100, 100, 255]},
                    {"name": "proteasome", "is_particle": True, "label": 2, "color": [100, 200, 100, 255]},
                ],
                "overlay_root": f"local://{src}",
                "overlay_fs_args": {"auto_mkdir": True},
            },
        ),
    )
    src_root = copick.from_file(str(src / "filesystem.json"))

    append_croissant(str(dest / "Croissant" / "metadata.json"), src_root)

    doc = json.loads((dest / "Croissant" / "metadata.json").read_text())
    names = {po["name"] for po in doc["copick:config"]["pickable_objects"]}
    assert names == {"ribosome", "proteasome"}


def test_append_cli(multi_run_filesystem_project):
    """End-to-end: copick config append-croissant ... --picks proteasome:*/*."""
    from click.testing import CliRunner
    from copick.cli.config import config

    proj = multi_run_filesystem_project
    runner = CliRunner()

    # Initial export restricted to ribosome.
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
            "--picks",
            "ribosome:*/*",
        ],
    )
    assert r.exit_code == 0, r.output

    # Append proteasome picks.
    r = runner.invoke(
        config,
        [
            "append-croissant",
            "--croissant",
            str(proj / "Croissant" / "metadata.json"),
            "--source-config",
            str(proj / "filesystem.json"),
            "--picks",
            "proteasome:*/*",
        ],
    )
    assert r.exit_code == 0, r.output

    picks_rows = _read_csv(proj / "Croissant" / "picks.csv")
    assert {r["object_name"] for r in picks_rows} == {"ribosome", "proteasome"}


def test_append_cli_requires_source(multi_run_filesystem_project):
    """append-croissant without --source-config or --source-dataset-ids errors."""
    from click.testing import CliRunner
    from copick.cli.config import config

    proj = multi_run_filesystem_project
    runner = CliRunner()
    # Pre-create a Croissant so the --croissant path exists.
    import copick
    from copick.ops.croissant import export_croissant

    export_croissant(
        copick.from_file(str(proj / "filesystem.json")),
        project_root=str(proj),
        base_url=f"file://{proj}",
    )
    r = runner.invoke(
        config,
        [
            "append-croissant",
            "--croissant",
            str(proj / "Croissant" / "metadata.json"),
        ],
    )
    assert r.exit_code != 0
    assert "source-config" in r.output or "source-dataset-ids" in r.output


def test_append_url_absolutized(multi_run_filesystem_project):
    """Appended rows carry absolute URLs so the destination is self-sufficient."""
    import copick
    from copick.ops.croissant import append_croissant, export_croissant

    proj = multi_run_filesystem_project
    root = copick.from_file(str(proj / "filesystem.json"))
    export_croissant(
        root,
        project_root=str(proj),
        base_url=f"file://{proj}",
        picks=["ribosome:*/*"],
    )
    append_croissant(
        str(proj / "Croissant" / "metadata.json"),
        root,
        picks=["proteasome:*/*"],
    )
    picks_rows = _read_csv(proj / "Croissant" / "picks.csv")
    # Newly appended proteasome row should have an absolute URL (scheme or /-rooted).
    proteasome_row = next(r for r in picks_rows if r["object_name"] == "proteasome")
    u = proteasome_row["url"]
    assert "://" in u or u.startswith("/"), f"expected absolute URL, got {u!r}"


# -----------------------------------------------------------------------------
# Splits tests
# -----------------------------------------------------------------------------


def test_export_with_splits(multi_run_filesystem_project):
    """Export with --split ... populates runs.csv and emits splits RecordSet."""
    import copick
    from copick.ops.croissant import export_croissant

    proj = multi_run_filesystem_project
    root = copick.from_file(str(proj / "filesystem.json"))
    export_croissant(
        root,
        project_root=str(proj),
        base_url=f"file://{proj}",
        splits={"train": ["TS_001"], "val": ["TS_002"]},
    )

    runs_rows = _read_csv(proj / "Croissant" / "runs.csv")
    by_name = {r["name"]: r for r in runs_rows}
    assert by_name["TS_001"]["split"] == "train"
    assert by_name["TS_002"]["split"] == "val"

    doc = json.loads((proj / "Croissant" / "metadata.json").read_text())
    splits_rs = next(rs for rs in doc["recordSet"] if rs["@id"] == "copick/splits")
    # RecordSet is keyed on name so consumers can navigate via `references`.
    assert splits_rs["key"] == {"@id": "copick/splits/name"}
    names_in_data = {d["copick/splits/name"] for d in splits_rs["data"]}
    assert names_in_data == {"train", "val"}
    train_entry = next(d for d in splits_rs["data"] if d["copick/splits/name"] == "train")
    assert train_entry["copick/splits/url"] == "https://mlcommons.org/definitions/training_split"
    val_entry = next(d for d in splits_rs["data"] if d["copick/splits/name"] == "val")
    assert val_entry["copick/splits/url"] == "https://mlcommons.org/definitions/validation_split"

    # runs/split field should have references into copick/splits/name
    runs_rs = next(rs for rs in doc["recordSet"] if rs["@id"] == "copick/runs")
    split_field = next(f for f in runs_rs["field"] if f["@id"] == "copick/runs/split")
    assert split_field["references"] == {"field": {"@id": "copick/splits/name"}}


def test_export_splits_custom_name_has_no_url(multi_run_filesystem_project):
    """Non-standard split names emit without a canonical URI."""
    import copick
    from copick.ops.croissant import export_croissant

    proj = multi_run_filesystem_project
    root = copick.from_file(str(proj / "filesystem.json"))
    export_croissant(
        root,
        project_root=str(proj),
        base_url=f"file://{proj}",
        splits={"holdout": ["TS_001"]},
    )
    doc = json.loads((proj / "Croissant" / "metadata.json").read_text())
    splits_rs = next(rs for rs in doc["recordSet"] if rs["@id"] == "copick/splits")
    holdout_entry = next(d for d in splits_rs["data"] if d["copick/splits/name"] == "holdout")
    # Validator requires every column in every row; custom splits get empty url.
    assert holdout_entry.get("copick/splits/url", "") == ""


def test_export_splits_unknown_run_raises(multi_run_filesystem_project):
    """Listing a run that doesn't exist raises ValueError before writing."""
    import copick
    from copick.ops.croissant import export_croissant

    proj = multi_run_filesystem_project
    root = copick.from_file(str(proj / "filesystem.json"))
    with pytest.raises(ValueError, match="unknown runs"):
        export_croissant(
            root,
            project_root=str(proj),
            base_url=f"file://{proj}",
            splits={"train": ["TS_does_not_exist"]},
        )


def test_export_no_splits_omits_splits_recordset(tiny_filesystem_project):
    """When no splits are provided, the splits RecordSet isn't emitted and runs/split has no references."""
    import copick
    from copick.ops.croissant import export_croissant

    proj = tiny_filesystem_project
    root = copick.from_file(str(proj / "filesystem.json"))
    export_croissant(root, project_root=str(proj), base_url=f"file://{proj}")
    doc = json.loads((proj / "Croissant" / "metadata.json").read_text())
    ids = {rs["@id"] for rs in doc["recordSet"]}
    assert "copick/splits" not in ids

    runs_rs = next(rs for rs in doc["recordSet"] if rs["@id"] == "copick/runs")
    split_field = next(f for f in runs_rs["field"] if f["@id"] == "copick/runs/split")
    assert "references" not in split_field


def test_run_split_property_round_trip(multi_run_filesystem_project):
    """Setting run.split persists to the CSV and survives refresh."""
    import copick
    from copick.ops.croissant import export_croissant

    proj = multi_run_filesystem_project
    root = copick.from_file(str(proj / "filesystem.json"))
    export_croissant(root, project_root=str(proj), base_url=f"file://{proj}")

    r = copick.from_croissant(str(proj / "Croissant" / "metadata.json"))
    run = r.get_run("TS_001")
    assert run.split is None
    run.split = "train"
    assert run.split == "train"

    # Reload from disk
    r2 = copick.from_croissant(str(proj / "Croissant" / "metadata.json"))
    assert r2.get_run("TS_001").split == "train"
    assert r2.splits == {"train": ["TS_001"]}


def test_root_set_splits_bulk(multi_run_filesystem_project):
    """root.set_splits does one commit covering all assignments."""
    import copick
    from copick.ops.croissant import export_croissant

    proj = multi_run_filesystem_project
    root = copick.from_file(str(proj / "filesystem.json"))
    export_croissant(root, project_root=str(proj), base_url=f"file://{proj}")

    md_path = proj / "Croissant" / "metadata.json"
    r = copick.from_croissant(str(md_path))
    t_before = md_path.stat().st_mtime_ns

    import time

    time.sleep(0.01)
    r.set_splits({"train": ["TS_001"], "val": ["TS_002"]})
    t_after = md_path.stat().st_mtime_ns
    assert t_after > t_before
    assert r.splits == {"train": ["TS_001"], "val": ["TS_002"]}

    # clear_existing wipes the previous state
    r.set_splits({"test": ["TS_001"]}, clear_existing=True)
    assert r.splits == {"test": ["TS_001"]}


def test_root_clear_splits(multi_run_filesystem_project):
    """clear_splits removes split assignments."""
    import copick
    from copick.ops.croissant import export_croissant

    proj = multi_run_filesystem_project
    root = copick.from_file(str(proj / "filesystem.json"))
    export_croissant(
        root,
        project_root=str(proj),
        base_url=f"file://{proj}",
        splits={"train": ["TS_001"], "val": ["TS_002"]},
    )
    r = copick.from_croissant(str(proj / "Croissant" / "metadata.json"))
    r.clear_splits(["TS_001"])
    assert r.splits == {"val": ["TS_002"]}
    r.clear_splits()
    assert r.splits == {}


def test_mode_b_split_assignment_raises(multi_run_filesystem_project, tmp_path):
    """Mode B refuses split assignment (read-only Croissant)."""
    import copick
    from copick.ops.croissant import export_croissant

    proj = multi_run_filesystem_project
    root = copick.from_file(str(proj / "filesystem.json"))
    export_croissant(root, project_root=str(proj), base_url=f"file://{proj}")

    overlay = tmp_path / "overlay"
    overlay.mkdir()
    r = copick.from_croissant(
        str(proj / "Croissant" / "metadata.json"),
        overlay_root=f"local://{overlay}",
    )
    assert r.mode == "B"
    run = r.get_run("TS_001")
    with pytest.raises(PermissionError, match="read-only"):
        run.split = "train"
    with pytest.raises(PermissionError, match="read-only"):
        r.set_splits({"train": ["TS_001"]})


def test_append_with_splits_preserves_prior(multi_run_filesystem_project):
    """Appending without --split preserves any previously-set split for that run."""
    import copick
    from copick.ops.croissant import append_croissant, export_croissant

    proj = multi_run_filesystem_project
    root = copick.from_file(str(proj / "filesystem.json"))
    export_croissant(
        root,
        project_root=str(proj),
        base_url=f"file://{proj}",
        splits={"train": ["TS_001"], "val": ["TS_002"]},
    )
    # Append a data-only slice (no --split); the existing splits must survive.
    append_croissant(
        str(proj / "Croissant" / "metadata.json"),
        root,
        picks=["proteasome:*/*"],
    )
    runs_rows = _read_csv(proj / "Croissant" / "runs.csv")
    by_name = {r["name"]: r for r in runs_rows}
    assert by_name["TS_001"]["split"] == "train"
    assert by_name["TS_002"]["split"] == "val"


def test_append_with_splits_override(multi_run_filesystem_project):
    """Explicit --split in append wins over existing destination split."""
    import copick
    from copick.ops.croissant import append_croissant, export_croissant

    proj = multi_run_filesystem_project
    root = copick.from_file(str(proj / "filesystem.json"))
    export_croissant(
        root,
        project_root=str(proj),
        base_url=f"file://{proj}",
        splits={"train": ["TS_001"]},
    )
    append_croissant(
        str(proj / "Croissant" / "metadata.json"),
        root,
        splits={"test": ["TS_001"]},
    )
    runs_rows = _read_csv(proj / "Croissant" / "runs.csv")
    by_name = {r["name"]: r for r in runs_rows}
    assert by_name["TS_001"]["split"] == "test"


def test_set_splits_cli(multi_run_filesystem_project):
    """End-to-end `copick config set-splits` invocation."""
    import copick
    from click.testing import CliRunner
    from copick.cli.config import config
    from copick.ops.croissant import export_croissant

    proj = multi_run_filesystem_project
    root = copick.from_file(str(proj / "filesystem.json"))
    export_croissant(root, project_root=str(proj), base_url=f"file://{proj}")

    runner = CliRunner()
    r = runner.invoke(
        config,
        [
            "set-splits",
            "--croissant",
            str(proj / "Croissant" / "metadata.json"),
            "--split",
            "train=TS_001",
            "--split",
            "val=TS_002",
        ],
    )
    assert r.exit_code == 0, r.output

    r2 = copick.from_croissant(str(proj / "Croissant" / "metadata.json"))
    assert r2.splits == {"train": ["TS_001"], "val": ["TS_002"]}

    # Now unassign TS_002 and clear-all+reassign
    r = runner.invoke(
        config,
        [
            "set-splits",
            "--croissant",
            str(proj / "Croissant" / "metadata.json"),
            "--clear-all",
            "--split",
            "test=TS_001,TS_002",
        ],
    )
    assert r.exit_code == 0, r.output
    r3 = copick.from_croissant(str(proj / "Croissant" / "metadata.json"))
    assert r3.splits == {"test": ["TS_001", "TS_002"]}


def test_set_splits_cli_noop_errors(multi_run_filesystem_project):
    """set-splits with no options errors out with a helpful message."""
    import copick
    from click.testing import CliRunner
    from copick.cli.config import config
    from copick.ops.croissant import export_croissant

    proj = multi_run_filesystem_project
    root = copick.from_file(str(proj / "filesystem.json"))
    export_croissant(root, project_root=str(proj), base_url=f"file://{proj}")

    runner = CliRunner()
    r = runner.invoke(
        config,
        ["set-splits", "--croissant", str(proj / "Croissant" / "metadata.json")],
    )
    assert r.exit_code != 0
    assert "Nothing to do" in r.output


def test_splits_from_file(multi_run_filesystem_project, tmp_path):
    """--splits-file CSV provides the mapping."""
    import copick

    proj = multi_run_filesystem_project
    copick.from_file(str(proj / "filesystem.json"))

    splits_csv = tmp_path / "splits.csv"
    splits_csv.write_text("split,run\ntrain,TS_001\nval,TS_002\n")

    from click.testing import CliRunner
    from copick.cli.config import config

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
            "--splits-file",
            str(splits_csv),
        ],
    )
    assert r.exit_code == 0, r.output

    r2 = copick.from_croissant(str(proj / "Croissant" / "metadata.json"))
    assert r2.splits == {"train": ["TS_001"], "val": ["TS_002"]}


def test_splits_validator_clean(multi_run_filesystem_project):
    """Splits-enabled Croissants pass the mlcroissant validator cleanly."""
    import copick
    import mlcroissant as mlc
    from copick.ops.croissant import export_croissant

    proj = multi_run_filesystem_project
    root = copick.from_file(str(proj / "filesystem.json"))
    metadata_path = export_croissant(
        root,
        project_root=str(proj),
        base_url=f"file://{proj}",
        splits={"train": ["TS_001"], "val": ["TS_002"]},
    )
    ds = mlc.Dataset(jsonld=metadata_path)
    assert list(ds.metadata.ctx.issues.errors) == []


def test_splits_conflict_raises(multi_run_filesystem_project):
    """A run assigned to two different splits raises ValueError."""
    import copick
    from copick.ops.croissant import export_croissant

    proj = multi_run_filesystem_project
    root = copick.from_file(str(proj / "filesystem.json"))
    with pytest.raises(ValueError, match="two splits"):
        export_croissant(
            root,
            project_root=str(proj),
            base_url=f"file://{proj}",
            splits={"train": ["TS_001"], "val": ["TS_001"]},
        )


def test_run_split_is_none_for_filesystem_backend(tiny_filesystem_project):
    """Non-mlcroissant backends return None for run.split."""
    import copick

    proj = tiny_filesystem_project
    root = copick.from_file(str(proj / "filesystem.json"))
    run = root.get_run("run_001")
    assert run.split is None


# -----------------------------------------------------------------------------
# fs_args propagation: consumer config must carry connection args so data URLs
# resolve, but the Croissant manifest itself stays credential-free.
# -----------------------------------------------------------------------------


def test_config_static_fs_args_round_trip(tiny_filesystem_project, monkeypatch):
    """static_fs_args on the mlcroissant config reach _fs_for_url via resolve_url."""
    import copick
    from copick.impl import mlcroissant as mlc_mod
    from copick.ops.croissant import export_croissant

    proj = tiny_filesystem_project
    src = copick.from_file(str(proj / "filesystem.json"))
    metadata_path = export_croissant(
        src,
        project_root=str(proj),
        base_url=f"file://{proj}",
    )

    cfg = {
        "config_type": "mlcroissant",
        "pickable_objects": [],
        "croissant_url": str(metadata_path),
        "static_fs_args": {"host": "example.com", "port": 22},
    }
    config_path = proj / "mlc_with_static_args.json"
    config_path.write_text(json.dumps(cfg))

    root = copick.from_file(str(config_path))
    assert root.index.static_fs_args == {"host": "example.com", "port": 22}

    captured = {}
    real_fs_for_url = mlc_mod._fs_for_url

    def capturing(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = dict(kwargs)
        return real_fs_for_url(url, **{k: v for k, v in kwargs.items() if k not in ("host", "port")})

    monkeypatch.setattr(mlc_mod, "_fs_for_url", capturing)

    root.index.resolve_url("ExperimentRuns/run_001/Picks/alice_42_ribosome.json")
    assert captured["kwargs"].get("host") == "example.com"
    assert captured["kwargs"].get("port") == 22


def test_cli_emit_config_propagates_source_fs_args(tmp_path):
    """Source overlay_fs_args flow into the emitted config; the Croissant stays clean."""
    from click.testing import CliRunner
    from copick.cli.config import config as config_cli

    proj = tmp_path / "proj"
    (proj / "ExperimentRuns" / "run_001" / "Picks").mkdir(parents=True)
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
    (proj / "ExperimentRuns" / "run_001" / "Picks" / "alice_42_ribosome.json").write_text(
        json.dumps(pick),
    )
    src_cfg = {
        "config_type": "filesystem",
        "name": "fs-args-src",
        "version": "1.0.0",
        "pickable_objects": [
            {"name": "ribosome", "is_particle": True, "label": 1, "color": [200, 100, 100, 255]},
        ],
        "overlay_root": f"local://{proj}",
        "overlay_fs_args": {"host": "example.com", "port": 2222},
    }
    src_path = proj / "filesystem.json"
    src_path.write_text(json.dumps(src_cfg))

    emitted = tmp_path / "emitted.json"

    runner = CliRunner()
    r = runner.invoke(
        config_cli,
        [
            "export-croissant",
            "--config",
            str(src_path),
            "--project-root",
            str(proj),
            "--base-url",
            f"file://{proj}",
            "--emit-config",
            str(emitted),
        ],
    )
    assert r.exit_code == 0, r.output

    emitted_cfg = json.loads(emitted.read_text())
    assert emitted_cfg["static_fs_args"] == {"host": "example.com", "port": 2222}
    assert emitted_cfg["croissant_fs_args"] == {}

    # Credential-leak guard: the Croissant manifest must not carry fs_args.
    manifest = json.loads((proj / "Croissant" / "metadata.json").read_text())

    def _walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                assert "fs_args" not in k.lower(), f"leaked fs-args key: {k}"
                assert not (isinstance(v, dict) and "host" in v and "port" in v), f"leaked host/port under {k}: {v}"
                _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    _walk(manifest)


def test_cli_remote_config_overlay(tiny_filesystem_project, tmp_path):
    """--config-overlay accepts a remote URL; overlay_fs_args are written; no local dir."""
    from click.testing import CliRunner
    from copick.cli.config import config as config_cli

    proj = tiny_filesystem_project
    emitted = tmp_path / "emitted_remote.json"
    remote_overlay = "ssh:///remote/overlay"

    runner = CliRunner()
    r = runner.invoke(
        config_cli,
        [
            "export-croissant",
            "--config",
            str(proj / "filesystem.json"),
            "--project-root",
            str(proj),
            "--base-url",
            f"file://{proj}",
            "--emit-config",
            str(emitted),
            "--config-overlay",
            remote_overlay,
            "--config-overlay-fs-args",
            '{"host":"h","port":22}',
        ],
    )
    assert r.exit_code == 0, r.output

    cfg = json.loads(emitted.read_text())
    assert cfg["overlay_root"] == remote_overlay
    assert cfg["overlay_fs_args"] == {"host": "h", "port": 22}
    # No auto_mkdir for remote overlays.
    assert "auto_mkdir" not in cfg["overlay_fs_args"]
    # And no stray local directory was created for the remote path.
    assert not (Path("/remote") / "overlay").exists()


def test_cli_local_config_overlay_backcompat(tiny_filesystem_project, tmp_path):
    """Bare local path still produces local:// URL + auto_mkdir + mkdirs."""
    from click.testing import CliRunner
    from copick.cli.config import config as config_cli

    proj = tiny_filesystem_project
    overlay = tmp_path / "local_overlay"
    emitted = tmp_path / "emitted_local.json"

    runner = CliRunner()
    r = runner.invoke(
        config_cli,
        [
            "export-croissant",
            "--config",
            str(proj / "filesystem.json"),
            "--project-root",
            str(proj),
            "--base-url",
            f"file://{proj}",
            "--emit-config",
            str(emitted),
            "--config-overlay",
            str(overlay),
        ],
    )
    assert r.exit_code == 0, r.output

    cfg = json.loads(emitted.read_text())
    assert cfg["overlay_root"].startswith("local://")
    assert cfg["overlay_root"].endswith(str(overlay))
    assert cfg["overlay_fs_args"].get("auto_mkdir") is True
    assert overlay.exists() and overlay.is_dir()


# -----------------------------------------------------------------------------
# Mode-B overlay==base_url: queries must not double-count artifacts that live
# in both the Croissant CSV index and the overlay filesystem when those point
# to the same location.
# -----------------------------------------------------------------------------


def test_mode_b_overlay_at_base_url_does_not_duplicate(tiny_filesystem_project, tmp_path):
    """When overlay_root == base_url, static and overlay queries must dedupe.

    The source filesystem project has 1 pick. After exporting a Croissant and
    loading a Mode-B companion config whose overlay_root points at the same
    location as base_url, we expect 1 pick (not 2) — the static CSV branch
    should short-circuit because static_is_overlay is True.
    """
    import copick
    from copick.ops.croissant import export_croissant

    proj = tiny_filesystem_project
    src = copick.from_file(str(proj / "filesystem.json"))
    src_run = src.get_run("run_001")
    src_pick_count = len(src_run.picks)
    assert src_pick_count == 1

    export_croissant(src, project_root=str(proj), base_url=f"file://{proj}")

    # Mode B with overlay_root == base_url (mirrors the bacteria use case).
    cfg = {
        "config_type": "mlcroissant",
        "pickable_objects": [],
        "croissant_url": str(proj / "Croissant" / "metadata.json"),
        "overlay_root": f"file://{proj}",
        "overlay_fs_args": {"auto_mkdir": True},
    }
    config_path = tmp_path / "overlay_eq_base.json"
    config_path.write_text(json.dumps(cfg))

    root = copick.from_file(str(config_path))
    assert root.mode == "B", "overlay_root is set, so mode should be B"
    assert (
        root.static_is_overlay is True
    ), "overlay_root normalizes to the same path as base_url, so static_is_overlay must be True for query dedup"

    run = root.get_run("run_001")
    assert len(run.picks) == src_pick_count, f"picks duplicated: expected {src_pick_count}, got {len(run.picks)}"
    # Meshes / segs / voxel_spacings lists should also match the source
    # (all zero in the tiny fixture, but the static_is_overlay gate applies).
    assert len(run.meshes) == len(src_run.meshes)
    assert len(run.segmentations) == len(src_run.segmentations)
    assert len(run.voxel_spacings) == len(src_run.voxel_spacings)


def test_mode_b_overlay_distinct_from_base_url_is_not_overlay(
    tiny_filesystem_project,
    tmp_path,
):
    """When overlay_root is a different path, static_is_overlay is False."""
    import copick
    from copick.ops.croissant import export_croissant

    proj = tiny_filesystem_project
    src = copick.from_file(str(proj / "filesystem.json"))
    export_croissant(src, project_root=str(proj), base_url=f"file://{proj}")

    overlay = tmp_path / "distinct_overlay"
    overlay.mkdir()
    cfg = {
        "config_type": "mlcroissant",
        "pickable_objects": [],
        "croissant_url": str(proj / "Croissant" / "metadata.json"),
        "overlay_root": f"file://{overlay}",
        "overlay_fs_args": {"auto_mkdir": True},
    }
    config_path = tmp_path / "distinct_overlay.json"
    config_path.write_text(json.dumps(cfg))

    root = copick.from_file(str(config_path))
    assert root.mode == "B"
    assert root.static_is_overlay is False, (
        "overlay_root is a distinct path from base_url — static_is_overlay "
        "must be False so Mode-B semantics apply (static CSV + empty overlay)"
    )

    # Source has 1 pick; distinct overlay is empty; still exactly 1 pick.
    run = root.get_run("run_001")
    assert len(run.picks) == 1


# -----------------------------------------------------------------------------
# CDP-style NDJSON pick loading + voxel_size column + Mode A graceful exit
# -----------------------------------------------------------------------------


def _patch_picks_csv(proj, *, url, voxel_size, drop_voxel_size_column=False):
    """Rewrite picks.csv to point at ``url`` and refresh metadata.json.

    Used by the NDJSON-loading tests to redirect the single exported pick at
    a hand-written CDP-style file. ``drop_voxel_size_column=True`` simulates
    a legacy Croissant exported before the column was added — also removes
    the corresponding field declaration from ``metadata.json`` so mlcroissant
    doesn't fail on schema mismatch.
    """
    import csv as _csv

    from copick.impl.mlcroissant import _sha256_bytes

    picks_csv = proj / "Croissant" / "picks.csv"
    rows = list(_csv.DictReader(picks_csv.open()))
    fieldnames = list(rows[0].keys()) if rows else []
    if drop_voxel_size_column and "voxel_size" in fieldnames:
        fieldnames = [f for f in fieldnames if f != "voxel_size"]
        for row in rows:
            row.pop("voxel_size", None)
    for row in rows:
        row["url"] = url
        if not drop_voxel_size_column:
            row["voxel_size"] = "" if voxel_size is None else str(voxel_size)
    with picks_csv.open("w", newline="") as f:
        writer = _csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    metadata_path = proj / "Croissant" / "metadata.json"
    doc = json.loads(metadata_path.read_text())
    if drop_voxel_size_column:
        for rs in doc.get("recordSet", []):
            if rs.get("@id") == "copick/picks":
                rs["field"] = [fld for fld in rs.get("field", []) if fld.get("@id") != "copick/picks/voxel_size"]
    new_sha = _sha256_bytes(picks_csv.read_bytes())
    for fo in doc.get("distribution", []):
        if fo.get("@id") == "picks-csv":
            fo["sha256"] = new_sha
    metadata_path.write_text(json.dumps(doc, indent=2))


@pytest.fixture
def cdp_like_croissant_project(tiny_filesystem_project):
    """Croissant whose picks.csv URL points at a CDP-style NDJSON file.

    Reuses ``tiny_filesystem_project`` to build a valid Croissant via
    ``export_croissant``, then redirects the pick row at a hand-written
    NDJSON file at ``<base>/dataset_001/run_001/Reconstructions/
    VoxelSpacing10.000/Annotations/100-ribosome-0.ndjson``. Coordinates in
    the NDJSON are in voxel units; the loader must scale by ``voxel_size``
    (= 10.0) to produce angstroms.
    """
    import copick
    from copick.ops.croissant import export_croissant

    proj = tiny_filesystem_project
    root = copick.from_file(str(proj / "filesystem.json"))
    export_croissant(root, project_root=str(proj), base_url=f"file://{proj}")

    ndjson_dir = proj / "dataset_001" / "run_001" / "Reconstructions" / "VoxelSpacing10.000" / "Annotations"
    ndjson_dir.mkdir(parents=True)
    ndjson_path = ndjson_dir / "100-ribosome-0.ndjson"
    ndjson_path.write_text(
        '{"location":{"x":1.0,"y":2.0,"z":3.0}}\n'
        '{"location":{"x":4.0,"y":5.0,"z":6.0},"xyz_rotation_matrix":[[1,0,0],[0,1,0],[0,0,1]]}\n',
    )

    rel_url = "dataset_001/run_001/Reconstructions/VoxelSpacing10.000/Annotations/100-ribosome-0.ndjson"
    _patch_picks_csv(proj, url=rel_url, voxel_size=10.0)
    return proj


def test_load_ndjson_picks_scales_via_csv_voxel_size(cdp_like_croissant_project):
    """The voxel_size column drives Å conversion for NDJSON picks."""
    import copick

    proj = cdp_like_croissant_project
    root = copick.from_croissant(str(proj / "Croissant" / "metadata.json"))
    pick = root.get_run("run_001").picks[0]
    pts = pick.points
    assert len(pts) == 2
    assert pts[0].location.x == 10.0  # 1.0 * vs(10.0)
    assert pts[0].location.y == 20.0
    assert pts[0].location.z == 30.0
    assert pts[1].location.z == 60.0  # 6.0 * 10.0
    assert pick.meta.unit == "angstrom"
    assert pick.meta.voxel_spacing == 10.0


def test_load_ndjson_picks_handles_orientation(cdp_like_croissant_project):
    """OrientedPoint NDJSON entries produce 4×4 transformations + trust_orientation."""
    import copick

    proj = cdp_like_croissant_project
    root = copick.from_croissant(str(proj / "Croissant" / "metadata.json"))
    pick = root.get_run("run_001").picks[0]
    pts = pick.points
    # Second point has xyz_rotation_matrix=identity → 4x4 identity transform
    mat = pts[1].transformation_
    assert mat[0][0] == 1.0
    assert mat[1][1] == 1.0
    assert mat[2][2] == 1.0
    assert mat[3][3] == 1.0
    # First point has no rotation matrix → identity (default)
    assert pick.meta.trust_orientation is True


def test_mode_a_loads_ndjson_via_csv_url(cdp_like_croissant_project):
    """Mode A reads CDP-style NDJSON picks via the CSV-recorded URL.

    Without the Mode A path-resolution fix, ``_load`` would synthesise an
    ``ExperimentRuns/.../Picks/...json`` path that doesn't exist and the
    points access would FileNotFoundError before even hitting the parser.
    """
    import copick

    proj = cdp_like_croissant_project
    root = copick.from_croissant(str(proj / "Croissant" / "metadata.json"))
    assert root.mode == "A"
    pick = root.get_run("run_001").picks[0]
    assert len(pick.points) == 2  # would raise FileNotFoundError without the fix


def test_load_pretty_printed_json_still_works(tiny_filesystem_project):
    """Native CopickPicksFile JSON files (pretty-printed, multi-line) still load.

    Regression guard: the NDJSON branch must key on the ``.ndjson`` suffix,
    not "this file contains newlines" — otherwise pretty-printed JSON would
    be misclassified as NDJSON and parsed line-by-line.
    """
    import copick
    from copick.ops.croissant import export_croissant

    proj = tiny_filesystem_project
    # Rewrite the pick file with indent=4 so it spans multiple lines.
    pick_path = proj / "ExperimentRuns" / "run_001" / "Picks" / "alice_42_ribosome.json"
    pick_data = json.loads(pick_path.read_text())
    pick_path.write_text(json.dumps(pick_data, indent=4))
    assert "\n" in pick_path.read_text()  # confirm it's now multi-line

    root = copick.from_file(str(proj / "filesystem.json"))
    export_croissant(root, project_root=str(proj), base_url=f"file://{proj}")
    root2 = copick.from_croissant(str(proj / "Croissant" / "metadata.json"))
    pick = root2.get_run("run_001").picks[0]
    # Coords are stored in Å in the JSON file; no scaling expected.
    assert pick.points[0].location.x == 1.0
    assert pick.points[0].location.y == 2.0


def test_mode_a_write_to_anon_base_raises_permission_error(tiny_filesystem_project, tmp_path):
    """Mode A writes against a read-only base URL fail with a clear PermissionError.

    Simulates a CDP-sourced Croissant: ``static_fs_args = {"anon": True}``.
    Without the guard, this would fail deep in s3fs/boto3 with no hint that
    Mode B is the right answer.
    """
    import copick
    from copick.impl.mlcroissant import CopickConfigMLCroissant, CopickRootMLC
    from copick.ops.croissant import export_croissant

    proj = tiny_filesystem_project
    root = copick.from_file(str(proj / "filesystem.json"))
    export_croissant(root, project_root=str(proj), base_url=f"file://{proj}")

    # Build a root with anon=True in static_fs_args (the CDP-public-bucket pattern).
    cfg = CopickConfigMLCroissant(
        config_type="mlcroissant",
        name="anon-test",
        version="1.0.0",
        user_id="alice",
        session_id="42",
        pickable_objects=[],
        croissant_url=str(proj / "Croissant" / "metadata.json"),
        static_fs_args={"anon": True},
    )
    r = CopickRootMLC(cfg)
    assert r.mode == "A"

    # Try to write a new pick → must raise PermissionError pointing at Mode B.
    # ``run.new_picks(...)`` writes through to disk on creation, so the guard
    # fires inside ``new_picks`` rather than at an explicit ``store()`` call.
    run = r.get_run("run_001")
    with pytest.raises(PermissionError, match="overlay_root"):
        run.new_picks(object_name="ribosome", user_id="bob", session_id="99")


def test_legacy_croissant_falls_back_to_url_parsing(cdp_like_croissant_project):
    """Croissants exported before the voxel_size column was added still load via URL regex.

    Migration safety net: ``picks.csv`` with no ``voxel_size`` column must still
    produce Å-valued points by parsing ``VoxelSpacing10.000`` from the URL.
    """
    import copick

    proj = cdp_like_croissant_project
    rel_url = "dataset_001/run_001/Reconstructions/VoxelSpacing10.000/Annotations/100-ribosome-0.ndjson"
    _patch_picks_csv(proj, url=rel_url, voxel_size=None, drop_voxel_size_column=True)

    root = copick.from_croissant(str(proj / "Croissant" / "metadata.json"))
    pts = root.get_run("run_001").picks[0].points
    assert len(pts) == 2
    assert pts[0].location.x == 10.0  # vs parsed from URL = 10.0 → 1.0 * 10.0
    assert pts[1].location.z == 60.0


def test_export_writes_voxel_size_column(tiny_filesystem_project):
    """export_croissant emits the voxel_size column populated from CopickPicksFile."""
    import copick
    from copick.ops.croissant import export_croissant

    proj = tiny_filesystem_project
    root = copick.from_file(str(proj / "filesystem.json"))
    export_croissant(root, project_root=str(proj), base_url=f"file://{proj}")

    rows = _read_csv(proj / "Croissant" / "picks.csv")
    assert len(rows) == 1
    assert "voxel_size" in rows[0]
    # tiny_filesystem_project's pick has voxel_spacing=10.0 — exporter must record it.
    assert float(rows[0]["voxel_size"]) == 10.0


def test_export_cdp_pick_uses_portal_metadata_voxel_spacing():
    """``_pick_voxel_size`` reads voxel_spacing from PortalAnnotationMeta for CDP picks."""
    from copick.ops.croissant import _pick_voxel_size

    class _Stub:
        pass

    pick = _Stub()
    pick.meta = _Stub()
    pick.meta.portal_metadata = _Stub()
    pick.meta.portal_metadata.voxel_spacing = 10.0
    pick.meta.voxel_spacing = None  # CDP picks don't go through CopickPicksFile.voxel_spacing

    assert _pick_voxel_size(pick, is_cdp=True) == 10.0
    # Non-CDP path with no voxel_spacing → None
    pick2 = _Stub()
    pick2.meta = _Stub()
    pick2.meta.voxel_spacing = None
    assert _pick_voxel_size(pick2, is_cdp=False) is None
    # Non-CDP path with voxel_spacing set → that value
    pick2.meta.voxel_spacing = 7.84
    assert _pick_voxel_size(pick2, is_cdp=False) == 7.84
