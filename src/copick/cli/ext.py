from importlib import metadata
from typing import List, Tuple

import click

from copick.util.log import get_logger

logger = get_logger(__name__)


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
    elif entry_point in ["inference", "training", "evaluation", "process", "convert"]:
        entry_points = metadata.entry_points(group=f"copick.{entry_point}.commands")

        for entry_point in entry_points:
            command_func = entry_point.load()
            if not isinstance(command_func, click.Command):
                logger.critical(f"Entry point '{entry_point.name}' is not a valid click command.")
                continue
            commands.append((command_func, entry_point.dist.name))

    return commands
