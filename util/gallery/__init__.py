"""copick CLI gallery: generate before/after ChimeraX renders for transform commands.

Dev-only tooling (not part of the shipped ``copick`` package). It fabricates a small,
deterministic copick project, runs each CLI command on it, and emits ChimeraX command
files (``.cxc``) that render an *input* (before) and *output* (after) image per command.

Run it via ``make -C util/gallery ...`` or, from the ``copick/util`` directory,
``python -m gallery.driver`` (see ``util/gallery/README.md``).
"""
