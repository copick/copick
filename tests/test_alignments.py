"""Alignments and tomogram links on every storage backend."""

import json
from typing import Any, Dict

import copick
import numpy as np
import pytest
from cets_schema import validate_cets
from copick.models import (
    CopickAlignment,
    CopickExcludedSection,
    CopickReferenceVolume,
    CopickSectionAlignment,
    CopickTiltSeriesMetadata,
)
from copick.ops.add import add_tomogram
from copick.util.cets import ALIGNMENT_SCHEMA, alignment_to_document

N_SECTIONS = 5


@pytest.fixture(params=pytest.common_cases)
def test_payload(request) -> Dict[str, Any]:
    payload = request.getfixturevalue(request.param)
    payload["root"] = copick.from_file(payload["cfg_file"])
    return payload


def _fresh_run(payload, name="TS_001"):
    return copick.from_file(payload["cfg_file"]).get_run(name)


def _sections(n=N_SECTIONS, rotation=85.0):
    return [
        CopickSectionAlignment(
            section=i,
            tilt_angle=-6.0 + 3.0 * i + 0.1,
            x_tilt=0.5,
            in_plane_rotation=rotation,
            shift_x=1.5 * i,
            shift_y=-2.0,
        )
        for i in range(n)
    ]


def _reference():
    # The sample project's 64^3 tomograms at 10 A
    return CopickReferenceVolume(size=(64, 64, 64), voxel_size=10.0)


def _tilt_series(run, ts_type="raw", **metadata):
    ts = run.new_tilt_series(ts_type)
    md = CopickTiltSeriesMetadata(pixel_size=10.0, width=64, height=64, **metadata)
    ts.from_numpy(np.zeros((N_SECTIONS, 64, 64), dtype=np.float32), metadata=md)
    return ts


def _writable_tomogram(run, tomo_type="reconstruction"):
    tomogram = run.get_voxel_spacing(10.0).new_tomogram(tomo_type, exist_ok=True)
    tomogram.from_numpy(np.zeros((64, 64, 64), dtype=np.float32))
    return tomogram


def test_alignment_roundtrip(test_payload: Dict[str, Any]):
    run = test_payload["root"].get_run("TS_001")
    ts = _tilt_series(run)
    alignment = run.new_alignment(
        "aretomo3",
        ts,
        sections=_sections(n=4),
        excluded_sections=[CopickExcludedSection(section=4, reason="dark")],
        reference_volume=_reference(),
        alignment_type="LOCAL",
        rigid_part_of_local=True,
        method="patch_tracking",
        source_format="ARETOMO3",
        native_frame={"image_center": "half", "volume_center": "half"},
        warnings=["Only the rigid part of the local alignment is stored."],
        provenance={"source_files": ["TS_001.aln"]},
    )
    assert alignment.is_valid and alignment.status == "author"

    reread = _fresh_run(test_payload).get_alignment("aretomo3")
    assert repr(reread).startswith("CopickAlignment(name=aretomo3, tilt_series=None)")  # not loaded yet
    assert reread.file == alignment.meta
    for stored, written in zip(reread.sections, _sections(n=4), strict=True):
        for field in ("tilt_angle", "x_tilt", "in_plane_rotation", "shift_x", "shift_y"):
            assert getattr(stored, field) == pytest.approx(getattr(written, field), abs=1e-9)
    assert reread.section(4) is None and reread.excluded_sections[0].reason == "dark"

    document = alignment_to_document(reread.file)
    assert document["schema"] == ALIGNMENT_SCHEMA
    validate_cets(document["alignment"], "Alignment")
    assert len(document["alignment"]["projection_alignments"]) == 4
    assert reread.to_cets() == document["alignment"]


def test_alignment_navigation_and_ranking(test_payload: Dict[str, Any]):
    run = test_payload["root"].get_run("TS_001")
    raw = _tilt_series(run, "raw")
    other = _tilt_series(run, "denoised-ts")
    run.new_alignment("imod", raw, sections=_sections(), reference_volume=_reference())
    run.new_alignment("aretomo3", raw, sections=_sections(), reference_volume=_reference(), alignment_type="LOCAL")
    run.new_alignment("placeholder", raw, status="portal_default", is_portal_standard=False)
    run.new_alignment("chosen", raw, sections=_sections(), reference_volume=_reference(), preferred=True)
    run.new_alignment("for-other", other, sections=_sections())

    run = _fresh_run(test_payload)
    raw = run.get_tilt_series("raw")
    assert [a.name for a in raw.alignments] == ["chosen", "aretomo3", "imod", "placeholder"]
    assert [a.name for a in raw.valid_alignments] == ["chosen", "aretomo3", "imod"]
    assert raw.default_alignment.name == "chosen"
    assert run.get_alignment("placeholder").is_default and not run.get_alignment("placeholder").is_valid
    assert [a.name for a in run.get_alignments("denoised-ts")] == ["for-other"]
    assert [a.name for a in run.get_alignments(alignment_type="LOCAL")] == ["aretomo3"]
    assert run.get_alignment("for-other").tilt_series.ts_type == "denoised-ts"
    assert "len(alignments)=5" in repr(run)


