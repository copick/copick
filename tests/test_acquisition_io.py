"""Import and export of tilt series, alignments and CTF fits in the formats of AreTomo3, Warp, RELION 5, IMOD,
CTFFIND4 and SerialEM.

The AreTomo3 golden is the alignment of CryoET Data Portal run 10445/TS_105_5 (``tests/data/acquisition``); the
portal ingested it as alignment 18924, whose records are in ``tests/data/portal``. Round trips use a small synthetic
dose-symmetric tilt series of odd-sized images, where the tools' image and volume centres differ.
"""

import json
from pathlib import Path
from typing import Any, Dict, List

import copick
import mrcfile
import numpy as np
import pytest
import zarr
from click.testing import CliRunner
from copick.models import (
    CopickCTF,
    CopickExcludedSection,
    CopickReferenceVolume,
    CopickSectionAlignment,
    CopickTiltImage,
    CopickTiltSeriesMetadata,
)
from copick.ops.acquisition import (
    add_alignment_from_file,
    add_ctf_from_file,
    add_tilt_series_from_file,
    export_alignment,
    export_alignments,
    export_ctf,
    export_tilt_series,
    write_relion_alignments,
)
from copick.util.acquisition_formats import (
    accumulate_dose,
    map_rows,
    native_to_copick,
    open_stack,
    read_angles,
    read_ctf,
    read_mdoc,
    read_native_alignment,
)
from copick.util.alignment_geometry import cets_to_native_shift, image_delta, volume_delta
from copick.util.portal_acquisition import portal_alignment_file, portal_tilt_series_metadata

DATA = Path(__file__).parent / "data"
GOLDEN_ALN = DATA / "acquisition" / "10445_TS_105_5.aln"
PORTAL = json.loads((DATA / "portal" / "10445_TS_105_5.json").read_text())["acquisition"]

# A dose-symmetric series in acquisition order (as SerialEM writes it), odd image sizes
ANGLES = [0.0, 3.0, -3.0, -6.0, 6.0, 9.0, -9.0]
N = len(ANGLES)
WIDTH, HEIGHT, PIXEL = 65, 63, 2.0
DOSE = 3.0
REFERENCE = CopickReferenceVolume(size=(65, 63, 21), voxel_size=PIXEL)
DARK = 5  # the section at +9 deg


# ---------------------------------------------------------------------------------------------------------------------
# Helpers


def _portal_golden():
    ts = PORTAL["tiltseries"][0]
    frames = {f["id"]: f for f in PORTAL["frames"]}
    metadata = portal_tilt_series_metadata(ts, PORTAL["per_section_parameters"], frames)
    file = portal_alignment_file(
        PORTAL["alignments"][0],
        PORTAL["per_section_alignment_parameters"],
        ts,
        "TS_105_5",
    )
    return metadata, file


def _stack() -> np.ndarray:
    rng = np.random.default_rng(0)
    return rng.normal(size=(N, HEIGHT, WIDTH)).astype(np.float32)


def _write_mrc(path: Path, data: np.ndarray, pixel_size: float = PIXEL) -> Path:
    with mrcfile.new(str(path), overwrite=True) as mrc:
        mrc.set_data(data)
        mrc.voxel_size = pixel_size
    return path


def _write_mdoc(path: Path, angles=ANGLES, z_values=None) -> Path:
    lines = ["PixelSpacing = 2", "Voltage = 300", "ImageFile = TS_01.mrc", f"ImageSize = {WIDTH} {HEIGHT}", ""]
    lines += ["[T =     Tilt axis angle = 85.3, binning = 1  spot = 7  camera = 0]", ""]
    z_values = list(range(len(angles))) if z_values is None else z_values
    for order, (z, angle) in enumerate(zip(z_values, angles, strict=True)):
        lines += [
            f"[ZValue = {z}]",
            f"TiltAngle = {angle + 0.004:.3f}",
            f"ExposureDose = {DOSE}",
            f"PriorRecordDose = {order * DOSE}",
            "ExposureTime = 0.5",
            f"SubFramePath = X:\\frames\\TS_01_{order:03d}_{angle:.1f}.eer",
            f"DateTime = 02-Jul-21  10:{10 + order:02d}:00",
            "",
        ]
    path.write_text("\n".join(lines))
    return path


def _ctf(section: int) -> CopickCTF:
    return CopickCTF(
        defocus_u=25000.0 + 100 * section,
        defocus_v=24000.0 + 100 * section,
        defocus_angle=30.0 + 5 * section,
    )


def _metadata(**changes) -> CopickTiltSeriesMetadata:
    order = list(range(N))
    images = [
        CopickTiltImage(
            section=s,
            nominal_tilt_angle=ANGLES[s],
            acquisition_order=order[s],
            exposure_dose=DOSE,
            accumulated_dose=order[s] * DOSE,
            frame_path=f"TS_01_{s:03d}.eer",
            ctf=_ctf(s),
        )
        for s in range(N)
    ]
    fields = dict(
        pixel_size=PIXEL,
        width=WIDTH,
        height=HEIGHT,
        images=images,
        voltage=300.0,
        spherical_aberration=2.7,
        amplitude_contrast=0.07,
    )
    fields.update(changes)
    return CopickTiltSeriesMetadata(**fields)


