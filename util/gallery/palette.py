"""Pickable-object catalog + deterministic camera presets for the gallery.

``OBJECTS`` is the single source of truth for the synthetic project's pickable
objects; ``fixtures.build_config`` writes them into the copick config. Colors carry
their own alpha — *reference* objects (boxes, planes, shells) are translucent so they
frame an operation without occluding the subject, with no per-model ChimeraX command.

``CAMERA_PRESETS`` are turn-sequences applied after ``view #1`` (which frames the
constant reference-tomogram box). Same preset -> identical framing for before & after.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

# (name, is_particle, label, (r, g, b, a), radius)
# Labels are unique and != 0. Names use dashes only (underscores are forbidden).
ObjectDef = Tuple[str, bool, int, Tuple[int, int, int, int], float]

OBJECTS: List[ObjectDef] = [
    # --- particles (rendered as ArtiaX markers) ------------------------------
    ("ribosome", True, 1, (0, 117, 220, 255), 60.0),
    ("proteasome", True, 2, (240, 130, 40, 255), 60.0),
    ("point", True, 3, (43, 206, 72, 255), 28.0),  # mesh2picks output (small so dense clouds read)
    ("point-blue", True, 26, (0, 117, 220, 255), 30.0),  # blue fitting-cloud markers (picks->shape)
    ("slab-top", True, 29, (240, 130, 40, 255), 26.0),  # picks2slab top boundary layer
    ("slab-bot", True, 30, (0, 117, 220, 255), 26.0),  # picks2slab bottom boundary layer
    # --- volumetric / surface objects (seg + mesh) ---------------------------
    ("membrane", False, 10, (200, 200, 200, 255), 10.0),
    ("vesicle", False, 11, (0, 170, 210, 255), 10.0),
    ("actin", False, 12, (255, 205, 0, 255), 10.0),
    ("filament", False, 13, (180, 90, 220, 255), 10.0),
    ("blob", False, 14, (90, 200, 120, 255), 10.0),
    ("blob-a", False, 15, (0, 200, 200, 255), 10.0),
    ("blob-b", False, 16, (235, 100, 160, 255), 10.0),
    ("sheet", False, 17, (245, 150, 60, 255), 10.0),
    ("inner", False, 18, (90, 200, 120, 255), 10.0),
    ("sphere-a", False, 20, (220, 60, 60, 255), 10.0),
    ("sphere-b", False, 21, (60, 110, 220, 255), 10.0),
    # --- translucent reference geometry (kept faint in both renders) ---------
    ("outer-shell", False, 19, (170, 170, 170, 70), 10.0),
    ("roi-box", False, 22, (250, 210, 0, 70), 10.0),
    ("ref-plane", False, 23, (0, 200, 220, 90), 10.0),
    ("validbox", False, 24, (250, 210, 0, 80), 10.0),
    ("membrane-faint", False, 25, (200, 200, 200, 130), 10.0),  # translucent mesh input (mesh2picks)
    ("fit-surface", False, 27, (190, 190, 190, 110), 10.0),  # translucent fitted output (picks->shape)
    ("fit-solid", False, 28, (190, 190, 190, 255), 10.0),  # opaque fitted output (picks2ellipsoid)
    ("caps", False, 31, (0, 117, 220, 255), 10.0),  # opaque blue cap surfaces (mesh2caps output)
]

OBJECTS_BY_NAME: Dict[str, ObjectDef] = {o[0]: o for o in OBJECTS}


def color_of(name: str) -> Tuple[int, int, int, int]:
    return OBJECTS_BY_NAME[name][3]


# Turn commands applied after ``view #1`` (default ChimeraX view looks down -z, i.e.
# the xy plane faces the camera). Rotations are about the box center (cofr at #1).
CAMERA_PRESETS: Dict[str, List[str]] = {
    "iso": ["turn y 35", "turn x -25"],
    "front": [],  # xy plane (good for picks clouds, planes)
    "top": ["turn x -90"],  # xz plane
    "side": ["turn y 90"],  # yz plane
}
