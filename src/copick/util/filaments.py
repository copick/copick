"""Filament curves: the editable or fitted representation of a filament centreline, and the polyline regenerated from
it.

This is the reference implementation of the specification in ``docs/datamodel.md`` (Filaments, Editable curves). It
uses numpy only, so that the same numbers can be reproduced from the specification in any language.
"""

import math
from typing import List, Optional, Sequence

import numpy as np

#: The curve kinds this version of copick evaluates. ``catmull-rom`` passes through its control points (interactive
#: tracing), ``linear`` joins them with straight segments, and ``bspline`` stores a fitted B-spline exactly.
CURVE_KINDS = ("catmull-rom", "linear", "bspline")

#: Minimum number of samples per segment or knot span of the fine polyline.
MIN_SAMPLES = 16
#: Samples of the fine polyline per ``step`` of segment (or control polygon) length.
SAMPLES_PER_STEP = 16
#: Consecutive Catmull-Rom and linear control points must be further apart than this, in Angstrom.
MIN_POINT_DISTANCE = 1e-6
#: A curve is current while its anchors lie within this fraction of ``step`` of the stored points (which contain them).
CURRENT_FRACTION = 0.01
#: Highest B-spline degree.
MAX_DEGREE = 5


def _as_points(points) -> np.ndarray:
    return np.asarray(points, dtype=float).reshape(-1, 3)


def check_curve(
    kind: str,
    control_points,
    step: float,
    alpha: Optional[float] = None,
    degree: Optional[int] = None,
    knots: Optional[Sequence[float]] = None,
) -> None:
    """Refuse a curve that cannot be evaluated.

    Raises:
        ValueError: If the kind is unknown, or the curve breaks one of its kind's rules.
    """
    if kind not in CURVE_KINDS:
        raise ValueError(f"Unknown curve kind {kind!r}; this copick evaluates {', '.join(CURVE_KINDS)}.")
    points = _as_points(control_points)
    if not np.all(np.isfinite(points)):
        raise ValueError("Curve control points must be finite.")
    if not (np.isfinite(step) and step > 0):
        raise ValueError(f"Curve step must be a positive number of Angstrom, not {step}.")

    if kind in ("catmull-rom", "linear"):
        if len(points) < 2:
            raise ValueError(f"A {kind} curve needs at least two control points.")
        gaps = np.linalg.norm(np.diff(points, axis=0), axis=1)
        if np.any(gaps <= MIN_POINT_DISTANCE):
            i = int(np.argmax(gaps <= MIN_POINT_DISTANCE))
            raise ValueError(f"Control points {i} and {i + 1} coincide; consecutive control points must be distinct.")
        if kind == "catmull-rom" and alpha is not None and not (0.0 <= alpha <= 1.0):
            raise ValueError(f"Catmull-Rom alpha must be between 0 and 1, not {alpha}.")
        return

    # bspline
    if degree is None or knots is None:
        raise ValueError("A bspline curve needs a degree and knots.")
    if isinstance(degree, bool) or int(degree) != degree or not (1 <= degree <= MAX_DEGREE):
        raise ValueError(f"B-spline degree must be an integer from 1 to {MAX_DEGREE}, not {degree}.")
    p, n = int(degree), len(points)
    if n < p + 1:
        raise ValueError(f"A degree {p} B-spline needs at least {p + 1} control points, got {n}.")
    u = np.asarray(knots, dtype=float)
    if u.ndim != 1 or len(u) != n + p + 1:
        raise ValueError(f"A degree {p} B-spline with {n} control points needs {n + p + 1} knots, got {u.size}.")
    if not np.all(np.isfinite(u)):
        raise ValueError("B-spline knots must be finite.")
    if np.any(np.diff(u) < 0):
        raise ValueError("B-spline knots must be non-decreasing.")
    if not (np.all(u[: p + 1] == u[0]) and np.all(u[-(p + 1) :] == u[-1]) and u[-1] > u[0]):
        raise ValueError(f"B-spline knots must be clamped: the first and the last {p + 1} knots equal.")
    if u[p + 1] == u[0] or u[-(p + 2)] == u[-1]:
        raise ValueError(f"B-spline end knots must repeat exactly {p + 1} times.")
    _, counts = np.unique(u[p + 1 : n], return_counts=True)
    if counts.size and counts.max() > p:
        raise ValueError(f"Interior B-spline knots may repeat at most {p} times.")


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