def _sections(x_tilt: float = 0.0) -> List[CopickSectionAlignment]:
    rng = np.random.default_rng(1)
    return [
        CopickSectionAlignment(
            section=s,
            tilt_angle=ANGLES[s] + 0.12,
            x_tilt=x_tilt,
            in_plane_rotation=84.5 + 0.01 * s,
            shift_x=float(np.round(rng.uniform(-20, 20), 3)),
            shift_y=float(np.round(rng.uniform(-20, 20), 3)),
        )
        for s in range(N)
        if s != DARK
    ]


def _project(
    payload: Dict[str, Any],
    tmp_path: Path,
    x_tilt: float = 0.0,
    width: int = WIDTH,
    height: int = HEIGHT,
    depth: int = 21,
    run_name: str = "TS_001",
):
    """A run with a tilt series (images, angles, dose, CTF) and an alignment of it."""
    root = copick.from_file(payload["cfg_file"])
    run = root.get_run(run_name)
    metadata = _metadata(width=width, height=height)
    ts = run.new_tilt_series("raw")
    ts.from_numpy(np.zeros((N, height, width), dtype=np.float32), metadata=metadata)
    reference = CopickReferenceVolume(size=(width, height, depth), voxel_size=PIXEL)
    alignment = run.new_alignment(
        "original",
        ts,
        sections=_sections(x_tilt),
        excluded_sections=[CopickExcludedSection(section=DARK, reason="dark")],
        reference_volume=reference,
        source_format="CETS",
    )
    return root, run, ts, alignment


def _assert_same_sections(a, b, angle_tolerance, shift_tolerance):
    assert [s.section for s in a] == [s.section for s in b]
    for x, y in zip(a, b, strict=True):
        assert x.tilt_angle == pytest.approx(y.tilt_angle, abs=angle_tolerance)
        assert x.x_tilt == pytest.approx(y.x_tilt, abs=angle_tolerance)
        assert x.in_plane_rotation == pytest.approx(y.in_plane_rotation, abs=angle_tolerance)
        assert x.shift_x == pytest.approx(y.shift_x, abs=shift_tolerance)
        assert x.shift_y == pytest.approx(y.shift_y, abs=shift_tolerance)


@pytest.fixture
def payload(local):
    return local


# ---------------------------------------------------------------------------------------------------------------------
# Section mapping


def test_map_rows_index_sorted_angle():
    nominal = ANGLES
    assert map_rows(N, None, "index", keys=[2, 0, 1, 3, 4, 5, 6]) == [2, 0, 1, 3, 4, 5, 6]
    # Rows in ascending angle pair with the sections in ascending nominal angle
    ascending = sorted(ANGLES)
    assert map_rows(N, ascending, "sorted", nominal=nominal) == [ANGLES.index(a) for a in ascending]
    # Without angles, the rows are taken to be in ascending angle already
    assert map_rows(N, None, "sorted", nominal=nominal, n_rows=N) == [ANGLES.index(a) for a in ascending]
    shuffled = [9.2, -0.1, 3.1]
    assert map_rows(N, shuffled, "angle", nominal=nominal) == [5, 0, 1]


def test_map_rows_refuses_flipped_signs_and_mismatches():
    asymmetric = [0.0, 3.0, 6.0, 9.0, 12.0, -3.0]
    with pytest.raises(ValueError, match="signs flipped"):
        map_rows(6, [-a + 0.01 for a in [6.0, 9.0, 12.0]], "angle", nominal=asymmetric)
    # Sorted pairing of flipped angles of an asymmetric series contradicts the nominal angles
    with pytest.raises(ValueError, match="differ from the nominal"):
        map_rows(6, [-a for a in asymmetric], "sorted", nominal=asymmetric)
    with pytest.raises(ValueError, match="matches no section"):
        map_rows(N, [1.5], "angle", nominal=ANGLES)
    with pytest.raises(ValueError, match="several rows"):
        map_rows(N, [3.1, 2.9], "angle", nominal=ANGLES)
    with pytest.raises(ValueError, match="outside the tilt series"):
        map_rows(N, None, "index", keys=[0, 7])
    with pytest.raises(ValueError, match="nominal tilt angles"):
        map_rows(N, ANGLES, "angle")


def test_map_rows_index_only_warns_about_mismatching_angles(caplog):
    assert map_rows(3, [10.0, 20.0, 30.0], "index", nominal=[0.0, 1.0, 2.0]) == [0, 1, 2]


# ---------------------------------------------------------------------------------------------------------------------
# AreTomo3 golden: portal alignment 18924


