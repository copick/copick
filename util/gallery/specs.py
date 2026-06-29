"""The spec registry: one RenderSpec per copick transform command.

CLI argv (the ``cli`` field) is the argument list AFTER ``copick <group> <command>``,
with ``{cfg}`` / ``{run}`` placeholders. Flags mirror the live ``--help`` for each
command. copick-utils commands share ``-c/--config``, ``-r/--run-names``,
``-i/--input``, ``-o/--output``; the copick-torch ``downsample`` uses ``--config`` /
``--tomo-alg`` and has no run scoping (so it is isolated by a unique tomo-alg).

Output ``user_id`` is set to the command name so produced entities never collide with
inputs (``user_id="gallery"``) and are trivially globbed / verified.
"""

from __future__ import annotations

from typing import Dict, List

from .schema import (
    DEFAULT_VOXEL,
    MESH,
    PICKS,
    SEGMENTATION,
    TOMOGRAM,
    Clip,
    EntitySpec,
    Mode,
    ProducedSpec,
    RenderSpec,
    ViewSpec,
)

V = DEFAULT_VOXEL  # 10.0


# --- entity constructors --------------------------------------------------- #
def picks(obj, recipe, role="subject", ghost=False, ghost_transparency=70, **kw):
    return EntitySpec(PICKS, obj, recipe, kw, role=role, ghost_in_after=ghost, ghost_transparency=ghost_transparency)


def seg(obj, recipe, role="subject", multilabel=False, voxel=V, ghost=False, **kw):
    return EntitySpec(
        SEGMENTATION,
        obj,
        recipe,
        kw,
        is_multilabel=multilabel,
        voxel_size=voxel,
        role=role,
        ghost_in_after=ghost,
    )


def mesh(obj, recipe, role="subject", ghost=False, **kw):
    return EntitySpec(MESH, obj, recipe, kw, role=role, ghost_in_after=ghost)


def tomo(obj, recipe, voxel=V, **kw):
    return EntitySpec(TOMOGRAM, obj, recipe, kw, voxel_size=voxel)


# --- produced constructors ------------------------------------------------- #
def _session_of(uri: str):
    """Literal session id from a copick URI, or None when it is a glob/template (so
    verification matches any instance, e.g. separate-components ``inst-{instance_id}``)."""
    rest = uri.split(":", 1)[1].split("@", 1)[0].split("?", 1)[0]
    session = rest.split("/", 1)[1] if "/" in rest else None
    if session and ("*" in session or "{" in session or session.startswith("re:")):
        return None
    return session


def out_picks(obj, user, uri, min_count=1):
    return ProducedSpec(PICKS, uri, object_name=obj, user_id=user, session_id=_session_of(uri), min_count=min_count)


def out_seg(obj, user, uri, multilabel=False):
    return ProducedSpec(
        SEGMENTATION,
        uri,
        object_name=obj,
        user_id=user,
        session_id=_session_of(uri),
        is_multilabel=multilabel,
    )


def out_mesh(obj, user, uri, min_count=4):
    return ProducedSpec(MESH, uri, object_name=obj, user_id=user, session_id=_session_of(uri), min_count=min_count)


# Common CLI prefix for copick-utils commands. Uses the long ``--run-names`` form: every
# copick-utils command declares it, but only some also define the ``-r`` short alias
# (e.g. separate-components / fit-spline declare ``--run-names`` only).
def _c(*rest: str) -> List[str]:
    return ["-c", "{cfg}", "--run-names", "{run}", *rest]


