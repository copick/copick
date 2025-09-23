import json

import click

from copick.cli.util import add_config_option, add_debug_option
from copick.ops.open import from_file
from copick.ops.stats import meshes_stats, picks_stats, segmentations_stats
from copick.util.log import get_logger


@click.group(short_help="Gather statistics about a copick project.")
@click.pass_context
def stats(ctx):
    """
    Statistics commands for Copick.

    This group contains commands for gathering statistics about Copick project entities.
    """
    pass


@stats.command(
    short_help="Display statistics about picks.",
    context_settings={"show_default": True},
    no_args_is_help=True,
)
@add_config_option
@click.option(
    "--runs",
    type=str,
    multiple=True,
    help="Specific run names to analyze. Can be specified multiple times.",
)
@click.option(
    "--user-id",
    type=str,
    multiple=True,
    help="Filter by user ID. Can be specified multiple times.",
)
@click.option(
    "--session-id",
    type=str,
    multiple=True,
    help="Filter by session ID. Can be specified multiple times.",
)
@click.option(
    "--object-name",
    type=str,
    multiple=True,
    help="Filter by pickable object name. Can be specified multiple times.",
)
@click.option(
    "--parallel/--no-parallel",
    default=True,
    help="Enable parallel processing.",
)
@click.option(
    "--workers",
    type=int,
    default=8,
    help="Number of workers for parallel processing.",
)
@click.option(
    "--output",
    type=click.Choice(["json", "table"]),
    default="table",
    help="Output format.",
)
@add_debug_option
@click.pass_context
def picks(
    ctx,
    config,
    runs,
    user_id,
    session_id,
    object_name,
    parallel,
    workers,
    output,
    debug,
):
    """Generate statistics for picks in the project."""
    get_logger(__name__, debug)

    if config is None:
        raise click.ClickException("Configuration file path is required. Use -c/--config option.")

    root = from_file(config)

    # Convert tuples to lists or None
    runs_param = list(runs) if runs else None
    user_id_param = list(user_id) if user_id else None
    session_id_param = list(session_id) if session_id else None
    object_name_param = list(object_name) if object_name else None

    stats_data = picks_stats(
        root=root,
        runs=runs_param,
        user_id=user_id_param,
        session_id=session_id_param,
        object_name=object_name_param,
        parallel=parallel,
        workers=workers,
        show_progress=True,
    )

    if output == "json":
        click.echo(json.dumps(stats_data, indent=2))
    else:
        _print_picks_table(stats_data)


@stats.command(
    short_help="Display statistics about meshes.",
    context_settings={"show_default": True},
    no_args_is_help=True,
)
@add_config_option
@click.option(
    "--runs",
    type=str,
    multiple=True,
    help="Specific run names to analyze. Can be specified multiple times.",
)
@click.option(
    "--user-id",
    type=str,
    multiple=True,
    help="Filter by user ID. Can be specified multiple times.",
)
@click.option(
    "--session-id",
    type=str,
    multiple=True,
    help="Filter by session ID. Can be specified multiple times.",
)
@click.option(
    "--object-name",
    type=str,
    multiple=True,
    help="Filter by pickable object name. Can be specified multiple times.",
)
@click.option(
    "--parallel/--no-parallel",
    default=True,
    help="Enable parallel processing.",
)
@click.option(
    "--workers",
    type=int,
    default=8,
    help="Number of workers for parallel processing.",
)
@click.option(
    "--output",
    type=click.Choice(["json", "table"]),
    default="table",
    help="Output format.",
)
@add_debug_option
@click.pass_context
def meshes(
    ctx,
    config,
    runs,
    user_id,
    session_id,
    object_name,
    parallel,
    workers,
    output,
    debug,
):
    """Generate statistics for meshes in the project."""
    get_logger(__name__, debug)

    if config is None:
        raise click.ClickException("Configuration file path is required. Use -c/--config option.")

    root = from_file(config)

    # Convert tuples to lists or None
    runs_param = list(runs) if runs else None
    user_id_param = list(user_id) if user_id else None
    session_id_param = list(session_id) if session_id else None
    object_name_param = list(object_name) if object_name else None

    stats_data = meshes_stats(
        root=root,
        runs=runs_param,
        user_id=user_id_param,
        session_id=session_id_param,
        object_name=object_name_param,
        parallel=parallel,
        workers=workers,
        show_progress=True,
    )

    if output == "json":
        click.echo(json.dumps(stats_data, indent=2))
    else:
        _print_meshes_table(stats_data)


