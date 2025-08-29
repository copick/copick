from collections import defaultdict
from typing import Dict, Iterable, Optional, Union

from copick.models import CopickRoot, CopickRun
from copick.ops.get import get_meshes, get_picks, get_segmentations


def picks_stats(
    root: Union[str, CopickRoot],
    runs: Union[str, CopickRun, Iterable[str], Iterable[CopickRun], None] = None,
    user_id: Union[str, Iterable[str], None] = None,
    session_id: Union[str, Iterable[str], None] = None,
    object_name: Union[str, Iterable[str], None] = None,
    parallel: bool = False,
    workers: Optional[int] = 8,
    show_progress: bool = True,
) -> Dict[str, Union[int, Dict[str, int]]]:
    """Generate statistics for picks in a Copick project.

    Args:
        root: The Copick project root.
        runs: The runs to query picks from. If `None`, query all runs.
        user_id: The user ID of the picks. If `None`, query all users.
        session_id: The session ID of the picks. If `None`, query all sessions.
        object_name: The pickable object of the picks. If `None`, query all picks.
        parallel: Whether to query picks in parallel. Default is `False`.
        workers: The number of workers to use. Default is `8`.
        show_progress: Whether to show progress. Default is `True`.

    Returns:
        A dictionary containing total pick count and distribution statistics.
    """
    picks_list = get_picks(
        root=root,
        runs=runs,
        user_id=user_id,
        session_id=session_id,
        object_name=object_name,
        parallel=parallel,
        workers=workers,
        show_progress=show_progress,
    )

    if not picks_list:
        return {
            "total_picks": 0,
            "total_pick_files": 0,
            "distribution_by_run": {},
            "distribution_by_user": {},
            "distribution_by_session": {},
            "distribution_by_object": {},
        }

    # Count individual picks
    total_individual_picks = 0
    distribution_by_run = defaultdict(int)
    distribution_by_user = defaultdict(int)
    distribution_by_session = defaultdict(int)
    distribution_by_object = defaultdict(int)

    for picks_file in picks_list:
        pick_count = len(picks_file.points) if picks_file.points else 0
        total_individual_picks += pick_count

        run_name = picks_file.run.name
        distribution_by_run[run_name] += pick_count
        distribution_by_user[picks_file.user_id] += pick_count
        distribution_by_session[picks_file.session_id] += pick_count
        distribution_by_object[picks_file.pickable_object_name] += pick_count

    return {
        "total_picks": total_individual_picks,
        "total_pick_files": len(picks_list),
        "distribution_by_run": dict(distribution_by_run),
        "distribution_by_user": dict(distribution_by_user),
        "distribution_by_session": dict(distribution_by_session),
        "distribution_by_object": dict(distribution_by_object),
    }


def meshes_stats(
    root: Union[str, CopickRoot],
    runs: Union[str, CopickRun, Iterable[str], Iterable[CopickRun], None] = None,
    user_id: Union[str, Iterable[str], None] = None,
    session_id: Union[str, Iterable[str], None] = None,
    object_name: Union[str, Iterable[str], None] = None,
    parallel: bool = False,
    workers: Optional[int] = 8,
    show_progress: bool = True,
) -> Dict[str, Union[int, Dict[str, int]]]:
    """Generate statistics for meshes in a Copick project.

    Args:
        root: The Copick project root.
        runs: The runs to query meshes from. If `None`, query all runs.
        user_id: The user ID of the meshes. If `None`, query all users.
        session_id: The session ID of the meshes. If `None`, query all sessions.
        object_name: The pickable object of the meshes. If `None`, query all meshes.
        parallel: Whether to query meshes in parallel. Default is `False`.
        workers: The number of workers to use. Default is `8`.
        show_progress: Whether to show progress. Default is `True`.

    Returns:
        A dictionary containing mesh count and frequency statistics.
    """
    meshes_list = get_meshes(
        root=root,
        runs=runs,
        user_id=user_id,
        session_id=session_id,
        object_name=object_name,
        parallel=parallel,
        workers=workers,
        show_progress=show_progress,
    )

    if not meshes_list:
        return {
            "total_meshes": 0,
            "distribution_by_user": {},
            "distribution_by_session": {},
            "distribution_by_object": {},
            "session_user_object_combinations": {},
        }

    # Track distributions and combinations
    distribution_by_user = defaultdict(int)
    distribution_by_session = defaultdict(int)
    distribution_by_object = defaultdict(int)
    session_user_object_freq = defaultdict(int)

    for mesh in meshes_list:
        distribution_by_user[mesh.user_id] += 1
        distribution_by_session[mesh.session_id] += 1
        distribution_by_object[mesh.pickable_object_name] += 1

        combo_key = f"{mesh.session_id}_{mesh.user_id}_{mesh.pickable_object_name}"
        session_user_object_freq[combo_key] += 1

    return {
        "total_meshes": len(meshes_list),
        "distribution_by_user": dict(distribution_by_user),
        "distribution_by_session": dict(distribution_by_session),
        "distribution_by_object": dict(distribution_by_object),
        "session_user_object_combinations": dict(session_user_object_freq),
    }


