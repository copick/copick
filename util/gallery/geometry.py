"""Deterministic, seeded geometry recipes for synthetic copick inputs.

Each recipe is a pure function ``fn(rng, *, shape, voxel_size, **kwargs)`` returning a
native array/object for one entity kind:

* picks         -> ``(positions[N, 3] xyz angstrom, transforms | None)``
* segmentation  -> ``mask[z, y, x]`` uint8 (single-label: value 1; multilabel: object labels)
* mesh          -> ``trimesh.Trimesh``
* tomogram      -> ``volume[z, y, x]`` float32

Conventions: shape is ``(nz, ny, nx)``; a voxel index ``(iz, iy, ix)`` maps to physical
``(x=ix*v, y=iy*v, z=iz*v)``. The box spans ``[0, n*v]`` per axis; its center is at
``n*v/2``. Recipes draw legible, well-separated features (>= ~8 voxels) so isosurfaces
are smooth and the commands have something real to operate on.
"""

from __future__ import annotations

from typing import Callable, Dict, Tuple

import numpy as np

# --------------------------------------------------------------------------- #
# low-level drawing helpers (operate in voxel space)
# --------------------------------------------------------------------------- #


def _center_vox(shape: Tuple[int, int, int]) -> np.ndarray:
    return np.array([s / 2.0 for s in shape], dtype=np.float64)  # (cz, cy, cx)


def _coord_grids(shape: Tuple[int, int, int]):
    nz, ny, nx = shape
    zz, yy, xx = np.ogrid[0:nz, 0:ny, 0:nx]
    return zz, yy, xx


def _draw_sphere(mask: np.ndarray, center_vox, radius_vox: float, value: int = 1) -> None:
    zz, yy, xx = _coord_grids(mask.shape)
    cz, cy, cx = center_vox
    d2 = (zz - cz) ** 2 + (yy - cy) ** 2 + (xx - cx) ** 2
    mask[d2 <= radius_vox**2] = value


def _draw_segment(mask: np.ndarray, p0, p1, radius_vox: float, value: int = 1) -> None:
    """Paint a capsule (cylinder + spherical caps) between two voxel-space points."""
    zz, yy, xx = _coord_grids(mask.shape)
    p0 = np.asarray(p0, dtype=np.float64)
    p1 = np.asarray(p1, dtype=np.float64)
    seg = p1 - p0
    length2 = float(seg @ seg) or 1.0
    # t = projection parameter of each voxel onto the segment, clamped to [0, 1].
    t = ((zz - p0[0]) * seg[0] + (yy - p0[1]) * seg[1] + (xx - p0[2]) * seg[2]) / length2
    t = np.clip(t, 0.0, 1.0)
    pz = p0[0] + t * seg[0]
    py = p0[1] + t * seg[1]
    px = p0[2] + t * seg[2]
    d2 = (zz - pz) ** 2 + (yy - py) ** 2 + (xx - px) ** 2
    mask[d2 <= radius_vox**2] = value


