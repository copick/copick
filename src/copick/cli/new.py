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

    Creates an empty pick set for the named particle in every run of the project,
    seeding an annotation session that can be populated later. Picks are written to
    the given output user and session (defaulting to `copick` and `0`). Runs that
    already have matching picks are skipped unless `--overwrite` is passed.

    Examples:

        \b
        # Create empty picks for ribosomes
        copick new picks --config config.json --particle-name ribosome

        \b
        # Create picks with a custom output user and session
        copick new picks --config config.json --particle-name proteasome \\
            --out-user alice --out-session 1

        \b
        # Overwrite existing picks for the particle
        copick new picks --config config.json --particle-name ribosome --overwrite

    See Also:

        \b
        copick new run: create an empty run to hold picks
        copick add picks: import picks from external formats (EM, STAR, Dynamo, CSV)
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

    Adds a new, empty run to the project so that tomograms, picks, segmentations,
    and other entities can later be attached to it. By default (`--create`) the run
    is created if it does not already exist; pass `--overwrite` to replace an
    existing run of the same name.

    Arguments:

        \b
        NAME: The name of the new run to be created.

    Examples:

        \b
        # Create a new run
        copick new run --config config.json TS_005

        \b
        # Create a run, overwriting any existing run of the same name
        copick new run --config config.json --overwrite TS_005

    See Also:

        \b
        copick new voxelspacing: add a voxel spacing to a run
        copick add tomogram: import a tomogram into a run
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

    Adds an empty voxel spacing (in Angstrom) to an existing run, providing a
    container for tomograms and segmentations at that resolution. Use `--run` to
    select the target run; `--create` makes the run if it does not yet exist, and
    `--overwrite` replaces an existing voxel spacing of the same value.

    Arguments:

        \b
        VOXEL_SPACING: The voxel spacing in Angstrom to be added to the run.

    Examples:

        \b
        # Add a 10.0 Angstrom voxel spacing to a run
        copick new voxelspacing --config config.json --run TS_001 10.0

        \b
        # Add a voxel spacing, overwriting any existing one
        copick new voxelspacing --config config.json --run TS_001 --overwrite 5.0

    See Also:

        \b
        copick new run: create the run that holds the voxel spacing
        copick add tomogram: import a tomogram at this voxel spacing
    """
    # Deferred import for performance
    import copick
    from copick.ops.add import add_voxelspacing

    get_logger(__name__, debug=debug)

    root = copick.from_file(config)
    add_voxelspacing(root, run, voxel_spacing, create=create, exist_ok=overwrite, log=debug)

    return 0
