from importlib import metadata
from typing import List

import click

from copick.util.log import get_logger

logger = get_logger(__name__)


def load_plugin_commands() -> List[click.Command]:
    """Discover and load commands from installed plugin packages.

    Returns:
        List[click.Command]: A list of click commands loaded from entry points.
    """
    entry_points = metadata.entry_points(group="copick.commands")
    commands = []

    for entry_point in entry_points:
        command_func = entry_point.load()
        if not isinstance(command_func, click.Command):
            logger.critical(f"Entry point '{entry_point.name}' is not a valid click command.")
            continue
        commands.append(command_func)

    return commands
