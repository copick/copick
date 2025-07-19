from typing import Any, Dict, List, Optional

from zarr.convenience import copy_store

from copick.models import CopickRoot, CopickRun
from copick.ops.run import map_runs
from copick.util.log import get_logger

logger = get_logger(__name__)


def _sync_picks_worker(
    run: CopickRun,
    target_root: CopickRoot,
    target_run_name: str,
    source_objects: List[str],
    target_objects: Dict[str, str],
    source_users: Optional[List[str]],
    target_users: Optional[Dict[str, str]],
    exist_ok: bool,
    log: bool,
) -> Dict[str, Any]:
    """Worker function for syncing picks from one run to another.

    Args:
        run: The source CopickRun to sync picks from.
        target_root: The target CopickRoot where picks will be synced to.
        target_run_name: The name of the target run in the target root.
        source_objects: List of source object names to sync picks for.
        target_objects: Dictionary mapping source object names to target object names in the target root.
        exist_ok: Whether to overwrite existing picks in the target project.
        log: Whether to log the synchronization process.

    Returns:
        A dictionary with the number of processed picks and any errors encountered during the sync.
    """
    result = {"processed": 0, "errors": []}

    try:
        target_run = target_root.get_run(target_run_name)

        for source_obj in source_objects:
            target_obj = target_objects.get(source_obj, source_obj)

            # Check if target object exists
            if target_root.get_object(target_obj) is None:
                result["errors"].append(f"Target object {target_obj} not found in target root")
                continue

            # Get all picks for this object in the source run
            source_picks = run.get_picks(object_name=source_obj)

            for pick in source_picks:
                try:
                    # Filter by source users if specified
                    if source_users and pick.user_id not in source_users:
                        continue

                    # Map user ID
                    target_user_id = target_users.get(pick.user_id, pick.user_id) if target_users else pick.user_id

                    # Create or get target pick
                    target_pick = target_run.new_picks(
                        object_name=target_obj,
                        user_id=target_user_id,
                        session_id=pick.session_id,
                        exist_ok=exist_ok,
                    )

                    # Copy points
                    target_pick.points = pick.points
                    target_pick.store()

                    result["processed"] += 1

                    if log:
                        logger.info(f"Synced picks {source_obj} -> {target_obj} from {run.name} to {target_run_name}")

                except Exception as e:
                    result["errors"].append(f"Error syncing picks {source_obj} from {run.name}: {str(e)}")

    except Exception as e:
        result["errors"].append(f"Error processing run {run.name}: {str(e)}")

    return result


def _sync_meshes_worker(
    run: CopickRun,
    target_root: CopickRoot,
    target_run_name: str,
    source_objects: List[str],
    target_objects: Dict[str, str],
    source_users: Optional[List[str]],
    target_users: Optional[Dict[str, str]],
    exist_ok: bool,
    log: bool,
) -> Dict[str, Any]:
    """Worker function for syncing meshes from one run to another.

    Args:
        run: The source CopickRun to sync meshes from.
        target_root: The target CopickRoot where meshes will be synced to.
        target_run_name: The name of the target run in the target root.
        source_objects: List of source object names to sync meshes for.
        target_objects: Dictionary mapping source object names to target object names in the target root.
        exist_ok: Whether to overwrite existing meshes in the target project.
        log: Whether to log the synchronization process.

    Returns:
        A dictionary with the number of processed meshes and any errors encountered.
    """
    result = {"processed": 0, "errors": []}

    try:
        target_run = target_root.get_run(target_run_name)

        for source_obj in source_objects:
            target_obj = target_objects.get(source_obj, source_obj)

            # Check if target object exists
            if target_root.get_object(target_obj) is None:
                result["errors"].append(f"Target object {target_obj} not found in target root")
                continue

            # Get all meshes for this object in the source run
            source_meshes = run.get_meshes(object_name=source_obj)

            for mesh in source_meshes:
                try:
                    # Filter by source users if specified
                    if source_users and mesh.user_id not in source_users:
                        continue

                    # Map user ID
                    target_user_id = target_users.get(mesh.user_id, mesh.user_id) if target_users else mesh.user_id

                    # Create or get target mesh
                    target_mesh = target_run.new_mesh(
                        object_name=target_obj,
                        user_id=target_user_id,
                        session_id=mesh.session_id,
                        exist_ok=exist_ok,
                    )

                    # Copy mesh data
                    target_mesh.mesh = mesh.mesh
                    target_mesh.store()

                    result["processed"] += 1

                    if log:
                        logger.info(f"Synced mesh {source_obj} -> {target_obj} from {run.name} to {target_run_name}")

                except Exception as e:
                    result["errors"].append(f"Error syncing mesh {source_obj} from {run.name}: {str(e)}")

    except Exception as e:
        result["errors"].append(f"Error processing run {run.name}: {str(e)}")

    return result


