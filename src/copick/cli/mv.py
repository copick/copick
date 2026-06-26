"""CLI command for moving/renaming copick objects."""

import click

from copick.cli.types import CopickURI
from copick.cli.util import add_config_option, add_debug_option
from copick.util.log import get_logger


@click.command(
    short_help="Move/rename copick objects by URI.",
    no_args_is_help=True,
)
@add_config_option
@click.option(
    "-r",
    "--run",
    type=str,
    default=None,
    help="Specific run name to operate on (default: all runs).",
)
@click.option(
    "--overwrite/--no-overwrite",
    is_flag=True,
    default=False,
    help="Allow overwriting existing target objects.",
    show_default=True,
)
@click.option(
    "--workers",
    "-w",
    type=int,
    default=8,
    help="Number of parallel worker processes.",
    show_default=True,
)
@add_debug_option
@click.argument(
    "object_type",
    type=click.Choice(["picks", "mesh", "segmentation"], case_sensitive=False),
)
@click.argument("source_uri", type=CopickURI("any", "input"))
@click.argument("target_uri", type=CopickURI("any", "output"))
@click.pass_context
def mv(
    ctx,
    config: str,
    run: str,
    overwrite: bool,
    workers: int,
    object_type: str,
    source_uri: str,
    target_uri: str,
    debug: bool,
):
    """
    Move/rename copick objects by URI.

    Renames or relocates picks, meshes, and segmentations within a project by
    rewriting their URI. A single concrete source/target pair renames one object,
    while a glob or regex source pattern combined with a templated target moves
    many objects at once. Each source object is deleted only after a successful
    copy to its target.

    Picks and meshes are addressed as `object_name:user_id/session_id`, and
    segmentations append a voxel spacing as `name:user_id/session_id@voxel_spacing`.
    For pattern-based moves the target URI may use placeholders that are filled in
    from each matched source: `{object_name}`, `{name}`, `{user_id}`,
    `{session_id}`, and `{voxel_spacing}` (segmentations only).

    For single-object moves the target URI should be concrete (no placeholders);
    for pattern-based moves it must contain at least one placeholder. Use
    `--overwrite` to replace existing target objects and `--run` to limit the
    operation to a single run.

    Arguments:

        \b
        OBJECT_TYPE: Type of object to move (picks, mesh, or segmentation).
        SOURCE_URI: Source copick URI pattern (supports glob and regex).
        TARGET_URI: Target copick URI (use placeholders for pattern-based moves).

    Examples:

        \b
        # Rename a single pick set
        copick mv picks "ribosome:user1/session-001" "ribosome:user2/session-001" -c config.json

        \b
        # Move all manual pick sessions to a backup user with a template
        copick mv picks "ribosome:user1/manual-*" "ribosome:backup/{session_id}" -c config.json

        \b
        # Rename matching segmentation sessions with a pattern
        copick mv segmentation "membrane:user1/session-*@10.0" \\
            "membrane:user1/renamed-{session_id}@10.0" -c config.json

    See Also:

        \b
        copick cp: copy or duplicate objects instead of moving them
        copick rm: remove objects matched by a URI
    """
    # Deferred import for performance
    import copick
    from copick.ops.manage import move_copick_objects_batch

    logger = get_logger(__name__, debug=debug)

    # Load root
    root = copick.from_file(config)

    # Log operation details
    logger.info(f"Moving {object_type} objects")
    logger.info(f"  Source: {source_uri}")
    logger.info(f"  Target: {target_uri}")

    if run:
        logger.info(f"  Run: {run}")
        run_names = [run]
    else:
        logger.info("  Run: all runs")
        run_names = None

    # Execute move
    try:
        results = move_copick_objects_batch(
            root=root,
            object_type=object_type,
            source_uri=source_uri,
            target_uri=target_uri,
            run_names=run_names,
            overwrite=overwrite,
            workers=workers,
        )

        # Aggregate results
        successful = sum(1 for r in results.values() if r and r.get("moved", 0) > 0)
        total_moved = sum(r.get("moved", 0) for r in results.values() if r)
        all_mappings = []
        all_errors = []

        for result in results.values():
            if result:
                all_mappings.extend(result.get("mappings", []))
                all_errors.extend(result.get("errors", []))

        # Report results
        logger.info(f"Completed: {successful}/{len(results)} runs processed successfully")
        if total_moved > 0:
            logger.info(f"Successfully moved {total_moved} objects")
            if debug:
                for source, target in all_mappings:
                    logger.debug(f"  {source} → {target}")
        else:
            logger.warning("No objects were moved")

        # Report errors
        if all_errors:
            logger.error(f"Encountered {len(all_errors)} errors:")
            for error in all_errors[:5]:
                logger.error(f"  - {error}")
            if len(all_errors) > 5:
                logger.error(f"  ... and {len(all_errors) - 5} more errors")

        # Exit with error code if any errors occurred and nothing was moved
        if all_errors and total_moved == 0:
            ctx.exit(1)

    except ValueError as e:
        logger.error(f"Invalid operation: {e}")
        ctx.fail(str(e))
    except Exception as e:
        logger.error(f"Failed to move objects: {e}")
        ctx.fail(f"Failed to move objects: {e}")