def test_aretomo3_golden_matches_the_portal_import():
    metadata, portal = _portal_golden()
    native = read_native_alignment(str(GOLDEN_ALN), "aretomo3", rigid_only=True)
    imported = native_to_copick(native, metadata, portal.reference_volume)
    assert imported.native_frame == {"image_center": "half", "volume_center": "half"}
    assert any("rigid part" in w for w in imported.warnings)
    _assert_same_sections(imported.sections, portal.sections, 1e-9, 1e-9)


def test_aretomo3_golden_values():
    from cryoet_alignment.io.aretomo3 import AreTomo3ALN

    metadata, portal = _portal_golden()
    aln = AreTomo3ALN.from_file(str(GOLDEN_ALN))
    native = read_native_alignment(str(GOLDEN_ALN), "aretomo3", rigid_only=True)
    imported = native_to_copick(native, metadata, portal.reference_volume)
    d_img = image_delta(4096, 4096, 1.54, "half")
    d_vol = volume_delta(portal.reference_volume.size, 1.54, "half", portal.reference_volume.native_extent)
    # SEC is the 1-based index of the tilt-sorted stack; the portal stack is sorted
    for row, section in zip(aln.GlobalAlignments, imported.sections, strict=True):
        assert section.section == row.sec - 1
        assert section.tilt_angle == pytest.approx(row.tilt, abs=1e-3)
        assert section.in_plane_rotation == pytest.approx(row.rot, abs=1e-3)
        tx, ty = cets_to_native_shift((section.shift_x, section.shift_y), section.matrix(), d_img, d_vol) / 1.54
        assert (tx, ty) == pytest.approx((row.tx, row.ty), abs=1e-3)


def test_aretomo3_local_alignment_needs_rigid_only():
    with pytest.raises(ValueError, match="rigid_only"):
        read_native_alignment(str(GOLDEN_ALN), "aretomo3")


def test_aretomo3_dark_frames_are_kept(tmp_path):
    from cryoet_alignment.io.aretomo3 import AreTomo3ALN
    from cryoet_alignment.io.aretomo3.aln import DarkFrameInfo

    metadata, portal = _portal_golden()
    aln = AreTomo3ALN.from_file(str(GOLDEN_ALN))
    dark = aln.GlobalAlignments[3]
    rigid = AreTomo3ALN(
        RawSize=aln.RawSize,
        NumPatches=0,
        DarkFrames=[DarkFrameInfo(section_idx=3, val2=4, angle=dark.tilt)],
        AlphaOffset=aln.AlphaOffset,
        BetaOffset=aln.BetaOffset,
        GlobalAlignments=[g for i, g in enumerate(aln.GlobalAlignments) if i != 3],
        LocalAlignments=[],
    )
    path = tmp_path / "dark.aln"
    path.write_text(str(rigid))
    imported = native_to_copick(read_native_alignment(str(path), "aretomo3"), metadata, portal.reference_volume)
    assert [(e.section, e.reason) for e in imported.excluded_sections] == [(3, "dark")]
    assert 3 not in {s.section for s in imported.sections}


def _golden_ctf_file(path: Path) -> Path:
    """An AreTomo3 _CTF.txt of the portal's CTF fits: one row per section of the tilt-sorted stack."""
    rows = sorted(PORTAL["per_section_parameters"], key=lambda r: r["z_index"])
    lines = ["# Columns: #1 micrograph number; #2 - defocus 1 [A]; #3 - defocus 2; ..."]
    for i, r in enumerate(rows):
        lines.append(
            f"{i + 1:4d} {r['major_defocus']:8.2f} {r['minor_defocus']:8.2f} {r['astigmatic_angle']:8.2f} "
            f"{r['phase_shift']:9.4f} {0.05:8.4f} {6.5:8.4f}",
        )
    path.write_text("\n".join(lines) + "\n")
    return path


def _golden_tlt_file(path: Path) -> Path:
    frames = {f["id"]: f for f in PORTAL["frames"]}
    rows = sorted(PORTAL["per_section_parameters"], key=lambda r: r["z_index"])
    lines = []
    for r in rows:
        frame = frames[r["frame_id"]]
        lines.append(f"{r['raw_angle']:8.2f}  {frame['acquisition_order'] + 1:4d}  {frame['exposure_dose']:8.2f}")
    path.write_text("\n".join(lines) + "\n")
    return path


def test_aretomo3_golden_ctf_and_tlt(tmp_path):
    from copick.ops.acquisition import apply_acquisition, apply_ctf

    metadata, _ = _portal_golden()
    bare = metadata.model_copy(
        update={
            "images": [
                CopickTiltImage(section=i.section, nominal_tilt_angle=i.nominal_tilt_angle) for i in metadata.images
            ],
        },
    )
    table = read_ctf(str(_golden_ctf_file(tmp_path / "TS_CTF.txt")), "aretomo3")
    with_ctf = apply_ctf(bare, 31, table)
    for expected, image in zip(metadata.images, with_ctf.images, strict=True):
        assert image.ctf.defocus_u == pytest.approx(expected.ctf.defocus_u, abs=1e-2)
        assert image.ctf.defocus_v == pytest.approx(expected.ctf.defocus_v, abs=1e-2)
        assert image.ctf.defocus_angle == pytest.approx(expected.ctf.defocus_angle, abs=1e-3)
        assert image.ctf.fit_resolution == 6.5

    tlt = read_angles(str(_golden_tlt_file(tmp_path / "TS_TLT.txt")))
    with_tlt = apply_acquisition(bare, 31, tlt)
    for expected, image in zip(metadata.images, with_tlt.images, strict=True):
        assert image.acquisition_order == expected.acquisition_order
        assert image.accumulated_dose == pytest.approx(expected.accumulated_dose, abs=0.5)


