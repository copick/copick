import click

from copick import __version__ as version
from copick.cli.add import add
from copick.cli.browse import browse
from copick.cli.config import config
from copick.cli.cp import cp
from copick.cli.deposit import deposit
from copick.cli.export import export
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
    "Data Management": ["add", "cp", "export", "mv", "new", "rm", "sync"],
    "Data Processing": ["convert", "inference", "logical", "process", "training", "evaluation"],
    "Utilities": ["browse", "config", "deposit", "info", "setup", "stats", "download"],
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
    logger.info(f"{'-' * len(text)}")


@click.group(
    short_help="Run inference on copick tomograms.",
    no_args_is_help=True,
)
@click.pass_context
def inference(ctx):
    """
    Run inference on copick tomograms.

    Commands in this group apply trained models to copick tomograms to produce
    predictions such as segmentations or particle picks. Subcommands are
    contributed by installed plugins.
    """
    pass


@click.group(
    short_help="Train a model with copick data.",
    no_args_is_help=True,
)
@click.pass_context
def training(ctx):
    """
    Train a model with copick data.

    Commands in this group train machine-learning models on annotated copick
    data. Subcommands are contributed by installed plugins.
    """
    pass


@click.group(
    short_help="Evaluate model predictions against ground truth.",
    no_args_is_help=True,
)
@click.pass_context
def evaluation(ctx):
    """
    Evaluate model predictions against ground truth.

    Commands in this group compare model predictions against ground-truth
    annotations and report performance metrics. Subcommands are contributed by
    installed plugins.
    """
    pass


@click.group(
    short_help="Apply processing methods to copick data.",
    no_args_is_help=True,
)
@click.pass_context
def process(ctx):
    """
    Apply processing methods to copick data.

    Commands in this group apply image-processing operations, such as filtering,
    denoising, or intensity transforms, to copick tomograms and related entities.
    Subcommands are contributed by installed plugins.
    """
    pass


@click.group(
    short_help="Convert one copick type to another.",
    no_args_is_help=True,
)
@click.pass_context
def convert(ctx):
    """
    Convert one copick type to another.

    Commands in this group convert between copick entity types, for example
    turning picks into meshes or segmentations into picks. Subcommands are
    contributed by installed plugins.
    """
    pass


@click.group(
    short_help="Perform logical operations on copick objects.",
    no_args_is_help=True,
)
@click.pass_context
def logical(ctx):
    """
    Perform logical operations on copick objects.

    Commands in this group perform boolean operations, distance-based filtering,
    and point inclusion/exclusion across meshes, segmentations, and picks.
    Subcommands are contributed by installed plugins.
    """
    pass


@click.group(
    short_help="Set up and manage external integrations.",
    no_args_is_help=True,
)
@click.pass_context
def setup(ctx):
    """
    Set up and manage external integrations.

    Commands in this group set up and manage external integrations such as MCP
    servers, database connections, and other third-party tools. Subcommands are
    contributed by installed plugins.
    """
    pass


@click.group(
    short_help="Download data and metadata for STA.",
    no_args_is_help=True,
)
@click.pass_context
def download(ctx):
    """
    Download data and metadata for STA.

    Commands in this group download tomograms, particle coordinates, and
    associated metadata needed for downstream tasks such as subtomogram
    averaging (STA). Subcommands are contributed by installed plugins.
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
    cmd.add_command(export)
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

    if download_commands := load_plugin_commands("download"):
        cmd.add_command(download)
        for command in download_commands:
            download.add_command(command[0])

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
