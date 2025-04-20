from copick.impl.cryoet_data_portal import CopickRootCDP, CopickRunCDP
from copick.impl.filesystem import CopickRootFSSpec, CopickRunFSSpec
from copick.models import CopickRoot, PickableObject

DEFAULT_MARKDOWN = """\
# Metadata
"""

LOCAL_PROJECT = """\
# Local Copick Project

|
"""


def object_to_md(object: PickableObject) -> str:
    """Convert the PickableObject object to a markdown string."""
    md = "# PickableObject Metadata\n"
    md += f"## Object: {object.name}\n"
    md += f"* ID: {object.id}\n"
    md += f"* Type: {object.type}\n"

    if object.description:
        md += f"* Description: {object.description}\n"

    if object.url:
        md += f"* URL: [{object.url}]({object.url})\n"

    if object.license:
        md += f"* License: {object.license}\n"

    return md


def root_to_md(root: CopickRoot) -> str:
    """Convert the CopickRoot object to a markdown string."""
    md = "# CopickRoot Metadata\n"

    md += f"## Project Name: {root.config.name}\n"

    if root.config.config_type == "filesystem":
        md += "* Project Type: Filesystem\n"
    elif root.config.config_type == "cryoet_data_portal":
        md += "* Project Type: CryoET Data Portal\n"

    if isinstance(root, CopickRootFSSpec):
        if root.static_is_overlay:
            md += f"* Location: {root.config.overlay_root}\n"
        else:
            md += f"* Static Location: {root.config.static_root}\n"
            md += f"* Overlay Location: {root.config.overlay_root}\n"
    elif isinstance(root, CopickRootCDP):
        md += "* Datasets: "
        for dataset in root.config.dataset_ids:
            md += f"[{dataset}](https://cryoetdataportal.czscience.com/datasets/{dataset}) "
        md += "\n"
        md += f"* Overlay Location: {root.config.overlay_root}\n"

    return md


def run_to_md(run: CopickRoot, run_id: str) -> str:
    """Convert the CopickRun object to a markdown string."""
    md = "# CopickRun Metadata\n"
    md += f"## Run ID: {run_id}\n"

    if isinstance(run, CopickRunFSSpec):
        if run.static_is_overlay:
            md += f"* Location: {run.overlay_path}\n"
        else:
            md += f"* Static Location: {run.static_path}\n"
            md += f"* Overlay Location: {run.overlay_path}\n"
    elif isinstance(run, CopickRunCDP):
        md += f"* [cryoET Data portal: {run.portal_run_id}](https://cryoetdataportal.czscience.com/runs/{run.portal_run_id})\n"
        md += f"* Overlay Location: {run.overlay_path}\n"

    return md


ENTITY_TO_MD = {
    "root": root_to_md,
    "run": run_to_md,
    "object": object_to_md,
}