# ---------------------------------------------------------------------------------------------------------------------
# Stacks, mdoc, add tiltseries


def test_read_mdoc_table(tmp_path):
    table = read_mdoc(str(_write_mdoc(tmp_path / "TS_01.mrc.mdoc")))
    assert table.keys == list(range(N))
    assert table.acquisition_order == list(range(N))
    assert table.accumulated_dose == [i * DOSE for i in range(N)]
    assert table.frame_paths[2] == "TS_01_002_-3.0.eer"
    assert (table.pixel_size, table.voltage, table.tilt_axis_angle) == (2.0, 300.0, 85.3)
    assert accumulate_dose([1.0, 2.0, 4.0], [2, 0, 1]) == [6.0, 0.0, 2.0]


@pytest.mark.parametrize("case", pytest.common_cases)
def test_add_tiltseries_from_mrc_and_mdoc(request, case, tmp_path):
    payload = request.getfixturevalue(case)
    root = copick.from_file(payload["cfg_file"])
    data = _stack()
    stack = _write_mrc(tmp_path / "TS_01.mrc", data)
    _write_mdoc(tmp_path / "TS_01.mrc.mdoc")

    ts = add_tilt_series_from_file(root, "TS_001", "raw", stack, spherical_aberration=2.7, amplitude_contrast=0.07)
    metadata = copick.from_file(payload["cfg_file"]).get_run("TS_001").get_tilt_series("raw").metadata
    assert (metadata.pixel_size, metadata.width, metadata.height, metadata.n_sections) == (PIXEL, WIDTH, HEIGHT, N)
    assert metadata.nominal_tilt_angles == pytest.approx([a + 0.004 for a in ANGLES])
    assert [i.acquisition_order for i in metadata.images] == list(range(N))
    assert [i.accumulated_dose for i in metadata.images] == [i * DOSE for i in range(N)]
    assert metadata.images[1].frame_path == "TS_01_001_3.0.eer"
    assert (metadata.voltage, metadata.spherical_aberration, metadata.tilt_axis_angle) == (300.0, 2.7, 85.3)
    assert metadata.amplitude_contrast_source == "user"
    assert "mdoc" in metadata.provenance["source"]
    np.testing.assert_array_equal(ts.numpy(), data)

    with pytest.raises(ValueError, match="exists"):
        add_tilt_series_from_file(root, "TS_001", "raw", stack)


def test_add_tiltseries_sorted_by_angle_with_rawtlt_and_ctf(payload, tmp_path):
    root = copick.from_file(payload["cfg_file"])
    data = _stack()
    stack = _write_mrc(tmp_path / "TS_01.st", data)
    rawtlt = tmp_path / "TS_01.rawtlt"
    rawtlt.write_text("".join(f"{a}\n" for a in ANGLES))
    # The mdoc lists the images in another order than the stack: matched by angle
    order = [3, 1, 0, 2, 6, 4, 5]
    _write_mdoc(tmp_path / "TS_01.mdoc", angles=[ANGLES[i] for i in order], z_values=list(range(N)))
    # A CTFFIND4 file in stack order
    ctf = tmp_path / "TS_01_ctffind4.txt"
    ctf.write_text(
        "# CTFFIND4\n"
        + "".join(f"{s + 1} {25000 + 100 * s} {24000 + 100 * s} {30 + 5 * s} 0.0 0.05 7.5\n" for s in range(N)),
    )

    ts = add_tilt_series_from_file(
        root,
        "TS_001",
        "raw",
        stack,
        angles=rawtlt,
        ctf=ctf,
        sort_by_angle=True,
        mdoc=tmp_path / "TS_01.mdoc",
    )
    metadata = ts.metadata
    by_angle = sorted(range(N), key=lambda s: ANGLES[s])
    assert metadata.nominal_tilt_angles == sorted(ANGLES)
    np.testing.assert_array_equal(ts.numpy(), data[by_angle])
    # Acquisition data followed the images: the mdoc's k-th row was acquired k-th
    for new, old in enumerate(by_angle):
        image = metadata.images[new]
        assert image.acquisition_order == order.index(old)
        assert image.ctf.defocus_u == 25000 + 100 * old
    assert metadata.ctf_status == "fitted"


