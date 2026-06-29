from importlib import metadata
from typing import Set

import click

from copick.cli.ext import PLUGIN_GROUPS, load_plugin_commands
from copick.util.log import get_logger


def get_installed_plugin_packages() -> Set[str]:
    """Get a set of installed plugin packages with their versions.

    Returns:
        Set of strings in format "package-name version"
    """
    plugin_packages = set()

    for group in PLUGIN_GROUPS:
        commands = load_plugin_commands(group)
        for _command, package_name in commands:
            try:
                version = metadata.version(package_name)
                plugin_packages.add(f"{package_name} {version}")
            except metadata.PackageNotFoundError:
                plugin_packages.add(f"{package_name} (version unknown)")

    return plugin_packages


@click.command(
    context_settings={"show_default": True},
    short_help="Display information about the Copick CLI.",
)
@click.pass_context
def info(ctx):
    """
    Display information about the Copick CLI.

    Lists the plugin commands currently registered with the Copick CLI, grouped by
    command group (main, inference, training, evaluation, process, convert, and
    logical). For each command the registered short help text and the providing
    package are shown, which is useful for discovering which plugins are installed
    and where each command comes from.

    Examples:

        \b
        # Show CLI information and available plugins
        copick info
    """
    logger = get_logger(__name__)

    command_groups = {
        "main": "Main commands (copick COMMAND)",
        "inference": "Inference commands (copick inference COMMAND)",
        "training": "Training commands (copick training COMMAND)",
        "evaluation": "Evaluation commands (copick evaluation COMMAND)",
        "process": "Processing commands (copick process COMMAND)",
        "convert": "Conversion commands (copick convert COMMAND)",
        "logical": "Logical/Set operations (copick logical COMMAND)",
    }

    logged_any_command = False

    for group, description in command_groups.items():
        commands = load_plugin_commands(group)
        if commands:
            logged_any_command = True
            logger.info(f"\n{description}:")
            logger.info("=" * len(description))
            for command, package_name in commands:
                description_text = command.short_help or "No description available"
                logger.info(f"  {command.name:<20} {description_text} [{package_name}]")

    if not logged_any_command:
        logger.info("\nNo plugin commands available.")