def _sync_segmentations_worker(
    run: CopickRun,
    target_root: CopickRoot,
    target_run_name: str,
    voxel_spacings: List[float],
    source_names: Optional[List[str]],
    target_names: Dict[str, str],
    source_users: Optional[List[str]],
    target_users: Optional[Dict[str, str]],
    exist_ok: bool,
    log: bool,
) -> Dict[str, Any]:
    """Worker function for syncing segmentations from one run to another.

    Args:
        run: The source CopickRun to sync segmentations from.
        target_root: The target CopickRoot where segmentations will be synced to.
        target_run_name: The name of the target run in the target root.
        voxel_spacings: List of voxel spacings to consider for synchronization. If None, all voxel spacings are used.
        source_names: List of source segmentation names to sync. If None, all segmentations are synced.
        target_names: Dictionary mapping source segmentation names to target names.
        source_users: List of source user IDs to sync. If None, all users are synced.
        target_users: Dictionary mapping source user IDs to target user IDs.
        exist_ok: Whether to overwrite existing segmentations in the target project.
        log: Whether to log the synchronization process.

    Returns:
        A dictionary with the number of processed segmentations and any errors encountered.
    """
    result = {"processed": 0, "errors": []}

    try:
        target_run = target_root.get_run(target_run_name)
        source_segmentations = run.get_segmentations(voxel_size=voxel_spacings)

        for segmentation in source_segmentations:
            try:
                # Filter by source names if specified
                seg_name = getattr(segmentation, "name", None)
                if source_names is not None and seg_name and seg_name not in source_names:
                    continue

                # Filter by source users if specified
                if source_users and segmentation.user_id not in source_users:
                    continue

                # Map user ID
                target_user_id = (
                    target_users.get(segmentation.user_id, segmentation.user_id)
                    if target_users
                    else segmentation.user_id
                )

                # Get target name
                target_name = target_names.get(seg_name, seg_name) if seg_name else None

                # Create or get target segmentation
                target_seg = target_run.new_segmentation(
                    name=target_name,
                    user_id=target_user_id,
                    session_id=segmentation.session_id,
                    voxel_size=segmentation.voxel_size,
                    is_multilabel=segmentation.is_multilabel,
                    exist_ok=exist_ok,
                )

                # Copy segmentation data
                if_exists = "replace" if exist_ok else "raise"
                src = segmentation.zarr()
                trg = target_seg.zarr()
                copy_store(src, trg, if_exists=if_exists)

                result["processed"] += 1

                if log:
                    logger.info(
                        f"Synced segmentation {seg_name} from {run.name} to {target_run_name} at voxel size {segmentation.voxel_size}",
                    )

            except Exception as e:
                result["errors"].append(f"Error syncing segmentation from {run.name}: {str(e)}")

    except Exception as e:
        result["errors"].append(f"Error processing run {run.name}: {str(e)}")

    return result


