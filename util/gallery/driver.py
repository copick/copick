"""Orchestrate the gallery pipeline: fabricate -> run+verify -> emit .cxc.

Run from the ``util`` directory so ``gallery`` is importable as a package:

    cd copick/util && python -m gallery.driver --only picks2seg
    cd copick/util && python -m gallery.driver --group convert
    cd copick/util && python -m gallery.driver --all

(or use the Makefile: ``make -C copick/util/gallery gallery CMD=picks2seg``)

The driver never launches ChimeraX. It prints the exact command to render the emitted
``.cxc`` (a windowed GUI session is required — see ``chimerax.py``).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List

from . import chimerax, specs
from .cxc import CxcEmitter
from .fixtures import FixtureBuilder, build_config
from .runner import CommandRunner, RunResult
from .schema import RenderSpec

GALLERY_DIR = Path(__file__).resolve().parent


def _docs_assets_dir() -> Path:
    """Locate ``<repo>/docs/assets/tools`` from this package's on-disk location.

    The gallery lives under ``util/`` — outside both the docs tree and the Python package — so we
    walk up to the repo root (the directory holding ``pyproject.toml`` next to ``docs/``) rather than
    assuming a fixed parent directory.
    """
    for d in (GALLERY_DIR, *GALLERY_DIR.parents):
        if (d / "pyproject.toml").is_file() and (d / "docs").is_dir():
            return d / "docs" / "assets" / "tools"
    raise RuntimeError(f"Could not locate <repo>/docs from {GALLERY_DIR}")


BUILD = GALLERY_DIR / "build"
PROJECT_DIR = BUILD / "project"
CXC_DIR = BUILD / "cxc"
LOG_DIR = BUILD / "logs"
ASSETS_DIR = _docs_assets_dir()  # <repo>/docs/assets/tools


def _select(args) -> List[RenderSpec]:
    if args.only:
        return [specs.get(c) for c in args.only]
    if args.group:
        return specs.by_group(args.group)
    # --all (default): everything except specs that need manual capture.
    return [s for s in specs.all_specs() if "manual" not in s.needs]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Generate before/after ChimeraX renders for copick CLI commands.")
    sel = p.add_mutually_exclusive_group()
    sel.add_argument("--only", nargs="+", metavar="CMD", help="One or more command names (e.g. picks2seg).")
    sel.add_argument("--group", choices=["convert", "process", "logical"], help="All commands in a group.")
    sel.add_argument("--all", action="store_true", help="All commands (default).")
    p.add_argument("--skip-fixtures", action="store_true", help="Do not (re)build input data.")
    p.add_argument("--skip-run", action="store_true", help="Do not run the CLI / verify outputs.")
    p.add_argument("--skip-emit", action="store_true", help="Do not write .cxc files.")
    args = p.parse_args(argv)

    selected = _select(args)
    print(f"[gallery] {len(selected)} command(s) selected.")
    BUILD.mkdir(parents=True, exist_ok=True)

    cfg_path = build_config(str(PROJECT_DIR))
    print(f"[gallery] config: {cfg_path}")

    builder = FixtureBuilder(cfg_path)
    runner = CommandRunner(cfg_path, str(LOG_DIR))
    emitter = CxcEmitter(cfg_path, str(ASSETS_DIR))

    results: List[RunResult] = []
    cxc_sections: List[str] = []

    for spec in selected:
        print(f"\n[gallery] === {spec.group} {spec.command} ===")
        if not args.skip_fixtures:
            builder.build_spec(spec)

        if args.skip_run:
            all_keys = {""} | {m.key for m in spec.modes}
            result = RunResult(spec, ran=False, verified_keys=all_keys, message="run skipped")
        else:
            result = runner.run(spec)
        results.append(result)
        print(f"[gallery]   {'OK ' if result.ok else 'FAIL'}: {result.message}")

        if args.skip_emit:
            continue
        if not result.ok:
            print("[gallery]   (skipping render — command did not verify)")
            continue
        emitter.ensure_dirs(spec)
        section = emitter.emit(spec, result.verified_keys)
        cxc_path = CXC_DIR / f"{spec.slug}.cxc"
        cxc_path.parent.mkdir(parents=True, exist_ok=True)
        cxc_path.write_text(section)
        cxc_sections.append(section)

    # master .cxc bundles every rendered command into one GUI-batch launch.
    if cxc_sections and not args.skip_emit:
        master = CXC_DIR / "master.cxc"
        master.write_text("\n".join(cxc_sections))
        print(f"\n[gallery] wrote {len(cxc_sections)} .cxc section(s) -> {master}")

    _summary(results)
    _write_gallery_manifest(results)

    if cxc_sections and not args.skip_emit:
        target = (CXC_DIR / f"{selected[0].slug}.cxc") if len(cxc_sections) == 1 else (CXC_DIR / "master.cxc")
        print("\n[gallery] To render the images, run a GUI ChimeraX (a window will open):\n")
        print("    " + chimerax.batch_command(str(target)))
        if chimerax.resolve_chimerax() is None:
            print("\n[gallery] (Set $CHIMERAX to your ChimeraX executable if the path above is a placeholder.)")
        print(
            "\n[gallery] Images will be written under docs/assets/tools/<group>/. "
            "Then run `make_cli_docs` and `zensical serve`.",
        )
    return 0


def _summary(results: List[RunResult]) -> None:
    ok = [r for r in results if r.ok]
    bad = [r for r in results if not r.ok]
    print("\n[gallery] ---- summary ----")
    print(f"[gallery]   verified: {len(ok)} / {len(results)}")
    for r in bad:
        print(f"[gallery]   FAIL {r.spec.group} {r.spec.command}: {r.message}")
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    manifest = [
        {
            "group": r.spec.group,
            "command": r.spec.command,
            "ok": r.ok,
            "verified_keys": sorted(r.verified_keys),
            "message": r.message,
            "log": r.log_path,
        }
        for r in results
    ]
    (LOG_DIR / "summary.json").write_text(json.dumps(manifest, indent=2))


def _write_gallery_manifest(results: List[RunResult]) -> None:
    """Write/merge ``docs/assets/tools/gallery.json`` — the authoritative per-command mode list.

    Consumed by ``make_cli_docs`` to render the before/after tabs with human labels (from
    ``Mode.label``) in a stable order (Default first, then spec order). Each entry is gated on the
    after-image actually existing on disk, so the docs never reference a missing render; the file is
    merged with any existing manifest so ``--only`` / ``--group`` runs stay incremental. Because it
    only reads ``verified_keys`` + the files on disk (no ChimeraX), a quick
    ``--all --skip-run --skip-emit`` regenerates it from whatever images are present.

    Schema (keyed ``"<group>/<command>"``)::

        {"convert/mesh2seg": {"modes": [{"key": "", "label": "Default"},
                                        {"key": "boundary", "label": "Boundary"}, ...]}}
    """
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = ASSETS_DIR / "gallery.json"
    try:
        manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    except (json.JSONDecodeError, OSError):
        manifest = {}

    for r in results:
        spec = r.spec
        group_dir = ASSETS_DIR / spec.group

        def _has(suffix: str, _dir=group_dir, _cmd=spec.command) -> bool:
            return (_dir / f"{_cmd}{suffix}.png").exists()

        modes = []
        if "" in r.verified_keys and _has("-after"):
            modes.append({"key": "", "label": "Default"})
        for m in spec.modes:
            if m.key in r.verified_keys and _has(f".{m.key}-after"):
                modes.append({"key": m.key, "label": m.label})
        if modes:
            manifest[f"{spec.group}/{spec.command}"] = {"modes": modes}

    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"[gallery] wrote manifest -> {manifest_path} ({len(manifest)} command(s))")


if __name__ == "__main__":
    raise SystemExit(main())
