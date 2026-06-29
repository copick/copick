# CLI gallery: before/after ChimeraX renders

Dev-only tooling that generates an **input** and **output** image for every copick
transform command (`convert` / `process` / `logical`). The images land in
`docs/assets/tools/<group>/<command>{-before,-after}.png` (+ a square `<command>.png`
thumbnail). `make_cli_docs` then auto-embeds them at the top of each command page, in
the processing gallery, and on the home-page carousels.

## How it works

```
fabricate synthetic inputs (copick API)  ->  run the CLI command  ->  verify output
   ->  emit a ChimeraX .cxc  ->  YOU run a GUI ChimeraX on it  ->  PNGs in docs/assets/tools/
```

* A small synthetic copick project is built under `build/project/` (one run per command,
  with geometry tailored so each command both succeeds and reads clearly). Deterministic
  and idempotent — rebuilding is byte-stable.
* Each command runs via the real `copick` CLI; the output is verified (picks have points,
  segmentations have voxels, meshes have faces) before its "after" image is rendered.
* A `.cxc` command file is emitted per command. Framing uses a **named view** anchored to
  the reference tomogram (the full constant box): it is saved once (`view name gallery`) and
  restored (`view gallery`) before every save, so before/after — and each mode — share an
  identical, scene-independent camera even when the output is smaller. Backgrounds are
  transparent → one render serves both docs themes.
* **Modes**: commands with variants (`meshop`/`segop` operations, `mesh2seg --mode/--invert`,
  `mesh2picks --sampling-type`, `picks2mesh --mesh-type`, `skeletonize --method`, clip
  `--invert`) render one shared "before" plus one "after" per mode
  (`{command}.{key}-after.png`); the docs page shows a "Modes" row.
* **Picks** render as ArtiaX axes (oriented points) sized per-command from the marker
  radius (`AXES_RADIUS_RATIO * radius` in `cxc.py`, so arrows protrude past the sphere),
  with random orientations (`geometry._random_orientations`). Fitting inputs use
  `orient="none"` -> plain markers (no axes), via `fixtures` setting `trust_orientation`.
* **Cross-sections**: commands where surfaces look hollow/identical (mesh2seg, seg2mesh,
  meshop/segop exclusion) use a line-of-sight clip + surface cap (`schema.Clip`,
  `cxc._clip_lines`: `clip near 0` + `surface cap true|false`, box hidden) to read solid /
  reveal interior holes. Re-asserted after each `view gallery`.
* **Ghosted inputs**: some commands keep the input translucent in the "after"
  (`EntitySpec.ghost_in_after`): picks via `transparency <#1.2.x> N target a` (markers dim,
  axes stay opaque), segs via `volume <#1.1.x> transparency`, meshes via a `*-faint`
  config-alpha object. `separate-components` colors each component (`colorize_colors`).

## Prerequisites

* `copick` plus the plugin packages that provide the commands:
  ```
  cd copick && uv sync --extra docs
  UV_TORCH_BACKEND=cpu uv pip install copick-utils copick-torch
  ```
* **ChimeraX** with the **chimerax-copick** (>= 1.9.0) and **ArtiaX** bundles installed.
  Set `$CHIMERAX` if it is not at `/Applications/ChimeraX.app/Contents/MacOS/ChimeraX`.
  Rendering needs a **GUI** session (a window opens) — `--offscreen`/`--nogui` do not
  work because `copick start` requires `session.ui.is_gui`.

## Usage

```bash
# 1. Build inputs, run the command(s), verify, and emit .cxc files
make -C util/gallery gallery CMD=picks2seg     # one command (fast iteration)
make -C util/gallery gallery GROUP=convert     # a whole group
make -C util/gallery gallery                   # everything

# 2. Render (opens a ChimeraX window, writes PNGs, exits). The driver prints this for you:
"$CHIMERAX" --exit util/gallery/build/cxc/master.cxc
#   or, for a single command:
"$CHIMERAX" --exit util/gallery/build/cxc/convert-picks2seg.cxc

# 3. Wire into the docs and preview
cd copick && make_cli_docs && zensical serve    # check light + dark
make_cli_docs --check                           # must be clean; commit images + regenerated docs together
```

Direct (without make): `cd copick/util && python -m gallery.driver --only picks2seg`.

Useful flags: `--skip-fixtures` (reuse built data), `--skip-run` (only fixtures+emit),
`--skip-emit` (only build+run). A pass/fail summary is written to
`build/logs/summary.json`; per-command CLI output is in `build/logs/<group>-<command>.log`.

## Tuning a render

Camera presets (`iso` / `front` / `top` / `side`) and zoom live in `palette.py` /
`schema.ViewSpec`; input geometry lives in `geometry.py`; per-command wiring (CLI flags,
what to show before/after) lives in `specs.py`. Re-run `gallery` for that command and
re-render its single `.cxc` to iterate quickly.

## Notes / limitations

* **downsample** is omitted for now: copick-torch's downsample is GPU-only and crashes on
  CPU-only hosts. An illustrative two-pyramid-level render path remains in `cxc.py`
  (`tomo-pyramid`) if it is reinstated later.
* Inference commands (`membrain-seg`, `nnunet`) and info-only `seg-stats` are out of
  scope (trained models / no annotation output).
* `separate-components` produces same-colored instances at the same positions; its
  before/after differ mainly in object count (a metadata change), so the pair is modest.