def _sync_tomograms_worker(
    run: CopickRun,
    target_root: CopickRoot,
    target_run_name: str,
    voxel_spacings: List[float],
    source_tomo_types: List[str],
    target_tomo_types: Dict[str, str],
    exist_ok: bool,
    log: bool,
) -> Dict[str, Any]:
    """Worker function for syncing tomograms from one run to another.

    Args:
        run: The source CopickRun to sync tomograms from.
        target_root: The target CopickRoot where tomograms will be synced to.
        target_run_name: The name of the target run in the target root.
        voxel_spacings: List of voxel spacings to consider for synchronization. If None, all voxel spacings are used.
        source_tomo_types: List of source tomogram types to sync. If None, all tomogram types are synced.
        target_tomo_types: Dictionary mapping source tomogram types to target types in the target root.
        exist_ok: Whether to overwrite existing tomograms in the target project.
        log: Whether to log the synchronization process.

    Returns:
        A dictionary with the number of processed tomograms and any errors encountered.
    """
    result = {"processed": 0, "errors": []}

    try:
        target_run = target_root.get_run(target_run_name)

        if voxel_spacings is None:
            voxel_spacings = [vs.voxel_size for vs in run.voxel_spacings]

        for voxel_size in voxel_spacings:
            try:
                source_voxel_spacing = run.get_voxel_spacing(voxel_size)
                target_voxel_spacing = target_run.new_voxel_spacing(voxel_size, exist_ok=True)

                if source_voxel_spacing is None:
                    result["errors"].append(f"Source voxel spacing {voxel_size} not found in run {run.name}")
                    continue

                if target_voxel_spacing is None:
                    result["errors"].append(f"Target voxel spacing {voxel_size} not found in run {target_run_name}")
                    continue

                if source_tomo_types is None:
                    source_tomo_types = [tomo.tomo_type for tomo in source_voxel_spacing.tomograms]

                for source_tomo_type in source_tomo_types:
                    target_tomo_type = target_tomo_types.get(source_tomo_type, source_tomo_type)

                    try:
                        source_tomogram = source_voxel_spacing.get_tomograms(source_tomo_type)
                        if len(source_tomogram) == 0:
                            result["errors"].append(f"Source tomogram {source_tomo_type} not found in run {run.name}")
                            continue
                        else:
                            source_tomogram = source_tomogram[0]

                        # Create or get target tomogram
                        target_tomogram = target_voxel_spacing.new_tomogram(
                            tomo_type=target_tomo_type,
                            exist_ok=exist_ok,
                        )

                        # Copy tomogram data
                        if_exists = "replace" if exist_ok else "raise"
                        src = source_tomogram.zarr()
                        trg = target_tomogram.zarr()
                        copy_store(src, trg, if_exists=if_exists)

                        result["processed"] += 1

                        if log:
                            logger.info(
                                f"Synced tomogram {source_tomo_type} -> {target_tomo_type} from {run.name} to {target_run_name} at voxel size {voxel_size}",
                            )

                    except Exception as e:
                        result["errors"].append(f"Error syncing tomogram {source_tomo_type} from {run.name}: {str(e)}")

            except Exception as e:
                result["errors"].append(f"Error processing voxel spacing {voxel_size} in run {run.name}: {str(e)}")

    except Exception as e:
        result["errors"].append(f"Error processing run {run.name}: {str(e)}")

    return result


def sync_picks(
    source_root: CopickRoot,
    target_root: CopickRoot,
    source_runs: Optional[List[str]] = None,
    target_runs: Optional[Dict[str, str]] = None,
    source_objects: Optional[List[str]] = None,
    target_objects: Optional[Dict[str, str]] = None,
    source_users: Optional[List[str]] = None,
    target_users: Optional[Dict[str, str]] = None,
    exist_ok: bool = False,
    max_workers: int = 4,
    log: bool = False,
) -> None:
    """
    Synchronize picks between two Copick projects.

    Args:
        source_root: The source Copick project root.
        target_root: The target Copick project root.
        source_runs: The list of source run names to synchronize.
        target_runs: A dictionary mapping source run names to target run names.
        source_objects: The list of source object types to synchronize.
        target_objects: The dictionary mapping source object types to target types.
        source_users: The list of source user IDs to synchronize. If None, all users are synced.
        target_users: The dictionary mapping source user IDs to target user IDs.
        exist_ok: Whether to overwrite existing picks in the target project.
        max_workers: The maximum number of worker threads to use for synchronization.
        log: Whether to log the synchronization process.

    """
    # Get runs to process
    if source_runs is None:
        source_runs = [run.name for run in source_root.runs]

    # Set up run name mapping
    if target_runs is None:
        target_runs = {run: run for run in source_runs}

    # Get objects to process
    if source_objects is None:
        source_objects = [obj.name for obj in source_root.config.pickable_objects]

    # Set up object name mapping
    if target_objects is None:
        target_objects = {obj: obj for obj in source_objects}

    # Create target runs if they don't exist
    for source_run_name in source_runs:
        target_run_name = target_runs[source_run_name]
        target_root.new_run(target_run_name, exist_ok=True)
        if log:
            logger.info(f"Ensured target run {target_run_name} exists")

    # Create run args for parallel processing
    run_args = [
        {
            "target_root": target_root,
            "target_run_name": target_runs[run_name],
            "source_objects": source_objects,
            "target_objects": target_objects,
            "source_users": source_users,
            "target_users": target_users,
            "exist_ok": exist_ok,
            "log": log,
        }
        for run_name in source_runs
    ]

    # Execute in parallel
    results = map_runs(
        callback=_sync_picks_worker,
        root=source_root,
        runs=source_runs,
        workers=max_workers,
        run_args=run_args,
        show_progress=log,
        task_desc="Syncing picks",
    )

    # Report results
    from copick.ops.run import report_results

    report_results(results, len(source_runs), logger)