@stats.command(
    short_help="Display statistics about segmentations.",
    context_settings={"show_default": True},
    no_args_is_help=True,
)
@add_config_option
@click.option(
    "--runs",
    type=str,
    multiple=True,
    help="Specific run names to analyze. Can be specified multiple times.",
)
@click.option(
    "--user-id",
    type=str,
    multiple=True,
    help="Filter by user ID. Can be specified multiple times.",
)
@click.option(
    "--session-id",
    type=str,
    multiple=True,
    help="Filter by session ID. Can be specified multiple times.",
)
@click.option(
    "--name",
    type=str,
    multiple=True,
    help="Filter by segmentation name. Can be specified multiple times.",
)
@click.option(
    "--voxel-size",
    type=float,
    multiple=True,
    help="Filter by voxel size. Can be specified multiple times.",
)
@click.option(
    "--multilabel/--no-multilabel",
    default=None,
    help="Filter by multilabel status.",
)
@click.option(
    "--parallel/--no-parallel",
    default=True,
    help="Enable parallel processing.",
)
@click.option(
    "--workers",
    type=int,
    default=8,
    help="Number of workers for parallel processing.",
)
@click.option(
    "--output",
    type=click.Choice(["json", "table"]),
    default="table",
    help="Output format.",
)
@add_debug_option
@click.pass_context
def segmentations(
    ctx,
    config,
    runs,
    user_id,
    session_id,
    name,
    voxel_size,
    multilabel,
    parallel,
    workers,
    output,
    debug,
):
    """Generate statistics for segmentations in the project."""
    get_logger(__name__, debug)

    if config is None:
        raise click.ClickException("Configuration file path is required. Use -c/--config option.")

    root = from_file(config)

    # Convert tuples to lists or None
    runs_param = list(runs) if runs else None
    user_id_param = list(user_id) if user_id else None
    session_id_param = list(session_id) if session_id else None
    name_param = list(name) if name else None
    voxel_size_param = list(voxel_size) if voxel_size else None

    stats_data = segmentations_stats(
        root=root,
        runs=runs_param,
        user_id=user_id_param,
        session_id=session_id_param,
        is_multilabel=multilabel,
        name=name_param,
        voxel_size=voxel_size_param,
        parallel=parallel,
        workers=workers,
        show_progress=True,
    )

    if output == "json":
        click.echo(json.dumps(stats_data, indent=2))
    else:
        _print_segmentations_table(stats_data)


def _print_picks_table(stats_data: dict):
    """Print picks statistics in table format."""
    click.echo("=== Picks Statistics ===")
    click.echo(f"Total individual picks: {stats_data['total_picks']}")
    click.echo(f"Total pick files: {stats_data['total_pick_files']}")

    if stats_data["distribution_by_run"]:
        click.echo("\nDistribution by run:")
        for run, count in stats_data["distribution_by_run"].items():
            click.echo(f"  {run}: {count}")

    if stats_data["distribution_by_user"]:
        click.echo("\nDistribution by user:")
        for user, count in stats_data["distribution_by_user"].items():
            click.echo(f"  {user}: {count}")

    if stats_data["distribution_by_session"]:
        click.echo("\nDistribution by session:")
        for session, count in stats_data["distribution_by_session"].items():
            click.echo(f"  {session}: {count}")

    if stats_data["distribution_by_object"]:
        click.echo("\nDistribution by object:")
        for obj, count in stats_data["distribution_by_object"].items():
            click.echo(f"  {obj}: {count}")


def _print_meshes_table(stats_data: dict):
    """Print meshes statistics in table format."""
    click.echo("=== Meshes Statistics ===")
    click.echo(f"Total meshes: {stats_data['total_meshes']}")

    if stats_data["distribution_by_user"]:
        click.echo("\nDistribution by user:")
        for user, count in stats_data["distribution_by_user"].items():
            click.echo(f"  {user}: {count}")

    if stats_data["distribution_by_session"]:
        click.echo("\nDistribution by session:")
        for session, count in stats_data["distribution_by_session"].items():
            click.echo(f"  {session}: {count}")

    if stats_data["distribution_by_object"]:
        click.echo("\nDistribution by object:")
        for obj, count in stats_data["distribution_by_object"].items():
            click.echo(f"  {obj}: {count}")

    if stats_data["session_user_object_combinations"]:
        click.echo("\nFrequent session_user_object combinations:")
        sorted_combos = sorted(
            stats_data["session_user_object_combinations"].items(),
            key=lambda x: x[1],
            reverse=True,
        )
        for combo, count in sorted_combos[:10]:  # Top 10
            click.echo(f"  {combo}: {count}")


def _print_segmentations_table(stats_data: dict):
    """Print segmentations statistics in table format."""
    click.echo("=== Segmentations Statistics ===")
    click.echo(f"Total segmentations: {stats_data['total_segmentations']}")

    if stats_data["distribution_by_user"]:
        click.echo("\nDistribution by user:")
        for user, count in stats_data["distribution_by_user"].items():
            click.echo(f"  {user}: {count}")

    if stats_data["distribution_by_session"]:
        click.echo("\nDistribution by session:")
        for session, count in stats_data["distribution_by_session"].items():
            click.echo(f"  {session}: {count}")

    if stats_data["distribution_by_name"]:
        click.echo("\nDistribution by name:")
        for name, count in stats_data["distribution_by_name"].items():
            click.echo(f"  {name}: {count}")

    if stats_data["distribution_by_voxel_size"]:
        click.echo("\nDistribution by voxel size:")
        for voxel_size, count in stats_data["distribution_by_voxel_size"].items():
            click.echo(f"  {voxel_size}: {count}")

    if stats_data["distribution_by_multilabel"]:
        click.echo("\nDistribution by multilabel:")
        for multilabel, count in stats_data["distribution_by_multilabel"].items():
            click.echo(f"  {multilabel}: {count}")

    if stats_data["session_user_voxelspacing_multilabel_combinations"]:
        click.echo("\nFrequent session_user_voxelspacing_multilabel combinations:")
        sorted_combos = sorted(
            stats_data["session_user_voxelspacing_multilabel_combinations"].items(),
            key=lambda x: x[1],
            reverse=True,
        )
        for combo, count in sorted_combos[:10]:  # Top 10
            click.echo(f"  {combo}: {count}")
