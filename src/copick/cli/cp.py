"""CLI command for copying/duplicating copick objects."""

import click

from copick.cli.types import CopickURI
from copick.cli.util import add_config_option, add_debug_option
from copick.util.log import get_logger


@click.command(
    short_help="Copy or duplicate copick objects by URI.",
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
def cp(
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
    Copy or duplicate copick objects by URI.

    Copies picks, meshes, or segmentations identified by copick URIs, either within a
    run or across runs. Both single-object copies and pattern-based batch copies are
    supported: a concrete TARGET_URI duplicates one object, while a glob/regex SOURCE_URI
    combined with a templated TARGET_URI copies many matching objects at once. Source
    objects are never modified, and existing targets are only replaced when --overwrite
    is given.

    Picks and meshes are addressed as `object_name:user_id/session_id`; segmentations
    add a voxel spacing as `name:user_id/session_id@voxel_spacing`. For pattern-based
    copies, the TARGET_URI may use the placeholders `{object_name}`, `{name}`,
    `{user_id}`, `{session_id}`, and `{voxel_spacing}` (segmentations only), each filled
    from the corresponding field of the matched source object.

    Arguments:

        \b
        OBJECT_TYPE: Type of object to copy (picks, mesh, or segmentation).
        SOURCE_URI: Source copick URI pattern (supports glob and regex).
        TARGET_URI: Target copick URI (use template placeholders for pattern-based copies).

    Examples:

        \b
        # Create a backup copy of a single pick set
        copick cp picks "ribosome:user1/session-001" "ribosome:backup/session-001" -c config.json

        \b
        # Duplicate all manual picks to a backup user
        copick cp picks "ribosome:user1/manual-*" "ribosome:backup/{session_id}" -c config.json

        \b
        # Create test copies of segmentations across voxel spacing
        copick cp segmentation "membrane:user1/final-*@10.0" "membrane:user1/test-{session_id}@10.0" -c config.json

        \b
        # Copy picks to a different object name
        copick cp picks "ribosome:user1/*" "ribosome_80s:user1/{session_id}" -c config.json

    See Also:

        \b
        copick mv: move or rename copick objects by URI
        copick rm: remove copick objects by URI
    """
    # Deferred import for performance
    import copick
    from copick.ops.manage import copy_copick_objects_batch

    logger = get_logger(__name__, debug=debug)

    # Load root
    root = copick.from_file(config)

    # Log operation details
    logger.info(f"Copying {object_type} objects")
    logger.info(f"  Source: {source_uri}")
    logger.info(f"  Target: {target_uri}")

    if run:
        logger.info(f"  Run: {run}")
        run_names = [run]
    else:
        logger.info("  Run: all runs")
        run_names = None

    # Execute copy
    try:
        results = copy_copick_objects_batch(
            root=root,
            object_type=object_type,
            source_uri=source_uri,
            target_uri=target_uri,
            run_names=run_names,
            overwrite=overwrite,
            workers=workers,
        )

        # Aggregate results
        successful = sum(1 for r in results.values() if r and r.get("copied", 0) > 0)
        total_copied = sum(r.get("copied", 0) for r in results.values() if r)
        all_mappings = []
        all_errors = []

        for result in results.values():
            if result:
                all_mappings.extend(result.get("mappings", []))
                all_errors.extend(result.get("errors", []))

        # Report results
        logger.info(f"Completed: {successful}/{len(results)} runs processed successfully")
        if total_copied > 0:
            logger.info(f"Successfully copied {total_copied} objects")
            if debug:
                for source, target in all_mappings:
                    logger.debug(f"  {source} → {target}")
        else:
            logger.warning("No objects were copied")

        # Report errors
        if all_errors:
            logger.error(f"Encountered {len(all_errors)} errors:")
            for error in all_errors[:5]:
                logger.error(f"  - {error}")
            if len(all_errors) > 5:
                logger.error(f"  ... and {len(all_errors) - 5} more errors")

        # Exit with error code if any errors occurred and nothing was copied
        if all_errors and total_copied == 0:
            ctx.exit(1)

    except ValueError as e:
        logger.error(f"Invalid operation: {e}")
        ctx.fail(str(e))
    except Exception as e:
        logger.error(f"Failed to copy objects: {e}")
        ctx.fail(f"Failed to copy objects: {e}")
