import os

import click

from copick.cli.util import add_config_option, add_debug_option
from copick.ops.sync import (
    sync_alignments,
    sync_meshes,
    sync_picks,
    sync_segmentations,
    sync_tilt_series,
    sync_tomograms,
)
from copick.util.log import get_logger
from copick.util.sync import (
    create_dataportal_config,
    ensure_pickable_objects,
    parse_dataset_ids,
    parse_list,
    parse_mapping,
)


@click.group()
@click.pass_context
def sync(ctx):
    """Synchronize data between Copick projects."""
    pass


@sync.command(
    short_help="Synchronize picks between two Copick projects.",
    context_settings={"show_default": True},
    no_args_is_help=True,
)
@add_config_option
@click.option(
    "--source-dataset-ids",
    type=str,
    help="Comma-separated list of dataset IDs to use as source from CryoET Data Portal. If provided, --config will be ignored and a temporary dataportal configuration will be created.",
    default="",
    required=False,
)
@click.option(
    "--target-config",
    type=click.Path(exists=True),
    help="Path to the target configuration file.",
    required=True,
    metavar="PATH",
)
@click.option(
    "--source-runs",
    type=str,
    help="Comma-separated list of source run names to synchronize. If not specified, all runs will be synced.",
    default="",
    show_default=True,
)
@click.option(
    "--target-runs",
    type=str,
    help="Comma-separated mapping of source run names to target run names (e.g. 'run1:target1,run2:target2'). If not specified, source run names will be used.",
    default="",
    show_default=True,
)
@click.option(
    "--source-objects",
    type=str,
    help="Comma-separated list of source object names to synchronize. If not specified, all objects will be synced.",
    default="",
    show_default=True,
)
@click.option(
    "--target-objects",
    type=str,
    help="Comma-separated mapping of source object names to target object names (e.g. 'ribosome:ribo,membrane:mem'). If not specified, source object names will be used.",
    default="",
    show_default=True,
)
@click.option(
    "--source-users",
    type=str,
    help="Comma-separated list of source user IDs to synchronize. If not specified, all users will be synced.",
    default="",
    show_default=True,
)
@click.option(
    "--target-users",
    type=str,
    help="Comma-separated mapping of source user IDs to target user IDs (e.g. 'user1:target1,user2:target2'). If not specified, source user IDs will be used.",
    default="",
    show_default=True,
)
@click.option(
    "--exist-ok/--no-exist-ok",
    is_flag=True,
    help="Allow overwriting existing picks in the target project.",
    show_default=True,
    default=False,
)
@click.option(
    "--max-workers",
    type=int,
    help="Maximum number of worker threads to use for synchronization.",
    default=4,
    show_default=True,
)
@click.option(
    "--log/--no-log",
    is_flag=True,
    help="Enable verbose logging of the synchronization process.",
    show_default=True,
    default=False,
)
@add_debug_option
def picks(
    config,
    source_dataset_ids,
    target_config,
    source_runs,
    target_runs,
    source_objects,
    target_objects,
    source_users,
    target_users,
    exist_ok,
    max_workers,
    log,
    debug,
):
    """Synchronize picks between two Copick projects.

    Copies pick annotations from a source Copick project to a target project. You can
    restrict the sync to specific runs, objects, and users, and optionally remap source
    names to different target names. The source may instead be one or more CryoET Data
    Portal datasets via `--source-dataset-ids`, in which case `--config` is ignored and a
    temporary dataportal configuration is created.

    Pickable objects missing from the target project are created automatically before the
    picks are copied. Use `--exist-ok` to overwrite picks that already exist in the target.

    Examples:

        \b
        # Sync all picks from all runs
        copick sync picks -c source_config.json --target-config target_config.json

        \b
        # Sync specific runs with name mapping
        copick sync picks -c source_config.json --target-config target_config.json \\
            --source-runs "run1,run2" --target-runs "run1:new_run1,run2:new_run2"

        \b
        # Sync specific objects with name mapping
        copick sync picks -c source_config.json --target-config target_config.json \\
            --source-objects "ribosome,membrane" --target-objects "ribosome:ribo,membrane:mem"

        \b
        # Sync picks sourced from CryoET Data Portal datasets
        copick sync picks --source-dataset-ids "10301,10302" --target-config target_config.json

    See Also:

        \b
        copick sync meshes: synchronize meshes between projects
        copick sync segmentations: synchronize segmentations between projects
        copick sync tomograms: synchronize tomograms between projects
    """

    logger = get_logger(__name__, debug=debug)

    # Parse arguments
    source_runs_list = parse_list(source_runs) if source_runs else None
    target_runs_dict = parse_mapping(target_runs) if target_runs else None
    source_objects_list = parse_list(source_objects) if source_objects else None
    target_objects_dict = parse_mapping(target_objects) if target_objects else None
    source_users_list = parse_list(source_users) if source_users else None
    target_users_dict = parse_mapping(target_users) if target_users else None

    # Handle dataportal source configuration
    temp_config_path = None
    if source_dataset_ids:
        dataset_ids = parse_dataset_ids(source_dataset_ids)
        temp_config_path = create_dataportal_config(dataset_ids)
        source_config = temp_config_path
    else:
        source_config = config

    # Load configurations
    import copick

    source_root = copick.from_file(source_config)
    target_root = copick.from_file(target_config)

    try:
        # Get objects to process (default to all objects if not specified)
        if source_objects_list is None:
            source_objects_list = [obj.name for obj in source_root.pickable_objects]
        if target_objects_dict is None:
            target_objects_dict = {obj: obj for obj in source_objects_list}

        # Ensure pickable objects exist in target before synchronization
        ensure_pickable_objects(
            source_root=source_root,
            target_root=target_root,
            target_config_path=target_config,
            source_objects_list=source_objects_list,
            target_objects_dict=target_objects_dict,
            log=log,
        )

        # Perform synchronization
        sync_picks(
            source_root=source_root,
            target_root=target_root,
            source_runs=source_runs_list,
            target_runs=target_runs_dict,
            source_objects=source_objects_list,
            target_objects=target_objects_dict,
            source_users=source_users_list,
            target_users=target_users_dict,
            exist_ok=exist_ok,
            max_workers=max_workers,
            log=log,
        )

        logger.info("Picks synchronization completed successfully.")
    finally:
        # Clean up temporary files
        if temp_config_path and os.path.exists(temp_config_path):
            os.unlink(temp_config_path)


