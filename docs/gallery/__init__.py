"""copick CLI gallery: generate before/after ChimeraX renders for transform commands.

Dev-only tooling (not part of the shipped ``copick`` package). It fabricates a small,
deterministic copick project, runs each CLI command on it, and emits ChimeraX command
files (``.cxc``) that render an *input* (before) and *output* (after) image per command.

Run it from the ``copick/`` repo root via ``make -C docs/gallery ...`` or
``python -m docs.gallery.driver`` (see ``docs/gallery/README.md``).
"""
