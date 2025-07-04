import click

from copick.cli.ext import load_plugin_commands
from copick.util.log import get_logger


@click.command(context_settings={"show_default": True}, short_help="Display information about the Copick CLI.")
@click.pass_context
def info(ctx):
    """Display information about the Copick CLI."""
    logger = get_logger(__name__)
    commands = load_plugin_commands()
    if commands:
        logger.info("Available commands:")
        for command in commands:
            logger.info(f"  - {command.name}: {command.short_help or 'No description available'}")
    else:
        logger.info("No plugin commands available.")
