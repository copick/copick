"""CLI command for moving/renaming copick objects."""

import click

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
@click.argument("source_uri", type=str)
@click.argument("target_uri", type=str)
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
    Move or rename copick objects by URI.

    \b
    OBJECT_TYPE: Type of object to move (picks, mesh, segmentation)
    SOURCE_URI: Source copick URI pattern (supports glob and regex)
    TARGET_URI: Target copick URI (use templates for pattern operations)

    \b
    URI Formats:
        Picks/Mesh:      object_name:user_id/session_id
        Segmentation:    name:user_id/session_id@voxel_spacing

    \b
    Template Placeholders (for pattern-based moves):
        {object_name}    - Original object/pickable name
        {name}           - Original segmentation name
        {user_id}        - Original user ID
        {session_id}     - Original session ID
        {voxel_spacing}  - Original voxel spacing (segmentations only)

    \b
    Examples:
        # Rename a single pick set
        copick mv picks "ribosome:user1/session-001" "ribosome:user2/session-001"

        # Move all manual picks to a backup user
        copick mv picks "ribosome:user1/manual-*" "ribosome:backup/{session_id}"

        # Rename segmentation sessions with pattern
        copick mv segmentation "membrane:user1/session-*@10.0" "membrane:user1/renamed-{session_id}@10.0"

        # Change user for all test segmentations
        copick mv segmentation "membrane:user1/test-*@10.0" "membrane:user2/{session_id}@10.0"

    \b
    Notes:
        - For single object moves, TARGET_URI should be concrete (no templates)
        - For pattern-based moves, TARGET_URI must contain template placeholders
        - Source objects are deleted after successful copy to target
        - Use --overwrite to replace existing target objects
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