@sync.command(short_help="Synchronize meshes between two Copick projects.")
@add_config_option
@click.option(
    "--source-dataset-ids",
    type=str,
    help="Comma-separated list of dataset IDs to use as source from CryoET Data Portal. If provided, --config will be ignored and a temporary dataportal configuration will be created.",
    default="",
    required=False,
)
@click.option(
    "--target-config",
    type=click.Path(exists=True),
    help="Path to the target configuration file.",
    required=True,
    metavar="PATH",
)
@click.option(
    "--source-runs",
    type=str,
    help="Comma-separated list of source run names to synchronize. If not specified, all runs will be synced.",
    default="",
    show_default=True,
)
@click.option(
    "--target-runs",
    type=str,
    help="Comma-separated mapping of source run names to target run names (e.g. 'run1:target1,run2:target2'). If not specified, source run names will be used.",
    default="",
    show_default=True,
)
@click.option(
    "--source-objects",
    type=str,
    help="Comma-separated list of source object names to synchronize. If not specified, all objects will be synced.",
    default="",
    show_default=True,
)
@click.option(
    "--target-objects",
    type=str,
    help="Comma-separated mapping of source object names to target object names (e.g. 'ribosome:ribo,membrane:mem'). If not specified, source object names will be used.",
    default="",
    show_default=True,
)
@click.option(
    "--source-users",
    type=str,
    help="Comma-separated list of source user IDs to synchronize. If not specified, all users will be synced.",
    default="",
    show_default=True,
)
@click.option(
    "--target-users",
    type=str,
    help="Comma-separated mapping of source user IDs to target user IDs (e.g. 'user1:target1,user2:target2'). If not specified, source user IDs will be used.",
    default="",
    show_default=True,
)
@click.option(
    "--exist-ok/--no-exist-ok",
    is_flag=True,
    help="Allow overwriting existing meshes in the target project.",
    show_default=True,
    default=False,
)
@click.option(
    "--max-workers",
    type=int,
    help="Maximum number of worker threads to use for synchronization.",
    default=4,
    show_default=True,
)
@click.option(
    "--log/--no-log",
    is_flag=True,
    help="Enable verbose logging of the synchronization process.",
    show_default=True,
    default=False,
)
@add_debug_option
def meshes(
    config,
    source_dataset_ids,
    target_config,
    source_runs,
    target_runs,
    source_objects,
    target_objects,
    source_users,
    target_users,
    exist_ok,
    max_workers,
    log,
    debug,
):
    """Synchronize meshes between two Copick projects.

    Copies mesh data from a source Copick project to a target project. You can restrict
    the sync to specific runs, objects, and users, and optionally remap source names to
    different target names. The source may instead be one or more CryoET Data Portal
    datasets via `--source-dataset-ids`, in which case `--config` is ignored and a
    temporary dataportal configuration is created.

    Pickable objects missing from the target project are created automatically before the
    meshes are copied. Use `--exist-ok` to overwrite meshes that already exist in the
    target.

    Examples:

        \b
        # Sync all meshes from all runs
        copick sync meshes -c source_config.json --target-config target_config.json

        \b
        # Sync specific runs with name mapping
        copick sync meshes -c source_config.json --target-config target_config.json \\
            --source-runs "run1,run2" --target-runs "run1:new_run1,run2:new_run2"

        \b
        # Sync specific objects with name mapping
        copick sync meshes -c source_config.json --target-config target_config.json \\
            --source-objects "ribosome,membrane" --target-objects "ribosome:ribo,membrane:mem"

    See Also:

        \b
        copick sync picks: synchronize picks between projects
        copick sync segmentations: synchronize segmentations between projects
        copick sync tomograms: synchronize tomograms between projects
    """
    logger = get_logger(__name__, debug=debug)

    # Parse arguments
    source_runs_list = parse_list(source_runs) if source_runs else None
    target_runs_dict = parse_mapping(target_runs) if target_runs else None
    source_objects_list = parse_list(source_objects) if source_objects else None
    target_objects_dict = parse_mapping(target_objects) if target_objects else None
    source_users_list = parse_list(source_users) if source_users else None
    target_users_dict = parse_mapping(target_users) if target_users else None

    # Handle dataportal source configuration
    temp_config_path = None
    if source_dataset_ids:
        dataset_ids = parse_dataset_ids(source_dataset_ids)
        temp_config_path = create_dataportal_config(dataset_ids)
        source_config = temp_config_path
    else:
        source_config = config

    # Load configurations
    import copick

    source_root = copick.from_file(source_config)
    target_root = copick.from_file(target_config)

    try:
        # Get objects to process (default to all objects if not specified)
        if source_objects_list is None:
            source_objects_list = [obj.name for obj in source_root.pickable_objects]
        if target_objects_dict is None:
            target_objects_dict = {obj: obj for obj in source_objects_list}

        # Ensure pickable objects exist in target before synchronization
        ensure_pickable_objects(
            source_root=source_root,
            target_root=target_root,
            target_config_path=target_config,
            source_objects_list=source_objects_list,
            target_objects_dict=target_objects_dict,
            log=log,
        )

        # Perform synchronization
        sync_meshes(
            source_root=source_root,
            target_root=target_root,
            source_runs=source_runs_list,
            target_runs=target_runs_dict,
            source_objects=source_objects_list,
            target_objects=target_objects_dict,
            source_users=source_users_list,
            target_users=target_users_dict,
            exist_ok=exist_ok,
            max_workers=max_workers,
            log=log,
        )

        logger.info("Meshes synchronization completed successfully.")
    finally:
        # Clean up temporary files
        if temp_config_path and os.path.exists(temp_config_path):
            os.unlink(temp_config_path)


