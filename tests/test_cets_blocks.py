"""CETS-shaped metadata blocks and the CTF model, without a storage backend."""

import json

import pytest
from cets_schema import SCHEMA_ROOT, validate_cets, validate_tilt_series_block
from copick.models import CopickCTF, CopickTiltImage, CopickTiltSeriesMetadata
from copick.util.cets import (
    CETS_TARGET,
    COPICK_ATTRS_KEY,
    TILT_SERIES_SCHEMA,
    image_frame,
    tilt_series_from_attrs,
    tilt_series_to_attrs,
)
from pydantic import ValidationError


def _metadata(n: int = 3, width: int = 65, height: int = 63, **kwargs) -> CopickTiltSeriesMetadata:
    images = [
        CopickTiltImage(
            section=i,
            nominal_tilt_angle=-3.0 + 3.0 * i,
            acquisition_order=[1, 0, 2][i % 3],
            accumulated_dose=3.0 * [1, 0, 2][i % 3],
            exposure_dose=3.0,
            exposure_time=0.5,
            frame_path=f"movie_{i}.eer",
            ctf=CopickCTF(defocus_u=30000 + i, defocus_v=29000, defocus_angle=45, phase_shift=0, fit_resolution=6.5),
        )
        for i in range(n)
    ]
    defaults = {
        "pixel_size": 1.54,
        "width": width,
        "height": height,
        "images": images,
        "tilt_axis_angle": -96.0,
        "voltage": 300.0,
        "spherical_aberration": 2.7,
        "amplitude_contrast": 0.07,
        "amplitude_contrast_source": "default",
        "microscope_model": "Titan Krios",
        "detector_model": "Falcon4i",
    }
    defaults.update(kwargs)
    return CopickTiltSeriesMetadata(**defaults)


def test_vendored_schemas_match_target():
    provenance = json.loads((SCHEMA_ROOT / CETS_TARGET["commit"] / "PROVENANCE.json").read_text())
    assert provenance["commit"] == CETS_TARGET["commit"]
    assert provenance["base"] == CETS_TARGET["base"]


@pytest.mark.parametrize(
    ("u", "v", "angle", "expected"),
    [
        (20000.0, 19000.0, 30.0, (20000.0, 19000.0, 30.0)),
        (19000.0, 20000.0, 30.0, (20000.0, 19000.0, 120.0)),
        (20000.0, 19000.0, -1.76, (20000.0, 19000.0, 178.24)),
        (20000.0, 19000.0, 180.0, (20000.0, 19000.0, 0.0)),
        (19000.0, 20000.0, 135.0, (20000.0, 19000.0, 45.0)),
    ],
)
def test_ctf_is_canonical(u, v, angle, expected):
    ctf = CopickCTF(defocus_u=u, defocus_v=v, defocus_angle=angle)
    assert (ctf.defocus_u, ctf.defocus_v, ctf.defocus_angle) == pytest.approx(expected)
    assert 0.0 <= ctf.defocus_angle < 180.0


def test_ctf_status():
    def status(*ctfs):
        images = [CopickTiltImage(section=i, ctf=c) for i, c in enumerate(ctfs)]
        return _metadata(images=images)

    good = CopickCTF(defocus_u=20000, defocus_v=19000)
    round_ = CopickCTF(defocus_u=20000, defocus_v=20000)
    bad = CopickCTF(defocus_u=0, defocus_v=0)
    assert status(None, None).ctf_status == "absent"
    assert status(good, None).ctf_status == "partial"
    assert status(good, bad).ctf_status == "suspicious"
    assert status(bad, None).ctf_status == "suspicious"
    assert status(good, good).ctf_status == "fitted"
    assert status(round_, round_).ctf_flags == {"astigmatism_fitted": False, "resolution_known": False}
    assert status(good, round_).ctf_flags["astigmatism_fitted"]
    assert _metadata(images=[]).ctf_status == "absent"


@pytest.mark.parametrize(("width", "height", "expected"), [(64, 64, [-32.0, -32.0]), (65, 63, [-32.0, -31.0])])
def test_image_frame_centers_at_floor_half(width, height, expected):
    systems, transforms = image_frame(width, height, 1.5)
    steps = transforms[0]["sequence"]
    assert steps[0]["translation"] == expected
    assert steps[1]["scale"] == [1.5, 1.5]
    assert [a["axis_unit"] for a in systems[0]["axes"]] == ["pixel", "pixel"]
    assert [a["axis_unit"] for a in systems[1]["axes"]] == ["angstrom", "angstrom"]