def test_add_tiltseries_needs_a_pixel_size(payload, tmp_path):
    root = copick.from_file(payload["cfg_file"])
    stack = tmp_path / "TS_01.tif"
    import tifffile

    tifffile.imwrite(str(stack), _stack())
    with pytest.raises(ValueError, match="pixel size"):
        add_tilt_series_from_file(root, "TS_001", "raw", stack)
    ts = add_tilt_series_from_file(root, "TS_001", "raw", stack, pixel_size=PIXEL)
    assert ts.metadata.pixel_size == PIXEL
    assert ts.metadata.images == []
    # Without an acquisition order, a dose per tilt gives the exposure dose only
    ts = add_tilt_series_from_file(root, "TS_001", "raw", stack, pixel_size=PIXEL, dose_per_tilt=2.0, overwrite=True)
    assert [(i.exposure_dose, i.accumulated_dose) for i in ts.metadata.images] == [(2.0, None)] * N


def test_open_stack_formats(tmp_path):
    import tifffile

    data = _stack()
    _write_mrc(tmp_path / "a.mrcs", data)
    tifffile.imwrite(str(tmp_path / "a.tiff"), data)
    zarr.save_array(str(tmp_path / "a.zarr"), data)
    for name, pixel_size in (("a.mrcs", PIXEL), ("a.tiff", None), ("a.zarr", None)):
        with open_stack(str(tmp_path / name)) as stack:
            assert stack.shape == data.shape and stack.pixel_size == pixel_size
            np.testing.assert_array_equal(np.asarray(stack.data[3]), data[3])
    with pytest.raises(ValueError, match="file type"):
        open_stack(str(tmp_path / "a.raw")).__enter__()


# ---------------------------------------------------------------------------------------------------------------------
# Alignment round trips


def _reimport(root, run, path, fmt, name, **kwargs):
    return add_alignment_from_file(root, run.name, path, fmt, "raw", name=name, **kwargs)


def test_aretomo3_round_trip(payload, tmp_path):
    root, run, ts, alignment = _project(payload, tmp_path)
    written = export_alignment(alignment, tmp_path / "out", "aretomo3", include_ctf=True)
    assert [p.name for p in written] == ["TS_001.aln", "TS_001_TLT.txt", "TS_001_CTF.txt"]
    again = _reimport(root, run, written[0], "aretomo3", "back")
    # .aln precision: TILT 0.01 deg, ROT 1e-4 deg, shifts 1e-3 px
    _assert_same_sections(again.file.sections, alignment.file.sections, 5e-3, 2e-3 * PIXEL)
    assert [(e.section, e.reason) for e in again.file.excluded_sections] == [(DARK, "dark")]
    assert again.file.native_frame == {"image_center": "half", "volume_center": "half"}
    assert again.file.reference_volume.size == REFERENCE.size

    # The _TLT.txt lists the stack in its order, the _CTF.txt the tilt-sorted stack
    tlt = read_angles(str(written[1]))
    assert tlt.angles == ANGLES and tlt.acquisition_order == list(range(N))
    ctf = read_ctf(str(written[2]), "aretomo3")
    assert [c.defocus_u for c in ctf.ctfs] == [25000.0 + 100 * ANGLES.index(a) for a in sorted(ANGLES)]


def test_aretomo3_export_refuses_x_tilt(payload, tmp_path):
    root, run, ts, alignment = _project(payload, tmp_path, x_tilt=0.3)
    with pytest.raises(ValueError, match="drop_x_tilt"):
        export_alignment(alignment, tmp_path / "out", "aretomo3")
    written = export_alignment(alignment, tmp_path / "out", "aretomo3", drop_x_tilt=True)
    again = _reimport(root, run, written[0], "aretomo3", "back")
    assert all(s.x_tilt == 0.0 for s in again.file.sections)


def test_warp_round_trip_with_ctf(payload, tmp_path):
    root, run, ts, alignment = _project(payload, tmp_path, x_tilt=0.3)
    (path,) = export_alignment(alignment, tmp_path / "out", "warp", include_ctf=True)
    again = _reimport(root, run, path, "warp", "back")
    _assert_same_sections(again.file.sections, alignment.file.sections, 1e-6, 1e-5)
    assert [(e.section, e.reason) for e in again.file.excluded_sections] == [(DARK, "excluded")]

    table = read_ctf(str(path), "warp")
    from copick.ops.acquisition import apply_ctf

    restored = apply_ctf(
        ts.metadata.model_copy(
            update={"images": [CopickTiltImage(section=s, nominal_tilt_angle=a) for s, a in enumerate(ANGLES)]},
        ),
        N,
        table,
    )
    for s, image in enumerate(restored.images):
        assert image.ctf.defocus_u == pytest.approx(_ctf(s).defocus_u, abs=1e-2)
        assert image.ctf.defocus_angle == pytest.approx(_ctf(s).defocus_angle, abs=1e-3)


