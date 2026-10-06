"""ChimeraX helper (``runscript``): wait until a just-opened instance / panoptic segmentation is shown.

chimerax-copick computes the label surfaces of instance and panoptic segmentations in a worker thread and adds the
model when the worker's result signal arrives. Signals need the Qt event loop, which a running command script does
not spin (``wait N`` only draws frames), so this pumps events until a new label-surface model appears.

Usage, right after ``copick open segmentation "<uri>?instance=true"``::

    runscript /path/to/cx_wait_label_surfaces.py [timeout_seconds]
"""

import sys
import time

TYPE_NAME = "LabelSurfaceModel"


def _count(session) -> int:
    return sum(type(m).__name__ == TYPE_NAME for m in session.models.list())


def wait_for_label_surfaces(session, timeout: float = 30.0) -> None:
    from Qt.QtWidgets import QApplication

    before = _count(session)
    deadline = time.time() + timeout
    while _count(session) <= before:
        if time.time() > deadline:
            session.logger.warning(f"[gallery] no label surfaces after {timeout:g} s")
            return
        QApplication.processEvents()
        time.sleep(0.02)
    QApplication.processEvents()  # let the model finish showing


wait_for_label_surfaces(session, float(sys.argv[1]) if len(sys.argv) > 1 else 30.0)  # noqa: F821
