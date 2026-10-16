"""CryoET Data Portal tilt series, alignments and CTF, offline.

Built on a recorded run of dataset 10445 (``tests/data/portal/10445_TS_105_5.json``, made by
``tests/scripts/make_portal_acquisition_fixture.py``); the portal queries are replaced by the recorded payloads.
"""

import copy
import json
import math
from pathlib import Path

import cryoet_data_portal as cdp
import numpy as np
import pytest
from copick.impl.cryoet_data_portal import CopickConfigCDP, CopickRootCDP, PortalCache
from copick.models import CopickReferenceVolume, CopickSectionAlignment
from copick.util.alignment_geometry import (
    center,
    cets_to_native_shift,
    image_delta,
    project,
    rotation,
    volume_delta,
)
from copick.util.portal_acquisition import (
    DEFAULT_AMPLITUDE_CONTRAST,
    classify_portal_alignment,
    parse_portal_matrix,
    portal_alignment_file,
    portal_alignment_name,
    portal_ctf,
    portal_tilt_series_metadata,
    resolve_alignment_tilt_series,
)

FIXTURE = json.loads((Path(__file__).parent / "data" / "portal" / "10445_TS_105_5.json").read_text())
RUN_ID = 17687
TS_ID = 17489
ALIGNMENT_ID = 18924


@pytest.fixture
def acquisition():
    return copy.deepcopy(FIXTURE["acquisition"])


def _frames(payload):
    return {f["id"]: f for f in payload["frames"]}


# ---------------------------------------------------------------------------------------------------------------------
# Pure mapping
# ---------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "{{1,0,0,0},{0,1,0,0},{0,0,1,0},{0,0,0,1}}",
        "[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]",
        [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
    ],
)
def test_parse_portal_matrix(value):
    np.testing.assert_array_equal(parse_portal_matrix(value), np.eye(4))


def test_parse_portal_matrix_absent():
    assert parse_portal_matrix(None) is None and parse_portal_matrix("") is None


def test_portal_ctf_conventions():
    ctf = portal_ctf(
        {"major_defocus": 20000.0, "minor_defocus": 21000.0, "astigmatic_angle": -10.0, "phase_shift": math.pi / 2},
    )
    # u >= v (swapped, angle turned by 90 degrees and wrapped), phase in degrees
    assert (ctf.defocus_u, ctf.defocus_v, ctf.defocus_angle, ctf.phase_shift) == pytest.approx((21000, 20000, 80, 90))
    no_phase = portal_ctf({"major_defocus": 2.0, "minor_defocus": 1.0, "phase_shift": None, "max_resolution": 0.0})
    assert no_phase.phase_shift == 0.0 and no_phase.fit_resolution is None
    assert portal_ctf({"major_defocus": None, "minor_defocus": None}) is None


def test_portal_tilt_series_metadata(acquisition):
    ts = acquisition["tiltseries"][0]
    metadata = portal_tilt_series_metadata(ts, acquisition["per_section_parameters"], _frames(acquisition))
    assert (metadata.pixel_size, metadata.width, metadata.height, metadata.n_sections) == (1.54, 4096, 4096, 31)
    assert metadata.voltage == 300.0 and metadata.spherical_aberration == 2.7 and metadata.tilt_axis_angle == -96.0
    assert metadata.amplitude_contrast == DEFAULT_AMPLITUDE_CONTRAST
    assert metadata.amplitude_contrast_source == "default"
    assert metadata.ctf_status == "fitted"
    assert metadata.provenance["portal_tiltseries_id"] == TS_ID

    first = metadata.images[0]
    assert first.nominal_tilt_angle == -45.03
    assert first.acquisition_order == 30  # 0-based
    assert first.accumulated_dose == pytest.approx(116.1225) and first.exposure_dose == pytest.approx(3.87075)
    assert first.frame_path.endswith("_031_-45.03_20240311_031951_EER.eer")
    assert (first.ctf.defocus_u, first.ctf.defocus_v, first.ctf.defocus_angle) == pytest.approx(
        (22481.63, 22086.07, 178.24),
    )
    assert sorted(image.acquisition_order for image in metadata.images) == list(range(31))


def test_portal_ctf_status(acquisition):
    ts = acquisition["tiltseries"][0]
    rows = acquisition["per_section_parameters"]
    frames = _frames(acquisition)

    no_ctf = [dict(r, major_defocus=None, minor_defocus=None) for r in rows]
    assert portal_tilt_series_metadata(ts, no_ctf, frames).ctf_status == "absent"
    assert portal_tilt_series_metadata(ts, [], frames).ctf_status == "absent"
    assert portal_tilt_series_metadata(ts, rows[:-1], frames).ctf_status == "partial"
    zero = [dict(rows[0], major_defocus=0.0, minor_defocus=0.0), *rows[1:]]
    assert portal_tilt_series_metadata(ts, zero, frames).ctf_status == "suspicious"