@sync.command(short_help="Synchronize segmentations between two Copick projects.")
@add_config_option
@click.option(
    "--source-dataset-ids",
    type=str,
    help="Comma-separated list of dataset IDs to use as source from CryoET Data Portal. If provided, --config will be ignored and a temporary dataportal configuration will be created.",
    default="",
    required=False,
)
@click.option(
    "--target-config",
    type=click.Path(exists=True),
    help="Path to the target configuration file.",
    required=True,
    metavar="PATH",
)
@click.option(
    "--source-runs",
    type=str,
    help="Comma-separated list of source run names to synchronize. If not specified, all runs will be synced.",
    default="",
    show_default=True,
)
@click.option(
    "--target-runs",
    type=str,
    help="Comma-separated mapping of source run names to target run names (e.g. 'run1:target1,run2:target2'). If not specified, source run names will be used.",
    default="",
    show_default=True,
)
@click.option(
    "--voxel-spacings",
    type=str,
    help="Comma-separated list of voxel spacings to consider for synchronization. If not specified, all voxel spacings will be synced.",
    default="",
    show_default=True,
)
@click.option(
    "--source-names",
    type=str,
    help="Comma-separated list of source segmentation names to synchronize. If not specified, all segmentations will be synced.",
    default="",
    show_default=True,
)
@click.option(
    "--target-names",
    type=str,
    help="Comma-separated mapping of source segmentation names to target names (e.g. 'seg1:target1,seg2:target2'). If not specified, source names will be used.",
    default="",
    show_default=True,
)
@click.option(
    "--source-users",
    type=str,
    help="Comma-separated list of source user IDs to synchronize. If not specified, all users will be synced.",
    default="",
    show_default=True,
)
@click.option(
    "--target-users",
    type=str,
    help="Comma-separated mapping of source user IDs to target user IDs (e.g. 'user1:target1,user2:target2'). If not specified, source user IDs will be used.",
    default="",
    show_default=True,
)
@click.option(
    "--segmentation-type",
    type=click.Choice(  # SEGMENTATION_TYPE_FILTERS
        ["binary", "multilabel", "instance", "panoptic", "all"],
        case_sensitive=False,
    ),
    default=None,
    help="Segmentation type to synchronize; 'all' for every type. Default: binary and multilabel segmentations.",
)
@click.option(
    "--exist-ok/--no-exist-ok",
    is_flag=True,
    help="Allow overwriting existing segmentations in the target project.",
    show_default=True,
    default=False,
)
@click.option(
    "--max-workers",
    type=int,
    help="Maximum number of worker threads to use for synchronization.",
    default=4,
    show_default=True,
)
@click.option(
    "--log/--no-log",
    is_flag=True,
    help="Enable verbose logging of the synchronization process.",
    show_default=True,
    default=False,
)
@add_debug_option
def segmentations(
    config,
    source_dataset_ids,
    target_config,
    source_runs,
    target_runs,
    voxel_spacings,
    source_names,
    target_names,
    source_users,
    target_users,
    segmentation_type,
    exist_ok,
    max_workers,
    log,
    debug,
):
    """Synchronize segmentations between two Copick projects.

    Copies segmentation data from a source Copick project to a target project. You can
    restrict the sync to specific runs, voxel spacings, segmentation names, and users, and
    optionally remap source names to different target names. The source may instead be one
    or more CryoET Data Portal datasets via `--source-dataset-ids`, in which case
    `--config` is ignored and a temporary dataportal configuration is created.

    When specific segmentation names are requested, the matching pickable objects are
    created in the target project before copying (binary and instance segmentations require
    the name to match a pickable object; multilabel and panoptic ones do not). Use `--exist-ok` to overwrite segmentations that
    already exist in the target.

    Examples:

        \b
        # Sync all segmentations from all runs
        copick sync segmentations -c source_config.json --target-config target_config.json

        \b
        # Sync specific runs and voxel spacings
        copick sync segmentations -c source_config.json --target-config target_config.json \\
            --source-runs "run1,run2" --voxel-spacings "10.0,20.0"

        \b
        # Sync specific segmentation names with name mapping
        copick sync segmentations -c source_config.json --target-config target_config.json \\
            --source-names "ribosome,membrane" --target-names "ribosome:ribo,membrane:mem"

    See Also:

        \b
        copick sync picks: synchronize picks between projects
        copick sync meshes: synchronize meshes between projects
        copick sync tomograms: synchronize tomograms between projects
    """
    from copick.util.segmentation import segmentation_type_query

    logger = get_logger(__name__, debug=debug)

    # Parse arguments
    source_runs_list = parse_list(source_runs) if source_runs else None
    target_runs_dict = parse_mapping(target_runs) if target_runs else None
    voxel_spacings_list = [float(x) for x in parse_list(voxel_spacings)] if voxel_spacings else None
    source_names_list = parse_list(source_names) if source_names else None
    target_names_dict = parse_mapping(target_names) if target_names else None
    source_users_list = parse_list(source_users) if source_users else None
    target_users_dict = parse_mapping(target_users) if target_users else None

    # Handle dataportal source configuration
    temp_config_path = None
    if source_dataset_ids:
        dataset_ids = parse_dataset_ids(source_dataset_ids)
        temp_config_path = create_dataportal_config(dataset_ids)
        source_config = temp_config_path
    else:
        source_config = config

    # Load configurations
    import copick

    source_root = copick.from_file(source_config)
    target_root = copick.from_file(target_config)

    try:
        # For segmentations, ensure pickable objects exist if we have specific segmentation names
        # (binary and instance segmentations require the segmentation name to match a pickable object)
        if source_names_list is not None:
            # Use segmentation names as pickable object names for validation
            target_names_for_objects = target_names_dict if target_names_dict else {}
            ensure_pickable_objects(
                source_root=source_root,
                target_root=target_root,
                target_config_path=target_config,
                source_objects_list=source_names_list,
                target_objects_dict=target_names_for_objects,
                log=log,
            )

        # Perform synchronization
        sync_segmentations(
            source_root=source_root,
            target_root=target_root,
            source_runs=source_runs_list,
            target_runs=target_runs_dict,
            voxel_spacings=voxel_spacings_list,
            source_names=source_names_list,
            target_names=target_names_dict,
            source_users=source_users_list,
            target_users=target_users_dict,
            exist_ok=exist_ok,
            max_workers=max_workers,
            log=log,
            **segmentation_type_query(segmentation_type),
        )

        logger.info("Segmentations synchronization completed successfully.")
    finally:
        # Clean up temporary files
        if temp_config_path and os.path.exists(temp_config_path):
            os.unlink(temp_config_path)