def test_warp_refuses_flipped_angles_and_varying_x_tilt(payload, tmp_path):
    root, run, ts, alignment = _project(payload, tmp_path)
    (path,) = export_alignment(alignment, tmp_path / "out", "warp")
    # Angles as Warp's ts_import --dont_invert stores them: the stage angles themselves
    from xml.etree import ElementTree

    tree = ElementTree.parse(path)
    angles = tree.getroot().find("Angles")
    angles.text = "\n".join(str(-float(v)) for v in angles.text.split())
    flipped = tmp_path / "flipped.xml"
    tree.write(flipped)
    with pytest.raises(ValueError, match="signs flipped"):
        _reimport(root, run, flipped, "warp", "flipped")

    file = alignment.file
    file.sections = [s.model_copy(update={"x_tilt": 0.1 * s.section}) for s in file.sections]
    with pytest.raises(ValueError, match="volume_x_rotation varies"):
        export_alignment(alignment, tmp_path / "out", "warp")


def test_relion_round_trip_keeps_nominal_angles(payload, tmp_path):
    from cryoet_alignment.io.relion import RelionAlignment

    root, run, ts, alignment = _project(payload, tmp_path, x_tilt=0.3)
    written = export_alignments(root, "original", tmp_path / "out", "relion", include_ctf=True)
    assert [p.name for p in written] == ["tomograms.star", "TS_001.star"]
    relion = RelionAlignment.from_file(written[0])
    # RELION rows: the kept tilts in ascending angle, with the nominal (not refined) stage angles
    kept = sorted((s for s in range(N) if s != DARK), key=lambda s: ANGLES[s])
    assert [e.nominal_stage_tilt_angle for e in relion.entries] == [ANGLES[s] for s in kept]
    assert [e.y_tilt for e in relion.entries] == pytest.approx([ANGLES[s] + 0.12 for s in kept])
    assert [e.pre_exposure for e in relion.entries] == [s * DOSE for s in kept]
    assert [e.defocus_u for e in relion.entries] == [25000.0 + 100 * s for s in kept]
    assert relion.volume_size_px == REFERENCE.size and relion.voltage == 300.0

    again = _reimport(root, run, written[0], "relion", "back")
    _assert_same_sections(again.file.sections, alignment.file.sections, 1e-6, 1e-5)
    assert again.file.native_frame == {"image_center": "floor", "volume_center": "floor"}
    assert [e.section for e in again.file.excluded_sections] == [DARK]


def test_relion_export_needs_voltage_and_cs(payload, tmp_path):
    root, run, ts, alignment = _project(payload, tmp_path)
    ts.store_metadata(ts.metadata.model_copy(update={"voltage": None}))
    with pytest.raises(ValueError, match="voltage"):
        export_alignment(alignment, tmp_path / "out", "relion")


def test_relion_several_runs_share_one_tomograms_star(payload, tmp_path):
    from cryoet_alignment.io.relion import RelionAlignment

    root, run, ts, alignment = _project(payload, tmp_path)
    first = export_alignment(alignment, tmp_path / "out", "relion", relion_tomo_name="TS_a")
    second = export_alignment(alignment, tmp_path / "out", "relion", relion_tomo_name="TS_b")
    star = tmp_path / "out" / "tomograms.star"
    write_relion_alignments([first, second], star)
    assert RelionAlignment.from_file(star, tomo_name="TS_b").n_tilts == N - 1
    with pytest.raises(ValueError, match="unique"):
        write_relion_alignments([first, first], star)


def test_imod_round_trip_even_sizes_and_odd_refusal(payload, tmp_path):
    root, run, ts, alignment = _project(payload, tmp_path, x_tilt=0.3, width=64, height=62, depth=20)
    written = export_alignment(alignment, tmp_path / "out", "imod")
    names = sorted(p.name for p in written)
    assert {"TS_001.xf", "TS_001.tlt", "TS_001.xtilt", "tilt.com", "newst.com"} <= set(names)
    # The volume comes from tilt.com (FULLIMAGE, THICKNESS)
    again = _reimport(root, run, tmp_path / "out" / "TS_001" / "TS_001.xf", "imod", "back")
    assert again.file.reference_volume.size == (64, 62, 20)
    # .xf precision: matrix 1e-7, shifts 1e-3 px
    _assert_same_sections(again.file.sections, alignment.file.sections, 1e-4, 2e-3 * PIXEL)
    assert [e.section for e in again.file.excluded_sections] == [DARK]

    root2, run2, ts2, odd = _project(payload, tmp_path, run_name="TS_002")
    with pytest.raises(ValueError, match="assume_frame"):
        export_alignment(odd, tmp_path / "odd", "imod")
    export_alignment(odd, tmp_path / "odd", "imod", assume_frame="floor")