def test_alignment_name():
    assert portal_alignment_name({"id": 7, "alignment_method": "patch_tracking", "alignment_type": "GLOBAL"}) == (
        "patchTracking-global-7"
    )
    assert portal_alignment_name({"id": 8, "alignment_method": None, "alignment_type": None}) == "undefined-global-8"


def _default_alignment(**changes):
    alignment = {
        "id": 99,
        "run_id": RUN_ID,
        "tiltseries_id": TS_ID,
        "alignment_type": "GLOBAL",
        "alignment_method": None,
        "is_portal_standard": False,
        "affine_transformation_matrix": "{{1,0,0,0},{0,1,0,0},{0,0,1,0},{0,0,0,1}}",
        "volume_x_offset": 0.0,
        "volume_y_offset": 0.0,
        "volume_z_offset": 0.0,
        "tilt_offset": 0.0,
        "x_rotation_offset": 0.0,
        "volume_x_dimension": 6287.4,
        "volume_y_dimension": 6287.4,
        "volume_z_dimension": 1836.32,
    }
    alignment.update(changes)
    return alignment


def test_classify_portal_alignments(acquisition):
    ts = acquisition["tiltseries"][0]
    real = acquisition["alignments"][0]
    rows = acquisition["per_section_alignment_parameters"]

    assert classify_portal_alignment(real, rows, ts) == ("author", [])
    assert classify_portal_alignment(_default_alignment(), [], ts)[0] == "portal_default"
    status, reasons = classify_portal_alignment(_default_alignment(alignment_method="fiducial_based"), [], ts)
    assert status == "no_per_section" and "no method" in reasons[0]
    assert classify_portal_alignment(_default_alignment(is_portal_standard=True), [], ts)[0] == "no_per_section"
    assert classify_portal_alignment(_default_alignment(volume_x_offset=5.0), [], ts)[0] == "no_per_section"
    shifted = "{{1,0,0,5},{0,1,0,0},{0,0,1,0},{0,0,0,1}}"
    assert classify_portal_alignment(_default_alignment(affine_transformation_matrix=shifted), [], ts)[0] == (
        "no_per_section"
    )

    out_of_range = [*rows, dict(rows[0], z_index=31)]
    assert classify_portal_alignment(real, out_of_range, ts)[0] == "inconsistent"
    repeated = [*rows[:-1], dict(rows[0])]
    assert classify_portal_alignment(real, repeated, ts)[0] == "inconsistent"
    assert classify_portal_alignment(real, rows, dict(ts, is_aligned=True))[0] == "inconsistent"
    assert classify_portal_alignment(real, rows, None)[0] == "inconsistent"
    # Trivial-looking values are not a placeholder
    trivial = [dict(r, x_offset=0.0, y_offset=0.0, in_plane_rotation=[[1, 0], [0, 1]]) for r in rows]
    assert classify_portal_alignment(real, trivial, ts)[0] == "author"


def test_resolve_alignment_tilt_series(acquisition):
    ts = acquisition["tiltseries"][0]
    other = dict(ts, id=1)
    assert resolve_alignment_tilt_series({"tiltseries_id": TS_ID}, [other, ts]) is ts
    assert resolve_alignment_tilt_series({"tiltseries_id": None}, [ts]) is ts
    assert resolve_alignment_tilt_series({"tiltseries_id": None}, [ts, other]) is None


