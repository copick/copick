"""Resolve the ChimeraX executable and print the GUI-batch invocation.

This module never launches ChimeraX (per project convention the maintainer runs it).
chimerax-copick's ``copick start`` requires a GUI session — ``get_singleton`` returns
None when ``session.ui.is_gui`` is False — so ``--offscreen`` / ``--nogui`` do not work.
Run the windowed app with a command file instead; ``--exit`` closes it when done.
"""

from __future__ import annotations

import os
import shutil
from typing import Optional

_MAC_DEFAULT = "/Applications/ChimeraX.app/Contents/MacOS/ChimeraX"


def resolve_chimerax() -> Optional[str]:
    """Best-effort path to the ChimeraX executable (env CHIMERAX wins)."""
    env = os.environ.get("CHIMERAX")
    if env:
        return env
    for name in ("ChimeraX", "chimerax"):
        found = shutil.which(name)
        if found:
            return found
    if os.path.exists(_MAC_DEFAULT):
        return _MAC_DEFAULT
    return None


def batch_command(cxc_path: str) -> str:
    """The shell command the maintainer runs to render a (master or single) .cxc."""
    exe = resolve_chimerax() or '"$CHIMERAX"'
    return f'"{exe}" --exit "{os.path.abspath(cxc_path)}"'
