"""CLI command for removing copick objects."""

import click

from copick.cli.util import add_config_option, add_debug_option
from copick.util.log import get_logger


@click.command(
    short_help="Remove copick objects by URI.",
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
    "--dry-run",
    is_flag=True,
    default=False,
    help="Show what would be deleted without actually deleting.",
    show_default=True,
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Required for pattern-based deletions (safety measure).",
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
    type=click.Choice(["picks", "mesh", "segmentation", "tomogram", "feature"], case_sensitive=False),
)
@click.argument("uri", type=str)
@click.pass_context
def rm(
    ctx,
    config: str,
    run: str,
    dry_run: bool,
    force: bool,
    workers: int,
    object_type: str,
    uri: str,
    debug: bool,
):
    """
    Remove copick objects matching a URI pattern.

    \b
    OBJECT_TYPE: Type of object to remove (picks, mesh, segmentation, tomogram, feature)
    URI: Copick URI pattern (supports glob and regex with 're:' prefix)

    \b
    URI Formats:
        Picks/Mesh:      object_name:user_id/session_id
        Segmentation:    name:user_id/session_id@voxel_spacing
        Tomogram:        tomo_type@voxel_spacing
        Feature:         tomo_type@voxel_spacing:feature_type

    \b
    Pattern Examples:
        Glob:    "ribosome:user1/session-*"
        Regex:   "re:ribosome:user1/session-\\d+"

    \b
    Examples:
        # Remove a specific pick set
        copick rm picks "ribosome:user1/session-001"

        # Preview deletion of test segmentations (dry run)
        copick rm --dry-run segmentation "membrane:*/test-*@10.0"

        # Remove all manual picks from user1 (requires --force)
        copick rm --force picks "ribosome:user1/manual-*"

        # Remove segmentations using regex pattern
        copick rm --force segmentation "re:membrane:user1/session-\\d+@10.0"
    """
    # Deferred import for performance
    import copick
    from copick.ops.manage import remove_copick_objects_batch
    from copick.util.uri import parse_copick_uri

    logger = get_logger(__name__, debug=debug)

    # Load root
    root = copick.from_file(config)

    # Check if URI contains patterns
    try:
        parsed = parse_copick_uri(uri, object_type)
        is_pattern = (
            parsed.get("pattern_type") == "regex"
            or "*" in str(parsed.get("object_name", ""))
            or "*" in str(parsed.get("user_id", ""))
            or "*" in str(parsed.get("session_id", ""))
            or "*" in str(parsed.get("name", ""))
            or "*" in str(parsed.get("tomo_type", ""))
            or "*" in str(parsed.get("feature_type", ""))
            or "*" in str(parsed.get("voxel_spacing", ""))
        )
    except ValueError as e:
        logger.error(f"Invalid URI: {e}")
        ctx.fail(f"Invalid URI: {e}")
        return

    # Require --force for pattern-based deletions (unless dry-run)
    if is_pattern and not force and not dry_run:
        logger.error(
            "Pattern-based deletion requires --force flag for safety. "
            "Use --dry-run to preview what would be deleted.",
        )
        ctx.fail("Pattern-based deletion requires --force flag. Use --dry-run to preview.")
        return

    # Log operation details
    if dry_run:
        logger.info(f"[DRY RUN] Previewing deletion of {object_type} matching: {uri}")
    else:
        logger.info(f"Removing {object_type} matching: {uri}")

    if run:
        logger.info(f"Operating on run: {run}")
        run_names = [run]
    else:
        logger.info("Operating on all runs")
        run_names = None

    # Execute removal
    try:
        results = remove_copick_objects_batch(
            root=root,
            object_type=object_type,
            uri=uri,
            run_names=run_names,
            dry_run=dry_run,
            workers=workers,
        )

        # Aggregate results
        successful = sum(1 for r in results.values() if r and r.get("deleted", 0) > 0)
        total_deleted = sum(r.get("deleted", 0) for r in results.values() if r)
        all_objects = []
        all_errors = []

        for result in results.values():
            if result:
                all_objects.extend(result.get("objects", []))
                all_errors.extend(result.get("errors", []))

        # Report results
        logger.info(f"Completed: {successful}/{len(results)} runs processed successfully")
        if dry_run:
            logger.info(f"[DRY RUN] Would delete {total_deleted} objects:")
            for obj_uri in all_objects[:10]:
                logger.info(f"  - {obj_uri}")
            if len(all_objects) > 10:
                logger.info(f"  ... and {len(all_objects) - 10} more objects")
        else:
            logger.info(f"Successfully deleted {total_deleted} objects")
            if debug:
                for obj_uri in all_objects:
                    logger.debug(f"  Deleted: {obj_uri}")

        # Report errors
        if all_errors:
            logger.error(f"Encountered {len(all_errors)} errors:")
            for error in all_errors[:5]:
                logger.error(f"  - {error}")
            if len(all_errors) > 5:
                logger.error(f"  ... and {len(all_errors) - 5} more errors")

    except Exception as e:
        logger.error(f"Failed to remove objects: {e}")
        ctx.fail(f"Failed to remove objects: {e}")