def test_tilt_series_block_roundtrip_and_validates():
    metadata = _metadata(native={"aretomo3_df_hand": 1}, provenance={"source": "test"})
    attrs = tilt_series_to_attrs("raw", metadata)
    block = attrs[COPICK_ATTRS_KEY]

    assert block["schema"] == TILT_SERIES_SCHEMA
    assert block["cets_target"]["commit"] == CETS_TARGET["commit"]
    assert block["tilt_series"]["images"][1]["id"] == "raw_1"
    assert block["tilt_series"]["acquisition_session_id"] == block["acquisition_session"]["id"]
    assert block["acquisition_session"]["instrument_id"] == block["instrument"]["id"]
    validate_tilt_series_block(block)
    for image in block["tilt_series"]["images"]:
        validate_cets(image, "TiltImage")

    assert "defocus_handedness" not in json.dumps(block)
    assert tilt_series_from_attrs(json.loads(json.dumps(attrs))) == metadata


def test_minimal_block_validates():
    metadata = CopickTiltSeriesMetadata(pixel_size=2.0, width=10, height=12)
    block = tilt_series_to_attrs("raw", metadata)[COPICK_ATTRS_KEY]
    validate_tilt_series_block(block)
    assert tilt_series_from_attrs({COPICK_ATTRS_KEY: block}) == metadata


def test_no_block_reads_as_none():
    assert tilt_series_from_attrs({"multiscales": []}) is None


def test_reader_is_strict():
    attrs = tilt_series_to_attrs("raw", _metadata())

    wrong_schema = json.loads(json.dumps(attrs))
    wrong_schema[COPICK_ATTRS_KEY]["schema"] = "copick-tiltseries/99"
    with pytest.raises(ValueError, match="schema"):
        tilt_series_from_attrs(wrong_schema)

    shifted = json.loads(json.dumps(attrs))
    shifted[COPICK_ATTRS_KEY]["tilt_series"]["images"][0]["coordinate_transformations"][0]["sequence"][0][
        "translation"
    ] = [-32.5, -31.5]
    with pytest.raises(ValueError, match="raw_0.*translation"):
        tilt_series_from_attrs(shifted)

    extra_step = json.loads(json.dumps(attrs))
    extra_step[COPICK_ATTRS_KEY]["tilt_series"]["images"][2]["coordinate_transformations"][0]["sequence"].insert(
        0,
        {"transformation_type": "rot90", "rot90": [[0, -1, 0], [1, 0, 0], [0, 0, 1]]},
    )
    with pytest.raises(ValueError, match="raw_2"):
        tilt_series_from_attrs(extra_step)


def test_sections_must_be_complete():
    with pytest.raises(ValidationError):
        _metadata(images=[CopickTiltImage(section=0), CopickTiltImage(section=0)])
    with pytest.raises(ValidationError):
        _metadata(images=[CopickTiltImage(section=1)])
    unordered = _metadata(images=[CopickTiltImage(section=1), CopickTiltImage(section=0)])
    assert [image.section for image in unordered.images] == [0, 1]


def test_pixel_size_is_rounded_and_positive():
    assert _metadata(pixel_size=1.23456).pixel_size == 1.235
    with pytest.raises(ValidationError):
        _metadata(pixel_size=0)


def test_alignment_document_reader_is_strict():
    from copick.models import CopickAlignmentFile, CopickSectionAlignment
    from copick.util.cets import alignment_from_document, alignment_to_document

    alignment = CopickAlignmentFile(
        name="aretomo3",
        tilt_series="raw",
        tilt_series_portal_id=123,
        sections=[CopickSectionAlignment(section=0, tilt_angle=-30.0)],
    )
    document = json.loads(json.dumps(alignment_to_document(alignment)))
    assert document["alignment"]["tilt_series_id"] == "raw-123"
    assert document["alignment"]["projection_alignments"][0]["tilt_image_id"] == "raw-123_0"
    validate_cets(document["alignment"], "Alignment")
    # Angles are stored as matrices, so they read back up to rounding
    reread = alignment_from_document(document)
    assert reread.model_dump(exclude={"sections"}) == alignment.model_dump(exclude={"sections"})
    assert reread.sections[0].tilt_angle == pytest.approx(-30.0, abs=1e-12)

    wrong_schema = dict(document, schema="copick-alignment/2")
    with pytest.raises(ValueError, match="schema"):
        alignment_from_document(wrong_schema)
    other_series = dict(document, alignment=dict(document["alignment"], tilt_series_id="aligned"))
    with pytest.raises(ValueError, match="tilt_series_id"):
        alignment_from_document(other_series)


def test_tomogram_link_block():
    from copick.models import CopickTomogramLink
    from copick.util.cets import tomogram_link_from_attrs, tomogram_link_to_attrs

    link = CopickTomogramLink(alignment="aretomo3", tilt_series="raw", reference_offset=(1.0, 2.0, 3.0))
    attrs = json.loads(json.dumps(tomogram_link_to_attrs("wbp@10.000", link)))
    validate_cets(attrs[COPICK_ATTRS_KEY]["tomogram"], "Tomogram")
    assert tomogram_link_from_attrs(attrs) == link
    assert tomogram_link_from_attrs({}) is None
