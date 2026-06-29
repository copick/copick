"""Run a CLI command (primary + each mode) for a spec and verify each produced output.

The "after" render must never show a stale/empty result, so a variant is only included
in ``verified_keys`` once every one of its ``ProducedSpec`` is found via the copick API
with non-trivial content (picks >= min_count points, segmentation has foreground voxels,
mesh has faces). The emitter renders only verified variants.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import List, Optional, Set

from .schema import MESH, PICKS, SEGMENTATION, TOMOGRAM, ProducedSpec, RenderSpec


@dataclass
class RunResult:
    spec: RenderSpec
    ran: bool
    verified_keys: Set[str]  # mode keys that verified ("" = primary)
    message: str
    log_path: Optional[str] = None

    @property
    def ok(self) -> bool:
        # Rendering needs the primary variant; modes are optional extras.
        return "" in self.verified_keys


class CommandRunner:
    def __init__(self, cfg_path: str, log_dir: str, verbose: bool = True):
        self.cfg_path = cfg_path
        self.log_dir = log_dir
        self.verbose = verbose
        os.makedirs(log_dir, exist_ok=True)

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(f"[runner] {msg}", flush=True)

    def _argv(self, spec: RenderSpec, cli: List[str]) -> List[str]:
        subst = {"{cfg}": self.cfg_path, "{run}": spec.run_name}
        args = [subst.get(a, a) for a in cli]
        return ["copick", spec.group, spec.command, *args]

    def run(self, spec: RenderSpec) -> RunResult:
        log_path = os.path.join(self.log_dir, f"{spec.slug}.log")
        verified: Set[str] = set()
        messages: List[str] = []

        # Variants: primary ("") + each mode. cli=None => illustrative (no command run).
        variants = [("", spec.cli, spec.produces)] + [(m.key, m.cli, m.produces) for m in spec.modes]

        with open(log_path, "w") as log:
            for key, cli, produces in variants:
                label = key or "primary"
                if cli is None:
                    verified.add(key)
                    messages.append(f"{label}: no CLI (illustrative)")
                    continue
                argv = self._argv(spec, cli)
                self._log(f"$ {' '.join(argv)}")
                log.write("$ " + " ".join(argv) + "\n")
                log.flush()
                proc = subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT, text=True)
                log.write("\n")
                if proc.returncode != 0:
                    messages.append(f"{label}: CLI exited {proc.returncode}")
                    continue
                ok, detail = self._verify(spec.run_name, produces)
                if ok:
                    verified.add(key)
                messages.append(f"{label}: {detail}")

        return RunResult(spec, ran=True, verified_keys=verified, message="; ".join(messages), log_path=log_path)

    # -- verification ----------------------------------------------------- #

    def _verify(self, run_name: str, produces: List[ProducedSpec]) -> tuple[bool, str]:
        if not produces:
            return True, "no produces declared"
        import copick

        root = copick.from_file(self.cfg_path)  # fresh open: no stale cache
        run = root.get_run(run_name)
        if run is None:
            return False, f"run '{run_name}' missing after CLI"
        problems: List[str] = []
        for ps in produces:
            ok, detail = self._verify_one(run, ps)
            if not ok:
                problems.append(detail)
        if problems:
            return False, "; ".join(problems)
        return True, f"verified {len(produces)} output(s)"

    def _verify_one(self, run, ps: ProducedSpec) -> tuple[bool, str]:
        import numpy as np

        sid = ps.session_id  # None -> match any session (glob/template outputs)

        if ps.kind == PICKS:
            for p in run.get_picks(object_name=ps.object_name, user_id=ps.user_id, session_id=sid):
                try:
                    if len(p.points or []) >= ps.min_count:
                        return True, "picks ok"
                except Exception:  # noqa: BLE001
                    continue
            return False, f"picks {ps.object_name}:{ps.user_id}/{sid} < {ps.min_count} pts"

        if ps.kind == SEGMENTATION:
            for s in run.get_segmentations(name=ps.object_name, user_id=ps.user_id, session_id=sid):
                try:
                    if int(np.count_nonzero(s.numpy())) > 0:
                        return True, "seg ok"
                except Exception:  # noqa: BLE001
                    continue
            return False, f"seg {ps.object_name}:{ps.user_id}/{sid} empty/missing"

        if ps.kind == MESH:
            for m in run.get_meshes(object_name=ps.object_name, user_id=ps.user_id, session_id=sid):
                try:
                    if _face_count(m.mesh) >= ps.min_count:
                        return True, "mesh ok"
                except Exception:  # noqa: BLE001
                    continue
            return False, f"mesh {ps.object_name}:{ps.user_id}/{sid} < {ps.min_count} faces"

        if ps.kind == TOMOGRAM:
            return True, "tomogram (not verified)"
        return False, f"unknown produced kind '{ps.kind}'"


def _face_count(geom) -> int:
    faces = getattr(geom, "faces", None)
    if faces is not None:
        return len(faces)
    geometry = getattr(geom, "geometry", None)  # trimesh.Scene
    if geometry:
        return sum(len(g.faces) for g in geometry.values())
    return 0
