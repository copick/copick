import os
import click
import copick
from tqdm import tqdm
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


@cli.command(context_settings={"show_default": True})
@click.option('--config', type=str, required=True, help='Path to the config file to write tomograms to')
@click.option('--particle-name', type=str, required=True, help='Name of the particle to create picks for')
@click.option('--out-user', type=str, required=False, default='copick', help='User ID to write picks to')
@click.option('--out-session', type=str, required=False, default='0', help='Session ID to write picks to')
@click.option('--overwrite', type=bool, required=False, default=False, help='Overwrite existing picks')
def empty_picks(
    config,
    particle_name,
    out_user,
    out_session,
    overwrite = False
):
    """
    Create empty picks for a given particle name.

    Taken from https://github.com/copick/copick-catalog/blob/main/solutions/copick/create_empty_picks/solution.py
    """

    # Load Copick Project
    if os.path.exists(config):
        root = copick.from_file(config)
    else:
        raise ValueError('Config file not found')

    # Create picks
    for run in tqdm(root.runs):

        picks = run.get_picks(
            object_name=particle_name, user_id=out_user, session_id=out_session
        )

        if len(picks) == 0:
            picks = run.new_picks(
                object_name=particle_name, user_id=out_user, session_id=out_session
            )
        else:
            if overwrite:
                picks = picks[0]
            else:
                raise ValueError(
                    f"Picks already exist for {run.name}. Set overwrite to True to overwrite."
                )

        picks.points = []
        picks.store()


if __name__ == "__main__":
    cli()
