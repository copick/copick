import click

from copick.cli.ext import load_plugin_commands
from copick.util.log import get_logger


@click.command(context_settings={"show_default": True}, short_help="Display information about the Copick CLI.")
@click.pass_context
def info(ctx):
    """Display information about the Copick CLI."""
    logger = get_logger(__name__)

    command_groups = {
        "main": "Main commands (copick COMMAND)",
        "inference": "Inference commands (copick inference COMMAND)",
        "training": "Training commands (copick training COMMAND)",
        "evaluation": "Evaluation commands (copick evaluation COMMAND)",
        "process": "Processing commands (copick process COMMAND)",
        "convert": "Conversion commands (copick convert COMMAND)",
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
