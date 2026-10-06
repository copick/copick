"""Filament curves (``copick.util.filaments`` and ``CopickFilamentCurve``): the specification in docs/datamodel.md.

``tests/data/filament_curves.json`` holds reference cases for other implementations of the specification. Regenerate it
with ``python tests/test_filament_curves.py`` after a deliberate change to the algorithm.
"""

import json
from pathlib import Path

import numpy as np
import pytest
from copick.models import CopickFilament, CopickFilamentCurve
from copick.util.filaments import (
    control_points_from_polyline,
    curve_anchors,
    curve_is_current,
    distances_to_polyline,
    evaluate_curve,
    reverse_knots,
)
from pydantic import ValidationError

FIXTURE = Path(__file__).parent / "data" / "filament_curves.json"

S_CURVE = [[0.0, 0.0, 0.0], [40.0, 10.0, 0.0], [45.0, 60.0, 5.0], [120.0, 80.0, 10.0], [200.0, 40.0, 20.0]]
CUBIC = {
    "degree": 3,
    "knots": [0.0, 0.0, 0.0, 0.0, 0.3, 0.7, 1.0, 1.0, 1.0, 1.0],
    "control_points": [[0, 0, 0], [30, 40, 0], [80, 50, 10], [120, 0, 20], [160, -20, 25], [200, 30, 30]],
}

REFERENCE_CASES = [
    {
        "name": "two points",
        "kind": "catmull-rom",
        "alpha": 0.5,
        "step": 10.0,
        "control_points": [[0, 0, 0], [95, 0, 0]],
    },
    {"name": "s-curve, centripetal", "kind": "catmull-rom", "alpha": 0.5, "step": 10.0, "control_points": S_CURVE},
    {"name": "s-curve, uniform", "kind": "catmull-rom", "alpha": 0.0, "step": 10.0, "control_points": S_CURVE},
    {"name": "s-curve, chordal", "kind": "catmull-rom", "alpha": 1.0, "step": 10.0, "control_points": S_CURVE},
    {"name": "s-curve, linear", "kind": "linear", "step": 10.0, "control_points": S_CURVE},
    {"name": "cubic B-spline", "kind": "bspline", "step": 10.0, **CUBIC},
    {
        "name": "quadratic B-spline",
        "kind": "bspline",
        "step": 7.5,
        "degree": 2,
        "knots": [0.0, 0.0, 0.0, 0.5, 1.0, 1.0, 1.0],
        "control_points": [[0, 0, 0], [50, 80, 0], [100, -20, 15], [150, 30, 30]],
    },
]


def _evaluate(case):
    return evaluate_curve(
        case["control_points"],
        case["step"],
        kind=case["kind"],
        alpha=case.get("alpha"),
        degree=case.get("degree"),
        knots=case.get("knots"),
    )


