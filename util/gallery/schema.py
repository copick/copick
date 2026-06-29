"""Dataclasses describing how to fabricate, run and render one CLI command.

These are inert data containers (no copick import), so the spec registry in
``specs.py`` can be imported and introspected cheaply. The pipeline modules consume
them: ``fixtures.py`` reads ``RenderSpec.inputs``; ``runner.py`` reads ``cli`` /
``produces``; ``cxc.py`` reads ``before_show`` / ``after_show`` / ``view``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# Physical frame shared by every fabricated run. A cube of (shape * voxel_size)
# angstroms. With the defaults below: 128 * 10 = 1280 A, centered at (640, 640, 640).
DEFAULT_SHAPE: Tuple[int, int, int] = (128, 128, 128)  # (z, y, x)
DEFAULT_VOXEL: float = 10.0
REFERENCE_TOMO_TYPE: str = "wbp"

# copick entity kinds.
PICKS = "picks"
SEGMENTATION = "segmentation"
MESH = "mesh"
TOMOGRAM = "tomogram"


@dataclass
class EntitySpec:
    """A synthetic input entity to materialize into the copick project.

    ``recipe`` keys a function in ``geometry.RECIPES``; ``recipe_kwargs`` are passed
    through. ``role`` controls rendering: ``subject`` entities are the focus (opaque,
    shown only in *before*), while ``reference``/``context`` entities frame the
    operation (kept faint in *both* renders). Faintness is driven by the object's
    config color alpha, so no per-model ChimeraX command is needed.
    """

    kind: str
    object_name: str  # pickable-object / single-label seg name / mesh object (dashes only)
    recipe: str
    recipe_kwargs: Dict[str, Any] = field(default_factory=dict)
    user_id: str = "gallery"
    session_id: str = "0"
    is_multilabel: bool = False
    voxel_size: float = DEFAULT_VOXEL
    role: str = "subject"  # subject | reference | context
    # Keep an opaque subject input visible-but-translucent in the AFTER frame (instead of
    # hidden), to show the transform in place. picks: per-frame transparency on the markers
    # (axes stay opaque); seg: volume transparency; mesh: must carry low config alpha
    # (no robust model id) — use a *-faint object instead.
    ghost_in_after: bool = False
    ghost_transparency: int = 70  # ChimeraX 'transparency' % for a ghosted PICKS input


@dataclass
class ProducedSpec:
    """An entity a command is expected to write — verification target + after-render.

    ``uri`` is the chimerax-copick URI to open in the *after* render (globs allowed).
    The remaining fields locate the entity via the copick API for verification.
    """

    kind: str
    uri: str
    object_name: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None  # may be a glob/regex for {instance_id} outputs
    voxel_size: Optional[float] = None
    is_multilabel: bool = False
    min_count: int = 1  # picks: >= N points; seg: > 0 voxels; mesh: >= N faces
    colorize: bool = False  # color each produced model distinctly (e.g. separate-components)
    colorize_colors: List[str] = field(default_factory=list)  # explicit per-model colors


@dataclass
class ShowSpec:
    """An explicit entity to display in a render (overrides the default derivation)."""

    kind: str
    uri: str
    faint: bool = False
    colorize: bool = False
    colorize_colors: List[str] = field(default_factory=list)


@dataclass
class Mode:
    """An additional CLI variant of a command that shares the same inputs.

    Modes differ only in flags + output (e.g. ``meshop`` operations, ``--invert``). They
    reuse the spec's inputs (one shared "before"); each produces its own "after" image
    named ``{command}.{key}-after.png``. ``key`` becomes the docs caption.
    """

    key: str
    label: str
    cli: List[str]
    produces: List["ProducedSpec"] = field(default_factory=list)
    after_show: List["ShowSpec"] = field(default_factory=list)
    clip: Optional["Clip"] = None  # cross-section for this mode's after frame


@dataclass
class Clip:
    """A cross-section for ONE rendered frame, defined in a volume's coordinate system.

    Emitted (after the camera is restored) as a ``clip front`` scene plane through the box
    center with normal ``axis`` in the reference tomogram's coordinate system — front/back
    planes "move along with the scene", so the cut is stable regardless of the camera
    (unlike near/far planes, which are tied to the viewer and broke after ``view gallery``).
    ``cap=True`` caps clipped segmentation isosurfaces (``volume capFaces``) so the cut reads
    SOLID; ``cap=False`` leaves a hollow rim (mesh outputs). ``view gallery`` clears clip
    planes, so the emitter re-asserts the clip every frame.
    """

    cap: bool = True
    offset: float = 0.0  # Angstrom along the axis from the box center
    # Clip-plane normal in the reference tomogram's coordinate system. "0,0,-1" keeps the
    # cut face toward the camera for the iso preset (the near, viewer-side half is removed).
    axis: str = "0,0,-1"


@dataclass
class ViewSpec:
    """Framing shared by BOTH renders of a pair, so they read as one transformation.

    The camera is established deterministically from the constant reference-tomogram
    box (see ``cxc.py``): ``view #1`` frames the box, then the ``preset`` turn-sequence
    rotates about its center. No hand-tuned matrices; before/after never re-frame.
    """

    preset: str = "iso"  # key into palette.CAMERA_PRESETS
    tomo_slab: bool = False  # show a faint slab of the reference tomogram for context
    zoom: float = 0.85  # <1 adds margin around the box
    # Square aspect, matching the (square) thumbnail, so before/after/thumb share the exact
    # framing — ``save`` at a different aspect than the camera's window-fit re-frames.
    width: int = 1200
    height: int = 1200
    supersample: int = 3


@dataclass
class RenderSpec:
    """Everything needed to fabricate, run and render one CLI command."""

    group: str  # convert | process | logical
    command: str  # picks2seg, skeletonize, ...
    run_name: str  # dashes only; unique per command
    inputs: Dict[str, EntitySpec] = field(default_factory=dict)
    cli: Optional[List[str]] = None  # argv after "copick"; {cfg} / {run} placeholders
    produces: List[ProducedSpec] = field(default_factory=list)
    # Additional mode variants (share inputs; each renders its own "after"). The fields
    # above are the "primary" variant (mode key "").
    modes: List[Mode] = field(default_factory=list)
    # Optional explicit show-lists; when empty, cxc.py derives them from inputs/produces.
    before_show: List[ShowSpec] = field(default_factory=list)
    after_show: List[ShowSpec] = field(default_factory=list)
    before_clip: Optional["Clip"] = None  # cross-section for the BEFORE frame
    after_clip: Optional["Clip"] = None  # cross-section for the PRIMARY after frame
    view: ViewSpec = field(default_factory=ViewSpec)
    tomo_shape: Tuple[int, int, int] = DEFAULT_SHAPE
    voxel_size: float = DEFAULT_VOXEL
    reference_tomo_type: str = REFERENCE_TOMO_TYPE
    needs: List[str] = field(default_factory=list)  # e.g. ["manual"] -> skipped by --all
    notes: str = ""

    @property
    def slug(self) -> str:
        """Stable identifier used for run names, cxc files and log files."""
        return f"{self.group}-{self.command}"
