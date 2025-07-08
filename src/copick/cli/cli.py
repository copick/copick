import click

import copick
from copick.cli.add import add
from copick.cli.browse import browse
from copick.cli.config import config
from copick.cli.ext import load_plugin_commands
from copick.cli.info import info
from copick.cli.new import new
from copick.util.log import get_logger

logger = get_logger(__name__)


@click.group()
@click.version_option(version=copick.__version__, message="copick %(version)s")
@click.pass_context
def _cli(ctx):
    text = f"copick {copick.__version__}"
    logger.info(text)
    logger.info(f"{'-'*len(text)}")


def add_core_commands(cmd: click.Command) -> click.Command:
    """
    Add core commands to the CLI.

    Args
        cmd (click.Command): The command object to which core commands will be added.

    Returns:
        cmd (click.Command): The command object with core commands added.
    """

    cmd.add_command(add)
    cmd.add_command(browse)
    cmd.add_command(config)
    cmd.add_command(info)
    cmd.add_command(new)

    return cmd


def add_plugin_commands(cmd: click.Command) -> click.Command:
    """
    Add plugin commands to the CLI.

    Args:
        cmd (click.Command): The command object to which plugin commands will be added.

    Returns:
        cmd (click.Command): The command object with plugin commands added.
    """

    for command in load_plugin_commands():
        cmd.add_command(command)

    return cmd


def main():
    """
    Main entry point for the Copick CLI.
    """
    cli = add_core_commands(_cli)
    cli = add_plugin_commands(cli)

    cli(prog_name="copick")


# Create a CLI instance that can be used by tests
cli = add_core_commands(_cli)
cli = add_plugin_commands(cli)


if __name__ == "__main__":
    main()