def sync_segmentations(
    source_root: CopickRoot,
    target_root: CopickRoot,
    source_runs: Optional[List[str]] = None,
    target_runs: Optional[Dict[str, str]] = None,
    voxel_spacings: Optional[List[float]] = None,
    source_names: Optional[List[str]] = None,
    target_names: Optional[Dict[str, str]] = None,
    source_users: Optional[List[str]] = None,
    target_users: Optional[Dict[str, str]] = None,
    exist_ok: bool = False,
    max_workers: int = 4,
    log: bool = False,
) -> None:
    """
    Synchronize segmentations between two Copick projects.

    Args:
        source_root: The source Copick project root.
        target_root: The target Copick project root.
        source_runs: The list of source run names to synchronize.
        target_runs: A dictionary mapping source run names to target run names.
        voxel_spacings: The voxel spacings to consider for synchronization.
        source_names: The list of source segmentation names to synchronize. If None, all segmentations are synced.
        target_names: The dictionary mapping source segmentation names to target names.
        source_users: The list of source user IDs to synchronize. If None, all users are synced.
        target_users: The dictionary mapping source user IDs to target user IDs.
        exist_ok: Whether to overwrite existing segmentations in the target project.
        max_workers: The maximum number of worker threads to use for synchronization.
        log: Whether to log the synchronization process.

    """
    # Get runs to process
    if source_runs is None:
        source_runs = [run.name for run in source_root.runs]

    # Set up run name mapping
    if target_runs is None:
        target_runs = {run: run for run in source_runs}

    # Set up name mapping (source_names can be None to sync all segmentations)
    if target_names is None:
        target_names = {}

    # Create target runs if they don't exist
    for source_run_name in source_runs:
        target_run_name = target_runs[source_run_name]
        target_root.new_run(target_run_name, exist_ok=True)
        if log:
            logger.info(f"Ensured target run {target_run_name} exists")

    # Create run args for parallel processing
    run_args = [
        {
            "target_root": target_root,
            "target_run_name": target_runs[run_name],
            "voxel_spacings": voxel_spacings,
            "source_names": source_names,
            "target_names": target_names,
            "source_users": source_users,
            "target_users": target_users,
            "exist_ok": exist_ok,
            "log": log,
        }
        for run_name in source_runs
    ]

    # Execute in parallel
    results = map_runs(
        callback=_sync_segmentations_worker,
        root=source_root,
        runs=source_runs,
        workers=max_workers,
        run_args=run_args,
        show_progress=log,
        task_desc="Syncing segmentations",
    )

    # Report results
    from copick.ops.run import report_results

    report_results(results, len(source_runs), logger)