def _catmull_rom_samples(q: np.ndarray, alpha: float, m: int) -> np.ndarray:
    """``m`` samples of the Catmull-Rom segment from ``q[1]`` to ``q[2]`` (Barry-Goldman), without its end."""
    t = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(q, axis=0), axis=1) ** alpha)])
    tt = (t[1] + (t[2] - t[1]) * np.arange(m) / m)[:, None]
    a = [((t[j + 1] - tt) * q[j] + (tt - t[j]) * q[j + 1]) / (t[j + 1] - t[j]) for j in range(3)]
    b0 = ((t[2] - tt) * a[0] + (tt - t[0]) * a[1]) / (t[2] - t[0])
    b1 = ((t[3] - tt) * a[1] + (tt - t[1]) * a[2]) / (t[3] - t[1])
    return ((t[2] - tt) * b0 + (tt - t[1]) * b1) / (t[2] - t[1])


def _span(knots: np.ndarray, degree: int, n: int, u: float) -> int:
    """The knot span ``j`` (``degree <= j <= n - 1``) holding parameter ``u``; the last non-empty span at the end."""
    if u >= knots[n]:
        j = n - 1
        while knots[j] >= knots[j + 1]:
            j -= 1
        return j
    j = int(np.searchsorted(knots, u, side="right")) - 1
    return min(max(j, degree), n - 1)


def _de_boor(c: np.ndarray, knots: np.ndarray, degree: int, j: int, u: np.ndarray) -> np.ndarray:
    """The B-spline at parameters ``u`` (all in span ``j``), by de Boor's algorithm."""
    p = degree
    d = np.repeat(c[j - p : j + 1][None, :, :], len(u), axis=0)
    for r in range(1, p + 1):
        for i in range(p, r - 1, -1):
            lo, hi = knots[j - p + i], knots[j + 1 + i - r]
            a = ((u - lo) / (hi - lo))[:, None]
            d[:, i] = (1.0 - a) * d[:, i - 1] + a * d[:, i]
    return d[:, p]


def _bspline_at(c: np.ndarray, knots: np.ndarray, degree: int, u: float) -> np.ndarray:
    j = _span(knots, degree, len(c), u)
    return _de_boor(c, knots, degree, j, np.array([u], dtype=float))[0]


def _fine_pieces(
    points: np.ndarray,
    step: float,
    kind: str,
    alpha: float,
    degree: Optional[int],
    knots: Optional[np.ndarray],
) -> List[np.ndarray]:
    """The fine polyline of every piece of the curve (each segment between consecutive control points, or each
    non-empty knot span), from the anchor that starts it to the anchor that ends it."""
    pieces = []
    if kind == "bspline":
        p, n = degree, len(points)
        for j in range(p, n):
            if knots[j] < knots[j + 1]:
                polygon = float(np.sum(np.linalg.norm(np.diff(points[j - p : j + 1], axis=0), axis=1)))
                m = max(MIN_SAMPLES, math.ceil(SAMPLES_PER_STEP * polygon / step))
                u = knots[j] + (knots[j + 1] - knots[j]) * np.arange(m) / m
                end = _bspline_at(points, knots, p, knots[j + 1])
                pieces.append(np.vstack([_de_boor(points, knots, p, j, u), end]))
    else:
        extended = np.vstack([2 * points[0] - points[1], points, 2 * points[-1] - points[-2]])
        for i in range(len(points) - 1):
            m = max(MIN_SAMPLES, math.ceil(SAMPLES_PER_STEP * float(np.linalg.norm(points[i + 1] - points[i])) / step))
            if kind == "linear":
                f = (np.arange(m) / m)[:, None]
                samples = points[i] + f * (points[i + 1] - points[i])
            else:
                samples = _catmull_rom_samples(extended[i : i + 4], alpha, m)
                samples[0] = points[i]  # the segment starts exactly at its control point
            pieces.append(np.vstack([samples, points[i + 1]]))
    return pieces


