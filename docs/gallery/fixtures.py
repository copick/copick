"""Materialize synthetic inputs for a RenderSpec into a local copick project.

``build_config`` writes the overlay-only filesystem config (pickable objects come from
``palette.OBJECTS``). ``FixtureBuilder`` opens that project once and, per spec, creates
a dedicated run, a reference tomogram (so the run has a defined voxel spacing / box),
and every input entity via the copick API. Everything is idempotent (``exist_ok``) and
seeded, so repeated builds are byte-stable.
"""

from __future__ import annotations

import json
import os

import numpy as np

from . import geometry
from .palette import OBJECTS
from .schema import MESH, PICKS, SEGMENTATION, TOMOGRAM, EntitySpec, RenderSpec

USER_ID = "gallery"


def build_config(project_dir: str) -> str:
    """Write ``<project_dir>/config.json`` (overlay-only, local backend). Returns path."""
    os.makedirs(project_dir, exist_ok=True)
    pickable = [
        {
            "name": name,
            "is_particle": is_particle,
            "label": label,
            "color": list(color),
            "radius": radius,
        }
        for (name, is_particle, label, color, radius) in OBJECTS
    ]
    config = {
        "name": "copick CLI gallery",
        "description": "Synthetic project for rendering CLI before/after figures.",
        "version": "0.5.0",
        "pickable_objects": pickable,
        "user_id": USER_ID,
        "config_type": "filesystem",
        "overlay_root": "local://" + os.path.abspath(os.path.join(project_dir, "overlay")),
        "overlay_fs_args": {"auto_mkdir": True},
    }
    cfg_path = os.path.join(project_dir, "config.json")
    with open(cfg_path, "w") as f:
        json.dump(config, f, indent=2)
    return cfg_path


class FixtureBuilder:
    """Creates runs + input entities for specs against one open copick root."""

    def __init__(self, cfg_path: str, verbose: bool = True):
        self.cfg_path = cfg_path
        self.verbose = verbose
        self._root = None

    @property
    def root(self):
        if self._root is None:
            import copick

            self._root = copick.from_file(self.cfg_path)
        return self._root

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(f"[fixtures] {msg}", flush=True)

    # -- entity materialization ------------------------------------------- #

    def _ensure_voxel_spacing(self, run, voxel_size: float):
        return run.new_voxel_spacing(voxel_size=voxel_size, exist_ok=True)

    def _reference_tomogram(self, run, spec: RenderSpec) -> None:
        if not spec.reference_tomo_type:
            return
        rng = np.random.default_rng(geometry.seed_for(spec.slug, "reference"))
        vol = geometry.reference_volume(rng, shape=spec.tomo_shape, voxel_size=spec.voxel_size)
        vs = self._ensure_voxel_spacing(run, spec.voxel_size)
        tomo = vs.new_tomogram(spec.reference_tomo_type, exist_ok=True)
        tomo.from_numpy(vol.astype(np.float32), levels=3)
        self._log(f"  reference tomogram {spec.reference_tomo_type}@{spec.voxel_size}")

    def _materialize(self, run, spec: RenderSpec, alias: str, ent: EntitySpec) -> None:
        rng = np.random.default_rng(geometry.seed_for(spec.slug, alias, ent.recipe))
        if ent.kind == PICKS:
            positions, transforms = geometry.build(
                ent.recipe,
                rng,
                shape=spec.tomo_shape,
                voxel_size=spec.voxel_size,
                **ent.recipe_kwargs,
            )
            picks = run.new_picks(ent.object_name, ent.session_id, user_id=ent.user_id, exist_ok=True)
            # Oriented picks (random transforms) show ArtiaX axes; transform-less picks
            # (orient="none", e.g. fitting clouds) render as plain markers.
            picks.meta.trust_orientation = transforms is not None
            picks.from_numpy(np.asarray(positions, dtype=np.float32), transforms)
            self._log(f"  picks {ent.object_name}:{ent.user_id}/{ent.session_id} ({len(positions)} pts)")

        elif ent.kind == SEGMENTATION:
            mask = geometry.build(
                ent.recipe,
                rng,
                shape=spec.tomo_shape,
                voxel_size=ent.voxel_size,
                **ent.recipe_kwargs,
            )
            self._ensure_voxel_spacing(run, ent.voxel_size)
            seg = run.new_segmentation(
                voxel_size=ent.voxel_size,
                name=ent.object_name,
                session_id=ent.session_id,
                is_multilabel=ent.is_multilabel,
                user_id=ent.user_id,
                exist_ok=True,
            )
            seg.from_numpy(mask.astype(np.uint8))
            self._log(
                f"  seg {ent.object_name}:{ent.user_id}/{ent.session_id}@{ent.voxel_size}"
                f" ({int((mask > 0).sum())} fg voxels, multilabel={ent.is_multilabel})",
            )

        elif ent.kind == MESH:
            tmesh = geometry.build(
                ent.recipe,
                rng,
                shape=spec.tomo_shape,
                voxel_size=spec.voxel_size,
                **ent.recipe_kwargs,
            )
            mesh = run.new_mesh(ent.object_name, ent.session_id, user_id=ent.user_id, exist_ok=True)
            mesh.mesh = tmesh
            mesh.store()
            self._log(f"  mesh {ent.object_name}:{ent.user_id}/{ent.session_id} ({len(tmesh.faces)} faces)")

        elif ent.kind == TOMOGRAM:
            vol = geometry.build(
                ent.recipe,
                rng,
                shape=spec.tomo_shape,
                voxel_size=ent.voxel_size,
                **ent.recipe_kwargs,
            )
            vs = self._ensure_voxel_spacing(run, ent.voxel_size)
            tomo = vs.new_tomogram(ent.object_name, exist_ok=True)  # object_name == tomo_type
            tomo.from_numpy(vol.astype(np.float32), levels=3)
            self._log(f"  tomogram {ent.object_name}@{ent.voxel_size}")

        else:
            raise ValueError(f"Unknown entity kind '{ent.kind}' for alias '{alias}'")

    # -- public ----------------------------------------------------------- #

    def build_spec(self, spec: RenderSpec) -> None:
        """Create the run, reference tomogram and all input entities for one spec."""
        self._log(f"run '{spec.run_name}' for {spec.group} {spec.command}")
        run = self.root.new_run(spec.run_name, exist_ok=True)
        self._reference_tomogram(run, spec)
        for alias, ent in spec.inputs.items():
            self._materialize(run, spec, alias, ent)