@sync.command(short_help="Synchronize tomograms between two Copick projects.")
@add_config_option
@click.option(
    "--source-dataset-ids",
    type=str,
    help="Comma-separated list of dataset IDs to use as source from CryoET Data Portal. If provided, --config will be ignored and a temporary dataportal configuration will be created.",
    default="",
    required=False,
)
@click.option(
    "--target-config",
    type=click.Path(exists=True),
    help="Path to the target configuration file.",
    required=True,
    metavar="PATH",
)
@click.option(
    "--source-runs",
    type=str,
    help="Comma-separated list of source run names to synchronize. If not specified, all runs will be synced.",
    default="",
    show_default=True,
)
@click.option(
    "--target-runs",
    type=str,
    help="Comma-separated mapping of source run names to target run names (e.g. 'run1:target1,run2:target2'). If not specified, source run names will be used.",
    default="",
    show_default=True,
)
@click.option(
    "--voxel-spacings",
    type=str,
    help="Comma-separated list of voxel spacings to consider for synchronization. If not specified, all voxel spacings will be synced.",
    default="",
    show_default=True,
)
@click.option(
    "--source-tomo-types",
    type=str,
    help="Comma-separated list of source tomogram types to synchronize. If not specified, all tomogram types will be synced.",
    default="",
    show_default=True,
)
@click.option(
    "--target-tomo-types",
    type=str,
    help="Comma-separated mapping of source tomogram types to target types (e.g. 'wbp:filtered,raw:original'). If not specified, source tomogram types will be used.",
    default="",
    show_default=True,
)
@click.option(
    "--exist-ok/--no-exist-ok",
    is_flag=True,
    help="Allow overwriting existing tomograms in the target project.",
    show_default=True,
    default=False,
)
@click.option(
    "--with-links/--no-with-links",
    is_flag=True,
    help="Link target tomograms to the target run's alignments of the names their sources are linked to (e.g. links "
    "the CryoET Data Portal reports). Sync the alignments first.",
    show_default=True,
    default=False,
)
@click.option(
    "--max-workers",
    type=int,
    help="Maximum number of worker threads to use for synchronization.",
    default=4,
    show_default=True,
)
@click.option(
    "--log/--no-log",
    is_flag=True,
    help="Enable verbose logging of the synchronization process.",
    show_default=True,
    default=False,
)
@add_debug_option
def tomograms(
    config,
    source_dataset_ids,
    target_config,
    source_runs,
    target_runs,
    voxel_spacings,
    source_tomo_types,
    target_tomo_types,
    exist_ok,
    with_links,
    max_workers,
    log,
    debug,
):
    """Synchronize tomograms between two Copick projects.

    Copies tomogram data from a source Copick project to a target project. You can restrict
    the sync to specific runs, voxel spacings, and tomogram types, and optionally remap
    source tomogram types to different target types. The source may instead be one or more
    CryoET Data Portal datasets via `--source-dataset-ids`, in which case `--config` is
    ignored and a temporary dataportal configuration is created.

    Use `--exist-ok` to overwrite tomograms that already exist in the target.

    Examples:

        \b
        # Sync all tomograms from all runs
        copick sync tomograms -c source_config.json --target-config target_config.json

        \b
        # Sync specific runs and voxel spacings
        copick sync tomograms -c source_config.json --target-config target_config.json \\
            --source-runs "run1,run2" --voxel-spacings "10.0,20.0"

        \b
        # Sync specific tomogram types with name mapping
        copick sync tomograms -c source_config.json --target-config target_config.json \\
            --source-tomo-types "wbp,raw" --target-tomo-types "wbp:filtered,raw:original"

    See Also:

        \b
        copick sync picks: synchronize picks between projects
        copick sync meshes: synchronize meshes between projects
        copick sync segmentations: synchronize segmentations between projects
    """
    logger = get_logger(__name__, debug=debug)

    # Parse arguments
    source_runs_list = parse_list(source_runs) if source_runs else None
    target_runs_dict = parse_mapping(target_runs) if target_runs else None
    voxel_spacings_list = [float(x) for x in parse_list(voxel_spacings)] if voxel_spacings else None
    source_tomo_types_list = parse_list(source_tomo_types) if source_tomo_types else None
    target_tomo_types_dict = parse_mapping(target_tomo_types) if target_tomo_types else None

    # Handle dataportal source configuration
    temp_config_path = None
    if source_dataset_ids:
        dataset_ids = parse_dataset_ids(source_dataset_ids)
        temp_config_path = create_dataportal_config(dataset_ids)
        source_config = temp_config_path
    else:
        source_config = config

    # Load configurations
    import copick

    source_root = copick.from_file(source_config)
    target_root = copick.from_file(target_config)

    try:
        # Perform synchronization
        sync_tomograms(
            source_root=source_root,
            target_root=target_root,
            source_runs=source_runs_list,
            target_runs=target_runs_dict,
            voxel_spacings=voxel_spacings_list,
            source_tomo_types=source_tomo_types_list,
            target_tomo_types=target_tomo_types_dict,
            exist_ok=exist_ok,
            max_workers=max_workers,
            log=log,
            with_links=with_links,
        )

        logger.info("Tomograms synchronization completed successfully.")
    finally:
        # Clean up temporary files
        if temp_config_path and os.path.exists(temp_config_path):
            os.unlink(temp_config_path)


