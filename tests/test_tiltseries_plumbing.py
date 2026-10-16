"""URIs, get, cp/mv/rm, sync, links and Croissant export of tilt series and alignments."""

import json
from typing import Any, Dict

import copick
import numpy as np
import pytest
from click.testing import CliRunner
from copick.models import (
    CopickReferenceVolume,
    CopickSectionAlignment,
    CopickTiltImage,
    CopickTiltSeriesMetadata,
)
from copick.ops.get import get_alignments, get_tilt_series
from copick.ops.manage import copy_copick_objects, move_copick_objects, remove_copick_objects
from copick.ops.sync import sync_alignments, sync_tilt_series, sync_tomograms
from copick.util.uri import parse_copick_uri, resolve_copick_objects, serialize_copick_uri

N = 3


@pytest.fixture(params=pytest.common_cases)
def test_payload(request) -> Dict[str, Any]:
    payload = request.getfixturevalue(request.param)
    payload["root"] = copick.from_file(payload["cfg_file"])
    return payload


def _metadata():
    return CopickTiltSeriesMetadata(
        pixel_size=10.0,
        width=16,
        height=16,
        voltage=300.0,
        images=[CopickTiltImage(section=i, nominal_tilt_angle=-3.0 + 3.0 * i, acquisition_order=i) for i in range(N)],
    )


def _sections():
    return [CopickSectionAlignment(section=i, tilt_angle=-3.0 + 3.0 * i, in_plane_rotation=85.0) for i in range(N)]


def _populate(run):
    """A tilt series ``raw``, its alignment ``aretomo3`` and a writable tomogram ``recon`` linked to it."""
    ts = run.new_tilt_series("raw")
    ts.from_numpy(np.arange(N * 16 * 16, dtype=np.float32).reshape(N, 16, 16), metadata=_metadata())
    alignment = run.new_alignment(
        "aretomo3",
        ts,
        sections=_sections(),
        reference_volume=CopickReferenceVolume(size=(64, 64, 64), voxel_size=10.0),
    )
    tomogram = run.get_voxel_spacing(10.0).new_tomogram("recon")
    tomogram.from_numpy(np.zeros((64, 64, 64), dtype=np.float32))
    tomogram.set_alignment(alignment)
    return ts, alignment, tomogram


def _fresh_run(payload, name="TS_001"):
    return copick.from_file(payload["cfg_file"]).get_run(name)


def _recon(run):
    return run.get_voxel_spacing(10.0).get_tomograms("recon")[0]


# ---------------------------------------------------------------------------------------------------------------------
# URIs
# ---------------------------------------------------------------------------------------------------------------------


def test_uri_parsing():
    assert parse_copick_uri("raw", "tiltseries") == {
        "object_type": "tiltseries",
        "pattern_type": "glob",
        "ts_type": "raw",
    }
    assert parse_copick_uri("re:raw.*", "tiltseries")["pattern_type"] == "regex"
    parsed = parse_copick_uri("*@raw?valid=true&default=true", "alignment")
    assert (parsed["name"], parsed["ts_type"], parsed["valid"], parsed["default"]) == ("*", "raw", True, True)
    parsed = parse_copick_uri("aretomo3", "alignment")
    assert (parsed["name"], parsed["ts_type"], parsed["valid"], parsed["default"]) == ("aretomo3", "*", False, False)
    with pytest.raises(ValueError, match="tiltseries"):
        parse_copick_uri("x", "tilt")


def test_uri_resolution_and_get(test_payload: Dict[str, Any]):
    run = test_payload["root"].get_run("TS_001")
    ts, alignment, _ = _populate(run)
    run.new_alignment("placeholder", ts, status="portal_default")
    run.new_alignment("other", ts, sections=_sections(), alignment_type="LOCAL")

    root = copick.from_file(test_payload["cfg_file"])
    assert [serialize_copick_uri(t) for t in resolve_copick_objects("raw", root, "tiltseries")] == ["raw"]
    assert resolve_copick_objects("missing", root, "tiltseries") == []
    names = [a.name for a in resolve_copick_objects("*@raw", root, "alignment", "TS_001")]
    assert names == ["other", "aretomo3", "placeholder"]
    assert [a.name for a in resolve_copick_objects("*@raw?valid=true", root, "alignment")] == ["other", "aretomo3"]
    assert [a.name for a in resolve_copick_objects("*@raw?default=true", root, "alignment")] == ["other"]
    assert [serialize_copick_uri(a) for a in resolve_copick_objects("aretomo3", root, "alignment")] == ["aretomo3@raw"]

    assert [t.ts_type for t in get_tilt_series(root, runs="TS_001")] == ["raw"]
    assert [a.name for a in get_alignments(root, valid_only=True)] == ["other", "aretomo3"]
    assert [a.name for a in get_alignments(root, name="aretomo3")] == ["aretomo3"]


