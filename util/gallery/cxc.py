"""Emit ChimeraX command files (.cxc) that render before/after image pairs.

Framing uses a **named view** anchored to the reference tomogram (which spans the full,
constant box): we ``view`` that model once, apply the preset turns + zoom, and save it as
``view name gallery``. Before every ``save`` we ``view gallery`` to restore the exact
camera — absolute and scene-independent, so before/after (and every mode) align even when
the output scene is smaller than the input. Backgrounds are transparent → one render
serves both docs themes.

Commands with modes (``RenderSpec.modes``) share one "before" (the inputs) and render one
"after" per mode: primary -> ``{command}-after.png`` (+ thumb ``{command}.png``), mode
``K`` -> ``{command}.{K}-after.png``.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional

from . import palette
from .schema import (
    MESH,
    PICKS,
    SEGMENTATION,
    TOMOGRAM,
    Clip,
    EntitySpec,
    ProducedSpec,
    RenderSpec,
    ShowSpec,
)

# chimerax-copick verb per entity kind.
_KIND_VERB = {PICKS: "picks", SEGMENTATION: "segmentation", MESH: "mesh"}

# Model spec of the reference tomogram loaded by ``copick open run``. In a fresh session
# ArtiaX is ``#1`` with manager groups Tomograms ``#1.1`` / Particle Lists ``#1.2`` /
# Geometric Models ``#1.3``; the run's tomogram is the first child of the Tomograms group
# -> ``#1.1.1``. We frame/hide/style only this model so the ArtiaX containers stay shown
# (entities opened afterwards are their children) and later segmentations — which ArtiaX
# also imports into the Tomograms group (#1.1.2, ...) — remain visible.
TOMO_SPEC = "#1.1.1"

# ArtiaX "Tomograms" manager group — contains the reference tomogram (#1.1.1) and every
# imported segmentation (#1.1.2, ...). Used to cap clipped segmentation isosurfaces.
TOMO_GROUP = "#1.1"

# Particle axes length (Angstrom) = ratio * marker radius, so the tri-colored arrows
# protrude past the opaque marker sphere. (ArtiaX's own default is 15*voxel = 150 at v=10;
# a flat 12 sat entirely inside the 50-60 A markers and was invisible.)
AXES_RADIUS_RATIO = 2.2
AXES_SIZE_FALLBACK = 120  # frames with no picks -> applies to 0 partlists (harmless)

VIEW_NAME = "gallery"


def _fmt_voxel(v: float) -> str:
    return f"{v:g}"


def _entity_uri(ent: EntitySpec) -> str:
    if ent.kind == SEGMENTATION:
        uri = f"{ent.object_name}:{ent.user_id}/{ent.session_id}@{_fmt_voxel(ent.voxel_size)}"
        if ent.is_multilabel:
            uri += "?multilabel=true"
        return uri
    return f"{ent.object_name}:{ent.user_id}/{ent.session_id}"


def _open(kind: str, uri: str) -> str:
    return f'copick open {_KIND_VERB[kind]} "{uri}"'


def _hide(kind: str, uri: str) -> str:
    return f'copick hide {_KIND_VERB[kind]} "{uri}"'


class CxcEmitter:
    def __init__(self, cfg_path: str, assets_dir: str):
        """``assets_dir`` is the docs assets root, e.g. ``docs/assets/tools``."""
        self.cfg_path = os.path.abspath(cfg_path)
        self.assets_dir = os.path.abspath(assets_dir)

    # -- paths ------------------------------------------------------------ #

    def _img(self, spec: RenderSpec, suffix: str) -> str:
        return os.path.join(self.assets_dir, spec.group, f"{spec.command}{suffix}.png")

    def _mode_img(self, spec: RenderSpec, key: str) -> str:
        return os.path.join(self.assets_dir, spec.group, f"{spec.command}.{key}-after.png")

    def _save(self, path: str, w: int, h: int, ss: int) -> str:
        return f'save "{path}" width {w} height {h} supersample {ss} transparentBackground true'

    # -- framing (named view) -------------------------------------------- #

    def _establish_view(self, spec: RenderSpec) -> List[str]:
        """Frame the constant box and save it as a named view, then drop the helper.

        Uses 8 opaque markers at the box corners as the framing anchor (ArtiaX shows the
        tomogram as a slice, which ``view <spec>`` does not treat as a framable displayed
        object). The markers are real geometry so ``view #200`` frames them reliably; they
        are opaque (transparent drawings are excluded from ``view``'s bbox) and closed
        before any save, so they never appear in a render. The resulting camera is saved
        as a named view and restored absolutely (scene-independent) before each save."""
        nz, ny, nx = spec.tomo_shape
        v = spec.voxel_size
        ex, ey, ez = nx * v, ny * v, nz * v
        cx, cy, cz = ex / 2, ey / 2, ez / 2
        corners = [(0, 0, 0), (ex, 0, 0), (0, ey, 0), (0, 0, ez), (ex, ey, 0), (ex, 0, ez), (0, ey, ez), (ex, ey, ez)]
        lines = [f"marker #200 position {x:g},{y:g},{z:g} radius 2 color #808080ff" for (x, y, z) in corners]
        lines.append(f"cofr {cx:g},{cy:g},{cz:g}")
        lines.append("view #200")
        lines += palette.CAMERA_PRESETS.get(spec.view.preset, [])
        lines.append(f"zoom {spec.view.zoom:g}")
        lines.append(f"view name {VIEW_NAME}")
        lines.append("close #200")
        return lines

    def _axes_size(self, spec: RenderSpec) -> int:
        """Axes length for this command, from the largest pick-object radius it shows
        (inputs + every variant's produced picks), so arrows protrude past the marker."""
        radii: List[float] = []

        def _add(obj_name):
            o = palette.OBJECTS_BY_NAME.get(obj_name or "")
            if o:
                radii.append(o[4])  # ObjectDef[4] = radius

        for e in spec.inputs.values():
            if e.kind == PICKS:
                _add(e.object_name)
        for produces in [spec.produces, *(m.produces for m in spec.modes)]:
            for p in produces:
                if p.kind == PICKS:
                    _add(p.object_name)
        return round(AXES_RADIUS_RATIO * max(radii)) if radii else AXES_SIZE_FALLBACK

    def _restore(self, spec: RenderSpec) -> List[str]:
        """Per-save: set protruding particle axes and restore the exact camera."""
        return [f"artiax particles axesSize {self._axes_size(spec)}", f"view {VIEW_NAME}"]

    def _uses_clip(self, spec: RenderSpec) -> bool:
        return bool(spec.before_clip or spec.after_clip or any(m.clip for m in spec.modes))

    def _clip_lines(self, spec: RenderSpec, clip: Optional[Clip]) -> List[str]:
        """Per-frame cross-section state, emitted AFTER ``_restore`` ('view gallery' clears
        clip planes) and just before ``save``. Returns [] for commands that never clip, so
        their output is byte-identical.

        Uses a ``clip front`` SCENE plane (which moves with the models, unlike near/far
        camera planes) through the box center, with normal ``axis`` expressed in the
        reference tomogram's coordinate system (``coordinateSystem #1.1.1``) — so the cut is
        stable regardless of the camera restore. ``volume #1.1 capFaces`` fills the cut on
        segmentation isosurfaces so they read solid (ArtiaX volumes don't honor the global
        ``surface cap`` toggle). Mesh outputs (seg2mesh after, meshop exclusion) stay hollow
        — intended. The outline box (set in ``_stage_tomo``) stays on, marking the cut."""
        if not self._uses_clip(spec):
            return []
        if clip is None:  # reset to the un-clipped default
            return ["clip off", f"volume {TOMO_GROUP} capFaces false"]
        nz, ny, nx = spec.tomo_shape
        v = spec.voxel_size
        cx, cy, cz = nx * v / 2, ny * v / 2, nz * v / 2
        return [
            f"clip front {clip.offset:g} coordinateSystem {TOMO_SPEC} "
            f"position {cx:g},{cy:g},{cz:g} axis {clip.axis}",
            f"volume {TOMO_GROUP} capFaces {'true' if clip.cap else 'false'}",
        ]

    def _stage_tomo(self, spec: RenderSpec) -> List[str]:
        """Keep the reference tomogram displayed only as a wireframe outline box — a
        spatial anchor shown in every render. ``tomo_slab`` additionally shows a faint
        data slab; otherwise the data is suppressed (empty surface above the data range)
        so just the box remains. The box spans the constant 1280 A cube."""
        lines = [f"volume {TOMO_SPEC} showOutlineBox true outlineBoxRgb #808080"]
        if spec.view.tomo_slab:
            lines += [f"volume {TOMO_SPEC} style image", f"volume {TOMO_SPEC} transparency 0.82"]
        else:
            lines.append(f"volume {TOMO_SPEC} style surface level 100")
        return lines

    # -- show-list derivation -------------------------------------------- #

    def _before_shows(self, spec: RenderSpec) -> List[ShowSpec]:
        if spec.before_show:
            return spec.before_show
        return [
            ShowSpec(kind=e.kind, uri=_entity_uri(e), faint=e.role in ("reference", "context"))
            for e in spec.inputs.values()
            if e.kind != TOMOGRAM
        ]

    def _produced_shows(self, produces: List[ProducedSpec], override: List[ShowSpec]) -> List[ShowSpec]:
        if override:
            return override
        return [
            ShowSpec(kind=p.kind, uri=p.uri, colorize=p.colorize, colorize_colors=p.colorize_colors)
            for p in produces
            if p.kind != TOMOGRAM
        ]

    def _variants(self, spec: RenderSpec, verified_keys: Optional[set]):
        """(key, produces, after_show, clip) for the primary ("") then each (kept) mode."""
        variants = [("", spec.produces, spec.after_show, spec.after_clip)]
        for m in spec.modes:
            variants.append((m.key, m.produces, m.after_show, m.clip))
        if verified_keys is not None:
            variants = [v for v in variants if v[0] in verified_keys]
        return variants

    # -- emit ------------------------------------------------------------- #

    def emit(self, spec: RenderSpec, verified_keys: Optional[set] = None) -> str:
        """Return the .cxc text for one command. ``verified_keys`` (mode keys that
        passed verification, "" = primary) filters which afters are rendered; ``None``
        renders all."""
        if "tomo-pyramid" in spec.needs:
            return self._emit_tomo_pyramid(spec)
        return self._emit_pair(spec, verified_keys)

    def _emit_pair(self, spec: RenderSpec, verified_keys: Optional[set]) -> str:
        v = spec.view
        before_png, after_png, thumb_png = (self._img(spec, s) for s in ("-before", "-after", ""))
        lines: List[str] = [
            f"# ===== {spec.group} {spec.command} =====",
            f"copick start {self.cfg_path}",
            f"copick open run {spec.run_name} tomo_type {spec.reference_tomo_type} zarr_level 0",
            "cks il",  # toggle copick info 2dlabels off (durable; survives later opens)
            "lighting soft",
            "graphics silhouettes true",
        ]
        # Establish the named view, then stage the tomogram as an outline-box anchor.
        lines += self._establish_view(spec)
        lines += self._stage_tomo(spec)

        # Track ArtiaX model ids of derived inputs so subjects can be ghosted in the after
        # (#1.1.1 = ref tomo; seg inputs -> #1.1.2+, picks inputs -> #1.2.1+, in open order).
        seg_n, pl_n = 1, 0
        ghost_id: Dict[str, str] = {}
        derive = not spec.before_show
        inputs_in_order = [e for e in spec.inputs.values() if e.kind != TOMOGRAM]
        n_before_segs = sum(1 for e in inputs_in_order if e.kind == SEGMENTATION)

        # BEFORE: shared inputs (subjects + references).
        lines.append("# --- before ---")
        for s in self._before_shows(spec):
            lines.append(_open(s.kind, s.uri))
        if derive:
            for e in inputs_in_order:  # same order as the derived before-shows
                if e.kind == SEGMENTATION:
                    seg_n += 1
                    ghost_id[_entity_uri(e)] = f"#1.1.{seg_n}"
                elif e.kind == PICKS:
                    pl_n += 1
                    ghost_id[_entity_uri(e)] = f"#1.2.{pl_n}"
        lines += self._restore(spec)
        lines += self._clip_lines(spec, spec.before_clip)
        lines.append(self._save(before_png, v.width, v.height, v.supersample))

        # AFTER: hide subjects (references persist); ghost the ones flagged ghost_in_after.
        lines.append("# --- after ---")
        for e in inputs_in_order:
            if e.role != "subject":
                continue  # references already persist (and stay faint)
            uri = _entity_uri(e)
            if e.ghost_in_after:
                g = ghost_id.get(uri)
                if e.kind == PICKS and g:
                    lines.append(f"transparency {g} {e.ghost_transparency} target a")
                elif e.kind == SEGMENTATION and g:
                    lines.append(f"volume {g} transparency 0.7")
                # MESH: no robust id -> translucency comes from a *-faint config alpha
            else:
                lines.append(_hide(e.kind, uri))

        prev: List[ShowSpec] = []
        for key, produces, override, clip in self._variants(spec, verified_keys):
            for s in prev:  # hide the previous variant's produced entities
                lines.append(_hide(s.kind, s.uri))
            shows = self._produced_shows(produces, override)
            for s in shows:
                lines.append(_open(s.kind, s.uri))
                if s.colorize and s.colorize_colors and s.kind == SEGMENTATION:
                    first = 2 + n_before_segs  # ref=#1.1.1, then before-seg inputs, then produced
                    for i, col in enumerate(s.colorize_colors):
                        lines.append(f"color #1.1.{first + i} {col}")
            lines += self._restore(spec)
            lines += self._clip_lines(spec, clip)
            if key == "":
                lines.append(self._save(after_png, v.width, v.height, v.supersample))
                lines.append(self._save(thumb_png, 640, 640, v.supersample))
            else:
                lines.append(f"# mode: {key}")
                lines.append(self._save(self._mode_img(spec, key), v.width, v.height, v.supersample))
            prev = shows

        lines.append("close session")
        lines.append("")
        return "\n".join(lines)

    def _emit_tomo_pyramid(self, spec: RenderSpec) -> str:
        """Render a tomogram subject at two pyramid levels (full vs coarse) — kept for a
        possible future ``downsample`` reinstatement. Two sessions, each with its own
        named view anchored to the box."""
        v = spec.view
        before_png, after_png, thumb_png = (self._img(spec, s) for s in ("-before", "-after", ""))
        alg = next((e.object_name for e in spec.inputs.values() if e.kind == TOMOGRAM), "wbp")

        def session(level: int, saves: List[str]) -> List[str]:
            block = [
                f"copick start {self.cfg_path}",
                f"copick open run {spec.run_name} tomo_type {alg} zarr_level {level}",
                "cks il",
                "lighting soft",
                "graphics silhouettes true",
                f"volume {TOMO_SPEC} style image",
                f"volume {TOMO_SPEC} showOutlineBox true outlineBoxRgb #808080",
            ]
            block += self._establish_view(spec)
            block += self._restore(spec)
            block += saves
            block.append("close session")
            return block

        lines = [f"# ===== {spec.group} {spec.command} ====="]
        lines += session(0, [self._save(before_png, v.width, v.height, v.supersample)])
        lines += session(
            2,
            [
                self._save(after_png, v.width, v.height, v.supersample),
                self._save(thumb_png, 640, 640, v.supersample),
            ],
        )
        lines.append("")
        return "\n".join(lines)

    def ensure_dirs(self, spec: RenderSpec) -> None:
        os.makedirs(os.path.join(self.assets_dir, spec.group), exist_ok=True)
