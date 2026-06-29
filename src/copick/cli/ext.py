from importlib import metadata
from typing import Dict, List, Tuple

import click

from copick.util.log import get_logger

logger = get_logger(__name__)

# Authoritative set of entry-point-fed command groups. ``"main"`` denotes the top-level
# ``copick.commands`` group; every other name maps to ``copick.<name>.commands`` and to the
# CLI group of the same name created in ``cli.add_plugin_commands``. Keep these in sync.
PLUGIN_GROUPS = [
    "main",
    "inference",
    "training",
    "evaluation",
    "process",
    "convert",
    "logical",
    "setup",
    "download",
]


def load_plugin_commands(entry_point: str = "main") -> List[Tuple[click.Command, str]]:
    """Discover and load commands from installed plugin packages.

    Returns:
        List[Tuple[click.Command, str]]: A list of tuples containing click commands and their source package names.
    """

    commands = []
    if entry_point == "main":
        entry_points = metadata.entry_points(group="copick.commands")

        for entry_point in entry_points:
            command_func = entry_point.load()
            if not isinstance(command_func, click.Command):
                logger.critical(f"Entry point '{entry_point.name}' is not a valid click command.")
                continue
            commands.append((command_func, entry_point.dist.name))
    elif entry_point in PLUGIN_GROUPS:
        entry_points = metadata.entry_points(group=f"copick.{entry_point}.commands")

        for entry_point in entry_points:
            command_func = entry_point.load()
            if not isinstance(command_func, click.Command):
                logger.critical(f"Entry point '{entry_point.name}' is not a valid click command.")
                continue
            commands.append((command_func, entry_point.dist.name))

    return commands


def get_plugin_command_sources() -> Dict[Tuple[str, ...], str]:
    """Map each plugin command's path to the distribution that provides it.

    Re-walks every entry-point group in :data:`PLUGIN_GROUPS` and returns a mapping from the
    command's path within the assembled ``copick`` CLI tree to its providing distribution name,
    e.g. ``{("convert", "picks2seg"): "copick-utils"}``. Top-level (``"main"``) plugin commands
    are keyed by a single-element path, ``{("mycommand",): "my-plugin"}``.

    The path keys line up with the ``path`` lists used by the docs generator because Click
    registers each command under ``command.name`` (the same object returned here).
    """
    sources: Dict[Tuple[str, ...], str] = {}
    for group in PLUGIN_GROUPS:
        prefix: Tuple[str, ...] = () if group == "main" else (group,)
        for command, dist in load_plugin_commands(group):
            sources[prefix + (command.name,)] = dist
    return sources