def segmentations_stats(
    root: Union[str, CopickRoot],
    runs: Union[str, CopickRun, Iterable[str], Iterable[CopickRun], None] = None,
    user_id: Union[str, Iterable[str], None] = None,
    session_id: Union[str, Iterable[str], None] = None,
    is_multilabel: bool = None,
    name: Union[str, Iterable[str], None] = None,
    voxel_size: Union[float, Iterable[float], None] = None,
    parallel: bool = False,
    workers: Optional[int] = 8,
    show_progress: bool = True,
) -> Dict[str, Union[int, Dict[str, int]]]:
    """Generate statistics for segmentations in a Copick project.

    Args:
        root: The Copick project root.
        runs: The runs to query segmentations from. If `None`, query all runs.
        user_id: The user ID of the segmentations. If `None`, query all users.
        session_id: The session ID of the segmentations. If `None`, query all sessions.
        is_multilabel: Whether the segmentations are multilabel. If `None`, query all segmentations.
        name: The name of the segmentation. If `None`, query all segmentations.
        voxel_size: The voxel size of the segmentation. If `None`, query all segmentations.
        parallel: Whether to query segmentations in parallel. Default is `False`.
        workers: The number of workers to use. Default is `8`.
        show_progress: Whether to show progress. Default is `True`.

    Returns:
        A dictionary containing segmentation count and frequency statistics.
    """
    segmentations_list = get_segmentations(
        root=root,
        runs=runs,
        user_id=user_id,
        session_id=session_id,
        is_multilabel=is_multilabel,
        name=name,
        voxel_size=voxel_size,
        parallel=parallel,
        workers=workers,
        show_progress=show_progress,
    )

    if not segmentations_list:
        return {
            "total_segmentations": 0,
            "distribution_by_user": {},
            "distribution_by_session": {},
            "distribution_by_name": {},
            "distribution_by_voxel_size": {},
            "distribution_by_multilabel": {},
            "session_user_voxelspacing_multilabel_combinations": {},
        }

    # Track distributions and combinations
    distribution_by_user = defaultdict(int)
    distribution_by_session = defaultdict(int)
    distribution_by_name = defaultdict(int)
    distribution_by_voxel_size = defaultdict(int)
    distribution_by_multilabel = defaultdict(int)
    combo_freq = defaultdict(int)

    for seg in segmentations_list:
        distribution_by_user[seg.user_id] += 1
        distribution_by_session[seg.session_id] += 1
        distribution_by_name[seg.name] += 1
        distribution_by_voxel_size[seg.voxel_size] += 1
        distribution_by_multilabel[str(seg.is_multilabel)] += 1

        combo_key = f"{seg.session_id}_{seg.user_id}_{seg.name}_{seg.voxel_size}_{seg.is_multilabel}"
        combo_freq[combo_key] += 1

    return {
        "total_segmentations": len(segmentations_list),
        "distribution_by_user": dict(distribution_by_user),
        "distribution_by_session": dict(distribution_by_session),
        "distribution_by_name": dict(distribution_by_name),
        "distribution_by_voxel_size": dict(distribution_by_voxel_size),
        "distribution_by_multilabel": dict(distribution_by_multilabel),
        "session_user_voxelspacing_multilabel_combinations": dict(combo_freq),
    }