def test_cross_format_chain_with_odd_sizes(payload, tmp_path):
    """AreTomo3 -> copick -> RELION -> copick -> AreTomo3 reproduces the AreTomo3 file; ignoring the centres does not."""
    from cryoet_alignment.io.aretomo3 import AreTomo3ALN

    root, run, ts, original = _project(payload, tmp_path)
    (aln_path, *_) = export_alignment(original, tmp_path / "a", "aretomo3")
    first = _reimport(root, run, aln_path, "aretomo3", "first")
    star = export_alignments(root, "first", tmp_path / "r", "relion")[0]
    second = _reimport(root, run, star, "relion", "second")
    _assert_same_sections(second.file.sections, first.file.sections, 1e-6, 1e-5)
    (back, *_) = export_alignment(second, tmp_path / "b", "aretomo3")

    a, b = AreTomo3ALN.from_file(str(aln_path)), AreTomo3ALN.from_file(str(back))
    for x, y in zip(a.GlobalAlignments, b.GlobalAlignments, strict=True):
        assert x.sec == y.sec
        assert (y.tx, y.ty) == pytest.approx((x.tx, x.ty), abs=1e-6 + 1e-3)
        assert y.tilt == pytest.approx(x.tilt, abs=1e-6) and y.rot == pytest.approx(x.rot, abs=1e-6)

    # Copying AreTomo3's pixel shifts into RELION's Angstrom shifts without the centre conversion is off by >= 0.25 px
    from cryoet_alignment.io.relion import RelionAlignment

    relion = RelionAlignment.from_file(star)
    naive = [(g.tx, g.ty) for g in a.GlobalAlignments]
    ours = [(e.x_shift_angst / PIXEL, e.y_shift_angst / PIXEL) for e in relion.entries]
    assert max(max(abs(n[0] - o[0]), abs(n[1] - o[1])) for n, o in zip(naive, ours, strict=True)) >= 0.25


def test_reference_tomogram_link_and_rebase(payload, tmp_path):
    root, run, ts, alignment = _project(payload, tmp_path)
    (aln_path, *_) = export_alignment(alignment, tmp_path / "out", "aretomo3")
    tomogram = run.get_voxel_spacing(10.0).new_tomogram("aretomo3", exist_ok=True)
    tomogram.from_numpy(np.zeros((21, 63, 65), dtype=np.float32))
    imported = _reimport(root, run, aln_path, "aretomo3", "linked", reference_tomogram="aretomo3@10.0")
    assert imported.file.reference_volume.size == (65, 63, 21)
    assert imported.file.reference_volume.voxel_size == 10.0
    reopened = copick.from_file(payload["cfg_file"]).get_run("TS_001")
    assert reopened.get_voxel_spacing(10.0).get_tomograms("aretomo3")[0].alignment.name == "linked"


def test_rebased_sections_project_like_the_alignment(payload, tmp_path):
    """Sections rebased to a tomogram project its points as the alignment does through the tomogram."""
    from copick.util.acquisition_formats import rebase_sections, tomogram_reference
    from copick.util.alignment_geometry import center, project

    root, run, ts, alignment = _project(payload, tmp_path)
    tomogram = run.get_voxel_spacing(10.0).new_tomogram("other", exist_ok=True)
    tomogram.from_numpy(np.zeros((5, 13, 14), dtype=np.float32))
    for frame in ("half", "floor"):
        alignment.meta.native_frame = {"image_center": frame, "volume_center": frame}
        reference = tomogram_reference(tomogram)
        rebased = rebase_sections(alignment.file, reference)
        points = np.array([[10.0, 20.0, 5.0], [125.0, 3.0, 40.0]])
        expected = alignment.project(points, tomogram=tomogram)
        relative = points - center(reference.size, reference.voxel_size, "floor")
        image_center = center((WIDTH, HEIGHT), PIXEL, "floor")
        for section in rebased:
            ours = (project(relative, section.matrix(), (section.shift_x, section.shift_y)) + image_center) / PIXEL
            np.testing.assert_allclose(ours, expected[section.section], atol=1e-9)


def test_cdp_export_matches_the_hub(payload, tmp_path):
    root, run, ts, alignment = _project(payload, tmp_path)
    (path,) = export_alignment(alignment, tmp_path / "out", "cdp")
    document = json.loads(path.read_text())
    assert len(document["per_section_alignment_parameters"]) == N - 1
    assert document["volume_dimension"] == {"x": 130.0, "y": 126.0, "z": 42.0}


# ---------------------------------------------------------------------------------------------------------------------
# CTF and tilt-series export


def test_ctf_export_and_import(payload, tmp_path):
    root, run, ts, alignment = _project(payload, tmp_path)
    path = export_ctf(ts, tmp_path / "out")
    ts.store_metadata(
        ts.metadata.model_copy(update={"images": [i.model_copy(update={"ctf": None}) for i in ts.metadata.images]}),
    )
    assert ts.metadata.ctf_status == "absent"
    add_ctf_from_file(root, run.name, "raw", path)
    restored = copick.from_file(payload["cfg_file"]).get_run(run.name).get_tilt_series("raw").metadata
    for s, image in enumerate(restored.images):
        assert image.ctf.defocus_u == pytest.approx(_ctf(s).defocus_u, abs=1e-2)
        assert image.ctf.defocus_angle == pytest.approx(_ctf(s).defocus_angle, abs=1e-2)


