import click

import copick
from copick.ops.browser import launch_app
from copick.util.log import get_logger

logger = get_logger(__name__)


@click.group()
@click.pass_context
def cli(ctx):
    pass


@cli.command(context_settings={"show_default": True})
@click.option(
    "-c",
    "--config",
    type=str,
    help="Path to the configuration file.",
    required=False,
    metavar="PATH",
    envvar="COPICK_CONFIG",
    show_envvar=True,
)
@click.option(
    "-ds",
    "--dataset-ids",
    type=int,
    multiple=True,
    help="Dataset IDs to include in the project (multiple inputs possible).",
    metavar="ID",
)
@click.pass_context
def browse(
    ctx,
    config: str = None,
    dataset_ids: list[int] = None,
):
    if config and dataset_ids:
        logger.critical("You cannot specify both a config and dataset IDs.")
        ctx.fail("Either --config or --dataset-ids must be provided, not both.")

    if config:
        project = copick.from_file(config)
        launch_app(copick_root=project)
    elif dataset_ids:
        project = copick.from_czcdp_datasets(
            dataset_ids=dataset_ids,
            overlay_root="/tmp/overlay_root",
            overlay_fs_args={},
        )
        launch_app(copick_root=project)
    else:
        logger.critical("You must specify either a config or a dataset.")
        ctx.fail("Either --config or --dataset-ids must be provided.")

@cli.command(context_settings={"show_default": True})
@click.option(
    '-ds',
    '--dataset-id',
    type=int, 
    required=True, 
    help="Dataset ID from the CryoET Data Portal to include in the configuration")
@click.option(
    '--overlay',
    type=str, 
    required=True, 
    help='Path to the local overlay directory where intermediate files will be stored or read.')
@click.option(
    '--output', 
    default='config.json',
    type=str, 
    required=False, 
    help='Path to save the generated configuration file.')
@click.pass_context
def generate_dataportal_config(
    ctx,
    dataset_id: str,
    overlay: str, 
    output: str):
    """
    Generate a configuration file from a CZDP dataset ID and local overlay directory
    """

    # Generate Config for the Given Directory
    copick.from_czcdp_datasets(
        [dataset_id], 
        overlay_root = overlay, 
        output_path = output,
        overlay_fs_args = {"auto_mkdir": True})

if __name__ == "__main__":
    cli()
