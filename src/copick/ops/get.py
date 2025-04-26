from typing import Iterable, List, Optional, Union

from copick.models import (
    CopickFeatures,
    CopickMesh,
    CopickPicks,
    CopickRoot,
    CopickRun,
    CopickSegmentation,
    CopickTomogram,
    CopickVoxelSpacing,
)
from copick.ops.open import from_file
from copick.ops.run import map_runs


def _segmentation_query(
    run: CopickRun,
    user_id: Union[str, Iterable[str], None] = None,
    session_id: Union[str, Iterable[str], None] = None,
    is_multilabel: bool = None,
    name: Union[str, Iterable[str], None] = None,
    voxel_size: Union[float, Iterable[float], None] = None,
) -> List[CopickSegmentation]:
    return run.get_segmentations(
        user_id=user_id,
        session_id=session_id,
        is_multilabel=is_multilabel,
        name=name,
        voxel_size=voxel_size,
    )


def get_segmentations(
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
) -> Union[List[CopickSegmentation], None]:
    """Query segmentations from a Copick project.

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
    """

    if isinstance(root, str):
        root = from_file(root)

    if runs is None:
        runs = root.runs
    elif isinstance(runs, str):
        runs = [root.get_run(name=runs)]
    elif isinstance(runs, CopickRun):
        runs = [runs]

    if parallel:
        res = map_runs(
            _segmentation_query,
            root,
            runs,
            workers=workers,
            user_id=user_id,
            session_id=session_id,
            is_multilabel=is_multilabel,
            name=name,
            voxel_size=voxel_size,
            show_progress=show_progress,
        )
        return [seg for seglist in res.values() for seg in seglist]
    else:
        res = map_runs(
            _segmentation_query,
            root,
            runs,
            workers=1,
            user_id=user_id,
            session_id=session_id,
            is_multilabel=is_multilabel,
            name=name,
            voxel_size=voxel_size,
            show_progress=show_progress,
        )
        return [seg for seglist in res.values() for seg in seglist]


def _mesh_query(
    run: CopickRun,
    user_id: Union[str, Iterable[str], None] = None,
    session_id: Union[str, Iterable[str], None] = None,
    object_name: Union[str, Iterable[str], None] = None,
) -> List[CopickMesh]:
    return run.get_meshes(user_id=user_id, session_id=session_id, object_name=object_name)


def get_meshes(
    root: Union[str, CopickRoot],
    runs: Union[str, CopickRun, Iterable[str], Iterable[CopickRun], None] = None,
    user_id: Union[str, Iterable[str], None] = None,
    session_id: Union[str, Iterable[str], None] = None,
    object_name: Union[str, Iterable[str], None] = None,
    parallel: bool = False,
    workers: Optional[int] = 8,
    show_progress: bool = True,
) -> Union[List[CopickMesh], None]:
    """Query meshes from a Copick project.

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
        A list of meshes.
    """

    if isinstance(root, str):
        root = from_file(root)

    if runs is None:
        runs = root.runs
    elif isinstance(runs, str):
        runs = [root.get_run(name=runs)]
    elif isinstance(runs, CopickRun):
        runs = [runs]

    if parallel:
        res = map_runs(
            _mesh_query,
            root,
            runs,
            workers=workers,
            user_id=user_id,
            session_id=session_id,
            object_name=object_name,
            show_progress=show_progress,
        )
        return [mesh for meshlist in res.values() for mesh in meshlist]
    else:
        return [mesh for run in runs for mesh in _mesh_query(run, user_id, session_id, object_name)]


def _pick_query(
    run: CopickRun,
    user_id: Union[str, Iterable[str], None] = None,
    session_id: Union[str, Iterable[str], None] = None,
    object_name: Union[str, Iterable[str], None] = None,
) -> List[CopickPicks]:
    return run.get_picks(user_id=user_id, session_id=session_id, object_name=object_name)


