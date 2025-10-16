import click

from copick import __version__ as version
from copick.cli.add import add
from copick.cli.browse import browse
from copick.cli.config import config
from copick.cli.cp import cp
from copick.cli.deposit import deposit
from copick.cli.ext import load_plugin_commands
from copick.cli.grouped_cli import GroupedCommandGroup
from copick.cli.info import get_installed_plugin_packages, info
from copick.cli.mv import mv
from copick.cli.new import new
from copick.cli.rm import rm
from copick.cli.stats import stats
from copick.cli.sync import sync
from copick.util.log import get_logger

logger = get_logger(__name__)

# Define command categories for organized help output
COMMAND_CATEGORIES = {
    "Data Management": ["add", "cp", "mv", "new", "rm", "sync"],
    "Data Processing": ["convert", "inference", "logical", "process", "training", "evaluation"],
    "Utilities": ["browse", "config", "deposit", "info", "setup", "stats"],
}


@click.group(cls=GroupedCommandGroup, command_categories=COMMAND_CATEGORIES)
@click.version_option(version=version, message="copick %(version)s")
@click.pass_context
def _cli(ctx):
    plugin_packages = get_installed_plugin_packages()
    plugins = ""
    if plugin_packages:
        for package in sorted(plugin_packages):
            plugins += f" {package} |"
        plugins = plugins[:-2]
        plugins = f"{plugins}"

    text = f"copick {version} |{plugins}" if plugins else f"copick {version}"
    logger.info(text)
    logger.info(f"{'-'*len(text)}")


@click.group(
    short_help="Run inference on copick tomograms.",
    no_args_is_help=True,
)
@click.pass_context
def inference(ctx):
    """
    Inference commands for Copick.

    This group contains commands related to inference tasks.
    """
    pass


@click.group(
    short_help="Train a model with copick data.",
    no_args_is_help=True,
)
@click.pass_context
def training(ctx):
    """
    Training commands for Copick.

    This group contains commands related to training tasks.
    """
    pass


@click.group(
    short_help="Evaluate model performance.",
    no_args_is_help=True,
)
@click.pass_context
def evaluation(ctx):
    """
    Evaluation commands for Copick.

    This group contains commands related to evaluation tasks.
    """
    pass


@click.group(
    short_help="Apply processing method to copick entity.",
    no_args_is_help=True,
)
@click.pass_context
def process(ctx):
    """
    Image processing commands for Copick.

    This group contains commands related to data management tasks.
    """
    pass


@click.group(
    short_help="Convert one copick type to another.",
    no_args_is_help=True,
)
@click.pass_context
def convert(ctx):
    """
    Data commands for Copick.

    This group contains commands related to data management tasks.
    """
    pass


@click.group(
    short_help="Perform logical operations on copick objects.",
    no_args_is_help=True,
)
@click.pass_context
def logical(ctx):
    """
    Logical operation commands for Copick.

    This group contains commands for boolean operations, distance-based filtering,
    and point inclusion/exclusion operations on meshes, segmentations, and picks.
    """
    pass


@click.group(
    short_help="Setup and manage external integrations.",
    no_args_is_help=True,
)
@click.pass_context
def setup(ctx):
    """
    Setup commands for Copick.

    This group contains commands for setting up and managing external integrations
    like MCP servers, database connections, and other third-party tools.
    """
    pass


def add_core_commands(cmd: click.group) -> click.group:
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
    cmd.add_command(cp)
    cmd.add_command(deposit)
    cmd.add_command(info)
    cmd.add_command(mv)
    cmd.add_command(new)
    cmd.add_command(rm)
    cmd.add_command(stats)
    cmd.add_command(sync)

    return cmd


def add_plugin_commands(cmd: click.group) -> click.group:
    """
    Add plugin commands to the CLI.

    Args:
        cmd (click.Command): The command object to which plugin commands will be added.

    Returns:
        cmd (click.Command): The command object with plugin commands added.
    """

    for command in load_plugin_commands("main"):
        cmd.add_command(command[0])

    if inference_commands := load_plugin_commands("inference"):
        cmd.add_command(inference)
        for command in inference_commands:
            inference.add_command(command[0])

    if training_commands := load_plugin_commands("training"):
        cmd.add_command(training)
        for command in training_commands:
            training.add_command(command[0])

    if evaluation_commands := load_plugin_commands("evaluation"):
        cmd.add_command(evaluation)
        for command in evaluation_commands:
            evaluation.add_command(command[0])

    if process_commands := load_plugin_commands("process"):
        cmd.add_command(process)
        for command in process_commands:
            process.add_command(command[0])

    if convert_commands := load_plugin_commands("convert"):
        cmd.add_command(convert)
        for command in convert_commands:
            convert.add_command(command[0])

    if logical_commands := load_plugin_commands("logical"):
        cmd.add_command(logical)
        for command in logical_commands:
            logical.add_command(command[0])

    if setup_commands := load_plugin_commands("setup"):
        cmd.add_command(setup)
        for command in setup_commands:
            setup.add_command(command[0])

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
