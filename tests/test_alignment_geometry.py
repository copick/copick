"""Alignment geometry: rotations, the CETS projection-alignment encoding and frame conversions."""

import itertools

import numpy as np
import pytest
from cets_schema import validate_cets
from copick.models import CopickSectionAlignment
from copick.util.alignment_geometry import (
    FRAME_CONVENTIONS,
    center,
    cets_to_native_shift,
    decompose_in_plane,
    decompose_tilt,
    image_delta,
    native_to_cets_shift,
    project,
    rot_x,
    rot_y,
    rot_z,
    rotation,
    tomogram_to_reference,
    volume_delta,
)
from copick.util.cets import projection_alignment_to_section, section_to_projection_alignment

RNG = np.random.default_rng(20261015)


def test_rotations_are_active_and_right_handed():
    # Matches the tilt of the CETS example (a tilt of -30 degrees)
    np.testing.assert_allclose(
        rot_y(-30.0),
        [[0.8660254, 0.0, -0.5], [0.0, 1.0, 0.0], [0.5, 0.0, 0.8660254]],
        atol=1e-7,
    )
    np.testing.assert_allclose(rot_z(90.0) @ [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], atol=1e-12)
    np.testing.assert_allclose(rot_x(90.0) @ [0.0, 1.0, 0.0], [0.0, 0.0, 1.0], atol=1e-12)
    np.testing.assert_allclose(rot_y(90.0) @ [0.0, 0.0, 1.0], [1.0, 0.0, 0.0], atol=1e-12)
    np.testing.assert_allclose(rotation(10.0, 5.0, 85.0), rot_z(85.0) @ rot_y(10.0) @ rot_x(5.0))


@pytest.mark.parametrize("seed", range(5))
def test_decompose_roundtrip(seed):
    rng = np.random.default_rng(seed)
    for _ in range(200):
        tilt, x_tilt, in_plane = rng.uniform(-89.9, 89.9), rng.uniform(-30, 30), rng.uniform(-179.9, 179.9)
        assert decompose_tilt(rot_y(tilt) @ rot_x(x_tilt)) == pytest.approx((tilt, x_tilt), abs=1e-9)
        assert decompose_in_plane(rot_z(in_plane)[:2, :2]) == pytest.approx(in_plane, abs=1e-9)


@pytest.mark.parametrize("tilt", [-90.0, 90.0])
def test_decompose_at_vertical_tilt(tilt):
    assert decompose_tilt(rot_y(tilt) @ rot_x(7.0)) == pytest.approx((tilt, 7.0), abs=1e-9)


def test_decompose_refuses_other_matrices():
    with pytest.raises(ValueError, match="tilt matrix"):
        decompose_tilt(rot_z(10.0) @ rot_y(20.0))
    with pytest.raises(ValueError, match="in-plane rotation"):
        decompose_in_plane([[1.0, 0.0], [0.0, -1.0]])


def test_projection_alignment_roundtrip_and_validates():
    for _ in range(100):
        section = CopickSectionAlignment(
            section=int(RNG.integers(0, 60)),
            tilt_angle=RNG.uniform(-70, 70),
            x_tilt=RNG.uniform(-5, 5),
            in_plane_rotation=RNG.uniform(-180, 180),
            shift_x=RNG.uniform(-200, 200),
            shift_y=RNG.uniform(-200, 200),
        )
        encoded = section_to_projection_alignment(section, "raw", "aretomo3")
        validate_cets(encoded, "ProjectionAlignment")
        decoded = projection_alignment_to_section(encoded, "raw")
        assert decoded.section == section.section
        for field in ("tilt_angle", "x_tilt", "in_plane_rotation", "shift_x", "shift_y"):
            assert getattr(decoded, field) == pytest.approx(getattr(section, field), abs=1e-9)
        np.testing.assert_allclose(decoded.matrix(), section.matrix(), atol=1e-12)

    sequence = encoded["sequence"]
    assert [step["name"] for step in sequence] == ["tilt", "project", "in_plane_rotation", "shift"]
    assert np.shape(sequence[0]["affine"]) == (4, 4) and np.shape(sequence[2]["affine"]) == (3, 3)
    assert sequence[1]["dropped_inputs"] == [2]


def test_projection_alignment_reader_is_strict():
    encoded = section_to_projection_alignment(CopickSectionAlignment(section=3, tilt_angle=20.0), "raw", "a")
    with pytest.raises(ValueError, match="not an image of tilt series"):
        projection_alignment_to_section(encoded, "aligned")
    swapped = dict(encoded, sequence=[encoded["sequence"][i] for i in (0, 1, 3, 2)])
    with pytest.raises(ValueError, match="expected the steps"):
        projection_alignment_to_section(swapped, "raw")
    sheared = dict(encoded, sequence=list(encoded["sequence"]))
    sheared["sequence"][0] = dict(sheared["sequence"][0], affine=np.diag([1.0, 2.0, 1.0, 1.0]).tolist())
    with pytest.raises(ValueError, match="tilt matrix"):
        projection_alignment_to_section(sheared, "raw")


