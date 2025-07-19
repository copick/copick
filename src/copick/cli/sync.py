import os

import click

from copick.cli.util import add_config_option, add_debug_option
from copick.ops.sync import sync_meshes, sync_picks, sync_segmentations, sync_tomograms
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


@sync.command(short_help="Synchronize picks between two Copick projects.")
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
    type=str,
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

    This command copies pick annotations from a source Copick project to a target project.
    You can specify which runs and objects to sync, and optionally map source names to
    different target names.

    Examples:

    # Sync all picks from all runs
    copick sync picks -c source_config.json --target-config target_config.json

    # Sync specific runs with name mapping
    copick sync picks -c source_config.json --target-config target_config.json \\
        --source-runs "run1,run2" --target-runs "run1:new_run1,run2:new_run2"

    # Sync specific objects with name mapping
    copick sync picks -c source_config.json --target-config target_config.json \\
        --source-objects "ribosome,membrane" --target-objects "ribosome:ribo,membrane:mem"
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
    type=str,
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

    This command copies mesh data from a source Copick project to a target project.
    You can specify which runs and objects to sync, and optionally map source names to
    different target names.

    Examples:

    # Sync all meshes from all runs
    copick sync meshes -c source_config.json --target-config target_config.json

    # Sync specific runs with name mapping
    copick sync meshes -c source_config.json --target-config target_config.json \\
        --source-runs "run1,run2" --target-runs "run1:new_run1,run2:new_run2"

    # Sync specific objects with name mapping
    copick sync meshes -c source_config.json --target-config target_config.json \\
        --source-objects "ribosome,membrane" --target-objects "ribosome:ribo,membrane:mem"
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
    type=str,
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
    exist_ok,
    max_workers,
    log,
    debug,
):
    """Synchronize segmentations between two Copick projects.

    This command copies segmentation data from a source Copick project to a target project.
    You can specify which runs, voxel spacings, and objects to sync, and optionally map
    source names to different target names.

    Examples:

    # Sync all segmentations from all runs
    copick sync segmentations -c source_config.json --target-config target_config.json

    # Sync specific runs and voxel spacings
    copick sync segmentations -c source_config.json --target-config target_config.json \\
        --source-runs "run1,run2" --voxel-spacings "10.0,20.0"

    # Sync specific objects with name mapping
    copick sync segmentations -c source_config.json --target-config target_config.json \\
        --source-objects "ribosome,membrane" --target-objects "ribosome:ribo,membrane:mem"
    """
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
        # (non-multilabel segmentations require the segmentation name to match a pickable object)
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
    type=str,
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
    max_workers,
    log,
    debug,
):
    """Synchronize tomograms between two Copick projects.

    This command copies tomogram data from a source Copick project to a target project.
    You can specify which runs, voxel spacings, and tomogram types to sync, and optionally
    map source names to different target names.

    Examples:

    # Sync all tomograms from all runs
    copick sync tomograms -c source_config.json --target-config target_config.json

    # Sync specific runs and voxel spacings
    copick sync tomograms -c source_config.json --target-config target_config.json \\
        --source-runs "run1,run2" --voxel-spacings "10.0,20.0"

    # Sync specific tomogram types with name mapping
    copick sync tomograms -c source_config.json --target-config target_config.json \\
        --source-tomo-types "wbp,raw" --target-tomo-types "wbp:filtered,raw:original"
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
        )

        logger.info("Tomograms synchronization completed successfully.")
    finally:
        # Clean up temporary files
        if temp_config_path and os.path.exists(temp_config_path):
            os.unlink(temp_config_path)