# ---------------------------------------------------------------------------------------------------------------------
# cp / mv / rm
# ---------------------------------------------------------------------------------------------------------------------


def test_copy_tilt_series_and_alignment(test_payload: Dict[str, Any]):
    _populate(test_payload["root"].get_run("TS_001"))
    root = copick.from_file(test_payload["cfg_file"])
    assert copy_copick_objects(root, "tiltseries", "raw", "raw-copy")["copied"] == 1
    result = copy_copick_objects(root, "alignment", "aretomo3@raw", "aretomo3-copy@raw-copy")
    assert result["copied"] == 1, result

    run = _fresh_run(test_payload)
    copy = run.get_tilt_series("raw-copy")
    np.testing.assert_array_equal(copy.numpy(), run.get_tilt_series("raw").numpy())
    assert copy.metadata == _metadata()
    assert copy.metadata is not None and copy.cets_id == "raw-copy"
    assert run.get_alignment("aretomo3-copy").tilt_series_name == "raw-copy"
    # Copies leave the sources and their links alone
    assert _recon(run).alignment.name == "aretomo3"
    assert copy_copick_objects(root, "tiltseries", "raw", "raw-copy")["errors"], "an existing target needs overwrite"


def test_move_alignment_relinks_tomograms(test_payload: Dict[str, Any]):
    _populate(test_payload["root"].get_run("TS_001"))
    result = move_copick_objects(copick.from_file(test_payload["cfg_file"]), "alignment", "aretomo3@raw", "moved@raw")
    assert result["moved"] == 1, result
    run = _fresh_run(test_payload)
    assert [a.name for a in run.alignments] == ["moved"]
    assert _recon(run).alignment.name == "moved"


def test_move_tilt_series_moves_its_alignments(test_payload: Dict[str, Any]):
    _populate(test_payload["root"].get_run("TS_001"))
    result = move_copick_objects(copick.from_file(test_payload["cfg_file"]), "tiltseries", "raw", "renamed")
    assert result["moved"] == 1, result
    run = _fresh_run(test_payload)
    assert [t.ts_type for t in run.tilt_series] == ["renamed"]
    assert run.get_alignment("aretomo3").tilt_series_name == "renamed"
    assert _recon(run).tilt_series.ts_type == "renamed"
    assert run.get_tilt_series("renamed").metadata.images[1].nominal_tilt_angle == 0.0


def test_remove_tilt_series_needs_cascade(test_payload: Dict[str, Any]):
    _populate(test_payload["root"].get_run("TS_001"))
    root = copick.from_file(test_payload["cfg_file"])
    assert remove_copick_objects(root, "tiltseries", "raw")["deleted"] == 0
    assert [t.ts_type for t in _fresh_run(test_payload).tilt_series] == ["raw"]

    assert (
        remove_copick_objects(copick.from_file(test_payload["cfg_file"]), "tiltseries", "raw", cascade=True)["deleted"]
        == 1
    )
    run = _fresh_run(test_payload)
    assert run.tilt_series == [] and run.alignments == []
    assert _recon(run).alignment_link is None


def test_remove_alignment_unlinks(test_payload: Dict[str, Any]):
    _populate(test_payload["root"].get_run("TS_001"))
    assert remove_copick_objects(copick.from_file(test_payload["cfg_file"]), "alignment", "aretomo3")["deleted"] == 1
    run = _fresh_run(test_payload)
    assert run.alignments == [] and _recon(run).alignment_link is None


# ---------------------------------------------------------------------------------------------------------------------
# sync
# ---------------------------------------------------------------------------------------------------------------------


@pytest.fixture
def target_project(tmp_path):
    config = tmp_path / "target.json"
    config.write_text(
        json.dumps(
            {
                "config_type": "filesystem",
                "name": "target",
                "pickable_objects": [],
                "overlay_root": f"local://{tmp_path / 'target'}",
                "overlay_fs_args": {"auto_mkdir": True},
            },
        ),
    )
    return str(config)