def _source_config(config, source_dataset_ids):
    """The source configuration: ``config``, or a temporary portal configuration for ``source_dataset_ids``."""
    if source_dataset_ids:
        path = create_dataportal_config(parse_dataset_ids(source_dataset_ids))
        return path, path
    return config, None


@sync.command(short_help="Synchronize tilt series between two Copick projects.")
@add_config_option
@click.option(
    "--source-dataset-ids",
    type=str,
    help="Comma-separated list of dataset IDs to use as source from CryoET Data Portal. If provided, --config will be ignored and a temporary dataportal configuration will be created.",
    default="",
    required=False,
)
@click.option(
    "--target-config",
    type=click.Path(exists=True),
    help="Path to the target configuration file.",
    required=True,
    metavar="PATH",
)
@click.option(
    "--source-runs",
    type=str,
    help="Comma-separated list of source run names to synchronize. If not specified, all runs will be synced.",
    default="",
    show_default=True,
)
@click.option(
    "--target-runs",
    type=str,
    help="Comma-separated mapping of source run names to target run names (e.g. 'run1:target1,run2:target2'). If not specified, source run names will be used.",
    default="",
    show_default=True,
)
@click.option(
    "--source-ts-types",
    type=str,
    help="Comma-separated list of source tilt series types to synchronize. If not specified, all tilt series will be synced.",
    default="",
    show_default=True,
)
@click.option(
    "--target-ts-types",
    type=str,
    help="Comma-separated mapping of source tilt series types to target types (e.g. 'raw:original'). If not specified, source types will be used.",
    default="",
    show_default=True,
)
@click.option(
    "--with-alignments/--no-with-alignments",
    is_flag=True,
    help="Also synchronize the alignments of each tilt series.",
    show_default=True,
    default=False,
)
@click.option(
    "--exist-ok/--no-exist-ok",
    is_flag=True,
    help="Allow overwriting existing objects in the target project.",
    show_default=True,
    default=False,
)
@click.option(
    "--max-workers",
    type=int,
    help="Maximum number of worker threads to use for synchronization.",
    default=4,
    show_default=True,
)
@click.option(
    "--log/--no-log",
    is_flag=True,
    help="Enable verbose logging of the synchronization process.",
    show_default=True,
    default=False,
)
@add_debug_option
def tiltseries(
    config,
    source_dataset_ids,
    target_config,
    source_runs,
    target_runs,
    source_ts_types,
    target_ts_types,
    with_alignments,
    exist_ok,
    max_workers,
    log,
    debug,
):
    """Synchronize tilt series between two Copick projects.

    Copies tilt series, images and metadata, from a source Copick project to a target project. The metadata is stored
    with each copy, so tilt series of the CryoET Data Portal (`--source-dataset-ids`) carry their per-image angles,
    dose and CTF in the target. `--with-alignments` copies their alignments too.

    Examples:

        \b
        # Copy the tilt series and alignments of two portal datasets into a local project
        copick sync tiltseries --source-dataset-ids 10445,10446 --target-config local.json --with-alignments

        \b
        # Copy raw tilt series under another type
        copick sync tiltseries -c source.json --target-config target.json --source-ts-types raw \\
            --target-ts-types raw:original

    See Also:

        \b
        copick sync alignments: synchronize alignments between projects
        copick sync tomograms: synchronize tomograms between projects
    """
    logger = get_logger(__name__, debug=debug)
    source_config, temp_config_path = _source_config(config, source_dataset_ids)

    import copick

    source_root = copick.from_file(source_config)
    target_root = copick.from_file(target_config)
    try:
        sync_tilt_series(
            source_root=source_root,
            target_root=target_root,
            source_runs=parse_list(source_runs) if source_runs else None,
            target_runs=parse_mapping(target_runs) if target_runs else None,
            source_ts_types=parse_list(source_ts_types) if source_ts_types else None,
            target_ts_types=parse_mapping(target_ts_types) if target_ts_types else None,
            with_alignments=with_alignments,
            exist_ok=exist_ok,
            max_workers=max_workers,
            log=log,
        )
        logger.info("Tilt series synchronization completed successfully.")
    finally:
        if temp_config_path and os.path.exists(temp_config_path):
            os.unlink(temp_config_path)