def _resample_piece(fine: np.ndarray, step: float) -> np.ndarray:
    """Points at equal arc-length spacing of at most ``step`` along one piece, from its start (exact) up to, not
    including, its end. Empty for a piece of zero length."""
    gaps = np.linalg.norm(np.diff(fine, axis=0), axis=1)
    keep = np.concatenate([[True], gaps > 0])
    fine, gaps = fine[keep], gaps[gaps > 0]
    s = np.concatenate([[0.0], np.cumsum(gaps)])
    length = float(s[-1])
    if length <= 0:
        return np.empty((0, 3))
    n = max(1, math.ceil(length / step - 1e-9))
    targets = np.arange(n) * (length / n)
    out = np.column_stack([np.interp(targets, s, fine[:, axis]) for axis in range(3)])
    out[0] = fine[0]
    return out


def evaluate_curve(
    control_points,
    step: float,
    kind: str = "catmull-rom",
    alpha: Optional[float] = 0.5,
    degree: Optional[int] = None,
    knots: Optional[Sequence[float]] = None,
) -> np.ndarray:
    """The centreline points of a curve, from its start to its end, at most ``step`` apart.

    Each piece of the curve (each segment between consecutive control points, or each non-empty knot span of a
    B-spline) is resampled on its own, evenly along its arc length, so every anchor (``curve_anchors``) is one of the
    points.

    Args:
        control_points: (n, 3) control points in Angstrom (B-spline coefficients for ``bspline``).
        step: Largest spacing of the returned points, in Angstrom.
        kind: One of ``CURVE_KINDS``.
        alpha: Catmull-Rom parameterisation (0.5: centripetal).
        degree: B-spline degree.
        knots: B-spline knots (clamped).

    Returns:
        The (N + 1, 3) points.

    Raises:
        ValueError: If the curve is invalid (see ``check_curve``).
    """
    alpha = 0.5 if alpha is None else float(alpha)
    check_curve(kind, control_points, step, alpha=alpha, degree=degree, knots=knots)
    points = _as_points(control_points)
    u = None if knots is None else np.asarray(knots, dtype=float)
    pieces = _fine_pieces(points, float(step), kind, alpha, None if degree is None else int(degree), u)
    resampled = [_resample_piece(piece, float(step)) for piece in pieces]
    if not any(len(r) for r in resampled):
        raise ValueError("The curve has zero length.")
    return np.vstack([*resampled, pieces[-1][-1:]])


def curve_anchors(
    control_points,
    kind: str = "catmull-rom",
    degree: Optional[int] = None,
    knots: Optional[Sequence[float]] = None,
) -> np.ndarray:
    """The points a curve is guaranteed to pass through: its control points for ``catmull-rom`` and ``linear``, and
    the curve at each distinct knot of its domain for ``bspline``."""
    points = _as_points(control_points)
    if kind != "bspline":
        return points
    u = np.asarray(knots, dtype=float)
    p, n = int(degree), len(points)
    return np.array([_bspline_at(points, u, p, value) for value in np.unique(u[p : n + 1])])