def test_sync_tilt_series_alignments_and_links(test_payload: Dict[str, Any], target_project):
    _populate(test_payload["root"].get_run("TS_001"))
    source = copick.from_file(test_payload["cfg_file"])
    target = copick.from_file(target_project)

    sync_tilt_series(source, target, source_runs=["TS_001"], target_ts_types={"raw": "original"}, with_alignments=True)
    run = copick.from_file(target_project).get_run("TS_001")
    assert [t.ts_type for t in run.tilt_series] == ["original"]
    assert run.get_tilt_series("original").metadata == _metadata()
    assert run.get_alignment("aretomo3").tilt_series_name == "original"

    sync_alignments(
        source,
        copick.from_file(target_project),
        source_runs=["TS_001"],
        target_ts_types={"raw": "original"},
        exist_ok=True,
    )
    sync_tomograms(
        copick.from_file(test_payload["cfg_file"]),
        copick.from_file(target_project),
        source_runs=["TS_001"],
        voxel_spacings=[10.0],
        source_tomo_types=["recon"],
        with_links=True,
    )
    tomogram = _recon(copick.from_file(target_project).get_run("TS_001"))
    assert tomogram.alignment.name == "aretomo3" and tomogram.tilt_series.ts_type == "original"


# ---------------------------------------------------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------------------------------------------------


def test_new_link_and_rm_cascade_cli(test_payload: Dict[str, Any]):
    from copick.cli.cli import _cli

    run = test_payload["root"].get_run("TS_001")
    _populate(run)
    run.new_alignment("other", run.get_tilt_series("raw"), sections=_sections())
    runner = CliRunner()
    cfg = str(test_payload["cfg_file"])

    result = runner.invoke(
        _cli,
        ["new", "link", "-c", cfg, "--run", "TS_001", "--tomogram-uri", "recon@10.0", "--alignment", "other"],
    )
    assert result.exit_code == 0, result.output
    assert _recon(_fresh_run(test_payload)).alignment.name == "other"

    result = runner.invoke(
        _cli,
        ["new", "link", "-c", cfg, "--run", "TS_001", "--tomogram-uri", "recon@10.0", "--unlink"],
    )
    assert result.exit_code == 0, result.output
    assert _recon(_fresh_run(test_payload)).alignment_link is None

    result = runner.invoke(_cli, ["rm", "-c", cfg, "--cascade", "tiltseries", "raw"])
    assert result.exit_code == 0, result.output
    run = _fresh_run(test_payload)
    assert run.tilt_series == [] and run.alignments == []


# ---------------------------------------------------------------------------------------------------------------------
# Croissant export
# ---------------------------------------------------------------------------------------------------------------------


def test_croissant_export_of_tilt_series_and_alignments(test_payload: Dict[str, Any], tmp_path):
    from copick.impl.filesystem import CopickRootFSSpec
    from copick.ops.croissant import export_croissant
    from fsspec.implementations.local import LocalFileSystem

    root = test_payload["root"]
    if (
        not isinstance(root, CopickRootFSSpec)
        or test_payload["testfs_static"] is not None
        or not isinstance(test_payload["testfs_overlay"], LocalFileSystem)
    ):
        pytest.skip("exports an overlay-only local filesystem project")
    _populate(root.get_run("TS_001"))
    project = str(test_payload["testpath_overlay"])
    export_croissant(
        copick.from_file(test_payload["cfg_file"]),
        project,
        base_url=f"file://{project}",
        validate=False,
        force=True,
    )

    reopened = copick.from_croissant(f"{project}/Croissant/metadata.json")
    assert reopened.mode == "A"
    run = reopened.get_run("TS_001")
    assert [t.ts_type for t in run.tilt_series] == ["raw"]
    assert run.get_tilt_series("raw").metadata == _metadata()
    assert run.get_alignment("aretomo3").sections[2].in_plane_rotation == pytest.approx(85.0)
    assert _recon(run).alignment.name == "aretomo3"

    filtered = tmp_path / "filtered"
    export_croissant(
        copick.from_file(test_payload["cfg_file"]),
        project,
        base_url=f"file://{project}",
        validate=False,
        force=True,
        tilt_series=["missing"],
        alignments=["missing"],
    )
    reopened = copick.from_croissant(f"{project}/Croissant/metadata.json")
    assert reopened.get_run("TS_001").tilt_series == [] and reopened.get_run("TS_001").alignments == []
    assert not filtered.exists()


def test_markdown_renderers(test_payload: Dict[str, Any]):
    from copick.ops._markdown import ENTITY_TO_MD

    ts, alignment, _ = _populate(test_payload["root"].get_run("TS_001"))
    md = ENTITY_TO_MD["tilt_series"](ts)
    assert "Tilt Series: raw" in md and "-3.0° to 3.0°" in md and "CTF: absent" in md
    md = ENTITY_TO_MD["alignment"](alignment)
    assert "Alignment: aretomo3" in md and "Status: author (valid)" in md and "recon@10.000" in md
