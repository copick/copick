from typing import List

import click

import copick
from copick.cli.util import add_debug_option
from copick.util.log import get_logger


@click.group(short_help="Manage copick configuration files.")
@click.pass_context
def config(ctx):
    pass


@config.command(
    context_settings={"show_default": True},
    short_help="Set up a configuration file from CZDP dataset IDs.",
)
@click.option(
    "-ds",
    "--dataset-id",
    type=int,
    required=True,
    multiple=True,
    help="Dataset IDs from the CryoET Data Portal to include in the configuration",
)
@click.option(
    "--overlay",
    type=str,
    required=True,
    help="Path to the local overlay directory where intermediate files will be stored or read.",
)
@click.option(
    "--output",
    default="config.json",
    type=str,
    required=True,
    help="Path to save the generated configuration file.",
)
@add_debug_option
@click.pass_context
def dataportal(
    ctx,
    dataset_id: List[int],
    overlay: str,
    output: str,
    debug: bool = False,
):
    """
    Generate a configuration file from a CZDP dataset ID and local overlay directory
    """
    logger = get_logger(__name__, debug=debug)
    logger.info("Generating configuration file from CZDP dataset IDs...")

    # Generate Config for the Given Directory
    try:
        copick.from_czcdp_datasets(
            dataset_id,
            overlay_root=overlay,
            output_path=output,
            overlay_fs_args={"auto_mkdir": True},
        )
    except Exception as e:
        logger.critical(f"Failed to generate configuration file: {e}")
        ctx.fail(f"Error generating configuration file: {e}")
        return

    logger.info(f"Generated configuration file at {output}.")


@config.command(context_settings={"show_default": True}, short_help="Set up a configuration file for a local project.")
@add_debug_option
@click.pass_context
def filesystem(ctx, debug: bool = False):
    """
    Generate a configuration file for a local project directory.
    """
    logger = get_logger(__name__, debug=debug)
    logger.info("Generating configuration file for a local project directory...")

    # TODO: implement

    # TODO: log
    # logger.info(f"Generated configuration file at {}.")