def test_portal_alignment_conversion(acquisition):
    ts = acquisition["tiltseries"][0]
    rows = {r["z_index"]: r for r in acquisition["per_section_alignment_parameters"]}
    alignment = portal_alignment_file(acquisition["alignments"][0], list(rows.values()), ts, run_name=str(RUN_ID))

    assert alignment.name == "projectionMatching-local-18924"
    assert (alignment.status, alignment.alignment_type, alignment.rigid_part_of_local) == ("author", "LOCAL", True)
    assert alignment.tilt_series == "raw" and alignment.tilt_series_portal_id == TS_ID
    assert alignment.is_portal_standard and alignment.provenance["portal_alignment_id"] == ALIGNMENT_ID
    assert alignment.native_frame == {"image_center": "half", "volume_center": "half"}
    reference = alignment.reference_volume
    assert reference.size == (4083, 4083, 1192) and reference.voxel_size == 1.54
    assert reference.native_extent == pytest.approx((6287.4, 6287.4, 1836.32))
    assert len(alignment.sections) == 31 and alignment.excluded_sections == []

    # Converting back to the portal's convention recovers its values exactly
    d_img = image_delta(4096, 4096, 1.54, "half")
    d_vol = volume_delta(reference.size, 1.54, "half", reference.native_extent)
    for section in alignment.sections:
        row = rows[section.section]
        assert section.tilt_angle == pytest.approx(row["tilt_angle"], abs=1e-9)
        m = row["in_plane_rotation"]
        assert section.in_plane_rotation == pytest.approx(math.degrees(math.atan2(m[1][0], m[0][0])), abs=1e-9)
        native = cets_to_native_shift((section.shift_x, section.shift_y), section.matrix(), d_img, d_vol) / 1.54
        np.testing.assert_allclose(native, [row["x_offset"], row["y_offset"]], atol=1e-9)

    # Projections agree with the portal's model: q_px = R p_px + (x_offset, y_offset) + N/2, centred at V/2
    rng = np.random.default_rng(0)
    points = rng.uniform(0, 1, (20, 3)) * np.asarray(reference.native_extent)
    for section in alignment.sections[::7]:
        row = rows[section.section]
        R = rotation(row["tilt_angle"], row["volume_x_rotation"], section.in_plane_rotation)
        portal = (
            project((points - np.asarray(reference.native_extent) / 2) / 1.54, R, (row["x_offset"], row["y_offset"]))
            + 2048.0
        )
        cets = (
            project(
                points - center(reference.size, 1.54, "floor"),
                section.matrix(),
                (section.shift_x, section.shift_y),
            )
            + center((4096, 4096), 1.54, "floor")
        ) / 1.54
        np.testing.assert_allclose(cets, portal, atol=1e-9)


def test_unaligned_sections_are_excluded(acquisition):
    ts = acquisition["tiltseries"][0]
    rows = [r for r in acquisition["per_section_alignment_parameters"] if r["z_index"] not in (0, 30)]
    alignment = portal_alignment_file(acquisition["alignments"][0], rows, ts)
    assert [e.section for e in alignment.excluded_sections] == [0, 30]
    assert {e.reason for e in alignment.excluded_sections} == {"not_aligned"}


# ---------------------------------------------------------------------------------------------------------------------
# The portal backend
# ---------------------------------------------------------------------------------------------------------------------


class _Fetch:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def __call__(self, root):
        self.calls += 1
        return copy.deepcopy(self.payload)


class _Record:
    """A portal client object: attribute access to a recorded ``to_dict()`` payload."""

    def __init__(self, data):
        self._data = data

    def __getattr__(self, name):
        try:
            return self._data[name]
        except KeyError as e:
            raise AttributeError(name) from e

    def to_dict(self):
        return dict(self._data)


def _annotation_cache():
    cache = PortalCache()
    for tomogram in FIXTURE["annotations"]["tomograms"]:
        cache.tomograms_by_vs.setdefault(tomogram["tomogram_voxel_spacing_id"], []).append(_Record(tomogram))
    return cache


@pytest.fixture
def portal(tmp_path, monkeypatch, acquisition):
    """A portal project over the recorded run, with an overlay in ``tmp_path``, offline."""
    runs = [_Record(r) for r in FIXTURE["annotations"]["runs"]]
    voxel_spacings = [_Record(v) for v in FIXTURE["annotations"]["voxel_spacings"]]
    monkeypatch.setattr(cdp, "Client", lambda *args, **kwargs: None)
    monkeypatch.setattr(cdp.Run, "find", staticmethod(lambda *args, **kwargs: list(runs)))
    monkeypatch.setattr(cdp.TomogramVoxelSpacing, "find", staticmethod(lambda *args, **kwargs: list(voxel_spacings)))
    monkeypatch.setattr(CopickRootCDP, "_ensure_annotation_cache", lambda self: _annotation_cache())

    fetch = _Fetch(acquisition)
    monkeypatch.setattr(CopickRootCDP, "_fetch_acquisition_data", lambda self: fetch(self))

    config = CopickConfigCDP(
        config_type="cryoet_data_portal",
        name="portal",
        overlay_root=f"local://{tmp_path / 'overlay'}",
        overlay_fs_args={"auto_mkdir": True},
        dataset_ids=[10445],
        pickable_objects=[],
    )

    def open_root():
        return CopickRootCDP(config)

    return {"open": open_root, "fetch": fetch, "acquisition": acquisition, "config": config, "tmp_path": tmp_path}


def _voxel_spacing(run, voxel_size):
    return next(vs for vs in run.voxel_spacings if vs.voxel_size == voxel_size)


def test_acquisition_data_is_fetched_lazily_and_once(portal):
    root = portal["open"]()
    assert portal["fetch"].calls == 0, "opening a portal project must not query tilt series"
    run = root.get_run(str(RUN_ID))
    assert [t.ts_type for t in run.tilt_series] == ["raw"]
    assert portal["fetch"].calls == 1
    assert len(run.alignments) == 1
    assert all(t.alignment is not None for t in _voxel_spacing(run, 10.012).tomograms)
    assert portal["fetch"].calls == 1