def _native_projection(points_corner, matrix, shift, image_size, pixel_size, volume_size, voxel_size, convention):
    """Project points (Angstrom from the corner of voxel 0) as a tool with ``convention`` does, returning pixel
    coordinates of the image from the corner of pixel 0."""
    p = points_corner - center(volume_size, voxel_size, convention.volume_center)
    q = project(p, matrix, shift)
    return (q + center(image_size, pixel_size, convention.image_center)) / pixel_size


def _cets_projection(points_corner, matrix, shift, image_size, pixel_size, volume_size, voxel_size):
    p = points_corner - center(volume_size, voxel_size, "floor")
    q = project(p, matrix, shift)
    return (q + center(image_size, pixel_size, "floor")) / pixel_size


@pytest.mark.parametrize(
    ("image_size", "volume_size", "convention"),
    list(itertools.product([(64, 64), (65, 63)], [(64, 64, 20), (65, 63, 21)], ["ARETOMO3", "RELION"])),
)
def test_frame_conversion_preserves_projections(image_size, volume_size, convention):
    frame = FRAME_CONVENTIONS[convention]
    pixel_size = voxel_size = 1.5
    points = RNG.uniform(0, 1, (50, 3)) * np.asarray(volume_size) * voxel_size
    d_img = image_delta(*image_size, pixel_size, frame.image_center)
    d_vol = volume_delta(volume_size, voxel_size, frame.volume_center)

    naive_errors = []
    for _ in range(20):
        matrix = rotation(RNG.uniform(-60, 60), RNG.uniform(-3, 3), RNG.uniform(-180, 180))
        native_shift = RNG.uniform(-30, 30, 2)
        cets_shift = native_to_cets_shift(native_shift, matrix, d_img, d_vol)

        native = _native_projection(
            points,
            matrix,
            native_shift,
            image_size,
            pixel_size,
            volume_size,
            voxel_size,
            frame,
        )
        cets = _cets_projection(points, matrix, cets_shift, image_size, pixel_size, volume_size, voxel_size)
        np.testing.assert_allclose(cets, native, atol=1e-9)
        np.testing.assert_allclose(cets_to_native_shift(cets_shift, matrix, d_img, d_vol), native_shift, atol=1e-9)

        # Ignoring the centre conventions shifts every projection by the centre offsets
        naive = _cets_projection(points, matrix, native_shift, image_size, pixel_size, volume_size, voxel_size)
        expected_error = -(d_img - (matrix @ d_vol)[:2]) / pixel_size
        np.testing.assert_allclose(naive - native, np.broadcast_to(expected_error, naive.shape), atol=1e-9)
        naive_errors.append(float(np.linalg.norm(expected_error)))

    if convention == "ARETOMO3" and (image_size[0] % 2 or volume_size[0] % 2):
        # ... which is a sizeable part of a pixel on odd sizes
        assert max(naive_errors) >= 0.25
    elif convention == "RELION":
        assert max(naive_errors) == 0.0


def test_half_volume_centre_uses_native_extent():
    # A native volume of 6307.84 A sampled at 4.99 A: the reference has round(V/s) voxels
    delta = volume_delta((1264, 1264, 300), 4.99, "half", native_extent=(6307.84, 6307.84, 1497.0))
    np.testing.assert_allclose(delta, [6307.84 / 2 - 632 * 4.99, 6307.84 / 2 - 632 * 4.99, 1497.0 / 2 - 150 * 4.99])


@pytest.mark.parametrize("convention", ["half", "floor"])
def test_tomogram_sharing_the_rotation_centre(convention):
    # A tomogram binned by 2 relative to the reference shares its centre (in the alignment's native convention)
    reference_size, reference_voxel = (65, 63, 21), 2.0
    tomogram_size, tomogram_voxel = (33, 32, 11), 4.0
    tomogram_centre = center(tomogram_size, tomogram_voxel, convention)
    reference_points = tomogram_to_reference(
        tomogram_centre[None],
        tomogram_size,
        tomogram_voxel,
        reference_size,
        reference_voxel,
        convention,
    )
    expected = volume_delta(reference_size, reference_voxel, convention)
    np.testing.assert_allclose(reference_points[0], expected, atol=1e-12)

    offset = (1.0, -2.0, 3.0)
    explicit = tomogram_to_reference(
        center(tomogram_size, tomogram_voxel, "floor")[None],
        tomogram_size,
        tomogram_voxel,
        reference_size,
        reference_voxel,
        convention,
        reference_offset=offset,
    )
    np.testing.assert_allclose(explicit[0], offset)
