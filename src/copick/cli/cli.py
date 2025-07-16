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


@click.group(short_help="Inference commands.")
@click.pass_context
def inference(ctx):
    """
    Inference commands for Copick.

    This group contains commands related to inference tasks.
    """
    pass


@click.group(short_help="Training commands.")
@click.pass_context
def training(ctx):
    """
    Training commands for Copick.

    This group contains commands related to training tasks.
    """
    pass


@click.group(short_help="Evaluation commands.")
@click.pass_context
def evaluation(ctx):
    """
    Evaluation commands for Copick.

    This group contains commands related to evaluation tasks.
    """
    pass


@click.group(short_help="Image processing commands.")
@click.pass_context
def process(ctx):
    """
    Image processing commands for Copick.

    This group contains commands related to data management tasks.
    """
    pass


@click.group(short_help="Conversion commands.")
@click.pass_context
def convert(ctx):
    """
    Data commands for Copick.

    This group contains commands related to data management tasks.
    """
    pass


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

    for command in load_plugin_commands("main"):
        cmd.add_command(command)

    if inference_commands := load_plugin_commands("inference"):
        for command in inference_commands:
            inference.add_command(command)

    if training_commands := load_plugin_commands("training"):
        for command in training_commands:
            training.add_command(command)

    if evaluation_commands := load_plugin_commands("evaluation"):
        for command in evaluation_commands:
            evaluation.add_command(command)

    if process_commands := load_plugin_commands("process"):
        for command in process_commands:
            process.add_command(command)

    if convert_commands := load_plugin_commands("convert"):
        for command in convert_commands:
            convert.add_command(command)

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