def test_new_alignment_checks(test_payload: Dict[str, Any]):
    run = test_payload["root"].get_run("TS_001")
    with pytest.raises(ValueError, match="no tilt series"):
        run.new_alignment("a", "raw")
    ts = _tilt_series(run)
    with pytest.raises(ValueError, match="'@'"):
        run.new_alignment("a@b", ts)
    with pytest.raises(ValueError, match="Sections must lie"):
        run.new_alignment("a", ts, sections=_sections(n=N_SECTIONS + 1))
    run.new_alignment("a", "raw")
    with pytest.raises(ValueError, match="already exists"):
        run.new_alignment("a", ts)
    assert run.new_alignment("a", ts, exist_ok=True).name == "a"
    with pytest.raises(ValueError, match="aligned images"):
        run.new_alignment("b", _tilt_series(run, "aligned-stack", is_aligned=True))
    with pytest.raises(ValueError):
        run.new_alignment("c", ts, sections=_sections(n=2), excluded_sections=[CopickExcludedSection(section=1)])


def test_tomogram_link(test_payload: Dict[str, Any]):
    run = test_payload["root"].get_run("TS_001")
    ts = _tilt_series(run)
    alignment = run.new_alignment("aretomo3", ts, sections=_sections(), reference_volume=_reference())
    tomogram = _writable_tomogram(run)
    assert tomogram.alignment_link is None and tomogram.alignment is None

    tomogram.set_alignment(alignment)
    run = _fresh_run(test_payload)
    tomogram = run.get_voxel_spacing(10.0).get_tomograms("reconstruction")[0]
    assert tomogram.alignment_link.source == "attrs"
    assert tomogram.alignment.name == "aretomo3" and tomogram.tilt_series.ts_type == "raw"
    assert [t.tomo_type for t in run.get_alignment("aretomo3").tomograms] == ["reconstruction"]

    # The link is stored CETS-shaped
    import zarr

    block = zarr.open_group(tomogram.zarr(), mode="r").attrs["copick"]
    validate_cets(block["tomogram"], "Tomogram")
    assert block["tomogram"] == {"id": "reconstruction@10.000", "tilt_series_id": "raw"}

    # Rewriting the data keeps the link
    tomogram.from_numpy(np.ones((64, 64, 64), dtype=np.float32))
    add_tomogram(
        copick.from_file(test_payload["cfg_file"]),
        "TS_001",
        "reconstruction",
        np.ones((64, 64, 64), dtype=np.float32),
        voxel_spacing=10.0,
        exist_ok=True,
        overwrite=True,
    )
    assert _fresh_run(test_payload).get_voxel_spacing(10.0).get_tomograms("reconstruction")[0].alignment.name == (
        "aretomo3"
    )

    # Projection through the link: the tomogram centre projects to the image centre shifted by the section's shift
    alignment = _fresh_run(test_payload).get_alignment("aretomo3")
    reread = _fresh_run(test_payload).get_voxel_spacing(10.0).get_tomograms("reconstruction")[0]
    projected = alignment.project([[320.0, 320.0, 320.0]], tomogram=reread, sections=[2])
    np.testing.assert_allclose(projected[2], [[32.0 + 0.3, 32.0 - 0.2]], atol=1e-9)

    # Unlinking, and errors
    reread.set_alignment(None)
    assert _fresh_run(test_payload).get_voxel_spacing(10.0).get_tomograms("reconstruction")[0].alignment is None
    with pytest.raises(ValueError, match="no alignment"):
        reread.set_alignment("missing")
    other_run = _fresh_run(test_payload, "TS_002")
    _tilt_series(other_run)
    foreign = other_run.new_alignment("foreign", "raw")
    with pytest.raises(ValueError, match="belongs to run"):
        reread.set_alignment(foreign)


def test_extent_check(test_payload: Dict[str, Any], caplog):
    run = test_payload["root"].get_run("TS_001")
    ts = _tilt_series(run)
    small = CopickReferenceVolume(size=(32, 32, 32), voxel_size=10.0)
    alignment = run.new_alignment("small", ts, sections=_sections(), reference_volume=small)
    tomogram = _writable_tomogram(run)
    with pytest.raises(ValueError, match="differ by more than a voxel"):
        tomogram.set_alignment(alignment, strict=True)
    tomogram.set_alignment(alignment)
    assert "differ by more than a voxel" in caplog.text


