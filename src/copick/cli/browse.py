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

    Launches an interactive terminal user interface (TUI) for exploring a copick
    project: runs, voxel spacings, tomograms, segmentations, picks, and meshes.

    Provide either a local configuration file with `--config` or one or more
    CryoET Data Portal dataset IDs with `--dataset-ids`; the two are mutually
    exclusive. If neither is given, the `COPICK_CONFIG` environment variable is
    used when set.

    Examples:

        \b
        # Browse a local project from a config file
        copick browse --config config.json

        \b
        # Browse CryoET Data Portal datasets by ID
        copick browse --dataset-ids 10000 --dataset-ids 10001

        \b
        # Browse using the COPICK_CONFIG environment variable
        copick browse

    See Also:

        \b
        copick config filesystem: create a config file for a local project
        copick config dataportal: create a config file from CryoET Data Portal datasets
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