def _arc_gaps(points, curve_points):
    """Spacing of ``points`` measured along the dense curve ``curve_points`` they were sampled from."""
    seg = np.linalg.norm(np.diff(curve_points, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    # arc-length position of each point: its nearest dense vertex
    nearest = [int(np.argmin(np.linalg.norm(curve_points - p, axis=1))) for p in points]
    return np.diff(s[nearest])


# ---------------------------------------------------------------------------
# The reference cases
# ---------------------------------------------------------------------------


def test_reference_cases():
    data = json.loads(FIXTURE.read_text())
    assert [c["name"] for c in data["cases"]] == [c["name"] for c in REFERENCE_CASES]
    for case in data["cases"]:
        got = _evaluate(case)
        expected = np.asarray(case["points"])
        assert got.shape == expected.shape, case["name"]
        assert np.max(np.abs(got - expected)) < 1e-6, case["name"]


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["catmull-rom", "linear"])
def test_curve_passes_through_its_control_points(kind):
    points = evaluate_curve(S_CURVE, 10.0, kind=kind)
    # each control point is one of the points
    assert all(np.min(np.linalg.norm(points - p, axis=1)) == 0 for p in np.asarray(S_CURVE, dtype=float))


@pytest.mark.parametrize("case", REFERENCE_CASES, ids=lambda c: c["name"])
def test_points_span_the_curve_evenly(case):
    points = _evaluate(case)
    start, end = (np.asarray(case["control_points"][0]), np.asarray(case["control_points"][-1]))
    assert np.array_equal(points[0], start) and np.array_equal(points[-1], end)
    dense = _evaluate({**case, "step": case["step"] / 50})
    assert _arc_gaps(points, dense).max() <= case["step"] + 0.2
    anchors = curve_anchors(
        case["control_points"],
        kind=case["kind"],
        degree=case.get("degree"),
        knots=case.get("knots"),
    )
    assert all(np.min(np.linalg.norm(points - a, axis=1)) < 1e-9 for a in anchors)


def test_collinear_control_points_give_a_straight_even_line():
    points = evaluate_curve([[0, 0, 0], [30, 0, 0], [60, 0, 0]], 7.0)
    assert np.allclose(points[:, 1:], 0)
    assert np.allclose(np.diff(points[:, 0]), 6.0) and len(points) == 11


def test_linear_follows_the_control_polyline():
    points = evaluate_curve(S_CURVE, 10.0, kind="linear")
    assert distances_to_polyline(points, S_CURVE).max() < 1e-9


@pytest.mark.parametrize("degree", [1, 2, 3])
def test_bspline_matches_scipy(degree):
    scipy_interpolate = pytest.importorskip("scipy.interpolate")
    rng = np.random.default_rng(degree)
    theta = np.linspace(0, 4, 80)
    xyz = np.c_[50 + 20 * np.cos(theta), 50 + 20 * np.sin(theta), 5 * theta] + rng.normal(0, 0.3, (80, 3))
    tck, _ = scipy_interpolate.splprep(xyz.T, s=10.0, k=degree)

    curve = CopickFilamentCurve.from_tck(tck, step=10.0, smoothing=10.0, scale=10.0)
    assert curve.kind == "bspline" and curve.degree == degree and curve.smoothing == 10.0
    points = curve.evaluate()
    reference = np.stack(scipy_interpolate.splev(np.linspace(0, 1, 20000), tck), axis=1) * 10.0
    assert distances_to_polyline(points, reference).max() < 1e-2
    at_knots = np.stack(scipy_interpolate.splev(np.unique(tck[0]), tck), axis=1) * 10.0
    assert np.allclose(curve.anchors(), at_knots)


def test_reversed_bspline_is_the_same_curve_backwards():
    forward = evaluate_curve(CUBIC["control_points"], 1.0, kind="bspline", degree=3, knots=CUBIC["knots"])
    backward = evaluate_curve(
        CUBIC["control_points"][::-1],
        1.0,
        kind="bspline",
        degree=3,
        knots=reverse_knots(CUBIC["knots"]),
    )
    assert np.allclose(backward[0], forward[-1]) and np.allclose(backward[-1], forward[0])
    assert distances_to_polyline(backward, forward).max() < 1e-3


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"kind": "catmull-rom", "control_points": [[0, 0, 0]]}, "at least two control points"),
        ({"kind": "linear", "control_points": [[0, 0, 0], [np.nan, 0, 0]]}, "finite"),
        ({"kind": "catmull-rom", "control_points": [[0, 0, 0], [0, 0, 0], [5, 0, 0]]}, "coincide"),
        ({"kind": "catmull-rom", "alpha": 1.5, "control_points": [[0, 0, 0], [5, 0, 0]]}, "alpha"),
        ({"kind": "linear", "step": 0, "control_points": [[0, 0, 0], [5, 0, 0]]}, "greater than 0"),
        ({**CUBIC, "kind": "bspline", "knots": CUBIC["knots"][:-1]}, "needs 10 knots"),
        ({**CUBIC, "kind": "bspline", "knots": [0, 0, 0, 0, 0.7, 0.3, 1, 1, 1, 1]}, "non-decreasing"),
        ({**CUBIC, "kind": "bspline", "knots": [0, 0, 0, 0.1, 0.3, 0.7, 1, 1, 1, 1]}, "clamped"),
        ({**CUBIC, "kind": "bspline", "knots": [0, 0, 0, 0, 0, 0.7, 1, 1, 1, 1]}, "exactly 4 times"),
        (
            {
                **CUBIC,
                "kind": "bspline",
                "knots": [0, 0, 0, 0, 0.5, 0.5, 1, 1, 1, 1],
                "control_points": CUBIC["control_points"],
            },
            None,
        ),
        ({**CUBIC, "kind": "bspline", "degree": 6}, "degree"),
        (
            {
                **CUBIC,
                "kind": "bspline",
                "degree": 3,
                "control_points": CUBIC["control_points"][:3],
                "knots": [0] * 4 + [1] * 3,
            },
            "at least 4",
        ),
    ],
)
def test_invalid_curves_are_refused(fields, message):
    fields = {"step": 10.0, **fields}
    if message is None:
        CopickFilamentCurve(**fields)  # interior knot repeated twice: valid
        return
    with pytest.raises(ValidationError, match=message):
        CopickFilamentCurve(**fields)