def sync_meshes(
    source_root: CopickRoot,
    target_root: CopickRoot,
    source_runs: Optional[List[str]] = None,
    target_runs: Optional[Dict[str, str]] = None,
    source_objects: Optional[List[str]] = None,
    target_objects: Optional[Dict[str, str]] = None,
    source_users: Optional[List[str]] = None,
    target_users: Optional[Dict[str, str]] = None,
    exist_ok: bool = False,
    max_workers: int = 4,
    log: bool = False,
) -> None:
    """
    Synchronize meshes between two Copick projects.

    Args:
        source_root: The source Copick project root.
        target_root: The target Copick project root.
        source_runs: The list of source run names to synchronize.
        target_runs: A dictionary mapping source run names to target run names.
        source_objects: The list of source object types to synchronize.
        target_objects: The dictionary mapping source object types to target types.
        source_users: The list of source user IDs to synchronize. If None, all users are synced.
        target_users: The dictionary mapping source user IDs to target user IDs.
        exist_ok: Whether to overwrite existing meshes in the target project.
        max_workers: The maximum number of worker threads to use for synchronization.
        log: Whether to log the synchronization process.

    """
    # Get runs to process
    if source_runs is None:
        source_runs = [run.name for run in source_root.runs]

    # Set up run name mapping
    if target_runs is None:
        target_runs = {run: run for run in source_runs}

    # Get objects to process
    if source_objects is None:
        source_objects = [obj.name for obj in source_root.config.pickable_objects]

    # Set up object name mapping
    if target_objects is None:
        target_objects = {obj: obj for obj in source_objects}

    # Create target runs if they don't exist
    for source_run_name in source_runs:
        target_run_name = target_runs[source_run_name]
        target_root.new_run(target_run_name, exist_ok=True)
        if log:
            logger.info(f"Ensured target run {target_run_name} exists")

    # Create run args for parallel processing
    run_args = [
        {
            "target_root": target_root,
            "target_run_name": target_runs[run_name],
            "source_objects": source_objects,
            "target_objects": target_objects,
            "source_users": source_users,
            "target_users": target_users,
            "exist_ok": exist_ok,
            "log": log,
        }
        for run_name in source_runs
    ]

    # Execute in parallel
    results = map_runs(
        callback=_sync_meshes_worker,
        root=source_root,
        runs=source_runs,
        workers=max_workers,
        run_args=run_args,
        show_progress=log,
        task_desc="Syncing meshes",
    )

    # Report results
    from copick.ops.run import report_results

    report_results(results, len(source_runs), logger)


def sync_tomograms(
    source_root: CopickRoot,
    target_root: CopickRoot,
    source_runs: Optional[List[str]] = None,
    target_runs: Optional[Dict[str, str]] = None,
    voxel_spacings: Optional[List[float]] = None,
    source_tomo_types: Optional[List[str]] = None,
    target_tomo_types: Optional[Dict[str, str]] = None,
    exist_ok: bool = False,
    max_workers: int = 4,
    log: bool = False,
) -> None:
    """
    Synchronize tomograms between two Copick projects.

    Args:
        source_root: The source Copick project root.
        target_root: The target Copick project root.
        source_runs: The list of source run names to synchronize.
        target_runs: A dictionary mapping source run names to target run names.
        voxel_spacings: The voxel spacings to consider for synchronization.
        source_tomo_types: The list of source tomogram types to synchronize.
        target_tomo_types: The dictionary mapping source tomogram types to target types.
        exist_ok: Whether to overwrite existing tomograms in the target project.
        max_workers: The maximum number of worker threads to use for synchronization.
        log: Whether to log the synchronization process.

    """
    # Get runs to process
    if source_runs is None:
        source_runs = [run.name for run in source_root.runs]

    # Set up run name mapping
    if target_runs is None:
        target_runs = {run: run for run in source_runs}

    if target_tomo_types is None:
        target_tomo_types = {}

    # Create target runs if they don't exist
    for source_run_name in source_runs:
        target_run_name = target_runs[source_run_name]
        target_root.new_run(target_run_name, exist_ok=True)
        if log:
            logger.info(f"Ensured target run {target_run_name} exists")

    # Create run args for parallel processing
    run_args = [
        {
            "target_root": target_root,
            "target_run_name": target_runs[run_name],
            "voxel_spacings": voxel_spacings,
            "source_tomo_types": source_tomo_types,
            "target_tomo_types": target_tomo_types,
            "exist_ok": exist_ok,
            "log": log,
        }
        for run_name in source_runs
    ]

    # Execute in parallel
    results = map_runs(
        callback=_sync_tomograms_worker,
        root=source_root,
        runs=source_runs,
        workers=max_workers,
        run_args=run_args,
        show_progress=log,
        task_desc="Syncing tomograms",
    )

    # Report results
    from copick.ops.run import report_results

    report_results(results, len(source_runs), logger)
