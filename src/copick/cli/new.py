import os

import click
import tqdm

from copick.cli.util import add_config_option, add_create_overwrite_options, add_debug_option
from copick.util.log import get_logger


@click.group(short_help="Create copick entities.")
@click.pass_context
def new(ctx):
    """Create copick entities."""
    pass


@new.command(
    context_settings={"show_default": True},
    short_help="Create empty picks for a given particle name.",
    no_args_is_help=True,
)
@add_config_option
@click.option("--particle-name", type=str, required=True, help="Name of the particle to create picks for")
@click.option("--out-user", type=str, required=False, default="copick", help="User ID to write picks to")
@click.option("--out-session", type=str, required=False, default="0", help="Session ID to write picks to")
@click.option("--overwrite/--no-overwrite", is_flag=True, default=False, help="Overwrite existing picks")
@add_debug_option
@click.pass_context
def picks(
    ctx,
    config: str,
    particle_name: str,
    out_user: str = "copick",
    out_session: str = "0",
    overwrite: bool = False,
    debug: bool = False,
):
    """
    Create empty picks for a given particle name.
    """
    # Deferred import for performance
    import copick

    logger = get_logger(__name__, debug=debug)

    # Load Copick Project
    if os.path.exists(config):
        root = copick.from_file(config)
    else:
        logger.critical(f"Configuration file {config} does not exist.")
        ctx.fail(f"Configuration file {config} does not exist.")
        return

    # Create picks
    for run in tqdm.tqdm(root.runs, desc="Creating picks", unit="runs", total=len(root.runs)):
        picks = run.get_picks(
            object_name=particle_name,
            user_id=out_user,
            session_id=out_session,
        )

        if len(picks) == 0:
            picks = run.new_picks(
                object_name=particle_name,
                user_id=out_user,
                session_id=out_session,
            )
        else:
            if overwrite:
                picks = picks[0]
            else:
                logger.warning(
                    f"Picks for {particle_name} already exist. Use --overwrite to overwrite them. Skipping creation.",
                )
                continue

        picks.points = []
        picks.store()


@new.command(
    short_help="Create an empty run with the given name.",
    context_settings={"show_default": True},
    no_args_is_help=True,
)
@add_config_option
@add_create_overwrite_options
@add_debug_option
@click.argument("name", required=True, type=str, metavar="NAME")
@click.pass_context
def run(
    ctx: click.Context,
    config: str,
    create: bool,
    overwrite: bool,
    debug: bool,
    name: str,
) -> int:
    """
    Create an empty run with the given name.

    NAME: The name of the new run to be created.
    """
    # Deferred import for performance
    import copick
    from copick.ops.add import add_run

    get_logger(__name__, debug=debug)

    root = copick.from_file(config)
    add_run(root, name, exist_ok=overwrite, log=debug)

    return 0


@new.command(
    short_help="Create an empty voxelspacing with the given name.",
    context_settings={"show_default": True},
    no_args_is_help=True,
)
@add_config_option
@click.option("--run", required=True, type=str, help="Name of the run to add voxel spacing to.", metavar="RUN")
@add_create_overwrite_options
@add_debug_option
@click.argument("voxel_spacing", required=True, type=float, metavar="VOXEL_SPACING")
def voxelspacing(
    config: str,
    run: str,
    voxel_spacing: float,
    create: bool,
    overwrite: bool,
    debug: bool,
):
    """
    Create an empty voxelspacing with the given name.

    VOXEL_SPACING: The voxel spacing in Angstrom to be added to the run.
    """
    # Deferred import for performance
    import copick
    from copick.ops.add import add_voxelspacing

    get_logger(__name__, debug=debug)

    root = copick.from_file(config)
    add_voxelspacing(root, run, voxel_spacing, create=create, exist_ok=overwrite, log=debug)

    return 0