def distances_to_polyline(queries, polyline) -> np.ndarray:
    """The distance of each query point to the nearest segment of ``polyline``."""
    q = _as_points(queries)
    line = _as_points(polyline)
    if len(line) == 1:
        return np.linalg.norm(q - line[0], axis=1)
    a, b = line[:-1], line[1:]
    ab = b - a
    ab2 = np.maximum(np.einsum("ij,ij->i", ab, ab), 1e-30)
    out = np.empty(len(q))
    chunk = max(1, 500_000 // max(len(a), 1))
    for start in range(0, len(q), chunk):
        block = q[start : start + chunk, None, :]
        t = np.clip(np.einsum("qsk,sk->qs", block - a[None], ab) / ab2[None], 0.0, 1.0)
        nearest = a[None] + t[..., None] * ab[None]
        out[start : start + chunk] = np.sqrt(np.min(np.sum((block - nearest) ** 2, axis=-1), axis=1))
    return out


def curve_is_current(
    points,
    control_points,
    step: float,
    kind: str = "catmull-rom",
    degree: Optional[int] = None,
    knots: Optional[Sequence[float]] = None,
) -> bool:
    """Whether a curve still describes ``points``: its first and last anchors are within ``0.01 * step`` of the ends
    of ``points``, and every anchor lies within that distance of the polyline. Points regenerated from the curve
    contain every anchor, so any edit of the curve that is not followed by regenerating ``points`` shows. A curve of
    an unknown kind is never current."""
    if kind not in CURVE_KINDS:
        return False
    line = _as_points(points)
    if len(line) < 2:
        return False
    try:
        anchors = curve_anchors(control_points, kind=kind, degree=degree, knots=knots)
    except (TypeError, ValueError, IndexError):
        return False
    eps = CURRENT_FRACTION * float(step)
    if np.linalg.norm(line[0] - anchors[0]) > eps or np.linalg.norm(line[-1] - anchors[-1]) > eps:
        return False
    return bool(np.all(distances_to_polyline(anchors, line) <= eps))


def control_points_from_polyline(points, tolerance: float) -> np.ndarray:
    """Catmull-Rom (alpha 0.5) control points, chosen from ``points``, whose curve stays within ``tolerance`` of them.

    Starts from the two end points and repeatedly adds the input point farthest from the curve regenerated with
    ``step = tolerance`` (lowest index on ties) until none is farther than ``tolerance``. Consecutive duplicate input
    points are ignored.

    Raises:
        ValueError: If ``tolerance`` is not positive, or the polyline has fewer than two distinct points or starts where
            it ends.
    """
    if not (np.isfinite(tolerance) and tolerance > 0):
        raise ValueError(f"Tolerance must be positive, not {tolerance}.")
    line = _as_points(points)
    if len(line) > 1:
        line = line[np.concatenate([[True], np.linalg.norm(np.diff(line, axis=0), axis=1) > MIN_POINT_DISTANCE])]
    if len(line) < 2:
        raise ValueError("A filament needs at least two distinct points.")
    if np.linalg.norm(line[-1] - line[0]) <= MIN_POINT_DISTANCE:
        raise ValueError("The polyline ends where it starts; closed filaments are not supported.")

    chosen = [0, len(line) - 1]
    while True:
        control = line[sorted(chosen)]
        curve = evaluate_curve(control, tolerance, kind="catmull-rom", alpha=0.5)
        distance = distances_to_polyline(line, curve)
        far = int(np.argmax(distance))
        if distance[far] <= tolerance or far in chosen:
            return control
        chosen.append(far)


def reverse_knots(knots: Sequence[float]) -> np.ndarray:
    """The knots of the same B-spline traversed backwards: ``u_0 + u_last - u``, in reverse order."""
    u = np.asarray(knots, dtype=float)
    return (u[0] + u[-1] - u)[::-1]


def median_spacing(points) -> float:
    """The median distance between consecutive points, or 0 for fewer than two."""
    line = _as_points(points)
    if len(line) < 2:
        return 0.0
    return float(np.median(np.linalg.norm(np.diff(line, axis=0), axis=1)))
