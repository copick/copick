import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import copick
from copick.impl.cryoet_data_portal import (
    CopickFeaturesCDP,
    CopickMeshCDP,
    CopickPicksCDP,
    CopickRootCDP,
    CopickSegmentationCDP,
    CopickTomogramCDP,
)
from copick.impl.filesystem import (
    CopickFeaturesFSSpec,
    CopickMeshFSSpec,
    CopickPicksFSSpec,
    CopickRootFSSpec,
    CopickSegmentationFSSpec,
    CopickTomogramFSSpec,
)
from copick.models import CopickFeatures, CopickMesh, CopickPicks, CopickRun, CopickSegmentation, CopickTomogram
from copick.ops.run import map_runs, report_results
from copick.util.log import get_logger
from copick.util.uri import resolve_copick_objects

logger = get_logger(__name__)


def _get_file_path(obj: Union[CopickPicks, CopickMesh, CopickSegmentation, CopickTomogram, CopickFeatures]) -> str:
    """Extract the filesystem path from a copick object.

    For FSSpec objects, returns the path property.
    For CDP objects, returns the overlay path if writable, or raises an error if read-only
    (since data on the portal cannot be symlinked).

    Args:
        obj: A copick object (picks, mesh, segmentation, tomogram, or features).

    Returns:
        str: The filesystem path to the object's data file.

    Raises:
        ValueError: If the object is read-only from the data portal and cannot be symlinked.
    """
    # FSSpec objects - straightforward path access
    if isinstance(obj, (CopickPicksFSSpec, CopickMeshFSSpec, CopickSegmentationFSSpec)):
        return obj.path
    elif isinstance(obj, CopickTomogramFSSpec):
        # For FSSpec tomograms, use static_path if read-only, overlay_path otherwise
        return obj.static_path if obj.read_only else obj.overlay_path
    elif isinstance(obj, CopickFeaturesFSSpec):
        return obj.path

    # CDP objects - need to check if they're writable
    elif isinstance(obj, (CopickPicksCDP, CopickSegmentationCDP)):
        if obj.read_only:
            raise ValueError(
                f"Cannot symlink read-only data portal object: {obj}. "
                "Data portal objects must be in the overlay to be deposited.",
            )
        return obj.path
    elif isinstance(obj, CopickMeshCDP):
        if obj.read_only:
            raise ValueError(
                "Cannot symlink read-only data portal mesh. "
                "Data portal does not store meshes on the portal; they must be in the overlay.",
            )
        return obj.path
    elif isinstance(obj, CopickTomogramCDP):
        if obj.read_only:
            raise ValueError(
                f"Cannot symlink read-only data portal tomogram: {obj}. "
                "Portal tomograms must be downloaded to overlay first to be deposited.",
            )
        return obj.overlay_path
    elif isinstance(obj, CopickFeaturesCDP):
        if obj.read_only:
            raise ValueError(
                "Cannot symlink read-only data portal features. Data portal does not support features yet.",
            )
        return obj.path

    else:
        raise TypeError(f"Unknown copick object type: {type(obj).__name__}")


def _create_symlink(source: str, target: str) -> None:
    """Safely create a symlink, creating parent directories as needed.

    Args:
        source: The source path to link to.
        target: The target path for the symlink.
    """
    target_path = Path(target)

    # Create parent directories if they don't exist
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # Skip if symlink already exists and points to the same source
    if target_path.is_symlink():
        if os.readlink(target_path) == source:
            return
        else:
            logger.warning(f"Symlink {target} already exists pointing to {os.readlink(target_path)}, skipping")
            return

    # Skip if a file/directory already exists at target
    if target_path.exists():
        logger.warning(f"File or directory {target} already exists, skipping")
        return

    # Create the symlink
    os.symlink(source, target)