@sync.command(short_help="Synchronize alignments between two Copick projects.")
@add_config_option
@click.option(
    "--source-dataset-ids",
    type=str,
    help="Comma-separated list of dataset IDs to use as source from CryoET Data Portal. If provided, --config will be ignored and a temporary dataportal configuration will be created.",
    default="",
    required=False,
)
@click.option(
    "--target-config",
    type=click.Path(exists=True),
    help="Path to the target configuration file.",
    required=True,
    metavar="PATH",
)
@click.option(
    "--source-runs",
    type=str,
    help="Comma-separated list of source run names to synchronize. If not specified, all runs will be synced.",
    default="",
    show_default=True,
)
@click.option(
    "--target-runs",
    type=str,
    help="Comma-separated mapping of source run names to target run names (e.g. 'run1:target1,run2:target2'). If not specified, source run names will be used.",
    default="",
    show_default=True,
)
@click.option(
    "--names",
    type=str,
    help="Comma-separated list of alignment names to synchronize. If not specified, all alignments will be synced.",
    default="",
    show_default=True,
)
@click.option(
    "--target-ts-types",
    type=str,
    help="Comma-separated mapping of source tilt series types to the target types the copies align (e.g. 'raw:original').",
    default="",
    show_default=True,
)
@click.option(
    "--valid-only/--no-valid-only",
    is_flag=True,
    help="Leave out alignments that do not come from their author (e.g. CryoET Data Portal placeholders).",
    show_default=True,
    default=False,
)
@click.option(
    "--exist-ok/--no-exist-ok",
    is_flag=True,
    help="Allow overwriting existing objects in the target project.",
    show_default=True,
    default=False,
)
@click.option(
    "--max-workers",
    type=int,
    help="Maximum number of worker threads to use for synchronization.",
    default=4,
    show_default=True,
)
@click.option(
    "--log/--no-log",
    is_flag=True,
    help="Enable verbose logging of the synchronization process.",
    show_default=True,
    default=False,
)
@add_debug_option
def alignments(
    config,
    source_dataset_ids,
    target_config,
    source_runs,
    target_runs,
    names,
    target_ts_types,
    valid_only,
    exist_ok,
    max_workers,
    log,
    debug,
):
    """Synchronize alignments between two Copick projects.

    Copies alignments from a source Copick project to a target project; the target runs must hold the tilt series
    they align (see `copick sync tiltseries`).

    Examples:

        \b
        # Copy the alignments from their authors of a portal dataset
        copick sync alignments --source-dataset-ids 10445 --target-config local.json --valid-only

    See Also:

        \b
        copick sync tiltseries: synchronize tilt series between projects
        copick sync tomograms: synchronize tomograms between projects
    """
    logger = get_logger(__name__, debug=debug)
    source_config, temp_config_path = _source_config(config, source_dataset_ids)

    import copick

    source_root = copick.from_file(source_config)
    target_root = copick.from_file(target_config)
    try:
        sync_alignments(
            source_root=source_root,
            target_root=target_root,
            source_runs=parse_list(source_runs) if source_runs else None,
            target_runs=parse_mapping(target_runs) if target_runs else None,
            names=parse_list(names) if names else None,
            target_ts_types=parse_mapping(target_ts_types) if target_ts_types else None,
            valid_only=valid_only,
            exist_ok=exist_ok,
            max_workers=max_workers,
            log=log,
        )
        logger.info("Alignments synchronization completed successfully.")
    finally:
        if temp_config_path and os.path.exists(temp_config_path):
            os.unlink(temp_config_path)