def get_picks(
    root: Union[str, CopickRoot],
    runs: Union[str, CopickRun, Iterable[str], Iterable[CopickRun], None] = None,
    user_id: Union[str, Iterable[str], None] = None,
    session_id: Union[str, Iterable[str], None] = None,
    object_name: Union[str, Iterable[str], None] = None,
    parallel: bool = False,
    workers: Optional[int] = 8,
    show_progress: bool = True,
) -> Union[List[CopickPicks], None]:
    """Query picks from a Copick project.

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
        A list of picks.
    """

    if isinstance(root, str):
        root = from_file(root)

    if runs is None:
        runs = root.runs
    elif isinstance(runs, str):
        runs = [root.get_run(name=runs)]
    elif isinstance(runs, CopickRun):
        runs = [runs]

    if parallel:
        res = map_runs(
            _pick_query,
            root,
            runs,
            workers=workers,
            user_id=user_id,
            session_id=session_id,
            object_name=object_name,
            show_progress=show_progress,
        )
        return [pick for picklist in res.values() for pick in picklist]
    else:
        return [pick for run in runs for pick in _pick_query(run, user_id, session_id, object_name)]


def _voxelspacing_query(
    run: CopickRun,
    voxel_size: Union[float, Iterable[float], None] = None,
) -> List[CopickVoxelSpacing]:
    if voxel_size is None:
        return run.voxel_spacings
    elif isinstance(voxel_size, float):
        return [run.get_voxel_spacing(voxel_size)]
    else:
        return [run.get_voxel_spacing(voxel_size=vs) for vs in voxel_size]


def get_voxelspacings(
    root: Union[str, CopickRoot],
    runs: Union[str, CopickRun, Iterable[str], Iterable[CopickRun], None] = None,
    voxel_size: Union[float, Iterable[float], None] = None,
    parallel: bool = False,
    workers: Optional[int] = 8,
    show_progress: bool = True,
) -> Union[List[CopickVoxelSpacing], None]:
    """Query voxel spacings from a Copick project.

    Args:
        root: The Copick project root.
        runs: The runs to query voxel spacings from. If `None`, query all runs.
        voxel_size: The voxel size of the voxel spacings. If `None`, query all voxel spacings.
        parallel: Whether to query voxel spacings in parallel. Default is `False`.
        workers: The number of workers to use. Default is `8`.
        show_progress: Whether to show progress. Default is `True`.

    Returns:
        A list of voxel spacings.
    """

    if isinstance(root, str):
        root = from_file(root)

    if runs is None:
        runs = root.runs
    elif isinstance(runs, str):
        runs = [root.get_run(name=runs)]
    elif isinstance(runs, CopickRun):
        runs = [runs]

    if parallel:
        res = map_runs(
            _voxelspacing_query,
            root,
            runs,
            workers=workers,
            voxel_size=voxel_size,
            show_progress=show_progress,
        )
        return [vs for vslist in res.values() for vs in vslist]
    else:
        return [vs for run in runs for vs in _voxelspacing_query(run, voxel_size)]


def _tomo_query(
    run: CopickRun,
    voxel_size: Union[float, Iterable[float], None] = None,
    tomo_type: Union[str, Iterable[str], None] = None,
) -> List[CopickTomogram]:
    tomos = []
    for vs in _voxelspacing_query(run, voxel_size):
        if tomo_type is None:
            tomos.extend(vs.tomograms)
        elif isinstance(tomo_type, str):
            t = vs.get_tomogram(tomo_type)
            tomos.extend([t] if t is not None else [])
        else:
            tomos.extend([vs.get_tomogram(tomo_type=t) for t in tomo_type])

    return tomos