def deposit_run(
    run: CopickRun,
    target_dir: str,
    run_name_prefix: str = "",
    run_name_regex: Optional[str] = None,
    picks_uris: Optional[List[str]] = None,
    meshes_uris: Optional[List[str]] = None,
    segmentations_uris: Optional[List[str]] = None,
    tomograms_uris: Optional[List[str]] = None,
    features_uris: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Process a single run and create symlinks for specified objects in the target directory.

    Args:
        run: The copick run to process.
        target_dir: The target directory for the deposited view.
        run_name_prefix: Prefix to prepend to the run name (e.g., "ds123_rn001_").
        run_name_regex: Optional regex to extract run name from copick run name. Run name will be taken from the
            first group defined using parentheses in the pattern.
        picks_uris: List of URIs to filter picks. If None, skip picks entirely.
        meshes_uris: List of URIs to filter meshes. If None, skip meshes entirely.
        segmentations_uris: List of URIs to filter segmentations. If None, skip segmentations entirely.
        tomograms_uris: List of URIs to filter tomograms. If None, skip tomograms entirely.
        features_uris: List of URIs to filter features. If None, skip features entirely.

    Returns:
        Dict with keys:
            - "processed": Number of objects successfully symlinked
            - "errors": List of error messages
    """
    processed = 0
    errors = []

    # Determine the run name, applying regex if provided
    output_run_name = run.name
    if run_name_regex:
        # Match run name with regex
        match = re.search(run_name_regex, run.name)
        if match:
            output_run_name = match.group(1)
        else:
            if logger:
                logger.error(f"Run name {run.name} does not match regex {run_name_regex}.")
            raise ValueError(f"Run name {run.name} does not match regex {run_name_regex}.")

    # Construct the prefixed run name
    prefixed_run_name = f"{run_name_prefix}{output_run_name}"
    run_dir = Path(target_dir) / "ExperimentRuns" / prefixed_run_name

    # Process picks
    if picks_uris is not None:
        for uri in picks_uris:
            try:
                picks_list = resolve_copick_objects(uri, run.root, "picks", run.name)
                for pick in picks_list:
                    source = _get_file_path(pick)
                    filename = f"{pick.user_id}_{pick.session_id}_{pick.pickable_object_name}.json"
                    target = run_dir / "Picks" / filename
                    _create_symlink(source, str(target))
                    processed += 1
            except Exception as e:
                errors.append(f"Error processing picks URI '{uri}': {e}")
                logger.error(f"Error processing picks URI '{uri}'", exc_info=e)

    # Process meshes
    if meshes_uris is not None:
        for uri in meshes_uris:
            try:
                meshes_list = resolve_copick_objects(uri, run.root, "mesh", run.name)
                for mesh in meshes_list:
                    source = _get_file_path(mesh)
                    filename = f"{mesh.user_id}_{mesh.session_id}_{mesh.pickable_object_name}.glb"
                    target = run_dir / "Meshes" / filename
                    _create_symlink(source, str(target))
                    processed += 1
            except Exception as e:
                errors.append(f"Error processing meshes URI '{uri}': {e}")
                logger.error(f"Error processing meshes URI '{uri}'", exc_info=e)

    # Process segmentations
    if segmentations_uris is not None:
        for uri in segmentations_uris:
            try:
                segs_list = resolve_copick_objects(uri, run.root, "segmentation", run.name)
                for seg in segs_list:
                    source = _get_file_path(seg)
                    if seg.is_multilabel:
                        filename = f"{seg.voxel_size:.3f}_{seg.user_id}_{seg.session_id}_{seg.name}-multilabel.zarr"
                    else:
                        filename = f"{seg.voxel_size:.3f}_{seg.user_id}_{seg.session_id}_{seg.name}.zarr"
                    target = run_dir / "Segmentations" / filename
                    _create_symlink(source, str(target))
                    processed += 1
            except Exception as e:
                errors.append(f"Error processing segmentations URI '{uri}': {e}")
                logger.error(f"Error processing segmentations URI '{uri}'", exc_info=e)

    # Process tomograms
    if tomograms_uris is not None:
        for uri in tomograms_uris:
            try:
                tomos_list = resolve_copick_objects(uri, run.root, "tomogram", run.name)
                for tomo in tomos_list:
                    source = _get_file_path(tomo)
                    voxel_dir = f"VoxelSpacing{tomo.voxel_spacing.voxel_size:.3f}"
                    filename = f"{tomo.tomo_type}.zarr"
                    target = run_dir / voxel_dir / filename
                    _create_symlink(source, str(target))
                    processed += 1
            except Exception as e:
                errors.append(f"Error processing tomograms URI '{uri}': {e}")
                logger.error(f"Error processing tomograms URI '{uri}'", exc_info=e)

    # Process features
    if features_uris is not None:
        for uri in features_uris:
            try:
                features_list = resolve_copick_objects(uri, run.root, "feature", run.name)
                for feature in features_list:
                    source = _get_file_path(feature)
                    voxel_dir = f"VoxelSpacing{feature.tomogram.voxel_spacing.voxel_size:.3f}"
                    filename = f"{feature.tomo_type}_{feature.feature_type}_features.zarr"
                    target = run_dir / voxel_dir / filename
                    _create_symlink(source, str(target))
                    processed += 1
            except Exception as e:
                errors.append(f"Error processing features URI '{uri}': {e}")
                logger.error(f"Error processing features URI '{uri}'", exc_info=e)

    return {"processed": processed, "errors": errors}


def deposit(
    config: str,
    target_dir: str,
    run_names: Optional[List[str]] = None,
    run_name_prefix: str = "",
    run_name_regex: Optional[str] = None,
    picks_uris: Optional[List[str]] = None,
    meshes_uris: Optional[List[str]] = None,
    segmentations_uris: Optional[List[str]] = None,
    tomograms_uris: Optional[List[str]] = None,
    features_uris: Optional[List[str]] = None,
    n_workers: int = 8,
) -> None:
    """Create a depositable view of a copick project using symlinks.

    This function creates a hierarchical directory structure suitable for uploading to the
    cryoET data portal. It operates on a single copick config and creates symlinks to the
    actual data files, allowing multiple projects to be deposited into the same target
    directory through successive executions.

    The directory structure created conforms to the standard copick filesystem layout.

    **Important**: This operation requires local filesystem storage for both the source
    copick project and the target directory. Symlinks cannot be created with remote
    filesystems (S3, SSH, SMB, etc.). If you need to deposit data from a remote filesystem,
    you must first download it to local storage.

    Args:
        config: Path to the copick configuration file.
        target_dir: Target directory for the deposited view.
        run_names: List of specific run names to process. If None, processes all runs.
        run_name_prefix: Prefix to prepend to all run names. For data portal projects, if not
            provided, automatically constructs "{dataset_id}_{portal_run_name}_" for each run.
            For filesystem projects or when explicitly provided, uses the same prefix for all runs.
        run_name_regex: Optional regex to define how to extract run names from copick run names. Run names will be
            extracted from the first group defined using parentheses in the pattern.
        picks_uris: List of URIs to filter picks (e.g., ["proteasome:*/*", "ribosome:user1/*"]).
            If None, skips picks entirely.
        meshes_uris: List of URIs to filter meshes. If None, skips meshes entirely.
        segmentations_uris: List of URIs to filter segmentations (e.g., ["membrane:*/*@10.0"]).
            If None, skips segmentations entirely.
        tomograms_uris: List of URIs to filter tomograms (e.g., ["wbp@10.0"]).
            If None, skips tomograms entirely.
        features_uris: List of URIs to filter features (e.g., ["wbp@10.0:cellcanvas"]).
            If None, skips features entirely.
        n_workers: Number of parallel workers for processing runs.

    Examples:
        # Deposit all runs from a filesystem project
        deposit(
            config="filesystem_config.json",
            target_dir="/path/to/deposit",
            picks_uris=["*:*/*"],  # All picks
            meshes_uris=["*:*/*"],  # All meshes
        )

        # Deposit from a data portal project (automatic run name transformation)
        # Runs will be named like: 10301_TS_001_<portal_run_id>
        deposit(
            config="portal_config.json",
            target_dir="/path/to/deposit",
            picks_uris=["proteasome:*/*", "ribosome:*/*"],
            segmentations_uris=["membrane:*/*@10.0"],
        )

        # Deposit with explicit prefix override
        deposit(
            config="config.json",
            target_dir="/path/to/deposit",
            run_names=["TS_001", "TS_002"],
            run_name_prefix="custom_prefix_",
            picks_uris=["*:*/*"],
        )

        # Multiple projects to same target (successive executions)
        deposit(config="project1.json", target_dir="/deposit", run_name_prefix="proj1_", ...)
        deposit(config="project2.json", target_dir="/deposit", run_name_prefix="proj2_", ...)

    Notes:
        - For data portal projects, run names are automatically transformed from portal run IDs
          to "{dataset_id}_{portal_run_name}_{portal_run_id}" unless run_name_prefix is provided.
        - Multiple executions to the same target_dir are safe and idempotent.
        - Symlinks that already exist and point to the correct source are skipped.
        - Read-only data from the portal cannot be symlinked and will raise an error.
    """
    # Load the copick root
    root = copick.from_file(config)

    # Check if filesystems are local (symlinks only work with local filesystems)
    if isinstance(root, CopickRootFSSpec):
        overlay_protocol = root.fs_overlay.protocol
        static_protocol = root.fs_static.protocol if root.fs_static else None

        # fsspec protocols can be string or tuple
        def is_local_protocol(protocol):
            if protocol is None:
                return True
            if isinstance(protocol, (list, tuple)):
                return any(p in ("file", "local") for p in protocol)
            return protocol in ("file", "local")

        overlay_is_local = is_local_protocol(overlay_protocol)
        static_is_local = is_local_protocol(static_protocol)

        if not (overlay_is_local and static_is_local):
            raise ValueError(
                "Deposit operation requires local filesystem storage. "
                "Symlinks cannot be created with remote filesystems (S3, SSH, SMB, etc.). "
                f"Current filesystems: overlay={overlay_protocol}, static={static_protocol}",
            )

    # Get the runs to process
    runs = root.runs if run_names is None else [root.get_run(name) for name in run_names]

    # For CDP projects, automatically construct run name prefixes from dataset_id and portal_run_name
    # unless a prefix is explicitly provided
    is_cdp = isinstance(root, CopickRootCDP)
    run_prefixes = []
    for run in runs:
        if is_cdp and not run_name_prefix:
            run_prefixes.append(f"{run.portal_dataset_id}_{run.portal_run_name}_")
        elif run_name_prefix:
            run_prefixes.append(run_name_prefix)
        else:
            run_prefixes.append("")

    # Build run_args - each run gets its own prefix
    run_args = [
        {
            "target_dir": target_dir,
            "run_name_prefix": prefix,
            "run_name_regex": run_name_regex,
            "picks_uris": picks_uris,
            "meshes_uris": meshes_uris,
            "segmentations_uris": segmentations_uris,
            "tomograms_uris": tomograms_uris,
            "features_uris": features_uris,
        }
        for prefix in run_prefixes
    ]

    # Process runs in parallel
    results = map_runs(
        callback=deposit_run,
        root=root,
        runs=runs,
        workers=n_workers,
        run_args=run_args,
        show_progress=True,
        task_desc="Depositing runs",
    )

    # Calculate total files that should have been processed
    total_files = sum(r["processed"] for r in results.values() if r is not None)

    # Report results
    report_results(results, total_files, logger)
