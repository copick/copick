import click

from copick.cli.util import add_config_option, add_debug_option
from copick.util.log import get_logger


@click.command(
    context_settings={"show_default": True},
    short_help="Browse Copick projects.",
)
@add_config_option
@click.option(
    "-ds",
    "--dataset-ids",
    type=int,
    multiple=True,
    help="Dataset IDs to include (multiple inputs possible).",
    metavar="ID",
)
@add_debug_option
@click.pass_context
def browse(
    ctx,
    config: str = None,
    dataset_ids: list[int] = None,
    debug: bool = False,
):
    """
    Browse Copick projects.
    """
    # Deferred import for performance
    import copick
    from copick.ops.browser import launch_app

    logger = get_logger(__name__, debug=debug)

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