def get_tomograms(
    root: Union[str, CopickRoot],
    runs: Union[str, CopickRun, Iterable[str], Iterable[CopickRun], None] = None,
    voxel_size: Union[float, Iterable[float], None] = None,
    tomo_type: Union[str, Iterable[str], None] = None,
    parallel: bool = False,
    workers: Optional[int] = 8,
    show_progress: bool = True,
) -> List[CopickTomogram]:
    """Query tomograms from a Copick project.

    Args:
        root: The Copick project root.
        runs: The runs to query tomograms from. If `None`, query all runs.
        voxel_size: The voxel size of the tomograms. If `None`, query all tomograms.
        tomo_type: The type of the tomograms. If `None`, query all tomograms.
        parallel: Whether to query tomograms in parallel. Default is `False`.
        workers: The number of workers to use. Default is `8`.
        show_progress: Whether to show progress. Default is `True`.

    Returns:
        A list of tomograms.
    """

    if isinstance(root, str):
        root = from_file(root)

    if runs is None:
        runs = root.runs
    elif isinstance(runs, str):
        runs = [root.get_run(name=runs)]
    elif isinstance(runs, CopickRun):
        runs = [runs]

    if parallel:
        res = map_runs(
            _tomo_query,
            root,
            runs,
            workers=workers,
            voxel_size=voxel_size,
            tomo_type=tomo_type,
            show_progress=show_progress,
        )
        return [tomo for tomolist in res.values() for tomo in tomolist]
    else:
        return [tomo for run in runs for tomo in _tomo_query(run, voxel_size, tomo_type)]


def _features_query(
    run: CopickRun,
    voxel_size: Union[float, Iterable[float], None] = None,
    tomo_type: Union[str, Iterable[str], None] = None,
    feature_type: Union[str, Iterable[str], None] = None,
) -> List[CopickFeatures]:
    features = []
    for tomo in _tomo_query(run, voxel_size, tomo_type):
        if feature_type is None:
            features.extend(tomo.features)
        elif isinstance(feature_type, str):
            f = tomo.get_features(feature_type)
            features.extend([f] if f is not None else [])
        else:
            features.extend([tomo.get_features(feature_type=f) for f in feature_type])

    return features


def get_features(
    root: Union[str, CopickRoot],
    runs: Union[str, CopickRun, Iterable[str], Iterable[CopickRun], None] = None,
    voxel_size: Union[float, Iterable[float], None] = None,
    tomo_type: Union[str, Iterable[str], None] = None,
    feature_type: Union[str, Iterable[str], None] = None,
    parallel: bool = False,
    workers: Optional[int] = 8,
    show_progress: bool = True,
) -> List[CopickFeatures]:
    """Query features from a Copick project.

    Args:
        root: The Copick project root.
        runs: The runs to query features from. If `None`, query all runs.
        voxel_size: The voxel size of the features. If `None`, query all features.
        tomo_type: The type of the tomograms. If `None`, query all features.
        feature_type: The type of the features. If `None`, query all features.
        parallel: Whether to query features in parallel. Default is `False`.
        workers: The number of workers to use. Default is `8`.
        show_progress: Whether to show progress. Default is `True`.

    Returns:
        A list of features.
    """

    if isinstance(root, str):
        root = from_file(root)

    if runs is None:
        runs = root.runs
    elif isinstance(runs, str):
        runs = [root.get_run(name=runs)]
    elif isinstance(runs, CopickRun):
        runs = [runs]

    if parallel:
        res = map_runs(
            _features_query,
            root,
            runs,
            workers=workers,
            voxel_size=voxel_size,
            tomo_type=tomo_type,
            feature_type=feature_type,
            show_progress=show_progress,
        )
        return [feat for featlist in res.values() for feat in featlist]
    else:
        return [feat for run in runs for feat in _features_query(run, voxel_size, tomo_type, feature_type)]


def get_runs(
    root: Union[str, CopickRoot],
    names: Union[str, Iterable[str], None] = None,
) -> List[CopickRun]:
    """Query runs from a Copick project.

    Args:
        root: The Copick project root.


    Returns:
        A list of runs.
    """

    if isinstance(root, str):
        root = from_file(root)

    if names is None:
        return root.runs
    elif isinstance(names, str):
        return [root.get_run(name=names)]
    else:
        return [root.get_run(name=name) for name in names]