def _smooth_noise(rng: np.random.Generator, shape, scale: int = 4, sigma: float = 1.0):
    """Low-frequency noise: random coarse grid, trilinearly upsampled."""
    from scipy.ndimage import zoom

    coarse = rng.normal(0.0, sigma, size=tuple(max(2, s // scale) for s in shape))
    factors = tuple(s / c for s, c in zip(shape, coarse.shape, strict=True))
    return zoom(coarse, factors, order=1).astype(np.float32)


# --------------------------------------------------------------------------- #
# tomogram recipes
# --------------------------------------------------------------------------- #


def reference_volume(rng, *, shape, voxel_size, **kw) -> np.ndarray:
    """Faint, structured volume used as the per-run reference frame / context slab."""
    vol = rng.normal(0.0, 0.02, size=shape).astype(np.float32)
    vol += 0.08 * _smooth_noise(rng, shape, scale=6, sigma=1.0)
    return vol


def structured_tomo(rng, *, shape, voxel_size, n_blobs: int = 14, **kw) -> np.ndarray:
    """A textured volume with embedded blobs — a legible subject for downsampling."""
    vol = 0.15 * _smooth_noise(rng, shape, scale=3, sigma=1.0)
    nz, ny, nx = shape
    for _ in range(n_blobs):
        c = rng.uniform(0.2, 0.8, size=3) * np.array(shape)
        r = rng.uniform(5, 11)
        zz, yy, xx = _coord_grids(shape)
        d2 = (zz - c[0]) ** 2 + (yy - c[1]) ** 2 + (xx - c[2]) ** 2
        vol += (1.0 * np.exp(-d2 / (2 * r**2))).astype(np.float32)
    return vol.astype(np.float32)


# --------------------------------------------------------------------------- #
# picks recipes  -> (positions[N,3] xyz angstrom, transforms|None)
# --------------------------------------------------------------------------- #


def _to_phys(points_vox: np.ndarray, voxel_size: float) -> np.ndarray:
    """(N,3) [z,y,x] voxel -> (N,3) [x,y,z] angstrom."""
    xyz = points_vox[:, ::-1].astype(np.float32) * voxel_size
    return xyz


def _random_orientations(rng, n: int) -> np.ndarray:
    """N uniformly-random orientations as (N,4,4) transforms (rotation only).

    Uses random unit quaternions (gaussian -> normalize) for uniform SO(3) sampling.
    The translation column is zero — chimerax-copick reads position from the pick
    location and orientation from ``transformation[0:3,:]`` — so markers stay put while
    their axes point in natural, varied directions."""
    q = rng.normal(size=(n, 4))
    q /= np.linalg.norm(q, axis=1, keepdims=True)
    w, x, y, z = q[:, 0], q[:, 1], q[:, 2], q[:, 3]
    t = np.zeros((n, 4, 4), dtype=np.float32)
    t[:, 0, 0] = 1 - 2 * (y * y + z * z)
    t[:, 0, 1] = 2 * (x * y - z * w)
    t[:, 0, 2] = 2 * (x * z + y * w)
    t[:, 1, 0] = 2 * (x * y + z * w)
    t[:, 1, 1] = 1 - 2 * (x * x + z * z)
    t[:, 1, 2] = 2 * (y * z - x * w)
    t[:, 2, 0] = 2 * (x * z - y * w)
    t[:, 2, 1] = 2 * (y * z + x * w)
    t[:, 2, 2] = 1 - 2 * (x * x + y * y)
    t[:, 3, 3] = 1.0
    return t


def _picks_return(rng, pts_vox: np.ndarray, voxel_size: float, orient: str):
    """Common return for picks recipes: physical positions + optional random orientations."""
    pos = _to_phys(pts_vox, voxel_size)
    transforms = _random_orientations(rng, len(pos)) if orient == "random" else None
    return pos, transforms


def point_cluster(rng, *, shape, voxel_size, n: int = 40, spread: float = 0.6, orient: str = "random", **kw):
    """N points scattered through a centered sub-box (fraction ``spread`` of the box)."""
    c = _center_vox(shape)
    half = np.array(shape) * 0.5 * spread
    pts = c + rng.uniform(-1.0, 1.0, size=(n, 3)) * half
    return _picks_return(rng, pts, voxel_size, orient)


def box_fill_points(rng, *, shape, voxel_size, n: int = 70, margin: float = 0.08, orient: str = "random", **kw):
    """N points filling (almost) the whole box — straddle a reference for filtering."""
    lo = np.array(shape) * margin
    hi = np.array(shape) * (1.0 - margin)
    pts = lo + rng.uniform(0.0, 1.0, size=(n, 3)) * (hi - lo)
    return _picks_return(rng, pts, voxel_size, orient)


def sphere_points(
    rng,
    *,
    shape,
    voxel_size,
    n: int = 60,
    radius_frac: float = 0.32,
    noise: float = 0.04,
    orient: str = "random",
    **kw,
):
    """Points on a sphere surface (a least-squares sphere fits them cleanly)."""
    c = _center_vox(shape)
    r = min(shape) * radius_frac
    v = rng.normal(size=(n, 3))
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    pts = c + v * r * (1.0 + rng.normal(0.0, noise, size=(n, 1)))
    return _picks_return(rng, pts, voxel_size, orient)


def ellipsoid_points(
    rng,
    *,
    shape,
    voxel_size,
    n: int = 60,
    radii_frac=(0.36, 0.22, 0.16),
    noise: float = 0.05,
    orient: str = "random",
    **kw,
):
    """Points on an anisotropic ellipsoid surface (for ellipsoid fitting)."""
    c = _center_vox(shape)
    radii = np.array(radii_frac) * min(shape)  # (z, y, x) radii
    v = rng.normal(size=(n, 3))
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    pts = c + v * radii * (1.0 + rng.normal(0.0, noise, size=(n, 1)))
    return _picks_return(rng, pts, voxel_size, orient)


def planar_points(
    rng,
    *,
    shape,
    voxel_size,
    n: int = 45,
    extent: float = 0.7,
    thickness: float = 0.04,
    tilt: float = 0.25,
    orient: str = "random",
    **kw,
):
    """Points near a tilted plane through the box center (a plane fits them)."""
    c = _center_vox(shape)
    half = np.array(shape) * 0.5 * extent
    # sample in the y-x plane, derive z from a tilt + small thickness noise.
    yx = rng.uniform(-1.0, 1.0, size=(n, 2)) * half[1:]
    z = c[0] + tilt * yx[:, 0] + rng.normal(0.0, shape[0] * thickness, size=n)
    pts = np.column_stack([z, c[1] + yx[:, 0], c[2] + yx[:, 1]])
    return _picks_return(rng, pts, voxel_size, orient)


def sheet_points(
    rng,
    *,
    shape,
    voxel_size,
    n: int = 80,
    extent: float = 0.75,
    amp: float = 0.16,
    orient: str = "random",
    **kw,
):
    """Points on a gently curved sheet z = f(x, y) (for open-surface fitting)."""
    c = _center_vox(shape)
    half = np.array(shape) * 0.5 * extent
    yx = rng.uniform(-1.0, 1.0, size=(n, 2)) * half[1:]
    wy = 1.6 * np.pi / (2 * half[1])
    wx = 1.3 * np.pi / (2 * half[2])
    z = c[0] + shape[0] * amp * np.sin(wy * yx[:, 0]) * np.cos(wx * yx[:, 1])
    pts = np.column_stack([z, c[1] + yx[:, 0], c[2] + yx[:, 1]])
    return _picks_return(rng, pts, voxel_size, orient)


def slab_layer_points(
    rng,
    *,
    shape,
    voxel_size,
    n: int = 70,
    extent: float = 0.74,
    z_frac: float = 0.5,
    tilt=(0.0, 0.0),
    amp: float = 0.04,
    orient: str = "random",
    **kw,
):
    """Points on a tilted, gently curved boundary layer at height ``z_frac`` of the box. Two of
    these (a top and a bottom layer with the same ``tilt``) bound a slab that ``picks2slab`` fits
    surfaces to and closes into a watertight slab mesh. ``tilt`` is ``(dz/dx, dz/dy)`` — modeled on
    the real sample-boundary layers (``dz/dy ~ 0.13``), so the surfaces are non-axis-aligned and the
    coupled / spline fits stay well-conditioned (a perfectly flat axis-aligned layer is degenerate)."""
    nz, ny, nx = shape
    c = _center_vox(shape)
    half = np.array(shape) * 0.5 * extent
    yx = rng.uniform(-1.0, 1.0, size=(n, 2)) * half[1:]  # (dy, dx) about the box center
    wy = 1.4 * np.pi / (2 * half[1])
    wx = 1.1 * np.pi / (2 * half[2])
    z = nz * z_frac + tilt[1] * yx[:, 0] + tilt[0] * yx[:, 1] + nz * amp * np.sin(wy * yx[:, 0]) * np.cos(wx * yx[:, 1])
    pts = np.column_stack([z, c[1] + yx[:, 0], c[2] + yx[:, 1]])
    return _picks_return(rng, pts, voxel_size, orient)


def two_lobe_cluster(
    rng,
    *,
    shape,
    voxel_size,
    n: int = 40,
    lobe_frac: float = 0.13,
    sep_frac: float = 0.26,
    orient: str = "none",
    **kw,
):
    """Two compact, solid point lobes separated along x -> a concave cloud. The convex
    hull (picks2mesh) bridges the gap into one elongated blob (a clear 'hull fills the
    concavity' illustration); points uniformly fill each lobe ball so the hull has volume."""
    c = _center_vox(shape)
    r = min(shape) * lobe_frac
    sep = min(shape) * sep_frac
    pts = []
    for sign in (-1.0, 1.0):
        ctr = c + np.array([0.0, 0.0, sign * sep])  # offset along x (axis index 2)
        k = n // 2
        d = rng.normal(size=(k, 3))
        d /= np.linalg.norm(d, axis=1, keepdims=True)
        rad = r * rng.uniform(0.0, 1.0, size=(k, 1)) ** (1.0 / 3.0)  # uniform in ball
        pts.append(ctr + d * rad)
    return _picks_return(rng, np.vstack(pts), voxel_size, orient)


# --------------------------------------------------------------------------- #
# segmentation recipes  -> mask[z,y,x] uint8
# --------------------------------------------------------------------------- #


def _fibonacci_directions(n: int) -> np.ndarray:
    """``n`` roughly-uniform unit vectors on the sphere (golden spiral), (n,3) in (z,y,x).
    Deterministic (no rng) so patch placement is reproducible."""
    i = np.arange(n) + 0.5
    phi = np.arccos(1.0 - 2.0 * i / n)
    theta = np.pi * (1.0 + 5.0**0.5) * i
    x = np.sin(phi) * np.cos(theta)
    y = np.sin(phi) * np.sin(theta)
    z = np.cos(phi)
    return np.column_stack([z, y, x])


def blob_sphere(
    rng,
    *,
    shape,
    voxel_size,
    center_frac=(0.5, 0.5, 0.5),
    radius_frac: float = 0.28,
    value: int = 1,
    **kw,
) -> np.ndarray:
    mask = np.zeros(shape, dtype=np.uint8)
    center = np.array(center_frac) * np.array(shape)
    _draw_sphere(mask, center, min(shape) * radius_frac, value=value)
    return mask


def disjoint_blobs(
    rng,
    *,
    shape,
    voxel_size,
    n: int = 5,
    radius_frac: float = 0.11,
    value: int = 1,
    min_gap_frac: float = 0.04,
    **kw,
) -> np.ndarray:
    """N well-separated spheres of one label (separate-/filter-components subject)."""
    mask = np.zeros(shape, dtype=np.uint8)
    r = min(shape) * radius_frac
    gap = min(shape) * min_gap_frac
    centers = []
    tries = 0
    while len(centers) < n and tries < 1000:
        tries += 1
        c = rng.uniform(0.18, 0.82, size=3) * np.array(shape)
        if all(np.linalg.norm(c - o) > 2 * r + gap for o in centers):
            centers.append(c)
    for c in centers:
        _draw_sphere(mask, c, r, value=value)
    return mask


def mixed_blobs(
    rng,
    *,
    shape,
    voxel_size,
    n_big: int = 3,
    n_small: int = 6,
    big_frac: float = 0.13,
    small_frac: float = 0.05,
    **kw,
) -> np.ndarray:
    """A few large + several small spheres (filter-components: small ones get culled)."""
    mask = np.zeros(shape, dtype=np.uint8)
    rb = min(shape) * big_frac
    rs = min(shape) * small_frac
    placed = []
    for radius, count in ((rb, n_big), (rs, n_small)):
        k = 0
        tries = 0
        while k < count and tries < 2000:
            tries += 1
            c = rng.uniform(0.15, 0.85, size=3) * np.array(shape)
            if all(np.linalg.norm(c - o[0]) > radius + o[1] + 3 for o in placed):
                _draw_sphere(mask, c, radius, value=1)
                placed.append((c, radius))
                k += 1
    return mask


def branching_tubes(rng, *, shape, voxel_size, n_branches: int = 5, tube_radius_frac: float = 0.05, **kw) -> np.ndarray:
    """A connected branching tube network (skeletonize -> thin centerline)."""
    mask = np.zeros(shape, dtype=np.uint8)
    c = _center_vox(shape)
    r = min(shape) * tube_radius_frac
    span = min(shape) * 0.36
    for _ in range(n_branches):
        v = rng.normal(size=3)
        v /= np.linalg.norm(v)
        end = c + v * span * rng.uniform(0.7, 1.0)
        _draw_segment(mask, c, end, r, value=1)
        # one secondary branch off each primary for visual richness
        if rng.random() < 0.7:
            mid = c + (end - c) * rng.uniform(0.4, 0.7)
            v2 = rng.normal(size=3)
            v2 /= np.linalg.norm(v2)
            _draw_segment(mask, mid, mid + v2 * span * 0.5, r * 0.85, value=1)
    return mask


def thin_curve(rng, *, shape, voxel_size, radius_frac: float = 0.018, n_seg: int = 60, **kw):
    """A single thin, smoothly curved tube (~1-2 voxels) — a skeleton for spline fitting."""
    mask = np.zeros(shape, dtype=np.uint8)
    nz, ny, nx = shape
    t = np.linspace(0.15, 0.85, n_seg)
    x = t * nx
    y = ny * (0.5 + 0.22 * np.sin(2 * np.pi * t))
    z = nz * (0.5 + 0.15 * np.cos(2 * np.pi * t))
    r = max(1.0, min(shape) * radius_frac)
    pts = np.column_stack([z, y, x])
    for i in range(len(t) - 1):
        _draw_segment(mask, pts[i], pts[i + 1], r, value=1)
    return mask


def thick_and_thin(rng, *, shape, voxel_size, **kw) -> np.ndarray:
    """A fat sphere (thick) + a thin sheet (thin) — thickness-filter drops the sheet."""
    mask = np.zeros(shape, dtype=np.uint8)
    nz, ny, nx = shape
    _draw_sphere(mask, (nz * 0.5, ny * 0.35, nx * 0.35), min(shape) * 0.16, value=1)
    # a thin slab spanning one side of the box
    z0 = int(nz * 0.62)
    z1 = int(nz * 0.66)
    mask[z0:z1, int(ny * 0.2) : int(ny * 0.8), int(nx * 0.45) : int(nx * 0.85)] = 1
    return mask


def shell(
    rng,
    *,
    shape,
    voxel_size,
    center_frac=(0.5, 0.5, 0.5),
    outer_frac: float = 0.34,
    thickness_frac: float = 0.07,
    **kw,
) -> np.ndarray:
    """A solid sphere acting as the enclosing 'outer' structure for ``enclosed``."""
    mask = np.zeros(shape, dtype=np.uint8)
    center = np.array(center_frac) * np.array(shape)
    _draw_sphere(mask, center, min(shape) * outer_frac, value=1)
    return mask


def enclosed_fragments(rng, *, shape, voxel_size, **kw) -> np.ndarray:
    """Two small blobs: one at the box center (inside the outer sphere), one near the
    edge (outside it). ``enclosed`` removes the central, enclosed one."""
    mask = np.zeros(shape, dtype=np.uint8)
    nz, ny, nx = shape
    _draw_sphere(mask, (nz * 0.5, ny * 0.5, nx * 0.5), min(shape) * 0.06, value=1)  # inside
    _draw_sphere(mask, (nz * 0.5, ny * 0.85, nx * 0.85), min(shape) * 0.06, value=1)  # outside
    return mask


def seed_blobs(rng, *, shape, voxel_size, n: int = 5, radius_frac: float = 0.045, **kw):
    """Several small blobs to be grown by ``expand-labels``."""
    return disjoint_blobs(rng, shape=shape, voxel_size=voxel_size, n=n, radius_frac=radius_frac, min_gap_frac=0.12)


def multilabel_regions(rng, *, shape, voxel_size, labels=(15, 16), **kw) -> np.ndarray:
    """A multilabel volume: two overlapping spheres with distinct object labels."""
    mask = np.zeros(shape, dtype=np.uint8)
    nz, ny, nx = shape
    _draw_sphere(mask, (nz * 0.5, ny * 0.5, nx * 0.4), min(shape) * 0.2, value=labels[0])
    _draw_sphere(mask, (nz * 0.5, ny * 0.5, nx * 0.62), min(shape) * 0.2, value=labels[1])
    return mask


def curved_tube(
    rng,
    *,
    shape,
    voxel_size,
    radius_frac: float = 0.06,
    n_seg: int = 96,
    span_frac: float = 0.80,
    arc_frac: float = 0.22,
    **kw,
) -> np.ndarray:
    """One long, thick, gently-curved tube spanning the box (no branches). Skeletonize
    thins it to an obvious single 1-voxel centerline. Fat radius -> dramatic contrast."""
    mask = np.zeros(shape, dtype=np.uint8)
    nz, ny, nx = shape
    t = np.linspace(0.0, 1.0, n_seg)
    lo, hi = (1.0 - span_frac) / 2.0, (1.0 + span_frac) / 2.0
    x = nx * (lo + (hi - lo) * t)  # sweep the long axis
    y = ny * (0.5 + arc_frac * np.sin(np.pi * t))  # single broad lateral arc
    z = nz * (0.5 + 0.5 * arc_frac * np.cos(np.pi * t))  # gentle depth drift
    r = max(2.0, min(shape) * radius_frac)
    pts = np.column_stack([z, y, x])
    for i in range(len(t) - 1):
        _draw_segment(mask, pts[i], pts[i + 1], r, value=1)
    return mask


def ring_blobs(
    rng,
    *,
    shape,
    voxel_size,
    n: int = 5,
    radius_frac: float = 0.1,
    ring_frac: float = 0.32,
    value: int = 1,
    **kw,
) -> np.ndarray:
    """Exactly ``n`` well-separated spheres of one label on a tilted ring -> a
    DETERMINISTIC component count (separate-components yields exactly n colors)."""
    mask = np.zeros(shape, dtype=np.uint8)
    c = _center_vox(shape)
    r = min(shape) * radius_frac
    ring = min(shape) * ring_frac
    u = np.array([0.20, 0.97, 0.0])
    u /= np.linalg.norm(u)
    w0 = np.array([0.60, 0.0, 0.80])
    w = w0 - (w0 @ u) * u
    w /= np.linalg.norm(w)  # u, w orthonormal -> clean ring
    for a in np.linspace(0.0, 2 * np.pi, n, endpoint=False):
        center = c + ring * (np.cos(a) * u + np.sin(a) * w)
        _draw_sphere(mask, center, r, value=value)
    return mask


def sphere_with_shell_patches(
    rng,
    *,
    shape,
    voxel_size,
    core_frac: float = 0.20,
    shell_frac: float = 0.32,
    shell_thickness_frac: float = 0.045,
    n_patches: int = 4,
    patch_halfangle_deg: float = 38.0,
    value: int = 1,
    **kw,
) -> np.ndarray:
    """A thick solid sphere + a thin concentric shell present only in a few angular
    patches. thickness-filter removes the thin patches and keeps the solid core."""
    mask = np.zeros(shape, dtype=np.uint8)
    c = _center_vox(shape)
    r_core = min(shape) * core_frac
    r_shell = min(shape) * shell_frac
    half_t = max(1.0, 0.5 * min(shape) * shell_thickness_frac)
    _draw_sphere(mask, c, r_core, value=value)

    zz, yy, xx = _coord_grids(shape)
    rz, ry, rx = zz - c[0], yy - c[1], xx - c[2]
    rad = np.sqrt(rz**2 + ry**2 + rx**2)
    band = (rad >= r_shell - half_t) & (rad <= r_shell + half_t)

    safe = np.where(rad == 0, 1.0, rad)
    nz_, ny_, nx_ = rz / safe, ry / safe, rx / safe
    cos_thr = np.cos(np.deg2rad(patch_halfangle_deg))
    patch = np.zeros(shape, dtype=bool)
    for d in _fibonacci_directions(n_patches):
        patch |= (nz_ * d[0] + ny_ * d[1] + nx_ * d[2]) >= cos_thr
    mask[band & patch] = value
    return mask


def seg_box(
    rng,
    *,
    shape,
    voxel_size,
    center_frac=(0.5, 0.5, 0.5),
    size_frac=(0.4, 0.4, 0.4),
    value: int = 1,
    **kw,
) -> np.ndarray:
    """A single axis-aligned solid block (cube/brick) of one label — reads as a crisp,
    countable box and isosurfaces cleanly (combine 'box-count' semantics)."""
    mask = np.zeros(shape, dtype=np.uint8)
    shape_arr = np.array(shape, dtype=np.float64)
    center = np.array(center_frac, dtype=np.float64) * shape_arr
    half = np.array(size_frac, dtype=np.float64) * shape_arr / 2.0
    lo = np.maximum(0, np.round(center - half).astype(int))
    hi = np.minimum(np.array(shape), np.round(center + half).astype(int))
    mask[lo[0] : hi[0], lo[1] : hi[1], lo[2] : hi[2]] = int(value)
    return mask


def tilted_slab(
    rng,
    *,
    shape,
    voxel_size,
    extent=(0.74, 0.80),
    z_frac: float = 0.5,
    tilt=(0.05, 0.16),
    amp: float = 0.04,
    thickness_frac: float = 0.16,
    value: int = 1,
    **kw,
) -> np.ndarray:
    """A tilted, gently curved thick slab filled between two parallel surfaces — modeled on the real
    sample-boundary slab (``valid-sample``: tilt ``dz/dy ~ 0.13``, thickness ~0.14 of depth, full
    lateral extent). ``seg2slab`` extracts its top/bottom surfaces and fits a slab mesh; the tilt
    keeps the coupled/spline plane-normal fit well-conditioned (a flat axis-aligned slab is a
    degenerate, NaN-prone case for them). ``extent`` is ``(y, x)`` footprint fraction; ``tilt`` is
    ``(dz/dx, dz/dy)``."""
    nz, ny, nx = shape
    mask = np.zeros(shape, dtype=np.uint8)
    cy, cx = ny / 2.0, nx / 2.0
    yy, xx = np.ogrid[0:ny, 0:nx]
    half_y = ny * 0.5 * extent[0]
    half_x = nx * 0.5 * extent[1]
    wy = 1.3 * np.pi / (2 * half_y)
    wx = 1.0 * np.pi / (2 * half_x)
    zc = (
        nz * z_frac
        + tilt[1] * (yy - cy)
        + tilt[0] * (xx - cx)
        + nz * amp * np.sin(wy * (yy - cy)) * np.cos(wx * (xx - cx))
    )  # mid-surface z (ny, nx)
    half_t = nz * thickness_frac * 0.5
    footprint = (np.abs(yy - cy) <= half_y) & (np.abs(xx - cx) <= half_x)  # (ny, nx)
    zgrid = np.arange(nz)[:, None, None]
    band = (zgrid >= (zc - half_t)[None, :, :]) & (zgrid <= (zc + half_t)[None, :, :])
    band &= footprint[None, :, :]
    mask[band] = int(value)
    return mask


def multilabel_boxes(
    rng,
    *,
    shape,
    voxel_size,
    labels=(15, 16),
    split_axis="x",
    box_frac=(0.4, 0.4, 0.24),
    gap_frac: float = 0.0,
    **kw,
) -> np.ndarray:
    """Two equal labeled boxes symmetric about the box center along ``split_axis`` with a
    centered gap. ``gap_frac==0`` -> they abut into ONE solid multilabel block (split's
    before / combine's after); ``gap_frac>0`` -> two adjacent labels that expand-labels
    grows to meet at the medial plane without bleeding. ``labels`` must match config labels."""
    mask = np.zeros(shape, dtype=np.uint8)
    shape_arr = np.array(shape, dtype=np.float64)
    axis = {"z": 0, "y": 1, "x": 2}[split_axis]
    half = np.array(box_frac, dtype=np.float64) * shape_arr / 2.0
    center = shape_arr * 0.5
    offset = half[axis] + gap_frac * shape_arr[axis] / 2.0
    for i, lbl in enumerate(labels[:2]):
        c = center.copy()
        c[axis] = center[axis] + (-offset if i == 0 else offset)
        lo = np.maximum(0, np.round(c - half).astype(int))
        hi = np.minimum(np.array(shape), np.round(c + half).astype(int))
        mask[lo[0] : hi[0], lo[1] : hi[1], lo[2] : hi[2]] = int(lbl)
    return mask


# --------------------------------------------------------------------------- #
# mesh recipes  -> trimesh.Trimesh
# --------------------------------------------------------------------------- #


def _phys_extent(shape, voxel_size):
    nz, ny, nx = shape
    return np.array([nx, ny, nz]) * voxel_size  # (x, y, z)


def icosphere(
    rng,
    *,
    shape,
    voxel_size,
    center_frac=(0.5, 0.5, 0.5),
    radius_frac: float = 0.26,
    subdivisions: int = 3,
    **kw,
):
    import trimesh

    ext = _phys_extent(shape, voxel_size)
    r = min(ext) * radius_frac
    m = trimesh.creation.icosphere(subdivisions=subdivisions, radius=r)
    # center_frac is (z,y,x); translate uses (x,y,z)
    cz, cy, cx = np.array(center_frac) * np.array(shape)
    m.apply_translation(np.array([cx, cy, cz]) * voxel_size)
    return m


def box_mesh(rng, *, shape, voxel_size, center_frac=(0.5, 0.5, 0.5), size_frac=(0.5, 0.5, 0.5), **kw):
    import trimesh

    ext = _phys_extent(shape, voxel_size)
    extents = np.array(size_frac)[::-1] * ext  # size_frac (z,y,x) -> (x,y,z)
    m = trimesh.creation.box(extents=extents)
    cz, cy, cx = np.array(center_frac) * np.array(shape)
    m.apply_translation(np.array([cx, cy, cz]) * voxel_size)
    return m


def plane_mesh(
    rng,
    *,
    shape,
    voxel_size,
    z_frac: float = 0.5,
    size_frac: float = 0.8,
    thickness_frac: float = 0.01,
    **kw,
):
    """A thin, wide slab acting as a reference surface (clippicks keeps a slab of points)."""
    import trimesh

    ext = _phys_extent(shape, voxel_size)
    extents = np.array([size_frac * ext[0], size_frac * ext[1], thickness_frac * ext[2]])
    m = trimesh.creation.box(extents=extents)
    m.apply_translation(np.array([ext[0] * 0.5, ext[1] * 0.5, ext[2] * z_frac]))
    return m


def big_sheet_mesh(rng, *, shape, voxel_size, **kw):
    """A wide thin sheet extending across the box (clipmesh trims it to a region)."""
    return plane_mesh(rng, shape=shape, voxel_size=voxel_size, z_frac=0.5, size_frac=0.95, thickness_frac=0.04)


def nonconvex_mesh(rng, *, shape, voxel_size, **kw):
    """Two separated spheres concatenated — a clearly non-convex input for ``hull``."""
    import trimesh

    a = icosphere(
        rng,
        shape=shape,
        voxel_size=voxel_size,
        center_frac=(0.5, 0.5, 0.34),
        radius_frac=0.14,
        subdivisions=2,
    )
    b = icosphere(
        rng,
        shape=shape,
        voxel_size=voxel_size,
        center_frac=(0.5, 0.5, 0.66),
        radius_frac=0.14,
        subdivisions=2,
    )
    return trimesh.util.concatenate([a, b])


# --------------------------------------------------------------------------- #
# registry + dispatch
# --------------------------------------------------------------------------- #

RECIPES: Dict[str, Callable] = {
    # tomogram
    "reference_volume": reference_volume,
    "structured_tomo": structured_tomo,
    # picks
    "point_cluster": point_cluster,
    "box_fill_points": box_fill_points,
    "sphere_points": sphere_points,
    "ellipsoid_points": ellipsoid_points,
    "planar_points": planar_points,
    "sheet_points": sheet_points,
    "slab_layer_points": slab_layer_points,
    "two_lobe_cluster": two_lobe_cluster,
    # segmentation
    "blob_sphere": blob_sphere,
    "disjoint_blobs": disjoint_blobs,
    "mixed_blobs": mixed_blobs,
    "branching_tubes": branching_tubes,
    "thin_curve": thin_curve,
    "thick_and_thin": thick_and_thin,
    "shell": shell,
    "enclosed_fragments": enclosed_fragments,
    "seed_blobs": seed_blobs,
    "multilabel_regions": multilabel_regions,
    "curved_tube": curved_tube,
    "ring_blobs": ring_blobs,
    "sphere_with_shell_patches": sphere_with_shell_patches,
    "seg_box": seg_box,
    "tilted_slab": tilted_slab,
    "multilabel_boxes": multilabel_boxes,
    # mesh
    "icosphere": icosphere,
    "box_mesh": box_mesh,
    "plane_mesh": plane_mesh,
    "big_sheet_mesh": big_sheet_mesh,
    "nonconvex_mesh": nonconvex_mesh,
}


def seed_for(*parts: str) -> int:
    """Stable per-(command, alias) seed so fabricated data never changes between runs."""
    import hashlib

    h = hashlib.blake2b("/".join(parts).encode(), digest_size=8)
    return int.from_bytes(h.digest(), "big")


def build(recipe: str, rng, *, shape, voxel_size, **kwargs):
    if recipe not in RECIPES:
        raise KeyError(f"Unknown geometry recipe '{recipe}'. Known: {sorted(RECIPES)}")
    return RECIPES[recipe](rng, shape=shape, voxel_size=voxel_size, **kwargs)