SPECS: List[RenderSpec] = [
    # ===================== convert ===================== #
    RenderSpec(
        group="convert",
        command="picks2seg",
        run_name="picks2seg",
        inputs={"pts": picks("ribosome", "point_cluster", n=35, spread=0.55)},  # hidden in after
        cli=_c("-i", "ribosome:gallery/0", "-o", "ribosome:picks2seg/0@10.0", "--radius", "70", "-tt", "wbp"),
        # picks2seg always writes a multilabel segmentation.
        produces=[out_seg("ribosome", "picks2seg", "ribosome:picks2seg/0@10.0?multilabel=true", multilabel=True)],
        notes="Sparse points -> painted spheres in a label volume.",
    ),
    RenderSpec(
        group="convert",
        command="seg2picks",
        run_name="seg2picks",
        inputs={"seg": seg("ribosome", "disjoint_blobs", n=6, radius_frac=0.09, ghost=True)},
        cli=_c(
            "-i",
            "ribosome:gallery/0@10.0",
            "-o",
            "ribosome:seg2picks/0",
            "--segmentation-idx",
            "1",
            "--min-particle-size",
            "100",
        ),
        produces=[out_picks("ribosome", "seg2picks", "ribosome:seg2picks/0")],
        notes="Connected components -> one centroid pick each.",
    ),
    RenderSpec(
        group="convert",
        command="mesh2seg",
        run_name="mesh2seg",
        inputs={"mesh": mesh("membrane", "icosphere", radius_frac=0.28)},
        cli=_c("-i", "membrane:gallery/0", "-o", "membrane:mesh2seg/0@10.0"),
        produces=[out_seg("membrane", "mesh2seg", "membrane:mesh2seg/0@10.0")],
        # default (normal) shown un-clipped (full solid seg); modes clip to reveal differences
        modes=[
            Mode(
                "boundary",
                "Boundary",
                _c(
                    "-i",
                    "membrane:gallery/0",
                    "-o",
                    "membrane:mesh2seg/boundary@10.0",
                    "--mode",
                    "boundary",
                    "--boundary-sampling-density",
                    "4.0",
                ),
                [out_seg("membrane", "mesh2seg", "membrane:mesh2seg/boundary@10.0")],
                clip=Clip(cap=True),
            ),  # thin solid ring
            Mode(
                "invert",
                "Invert",
                _c("-i", "membrane:gallery/0", "-o", "membrane:mesh2seg/invert@10.0", "--invert"),
                [out_seg("membrane", "mesh2seg", "membrane:mesh2seg/invert@10.0")],
                clip=Clip(cap=True),
            ),  # square with circular hole
        ],
        notes="Mesh interior voxelized into a label volume (cross-sectioned to read solid).",
    ),
    RenderSpec(
        group="convert",
        command="seg2mesh",
        run_name="seg2mesh",
        inputs={"seg": seg("vesicle", "blob_sphere", radius_frac=0.3)},
        cli=_c("-i", "vesicle:gallery/0@10.0", "-o", "vesicle:seg2mesh/0", "--level", "0.5"),
        produces=[out_mesh("vesicle", "seg2mesh", "vesicle:seg2mesh/0")],
        before_clip=Clip(cap=True),  # input seg -> solid capped disk
        after_clip=Clip(cap=False),  # output mesh -> hollow rim (distinguishes them)
        notes="Marching cubes surface from a label volume (solid seg -> hollow mesh).",
    ),
    RenderSpec(
        group="convert",
        command="picks2mesh",
        run_name="picks2mesh",
        inputs={
            "pts": picks(
                "point-blue",
                "two_lobe_cluster",
                n=40,
                lobe_frac=0.13,
                sep_frac=0.26,
                ghost=True,
                ghost_transparency=40,
            ),
        },
        cli=_c("-i", "point-blue:gallery/0", "-o", "fit-solid:picks2mesh/0"),
        produces=[out_mesh("fit-solid", "picks2mesh", "fit-solid:picks2mesh/0")],
        # NOTE: no alpha mode — copick-utils alpha_shape_mesh() is disabled (falls back to
        # convex hull), so an "alpha" after would be byte-identical to the primary. The
        # two-lobe cloud shows the hull bridging the concavity.
        notes="Convex hull enclosing the picks; the two lobes show the hull bridging the gap.",
    ),
    RenderSpec(
        group="convert",
        command="picks2sphere",
        run_name="picks2sphere",
        inputs={"pts": picks("ribosome", "sphere_points", n=60, radius_frac=0.3)},
        cli=_c("-i", "ribosome:gallery/0", "-o", "ribosome:picks2sphere/0", "--subdivisions", "3"),
        produces=[out_mesh("ribosome", "picks2sphere", "ribosome:picks2sphere/0")],
        notes="Least-squares sphere fit -> icosphere mesh.",
    ),
    RenderSpec(
        group="convert",
        command="picks2ellipsoid",
        run_name="picks2ellipsoid",
        inputs={"pts": picks("point-blue", "ellipsoid_points", n=70, ghost=True, ghost_transparency=40)},
        cli=_c("-i", "point-blue:gallery/0", "-o", "fit-solid:picks2ellipsoid/0"),
        produces=[out_mesh("fit-solid", "picks2ellipsoid", "fit-solid:picks2ellipsoid/0")],
        notes="Ellipsoid fit -> tessellated mesh (opaque); input picks ghosted in the after.",
    ),
    RenderSpec(
        group="convert",
        command="picks2plane",
        run_name="picks2plane",
        inputs={"pts": picks("point-blue", "planar_points", n=45, ghost=True, ghost_transparency=40)},
        cli=_c("-i", "point-blue:gallery/0", "-o", "fit-solid:picks2plane/0", "--padding", "1.1"),
        produces=[out_mesh("fit-solid", "picks2plane", "fit-solid:picks2plane/0", min_count=1)],
        notes="Best-fit plane -> rectangular mesh; blue picks ghosted over the plane in after.",
    ),
    RenderSpec(
        group="convert",
        command="picks2surface",
        run_name="picks2surface",
        inputs={"pts": picks("point-blue", "sheet_points", n=90, ghost=True, ghost_transparency=40)},
        cli=_c("-i", "point-blue:gallery/0", "-o", "fit-solid:picks2surface/0", "--surface-method", "delaunay"),
        produces=[out_mesh("fit-solid", "picks2surface", "fit-solid:picks2surface/0")],
        notes="Open 2D surface fit; blue picks shown (ghosted) in before AND after.",
    ),
    RenderSpec(
        group="convert",
        command="mesh2picks",
        run_name="mesh2picks",
        inputs={"mesh": mesh("membrane-faint", "icosphere", radius_frac=0.28, subdivisions=2, ghost=True)},
        cli=_c(
            "-i",
            "membrane-faint:gallery/0",
            "-t",
            "wbp@10.0",
            "--sampling-type",
            "surface",
            "--edge-dist",
            "2",
            "--min-dist",
            "110",
            "--n-points",
            "150",
            "-o",
            "point:mesh2picks/0",
        ),
        produces=[out_picks("point", "mesh2picks", "point:mesh2picks/0")],
        modes=[
            Mode(
                "inside",
                "Inside",
                _c(
                    "-i",
                    "membrane-faint:gallery/0",
                    "-t",
                    "wbp@10.0",
                    "--sampling-type",
                    "inside",
                    "--edge-dist",
                    "2",
                    "--min-dist",
                    "110",
                    "--n-points",
                    "150",
                    "-o",
                    "point:mesh2picks/inside",
                ),
                [out_picks("point", "mesh2picks", "point:mesh2picks/inside")],
            ),
            Mode(
                "outside",
                "Outside",
                _c(
                    "-i",
                    "membrane-faint:gallery/0",
                    "-t",
                    "wbp@10.0",
                    "--sampling-type",
                    "outside",
                    "--edge-dist",
                    "2",
                    "--min-dist",
                    "110",
                    "--n-points",
                    "150",
                    "-o",
                    "point:mesh2picks/outside",
                ),
                [out_picks("point", "mesh2picks", "point:mesh2picks/outside")],
            ),
            Mode(
                "vertices",
                "Vertices",
                _c(
                    "-i",
                    "membrane-faint:gallery/0",
                    "-t",
                    "wbp@10.0",
                    "--sampling-type",
                    "vertices",
                    "--edge-dist",
                    "2",
                    "-o",
                    "point:mesh2picks/vertices",
                ),
                [out_picks("point", "mesh2picks", "point:mesh2picks/vertices")],
            ),
        ],
        notes="Sample points on/in/around a mesh; small edge-dist covers the full sphere cleanly.",
    ),
    RenderSpec(
        group="convert",
        command="picks2slab",
        run_name="picks2slab",
        inputs={
            "top": picks(
                "slab-top",
                "slab_layer_points",
                n=70,
                z_frac=0.60,
                tilt=(0.05, 0.16),
                ghost=True,
                ghost_transparency=45,
            ),
            "bot": picks(
                "slab-bot",
                "slab_layer_points",
                n=70,
                z_frac=0.40,
                tilt=(0.05, 0.16),
                ghost=True,
                ghost_transparency=45,
            ),
        },
        cli=_c(
            "-i1",
            "slab-top:gallery/0",
            "-i2",
            "slab-bot:gallery/0",
            "-t",
            "wbp@10.0",
            "-o",
            "fit-solid:picks2slab/0",
            "--regularization",
            "5",
            "-w",
            "1",
        ),
        produces=[out_mesh("fit-solid", "picks2slab", "fit-solid:picks2slab/0")],
        # default (spline) shown first; coupled/parallel are the alternative fits
        modes=[
            Mode(
                "coupled",
                "Coupled",
                _c(
                    "-i1",
                    "slab-top:gallery/0",
                    "-i2",
                    "slab-bot:gallery/0",
                    "-t",
                    "wbp@10.0",
                    "-o",
                    "fit-solid:picks2slab/coupled",
                    "--method",
                    "coupled",
                    "--regularization",
                    "5",
                    "-w",
                    "1",
                ),
                [out_mesh("fit-solid", "picks2slab", "fit-solid:picks2slab/coupled")],
            ),
            Mode(
                "parallel",
                "Parallel",
                _c(
                    "-i1",
                    "slab-top:gallery/0",
                    "-i2",
                    "slab-bot:gallery/0",
                    "-t",
                    "wbp@10.0",
                    "-o",
                    "fit-solid:picks2slab/parallel",
                    "--method",
                    "parallel",
                    "-w",
                    "1",
                ),
                [out_mesh("fit-solid", "picks2slab", "fit-solid:picks2slab/parallel")],
            ),
        ],
        notes="Fit surfaces to two pick layers and close them into a watertight slab mesh.",
    ),
    RenderSpec(
        group="convert",
        command="seg2slab",
        run_name="seg2slab",
        inputs={
            "seg": seg(
                "membrane",
                "tilted_slab",
                z_frac=0.5,
                tilt=(0.05, 0.16),
                thickness_frac=0.16,
                extent=(0.74, 0.80),
            ),
        },
        cli=_c(
            "-i",
            "membrane:gallery/0@10.0",
            "-l",
            "1",
            "-o",
            "fit-solid:seg2slab/0",
            "--grid-resolution",
            "5",
            "5",
            "--regularization",
            "5",
            "-w",
            "1",
        ),
        produces=[out_mesh("fit-solid", "seg2slab", "fit-solid:seg2slab/0")],
        # default (coupled) shown first; spline/parallel/iou are the alternative fits
        modes=[
            Mode(
                "spline",
                "Spline",
                _c(
                    "-i",
                    "membrane:gallery/0@10.0",
                    "-l",
                    "1",
                    "-o",
                    "fit-solid:seg2slab/spline",
                    "--method",
                    "spline",
                    "--grid-resolution",
                    "5",
                    "5",
                    "--regularization",
                    "5",
                    "-w",
                    "1",
                ),
                [out_mesh("fit-solid", "seg2slab", "fit-solid:seg2slab/spline")],
            ),
            Mode(
                "parallel",
                "Parallel",
                _c(
                    "-i",
                    "membrane:gallery/0@10.0",
                    "-l",
                    "1",
                    "-o",
                    "fit-solid:seg2slab/parallel",
                    "--method",
                    "parallel",
                    "-w",
                    "1",
                ),
                [out_mesh("fit-solid", "seg2slab", "fit-solid:seg2slab/parallel")],
            ),
            Mode(
                "iou",
                "IoU",
                _c(
                    "-i",
                    "membrane:gallery/0@10.0",
                    "-l",
                    "1",
                    "-o",
                    "fit-solid:seg2slab/iou",
                    "--method",
                    "iou",
                    "-w",
                    "1",
                ),
                [out_mesh("fit-solid", "seg2slab", "fit-solid:seg2slab/iou")],
            ),
        ],
        notes="Extract a label's slab and fit parallel surfaces into a watertight slab mesh.",
    ),
    RenderSpec(
        group="convert",
        command="mesh2caps",
        run_name="mesh2caps",
        inputs={
            "box": mesh(
                "membrane-faint",
                "box_mesh",
                center_frac=(0.5, 0.5, 0.5),
                size_frac=(0.30, 0.66, 0.66),
                ghost=True,
            ),
        },
        cli=_c("-i", "membrane-faint:gallery/0", "-o", "caps:mesh2caps/0"),
        produces=[out_mesh("caps", "mesh2caps", "caps:mesh2caps/0", min_count=1)],
        # default (both caps) shown first; top/bottom isolate a single cap
        modes=[
            Mode(
                "top",
                "Top",
                _c("-i", "membrane-faint:gallery/0", "-o", "caps:mesh2caps/top", "--surface", "top"),
                [out_mesh("caps", "mesh2caps", "caps:mesh2caps/top", min_count=1)],
            ),
            Mode(
                "bottom",
                "Bottom",
                _c("-i", "membrane-faint:gallery/0", "-o", "caps:mesh2caps/bottom", "--surface", "bottom"),
                [out_mesh("caps", "mesh2caps", "caps:mesh2caps/bottom", min_count=1)],
            ),
        ],
        notes="Keep only the top/bottom cap surfaces of a closed slab box mesh (drop the side walls).",
    ),
    # ===================== process ===================== #
    RenderSpec(
        group="process",
        command="skeletonize",
        run_name="skeletonize",
        inputs={"seg": seg("actin", "curved_tube", radius_frac=0.06)},
        cli=_c("-i", "actin:gallery/0@10.0", "-o", "actin:skeletonize/0@10.0"),
        produces=[out_seg("actin", "skeletonize", "actin:skeletonize/0@10.0")],
        modes=[
            Mode(
                "distance",
                "Distance transform",
                _c(
                    "-i",
                    "actin:gallery/0@10.0",
                    "-o",
                    "actin:skeletonize/distance@10.0",
                    "--method",
                    "distance_transform",
                ),
                [out_seg("actin", "skeletonize", "actin:skeletonize/distance@10.0")],
            ),
        ],
        notes="Reduce a volume to its 1-voxel medial skeleton.",
    ),
    RenderSpec(
        group="process",
        command="separate-components",
        run_name="separate-components",
        inputs={"seg": seg("blob", "ring_blobs", n=5, radius_frac=0.1)},
        cli=_c("-i", "blob:gallery/0@10.0", "-o", "blob:separate-components/inst-{instance_id}@10.0"),
        produces=[
            ProducedSpec(
                SEGMENTATION,
                "blob:separate-components/*@10.0",
                object_name="blob",
                user_id="separate-components",
                colorize=True,
                colorize_colors=["#e6194B", "#3cb44b", "#4363d8", "#f58231", "#911eb4"],
            ),
        ],
        notes="Relabel each connected component as its own segmentation (one color each).",
    ),
    RenderSpec(
        group="process",
        command="filter-components",
        run_name="filter-components",
        inputs={"seg": seg("blob", "mixed_blobs", n_big=3, n_small=6)},
        cli=_c("-i", "blob:gallery/0@10.0", "-o", "blob:filter-components/0@10.0", "--min-size", "5000000"),
        produces=[out_seg("blob", "filter-components", "blob:filter-components/0@10.0")],
        notes="Drop connected components below a size threshold.",
    ),
    RenderSpec(
        group="process",
        command="expand-labels",
        run_name="expand-labels",
        inputs={
            "seg": seg(
                "labels",
                "multilabel_boxes",
                multilabel=True,
                labels=(15, 16),
                split_axis="x",
                box_frac=(0.40, 0.40, 0.24),
                gap_frac=0.06,
            ),
        },
        cli=_c("-i", "labels:gallery/0@10.0", "-o", "labels:expand-labels/0@10.0", "--distance", "60"),
        produces=[out_seg("labels", "expand-labels", "labels:expand-labels/0@10.0?multilabel=true", multilabel=True)],
        notes="Two adjacent labels grown to meet at the medial plane without bleeding.",
    ),
    RenderSpec(
        group="process",
        command="fit-spline",
        run_name="fit-spline",
        inputs={"seg": seg("filament", "thin_curve")},
        cli=_c(
            "-i",
            "filament:gallery/0@10.0",
            "-o",
            "filament:fit-spline/0",
            "--spacing-distance",
            "40",
            "--voxel-spacing",
            "10.0",
        ),
        produces=[out_picks("filament", "fit-spline", "filament:fit-spline/0", min_count=3)],
        notes="Fit a 3D spline to a skeleton and sample oriented picks.",
    ),
    RenderSpec(
        group="process",
        command="hull",
        run_name="hull",
        inputs={"mesh": mesh("membrane", "nonconvex_mesh")},
        cli=_c("-i", "membrane:gallery/0", "-o", "membrane:hull/0", "--hull-type", "convex"),
        produces=[out_mesh("membrane", "hull", "membrane:hull/0")],
        notes="Convex hull of a mesh.",
    ),
    RenderSpec(
        group="process",
        command="rescale",
        run_name="rescale",
        inputs={"seg": seg("membrane", "blob_sphere", radius_frac=0.32)},
        cli=_c("-i", "membrane:gallery/0@10.0", "-o", "membrane:rescale/0@20.0", "--target-voxel-spacing", "20.0"),
        produces=[out_seg("membrane", "rescale", "membrane:rescale/0@20.0")],
        notes="Resample a segmentation to a different voxel spacing.",
    ),
    RenderSpec(
        group="process",
        command="split",
        run_name="split",
        inputs={
            "seg": seg(
                "labels",
                "multilabel_boxes",
                multilabel=True,
                labels=(15, 16),
                split_axis="x",
                box_frac=(0.60, 0.60, 0.30),
            ),
        },
        cli=_c("-i", "labels:gallery/0@10.0", "--output-user-id", "split"),
        produces=[
            out_seg("blob-a", "split", "blob-a:split/0@10.0"),
            out_seg("blob-b", "split", "blob-b:split/0@10.0"),
        ],
        before_show=[],  # derived: the multilabel input
        notes="Split a multilabel volume into per-object single-label masks.",
    ),
    RenderSpec(
        group="process",
        command="combine",
        run_name="combine",
        inputs={
            "a": seg("blob-a", "seg_box", center_frac=(0.5, 0.5, 0.32), size_frac=(0.60, 0.60, 0.24)),
            "b": seg("blob-b", "seg_box", center_frac=(0.5, 0.5, 0.68), size_frac=(0.60, 0.60, 0.24)),
        },
        cli=_c("-i", "*:gallery/0@10.0", "-o", "combined:combine/0@10.0"),
        produces=[out_seg("combined", "combine", "combined:combine/0@10.0?multilabel=true", multilabel=True)],
        notes="Two separated single-label blocks merged into one multilabel volume.",
    ),
    RenderSpec(
        group="process",
        command="thickness-filter",
        run_name="thickness-filter",
        inputs={
            "seg": seg(
                "membrane",
                "sphere_with_shell_patches",
                core_frac=0.20,
                shell_frac=0.32,
                shell_thickness_frac=0.025,
                n_patches=4,
                patch_halfangle_deg=38,
            ),
        },
        cli=_c("-i", "membrane:gallery/0@10.0", "-o", "membrane:thickness-filter/0@10.0", "--min-thickness", "120"),
        produces=[out_seg("membrane", "thickness-filter", "membrane:thickness-filter/0@10.0")],
        notes="Remove the thin partial shell patches by inscribed-sphere diameter, keeping the core.",
    ),
    RenderSpec(
        group="process",
        command="validbox",
        run_name="validbox",
        inputs={},  # uses the reference tomogram only
        cli=_c("-t", "wbp@10.0", "-o", "validbox:validbox/0", "--angle", "10"),
        produces=[out_mesh("validbox", "validbox", "validbox:validbox/0", min_count=1)],
        view=ViewSpec(preset="iso", tomo_slab=True),
        notes="Derive the valid imaging-area box mesh from a tomogram.",
    ),
    # NOTE: ``downsample`` (copick-torch, tomo->tomo) is intentionally omitted for now —
    # it is GPU-only (crashes with ZeroDivisionError on CPU-only hosts). The illustrative
    # pyramid-level render path remains in cxc.py if it is reinstated later.
    # ===================== logical ===================== #
    RenderSpec(
        group="logical",
        command="meshop",
        run_name="meshop",
        inputs={
            "a": mesh("sphere-a", "icosphere", center_frac=(0.5, 0.5, 0.42), radius_frac=0.2),
            "b": mesh("sphere-b", "icosphere", center_frac=(0.5, 0.5, 0.58), radius_frac=0.2),
        },
        cli=_c(
            "--operation",
            "union",
            "-i",
            "sphere-a:gallery/0",
            "-i",
            "sphere-b:gallery/0",
            "-o",
            "sphere-a:meshop/0",
        ),
        produces=[out_mesh("sphere-a", "meshop", "sphere-a:meshop/0")],
        modes=[
            Mode(
                op,
                op.capitalize(),
                _c(
                    "--operation",
                    op,
                    "-i",
                    "sphere-a:gallery/0",
                    "-i",
                    "sphere-b:gallery/0",
                    "-o",
                    f"sphere-a:meshop/{op}",
                ),
                [out_mesh("sphere-a", "meshop", f"sphere-a:meshop/{op}")],
                clip=Clip(cap=True) if op == "exclusion" else None,
            )  # cross-section reveals the XOR hole
            for op in ("difference", "intersection", "exclusion")
        ],
        notes="Boolean operations between two meshes.",
    ),
    RenderSpec(
        group="logical",
        command="segop",
        run_name="segop",
        inputs={
            "a": seg("blob-a", "blob_sphere", center_frac=(0.5, 0.5, 0.42), radius_frac=0.22),
            "b": seg("blob-b", "blob_sphere", center_frac=(0.5, 0.5, 0.58), radius_frac=0.22),
        },
        cli=_c(
            "--operation",
            "union",
            "-vs",
            "10.0",
            "-i",
            "blob-a:gallery/0",
            "-i",
            "blob-b:gallery/0",
            "-o",
            "blob-a:segop/0",
        ),
        produces=[out_seg("blob-a", "segop", "blob-a:segop/0@10.0")],
        modes=[
            Mode(
                op,
                op.capitalize(),
                _c(
                    "--operation",
                    op,
                    "-vs",
                    "10.0",
                    "-i",
                    "blob-a:gallery/0",
                    "-i",
                    "blob-b:gallery/0",
                    "-o",
                    f"blob-a:segop/{op}",
                ),
                [out_seg("blob-a", "segop", f"blob-a:segop/{op}@10.0")],
                clip=Clip(cap=True) if op == "exclusion" else None,
            )  # cross-section reveals the XOR hole
            for op in ("difference", "intersection", "exclusion")
        ],
        notes="Boolean operations between two segmentations.",
    ),
    RenderSpec(
        group="logical",
        command="enclosed",
        run_name="enclosed",
        inputs={
            "inner": seg("inner", "enclosed_fragments"),
            "outer": seg("outer-shell", "shell", role="reference", outer_frac=0.34),
        },
        cli=_c(
            "-vs",
            "10.0",
            "-i1",
            "inner:gallery/0",
            "-i2",
            "outer-shell:gallery/0",
            "-o",
            "inner:enclosed/0",
            "--margin",
            "1",
        ),
        produces=[out_seg("inner", "enclosed", "inner:enclosed/0@10.0")],
        notes="Remove components fully enclosed by another segmentation.",
    ),
    RenderSpec(
        group="logical",
        command="clipmesh",
        run_name="clipmesh",
        inputs={
            "mesh": mesh("membrane", "icosphere", radius_frac=0.34),
            "plane": mesh("ref-plane", "plane_mesh", role="reference", z_frac=0.5),
        },
        cli=_c(
            "-i",
            "membrane:gallery/0",
            "-rm",
            "ref-plane:gallery/0",
            "-o",
            "membrane:clipmesh/0",
            "--max-distance",
            "150",
        ),
        produces=[out_mesh("membrane", "clipmesh", "membrane:clipmesh/0")],
        modes=[
            Mode(
                "beyond",
                "Invert (beyond)",
                _c(
                    "-i",
                    "membrane:gallery/0",
                    "-rm",
                    "ref-plane:gallery/0",
                    "-o",
                    "membrane:clipmesh/beyond",
                    "--max-distance",
                    "150",
                    "--invert",
                ),
                [out_mesh("membrane", "clipmesh", "membrane:clipmesh/beyond")],
            ),
        ],
        notes="Keep mesh vertices within (or, inverted, beyond) a distance of a reference surface.",
    ),
    RenderSpec(
        group="logical",
        command="clipseg",
        run_name="clipseg",
        inputs={
            "seg": seg("membrane", "blob_sphere", radius_frac=0.32),
            "plane": mesh("ref-plane", "plane_mesh", role="reference", z_frac=0.5),
        },
        cli=_c(
            "-i",
            "membrane:gallery/0@10.0",
            "-rm",
            "ref-plane:gallery/0",
            "-o",
            "membrane:clipseg/0@10.0",
            "--max-distance",
            "60",
        ),
        produces=[out_seg("membrane", "clipseg", "membrane:clipseg/0@10.0")],
        modes=[
            Mode(
                "beyond",
                "Invert (beyond)",
                _c(
                    "-i",
                    "membrane:gallery/0@10.0",
                    "-rm",
                    "ref-plane:gallery/0",
                    "-o",
                    "membrane:clipseg/beyond@10.0",
                    "--max-distance",
                    "60",
                    "--invert",
                ),
                [out_seg("membrane", "clipseg", "membrane:clipseg/beyond@10.0")],
            ),
        ],
        notes="Keep segmentation voxels within (or, inverted, beyond) a distance of a reference.",
    ),
    RenderSpec(
        group="logical",
        command="clippicks",
        run_name="clippicks",
        inputs={
            "pts": picks("ribosome", "box_fill_points", n=70),
            "plane": mesh("ref-plane", "plane_mesh", role="reference", z_frac=0.5),
        },
        cli=_c(
            "-i",
            "ribosome:gallery/0",
            "-rm",
            "ref-plane:gallery/0",
            "-o",
            "ribosome:clippicks/0",
            "--max-distance",
            "250",
        ),
        produces=[out_picks("ribosome", "clippicks", "ribosome:clippicks/0")],
        modes=[
            Mode(
                "beyond",
                "Invert (beyond)",
                _c(
                    "-i",
                    "ribosome:gallery/0",
                    "-rm",
                    "ref-plane:gallery/0",
                    "-o",
                    "ribosome:clippicks/beyond",
                    "--max-distance",
                    "250",
                    "--invert",
                ),
                [out_picks("ribosome", "clippicks", "ribosome:clippicks/beyond")],
            ),
        ],
        notes="Keep picks within (or, inverted, beyond) a distance of a reference surface.",
    ),
    RenderSpec(
        group="logical",
        command="picksin",
        run_name="picksin",
        inputs={
            "pts": picks("ribosome", "box_fill_points", n=40),
            "box": mesh("roi-box", "box_mesh", role="reference", size_frac=(0.6, 0.6, 0.6)),
        },
        cli=_c("-i", "ribosome:gallery/0", "-rm", "roi-box:gallery/0", "-o", "ribosome:picksin/0"),
        produces=[out_picks("ribosome", "picksin", "ribosome:picksin/0")],
        notes="Keep only picks inside a reference volume.",
    ),
    RenderSpec(
        group="logical",
        command="picksout",
        run_name="picksout",
        inputs={
            "pts": picks("ribosome", "box_fill_points", n=40),
            "box": mesh("roi-box", "box_mesh", role="reference", size_frac=(0.6, 0.6, 0.6)),
        },
        cli=_c("-i", "ribosome:gallery/0", "-rm", "roi-box:gallery/0", "-o", "ribosome:picksout/0"),
        produces=[out_picks("ribosome", "picksout", "ribosome:picksout/0")],
        notes="Keep only picks outside a reference volume.",
    ),
]

SPECS_BY_COMMAND: Dict[str, RenderSpec] = {s.command: s for s in SPECS}


def all_specs() -> List[RenderSpec]:
    return list(SPECS)


def by_group(group: str) -> List[RenderSpec]:
    return [s for s in SPECS if s.group == group]


def get(command: str) -> RenderSpec:
    if command not in SPECS_BY_COMMAND:
        raise KeyError(f"Unknown command '{command}'. Known: {sorted(SPECS_BY_COMMAND)}")
    return SPECS_BY_COMMAND[command]
