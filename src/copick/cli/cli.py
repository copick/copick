import click

import copick
from copick.ops.browser import launch_app
from copick.util.log import get_logger

logger = get_logger(__name__)


@click.group()
@click.pass_context
def cli(ctx):
    pass


@cli.command()
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


if __name__ == "__main__":
    cli()