def test_unknown_kinds_are_kept_but_never_current():
    filament = CopickFilament(
        instance_id=1,
        points=[(0, 0, 0), (5, 0, 0)],
        curve={"kind": "nurbs", "step": 5.0, "control_points": [(0, 0, 0), (5, 0, 0)], "weights": [1, 1]},
    )
    assert filament.curve.model_dump()["weights"] == [1, 1]
    assert not filament.curve_is_current()
    assert filament.editable_curve().kind == "catmull-rom"


def test_curve_omits_fields_of_other_kinds():
    assert set(CopickFilamentCurve(kind="catmull-rom", step=10, control_points=S_CURVE).model_dump()) == {
        "kind",
        "alpha",
        "step",
        "control_points",
    }


# ---------------------------------------------------------------------------
# Current curves
# ---------------------------------------------------------------------------


def test_current_check():
    points = evaluate_curve(S_CURVE, 10.0)
    assert curve_is_current(points, S_CURVE, 10.0)
    moved = np.array(S_CURVE)
    moved[2] += [0, 20, 0]
    assert not curve_is_current(points, moved, 10.0)
    moved_end = np.array(S_CURVE)
    moved_end[-1] += [10, 0, 0]
    assert not curve_is_current(points, moved_end, 10.0)

    bspline = {"kind": "bspline", "degree": 3, "knots": CUBIC["knots"]}
    points = evaluate_curve(CUBIC["control_points"], 10.0, **bspline)
    assert curve_is_current(points, CUBIC["control_points"], 10.0, **bspline)
    moved = np.array(CUBIC["control_points"], dtype=float)
    moved[2] += [0, 30, 0]
    assert not curve_is_current(points, moved, 10.0, **bspline)
    assert len(curve_anchors(CUBIC["control_points"], **bspline)) == 4


# ---------------------------------------------------------------------------
# Deriving control points
# ---------------------------------------------------------------------------


def test_control_points_from_polyline_stay_within_tolerance():
    rng = np.random.default_rng(1)
    theta = np.linspace(0, 6, 600)
    dense = np.c_[300 + 120 * np.cos(theta), 300 + 120 * np.sin(theta), 40 * theta] + rng.normal(0, 0.5, (600, 3))
    control = control_points_from_polyline(dense, 5.0)
    assert 3 <= len(control) < 60
    assert np.array_equal(control[0], dense[0]) and np.array_equal(control[-1], dense[-1])
    assert distances_to_polyline(dense, evaluate_curve(control, 5.0)).max() <= 5.0