def test_portal_tilt_series(portal):
    run = portal["open"]().get_run(str(RUN_ID))
    (ts,) = run.tilt_series
    assert ts.read_only and ts.portal_tilt_series and ts.cets_id == f"raw-{TS_ID}"
    assert (
        ts.meta.portal_tiltseries_path == "s3://cryoet-data-portal-public/10445/TS_105_5/TiltSeries/100/TS_105_5.zarr"
    )
    metadata = ts.metadata
    assert metadata.n_sections == 31 and metadata.ctf_status == "fitted" and metadata.images[0].acquisition_order == 30
    with pytest.raises(PermissionError):
        ts.store_metadata(metadata)
    assert run.get_tilt_series_list("raw", portal_meta_query={"id": TS_ID}) == [ts]
    assert run.get_tilt_series_list("raw", portal_meta_query={"id": 1}) == []


def test_portal_alignments_and_navigation(portal):
    run = portal["open"]().get_run(str(RUN_ID))
    (alignment,) = run.alignments
    assert alignment.read_only and alignment.name == "projectionMatching-local-18924"
    assert alignment.is_valid and not alignment.is_default and alignment.portal_alignment_id == ALIGNMENT_ID
    with pytest.raises(PermissionError):
        alignment.store()

    ts = run.get_tilt_series("raw")
    assert alignment.tilt_series is ts
    assert ts.alignments == [alignment] and ts.default_alignment is alignment

    tomograms = [t for vs in run.voxel_spacings for t in vs.tomograms]
    assert len(tomograms) == 4
    for tomogram in tomograms:
        assert tomogram.alignment_link.source == "portal"
        assert tomogram.alignment is alignment and tomogram.tilt_series is ts
    assert sorted(t.meta.portal_tomo_id for t in alignment.tomograms) == [18954, 18955, 18956, 18957]


def test_portal_placeholders_are_flagged(portal):
    acquisition = portal["acquisition"]
    acquisition["alignments"].append(_default_alignment(id=12))
    acquisition["alignments"].append(_default_alignment(id=13, alignment_method="fiducial_based"))
    run = portal["open"]().get_run(str(RUN_ID))

    by_name = {a.name: a for a in run.alignments}
    assert by_name["undefined-global-12"].status == "portal_default" and by_name["undefined-global-12"].is_default
    assert by_name["fiducialBased-global-13"].status == "no_per_section"
    ts = run.get_tilt_series("raw")
    assert [a.name for a in ts.alignments][0] == "projectionMatching-local-18924"
    assert [a.name for a in ts.valid_alignments] == ["projectionMatching-local-18924"]


def test_portal_tomogram_linked_to_an_overlay_alignment(portal):
    run = portal["open"]().get_run(str(RUN_ID))
    tomogram = _voxel_spacing(run, 10.012).tomograms[0]
    reference = CopickReferenceVolume(size=(630, 630, 184), voxel_size=10.012)
    mine = run.new_alignment(
        "mine",
        run.get_tilt_series("raw"),
        reference_volume=reference,
        sections=[CopickSectionAlignment(section=i, tilt_angle=-45.0 + 3.0 * i) for i in range(31)],
    )
    assert not mine.read_only

    with pytest.raises(PermissionError, match="Neither"):
        tomogram.set_alignment(run.get_alignment("projectionMatching-local-18924"))
    tomogram.set_alignment(mine)

    reread = _voxel_spacing(portal["open"]().get_run(str(RUN_ID)), 10.012).tomograms[0]
    assert reread.link_id == tomogram.link_id
    assert reread.alignment_link.source == "alignment" and reread.alignment.name == "mine"
    reread.set_alignment(None)
    again = _voxel_spacing(portal["open"]().get_run(str(RUN_ID)), 10.012).tomograms[0]
    assert again.alignment_link.source == "portal"


def test_overlay_tilt_series_next_to_portal_ones(portal):
    run = portal["open"]().get_run(str(RUN_ID))
    mine = run.new_tilt_series("denoised")
    mine.from_numpy(np.zeros((2, 8, 8), dtype=np.float32), pixel_size=1.54)
    reread = portal["open"]().get_run(str(RUN_ID))
    assert sorted((t.ts_type, t.read_only) for t in reread.tilt_series) == [("denoised", False), ("raw", True)]
    assert reread.get_tilt_series("denoised").metadata.pixel_size == 1.54


def test_acquisition_cache_is_memoized(portal):
    root = portal["open"]()
    assert len(root.get_run(str(RUN_ID)).tilt_series) == 1
    assert len(root.get_run(str(RUN_ID)).alignments) == 1
    assert portal["fetch"].calls == 1
    root._ensure_acquisition_cache(force=True)
    assert portal["fetch"].calls == 2