def test_partial_ctf_is_not_exported(payload, tmp_path):
    root, run, ts, alignment = _project(payload, tmp_path)
    images = list(ts.metadata.images)
    images[2] = images[2].model_copy(update={"ctf": None})
    ts.store_metadata(ts.metadata.model_copy(update={"images": images}))
    with pytest.raises(ValueError, match="partial"):
        export_ctf(ts, tmp_path / "out")
    with pytest.raises(ValueError, match="partial"):
        export_alignment(alignment, tmp_path / "out", "warp", include_ctf=True)


@pytest.mark.parametrize("output_format", ["mrc", "tiff", "zarr"])
def test_export_tiltseries(payload, tmp_path, output_format):
    root = copick.from_file(payload["cfg_file"])
    stack = _write_mrc(tmp_path / "TS_01.mrc", _stack())
    _write_mdoc(tmp_path / "TS_01.mrc.mdoc")
    ts = add_tilt_series_from_file(root, "TS_001", "raw", stack)
    written = export_tilt_series(ts, tmp_path / "out", output_format, angles="aretomo3-tlt")
    with open_stack(str(written[0]), "zarr" if output_format == "zarr" else None) as exported:
        np.testing.assert_array_equal(np.asarray(exported.data[:]), ts.numpy())
        if output_format != "tiff":
            assert exported.pixel_size == PIXEL
    tlt = read_angles(str(written[1]))
    assert tlt.angles == pytest.approx([a + 0.004 for a in ANGLES], abs=1e-2)
    assert tlt.acquisition_order == list(range(N))
    assert tlt.exposure_dose == [DOSE] * N


def test_export_level_one_pixel_size(payload, tmp_path):
    root = copick.from_file(payload["cfg_file"])
    ts = add_tilt_series_from_file(root, "TS_001", "raw", _write_mrc(tmp_path / "TS_01.mrc", _stack()), mdoc=None)
    (mrc_path,) = export_tilt_series(ts, tmp_path / "out", "mrc", level=1, angles=None)
    with mrcfile.open(str(mrc_path)) as mrc:
        assert mrc.data.shape == (N, 32, 33) and float(mrc.voxel_size.x) == pytest.approx(2 * PIXEL)
    with pytest.raises(ValueError, match="nominal tilt angles"):
        export_tilt_series(ts, tmp_path / "out", "mrc")


# ---------------------------------------------------------------------------------------------------------------------
# CLI


def test_cli_round_trip(payload, tmp_path):
    from copick.cli.cli import _cli

    config = str(payload["cfg_file"])
    stack = _write_mrc(tmp_path / "TS_001.mrc", _stack())
    _write_mdoc(tmp_path / "TS_001.mrc.mdoc")
    runner = CliRunner()

    def invoke(*args):
        result = runner.invoke(_cli, list(args), catch_exceptions=False)
        assert result.exit_code == 0, result.output
        return result

    invoke("add", "tiltseries", str(stack), "-c", config, "--run", "TS_001", "--cs", "2.7")
    root, run, ts, alignment = _project_alignment_only(payload)
    out = tmp_path / "out"
    invoke(
        "export",
        "alignment",
        "-c",
        config,
        "--alignment-uri",
        "original",
        "-r",
        "TS_001",
        "--output-dir",
        str(out),
        "--output-format",
        "aretomo3",
    )
    invoke(
        "add",
        "alignment",
        str(out / "TS_001.aln"),
        "--format",
        "aretomo3",
        "--run",
        "TS_001",
        "--name",
        "cli",
        "-c",
        config,
    )
    invoke(
        "export",
        "tiltseries",
        "-c",
        config,
        "--tiltseries-uri",
        "raw",
        "--output-dir",
        str(out),
        "--angles",
        "rawtlt",
    )
    assert (out / "TS_001.mrc").exists() and (out / "TS_001.rawtlt").exists()
    reopened = copick.from_file(config).get_run("TS_001")
    assert reopened.get_alignment("cli").file.source_format == "ARETOMO3"

    volume = tmp_path / "tomo.mrc"
    _write_mrc(volume, np.zeros((21, 63, 65), dtype=np.float32), pixel_size=10.0)
    invoke(
        "add",
        "tomogram",
        str(volume),
        "-c",
        config,
        "--run",
        "TS_001",
        "--tomo-type",
        "linked",
        "--alignment",
        "cli",
    )
    tomogram = copick.from_file(config).get_run("TS_001").get_voxel_spacing(10.0).get_tomograms("linked")[0]
    assert tomogram.alignment.name == "cli"

    result = runner.invoke(
        _cli,
        ["add", "alignment", str(GOLDEN_ALN), "--format", "aretomo3", "--run", "TS_001", "-c", config],
    )
    assert result.exit_code != 0


def _project_alignment_only(payload):
    root = copick.from_file(payload["cfg_file"])
    run = root.get_run("TS_001")
    ts = run.get_tilt_series("raw")
    alignment = run.new_alignment(
        "original",
        ts,
        sections=_sections(),
        excluded_sections=[CopickExcludedSection(section=DARK, reason="dark")],
        reference_volume=REFERENCE,
    )
    return root, run, ts, alignment