def test_deleting_an_alignment_unlinks(test_payload: Dict[str, Any]):
    run = test_payload["root"].get_run("TS_001")
    alignment = run.new_alignment("aretomo3", _tilt_series(run), sections=_sections(), reference_volume=_reference())
    _writable_tomogram(run).set_alignment(alignment)

    run = _fresh_run(test_payload)
    run.delete_alignments("aretomo3")
    assert run.alignments == []
    fresh = _fresh_run(test_payload)
    assert fresh.alignments == []
    assert fresh.get_voxel_spacing(10.0).get_tomograms("reconstruction")[0].alignment_link is None


def test_read_only_tomogram_is_named_by_the_alignment(test_payload: Dict[str, Any]):
    run = test_payload["root"].get_run("TS_001")
    static = [t for t in run.get_voxel_spacing(10.0).tomograms if getattr(t, "read_only", False)]
    if not static:
        pytest.skip("needs a read-only (static) tomogram")
    tomogram = static[0]

    alignment = run.new_alignment("aretomo3", _tilt_series(run), sections=_sections(), reference_volume=_reference())
    tomogram.set_alignment(alignment)
    run.new_alignment("other", "raw", sections=_sections())
    with pytest.raises(ValueError, match="reference offset"):
        tomogram.set_alignment("other", reference_offset=(1.0, 2.0, 3.0))

    run = _fresh_run(test_payload)
    reread = next(t for t in run.get_voxel_spacing(10.0).tomograms if t.tomo_type == tomogram.tomo_type and t.read_only)
    assert reread.alignment_link.source == "alignment"
    assert reread.alignment.name == "aretomo3"
    # The refused request changed nothing
    assert run.get_alignment("aretomo3").linked_tomograms == [reread.link_id]
    assert run.get_alignment("other").linked_tomograms == []
    assert [t.link_id for t in run.get_alignment("aretomo3").tomograms] == [reread.link_id]

    # Relinking moves the entry
    reread.set_alignment("other")
    run = _fresh_run(test_payload)
    assert run.get_alignment("aretomo3").linked_tomograms == []
    assert run.get_alignment("other").linked_tomograms == [reread.link_id]
    reread = next(t for t in run.get_voxel_spacing(10.0).tomograms if t.tomo_type == tomogram.tomo_type and t.read_only)
    reread.set_alignment(None)
    assert _fresh_run(test_payload).get_alignment("other").linked_tomograms == []


def test_static_alignments_are_read_only(test_payload: Dict[str, Any]):
    from copick.impl.filesystem import CopickRootFSSpec

    root = test_payload["root"]
    if test_payload["testfs_static"] is None or not isinstance(root, CopickRootFSSpec):
        pytest.skip("needs a separate static filesystem source")

    from copick.models import CopickAlignmentFile

    document = alignment_to_document(
        CopickAlignmentFile(name="static-aln", tilt_series="raw", sections=_sections(), reference_volume=_reference()),
    )
    directory = test_payload["testpath_static"] / "ExperimentRuns" / "TS_001" / "Alignments"
    fs = test_payload["testfs_static"]
    fs.makedirs(str(directory), exist_ok=True)
    with fs.open(str(directory / "static-aln.json"), "w") as f:
        json.dump(document, f)

    run = _fresh_run(test_payload)
    (alignment,) = run.alignments
    assert isinstance(alignment, CopickAlignment) and alignment.read_only
    assert alignment.sections[3].shift_x == pytest.approx(4.5)
    with pytest.raises(PermissionError):
        alignment.store()
    with pytest.raises(PermissionError):
        alignment.delete()

    static_tomograms = [t for t in run.get_voxel_spacing(10.0).tomograms if t.read_only]
    if static_tomograms:
        with pytest.raises(PermissionError, match="Neither"):
            static_tomograms[0].set_alignment(alignment)


def test_croissant_mode_a_index_rows(test_payload: Dict[str, Any]):
    root = test_payload["root"]
    if getattr(root, "mode", None) != "A":
        pytest.skip("needs a self-contained (Mode A) Croissant project")

    run = root.get_run("TS_001")
    run.new_alignment("aretomo3", _tilt_series(run), sections=_sections(), alignment_type="LOCAL")
    (row,) = [r for r in root.index.alignments if r["run"] == "TS_001"]
    assert (row["name"], row["tilt_series"], row["alignment_type"], row["status"]) == (
        "aretomo3",
        "raw",
        "LOCAL",
        "author",
    )
    assert row["url"] == "ExperimentRuns/TS_001/Alignments/aretomo3.json" and row["sha256"]

    root.index.reload()
    assert _fresh_run(test_payload).get_alignment("aretomo3").alignment_type == "LOCAL"
    _fresh_run(test_payload).get_alignment("aretomo3").delete()
    assert copick.from_file(test_payload["cfg_file"]).index.alignments == []