@pytest.mark.parametrize(
    ("points", "tolerance", "message"),
    [
        ([[0, 0, 0], [10, 0, 0]], 0, "positive"),
        ([[0, 0, 0], [0, 0, 0]], 1, "two distinct"),
        ([[0, 0, 0], [10, 0, 0], [0, 0, 0]], 1, "closed"),
    ],
)
def test_control_points_from_polyline_refusals(points, tolerance, message):
    with pytest.raises(ValueError, match=message):
        control_points_from_polyline(points, tolerance)


# ---------------------------------------------------------------------------
# CopickFilament
# ---------------------------------------------------------------------------


def test_filament_from_and_with_control_points():
    long_curve = np.array(S_CURVE + [[260.0, 60.0, 30.0], [320.0, 120.0, 30.0], [380.0, 110.0, 40.0]])
    filament = CopickFilament.from_control_points(4, long_curve, step=10.0, radius=120.0, polarity_known=True)
    assert filament.curve_is_current()
    assert np.allclose(filament.points, evaluate_curve(long_curve, 10.0))

    moved = long_curve.copy()
    moved[5] += [0, 20, 0]
    edited = filament.with_control_points(moved)
    assert edited.curve_is_current() and edited.curve.step == 10.0
    assert (edited.instance_id, edited.radius, edited.polarity_known) == (4, 120.0, True)
    assert np.allclose(edited.points, evaluate_curve(moved, 10.0))
    # Moving control point 5 reshapes segments 3-6 only: the points up to control point 3 are unchanged
    before = np.asarray(filament.points)
    upto = int(np.argmin(np.linalg.norm(before - long_curve[3], axis=1)))
    assert np.array_equal(np.asarray(edited.points)[: upto + 1], before[: upto + 1])
    assert not filament.model_copy(update={"curve": edited.curve}).curve_is_current()

    backwards = filament.reversed()
    assert backwards.curve_is_current() and np.allclose(backwards.points[0], filament.points[-1])


def test_bspline_edits_keep_knots_and_count():
    filament = CopickFilament.from_curve(1, CopickFilamentCurve(kind="bspline", step=10.0, **CUBIC))
    moved = np.array(CUBIC["control_points"], dtype=float)
    moved[3] += [0, 0, 15]
    edited = filament.with_control_points(moved)
    assert edited.curve.knots == CUBIC["knots"] and edited.curve_is_current()
    with pytest.raises(ValueError, match="keeps its knots"):
        filament.with_control_points(moved[:-1])
    converted = filament.editable_curve(kinds=("catmull-rom", "linear"))
    assert converted.kind == "catmull-rom"
    assert distances_to_polyline(filament.points, converted.evaluate()).max() <= converted.step / 2 + 1e-9


def test_editable_curve_of_a_plain_polyline():
    points = evaluate_curve(S_CURVE, 2.0)
    filament = CopickFilament(instance_id=1, points=[tuple(p) for p in points])
    curve = filament.editable_curve()
    assert curve.kind == "catmull-rom" and curve.step == pytest.approx(
        np.median(np.linalg.norm(np.diff(points, axis=0), axis=1)),
    )
    assert len(filament.editable_control_points()) < len(points)
    assert filament.with_control_points(curve.control_points).curve_is_current()


def _write_fixture():
    cases = [{**case, "points": _evaluate(case).tolist()} for case in REFERENCE_CASES]
    FIXTURE.parent.mkdir(exist_ok=True)
    FIXTURE.write_text(
        json.dumps(
            {
                "description": "Reference cases of the copick filament curve specification (docs/datamodel.md, "
                "Filaments, Editable curves): each case's points regenerated from its curve. A conforming "
                "implementation reproduces them to within 1e-3 Angstrom.",
                "cases": cases,
            },
            indent=1,
        )
        + "\n",
    )


if __name__ == "__main__":
    _write_fixture()
