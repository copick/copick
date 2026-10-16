"""Operations for managing copick objects (move, copy, delete)."""

from typing import Any, Dict, List, Optional, Union

import zarr
from zarr.convenience import copy_store

from copick.models import (
    CopickAlignment,
    CopickMesh,
    CopickPicks,
    CopickRoot,
    CopickRun,
    CopickSegmentation,
    CopickTiltSeries,
)
from copick.util.log import get_logger
from copick.util.uri import parse_copick_uri, resolve_copick_objects, serialize_copick_uri

logger = get_logger(__name__)


#: Object types cp and mv handle.
_TRANSFERABLE_TYPES = ("picks", "filaments", "mesh", "segmentation", "tiltseries", "alignment")
#: Object types cp and mv transfer with ``copy_tilt_series`` / ``copy_alignment``.
_ACQUISITION_TYPES = ("tiltseries", "alignment")


def _copy_segmentation_store(
    source: Union[CopickSegmentation, CopickTiltSeries],
    target: Union[CopickSegmentation, CopickTiltSeries],
    *,
    verify_before_delete: bool,
) -> None:
    """Raw-copy a segmentation's (or tilt series') store, keeping its dtype and every pyramid level.

    Round-tripping through ``numpy()``/``from_numpy()`` would keep only level 0 and re-choose the dtype.
    """
    source_store = source.zarr()
    target_store = target.zarr()
    source_path = getattr(source_store, "path", None)
    if source_path is not None and source_path == getattr(target_store, "path", None):
        raise ValueError("Source and target are the same store.")
    # An overwritten target must not keep levels the source doesn't have.
    for key in list(target_store.keys()):
        del target_store[key]
    copy_store(source_store, target_store, if_exists="replace")
    if verify_before_delete:
        src = zarr.open_group(source_store, mode="r")
        trg = zarr.open_group(target_store, mode="r")
        for name, array in src.arrays():
            copied = trg[name]
            if copied.shape != array.shape or copied.dtype != array.dtype:
                raise ValueError(f"Copied level {name} does not match its source.")


def copy_tilt_series(
    source: CopickTiltSeries,
    target_run: CopickRun,
    ts_type: Optional[str] = None,
    exist_ok: bool = False,
) -> CopickTiltSeries:
    """Copy a tilt series, images and metadata, into a run (the same or another).

    The images are copied store to store, keeping every level. The metadata is stored with the copy, so the copy of a
    tilt series whose metadata is synthesized (e.g. from the CryoET Data Portal) carries it.

    Args:
        source: The tilt series to copy.
        target_run: The run to copy it into.
        ts_type: Type of the copy. Default: the source's.
        exist_ok: Whether to overwrite an existing tilt series of that type.

    Returns:
        CopickTiltSeries: The copy.
    """
    ts_type = ts_type or source.ts_type
    if target_run is source.run and ts_type == source.ts_type and not source.read_only:
        raise ValueError(f"Source and target are the same tilt series {ts_type}.")
    if target_run.get_tilt_series_list(ts_type) and not exist_ok:
        raise ValueError(f"Tilt series {ts_type} already exists in run {target_run.name}.")
    target = target_run.new_tilt_series(ts_type, exist_ok=exist_ok)
    _copy_segmentation_store(source, target, verify_before_delete=True)
    target.refresh()
    metadata = source.metadata
    if metadata is not None:
        target.store_metadata(metadata)
    return target


def copy_alignment(
    source: CopickAlignment,
    target_run: CopickRun,
    name: Optional[str] = None,
    tilt_series: Optional[str] = None,
    exist_ok: bool = False,
    keep_links: bool = False,
) -> CopickAlignment:
    """Copy an alignment into a run (the same or another).

    Args:
        source: The alignment to copy.
        target_run: The run to copy it into; it must hold the tilt series the copy aligns.
        name: Name of the copy. Default: the source's.
        tilt_series: Type of the tilt series the copy aligns. Default: the source's.
        exist_ok: Whether to overwrite an existing alignment of that name.
        keep_links: Whether the copy names the read-only tomograms the source names.

    Returns:
        CopickAlignment: The copy.
    """
    file = source.file
    name = name or source.name
    ts_type = tilt_series or file.tilt_series
    if target_run is source.run and ts_type == file.tilt_series:
        target_ts = source.tilt_series
    else:
        found = target_run.get_tilt_series_list(ts_type)
        target_ts = found[0] if found else None
    if target_ts is None:
        raise ValueError(f"Run {target_run.name} has no tilt series {ts_type} for alignment {name}.")

    existing = target_run.get_alignment(name)
    if existing is not None:
        if existing is source:
            raise ValueError(f"Source and target are the same alignment {name}.")
        if not exist_ok:
            raise ValueError(f"Alignment {name} already exists in run {target_run.name}.")
        existing.delete(unlink=False)

    fields = file.model_dump(
        exclude={
            "name",
            "run_name",
            "tilt_series",
            "tilt_series_portal_id",
            "linked_tomograms",
            "sections",
            "reference_volume",
        },
    )
    return target_run.new_alignment(
        name,
        target_ts,
        sections=file.sections,
        reference_volume=file.reference_volume,
        linked_tomograms=list(file.linked_tomograms) if keep_links else [],
        **fields,
    )


def _transfer_acquisition_object(
    source: Union[CopickTiltSeries, CopickAlignment],
    object_type: str,
    target_params: Dict[str, Any],
    overwrite: bool,
    move: bool,
) -> None:
    """Copy or move a tilt series or an alignment within its run.

    Moving a tilt series moves its alignments along (their writable tomograms are relinked); moving an alignment
    relinks the tomograms reconstructed with it. A move that would leave a read-only record pointing nowhere is refused
    before anything changes.
    """
    run = source.run
    if move and getattr(source, "read_only", False):
        raise PermissionError(f"{serialize_copick_uri(source)} is read-only and cannot be moved.")

    if object_type == "tiltseries":
        alignments = source.alignments if move else []
        if blocked := [a.name for a in alignments if getattr(a, "read_only", False)]:
            raise PermissionError(f"Read-only alignments {blocked} align tilt series {source.ts_type}.")
        linked = {a.name: a.tomograms for a in alignments}
        target = copy_tilt_series(source, run, target_params["ts_type"], exist_ok=overwrite)
        for alignment in alignments:
            alignment.meta.tilt_series = target.ts_type
            alignment.meta.tilt_series_portal_id = None
            alignment.store()
            for tomogram in linked[alignment.name]:
                link = tomogram.alignment_link
                if link.source == "attrs" and not getattr(tomogram, "read_only", False):
                    tomogram.set_alignment(alignment, reference_offset=link.reference_offset)
        if move:
            source.delete()
        return

    tomograms = source.tomograms if move else []
    if move:
        # Links the tomogram or its source record (portal, Croissant) cannot follow; those the alignment records do
        fixed = [
            t.link_id
            for t in tomograms
            if t.alignment_link.source in ("portal", "croissant")
            or (t.alignment_link.source == "attrs" and getattr(t, "read_only", False))
        ]
        if fixed:
            raise PermissionError(f"Tomograms {fixed} record alignment {source.name} where it cannot be changed.")
    target_ts = target_params.get("ts_type")
    target = copy_alignment(
        source,
        run,
        name=target_params["name"],
        tilt_series=None if target_ts in (None, "*") else target_ts,
        exist_ok=overwrite,
        keep_links=move,
    )
    if move:
        for tomogram in tomograms:
            link = tomogram.alignment_link
            if link.source == "attrs":
                tomogram.set_alignment(target, reference_offset=link.reference_offset)
        source.delete(unlink=False)


def _keep_segmentation_type(source: CopickSegmentation, target_params: Dict[str, Any]) -> None:
    """cp and mv keep a segmentation's type: a target URI may restate it, never change it."""
    for flag, value in (
        ("multilabel", source.is_multilabel),
        ("instance", source.is_instance),
        ("panoptic", source.is_panoptic),
    ):
        wanted = target_params.get(flag)
        if wanted is not None and wanted != value:
            raise ValueError(
                f"The source is a {source.segmentation_type} segmentation; cp and mv do not convert segmentation "
                "types.",
            )


def _validate_target_template(
    source_uri: str,
    target_uri: str,
    object_type: str,
    num_source_objects: int,
) -> None:
    """Validate that target URI is appropriate for the source pattern.

    Args:
        source_uri: Source URI pattern
        target_uri: Target URI (may contain templates)
        object_type: Type of object being moved/copied
        num_source_objects: Number of objects matched by source pattern

    Raises:
        ValueError: If target URI is invalid for the source pattern
    """
    source_params = parse_copick_uri(source_uri, object_type)
    parse_copick_uri(target_uri, object_type)

    # Check if source is a pattern
    is_pattern = (
        source_params.get("pattern_type") == "regex"
        or "*" in str(source_params.get("object_name", ""))
        or "*" in str(source_params.get("user_id", ""))
        or "*" in str(source_params.get("session_id", ""))
        or (object_type in ("segmentation", "alignment") and "*" in str(source_params.get("name", "")))
        or "*" in str(source_params.get("ts_type", ""))
    )

    # If source matches multiple objects or is a pattern, target must use templates
    if num_source_objects > 1 or is_pattern:
        # Check for template placeholders in target
        has_template = (
            "{object_name}" in target_uri
            or "{name}" in target_uri
            or "{user_id}" in target_uri
            or "{session_id}" in target_uri
            or "{voxel_spacing}" in target_uri
            or "{ts_type}" in target_uri
        )

        if not has_template:
            raise ValueError(
                f"Source URI matches {num_source_objects} objects or uses patterns. "
                "Target URI must contain template placeholders like {user_id}, {session_id}, etc. "
                f"Source: {source_uri}, Target: {target_uri}",
            )

    # If source is exact (single object), target should not have templates
    elif num_source_objects == 1 and not is_pattern and "{" in target_uri:
        raise ValueError(
            f"Source URI matches a single object. Target URI should not contain template placeholders. "
            f"Source: {source_uri}, Target: {target_uri}",
        )


def _apply_template(
    template_uri: str,
    obj: Union[CopickPicks, CopickMesh, CopickSegmentation, CopickTiltSeries, CopickAlignment],
    object_type: str,
) -> str:
    """Apply template placeholders to generate a concrete URI.

    Args:
        template_uri: URI template with placeholders
        obj: Source copick object
        object_type: Type of object

    Returns:
        Concrete URI with placeholders replaced
    """
    result = template_uri

    # Replace placeholders based on object type
    if object_type in ("picks", "filaments", "mesh"):
        result = result.replace("{object_name}", obj.pickable_object_name)
        result = result.replace("{user_id}", obj.user_id)
        result = result.replace("{session_id}", obj.session_id)
    elif object_type == "segmentation":
        result = result.replace("{name}", obj.name)
        result = result.replace("{user_id}", obj.user_id)
        result = result.replace("{session_id}", obj.session_id)
        result = result.replace("{voxel_spacing}", str(obj.voxel_size))
    elif object_type == "tiltseries":
        result = result.replace("{ts_type}", obj.ts_type)
    elif object_type == "alignment":
        result = result.replace("{name}", obj.name)
        result = result.replace("{ts_type}", obj.tilt_series_name or "")

    return result


def _delete_object(obj: Any, cascade: bool) -> None:
    """Delete one object. A tilt series still aligned by alignments is refused unless ``cascade`` deletes those too."""
    if isinstance(obj, CopickTiltSeries):
        alignments = obj.alignments
        if alignments and not cascade:
            raise ValueError(
                f"Tilt series {obj.ts_type} is aligned by {[a.name for a in alignments]}; remove those first, or "
                "remove them along (cascade).",
            )
        for alignment in alignments:
            alignment.delete()
    obj.delete()


def remove_copick_objects(
    root: CopickRoot,
    object_type: str,
    uri: str,
    run_name: Optional[str] = None,
    dry_run: bool = False,
    log: bool = False,
    cascade: bool = False,
) -> Dict[str, Any]:
    """Remove copick objects matching a URI pattern.

    Args:
        root: CopickRoot instance
        object_type: Type of object ('picks', 'filaments', 'mesh', 'segmentation', 'tomogram', 'feature',
            'tiltseries', 'alignment')
        uri: Copick URI (supports patterns)
        run_name: Specific run name to operate on (None = all runs)
        dry_run: If True, only list objects that would be deleted
        log: Enable logging
        cascade: Also remove the alignments of removed tilt series (otherwise such tilt series are not removed)

    Returns:
        Dict with 'deleted' count and 'objects' list (URIs)

    Raises:
        ValueError: If object_type is invalid or URI is malformed
    """
    # Resolve objects
    objects = resolve_copick_objects(uri, root, object_type, run_name)

    if not objects:
        if log:
            logger.info(f"No objects found matching URI: {uri}")
        return {"deleted": 0, "objects": []}

    deleted_uris = []

    if dry_run:
        for obj in objects:
            obj_uri = serialize_copick_uri(obj)
            deleted_uris.append(obj_uri)
            if log:
                logger.info(f"[DRY RUN] Would delete: {obj_uri}")
    else:
        for obj in objects:
            obj_uri = serialize_copick_uri(obj)
            try:
                _delete_object(obj, cascade)
                deleted_uris.append(obj_uri)
                if log:
                    logger.info(f"Deleted: {obj_uri}")
            except Exception as e:
                if log:
                    logger.error(f"Failed to delete {obj_uri}: {e}")

    return {"deleted": len(deleted_uris), "objects": deleted_uris}


def move_copick_objects(
    root: CopickRoot,
    object_type: str,
    source_uri: str,
    target_uri: str,
    run_name: Optional[str] = None,
    overwrite: bool = False,
    log: bool = False,
) -> Dict[str, Any]:
    """Move/rename copick objects by URI.

    For pattern-based operations, target_uri must contain template placeholders.
    For single object operations, target_uri should be concrete.

    Args:
        root: CopickRoot instance
        object_type: Type of object ('picks', 'filaments', 'mesh', 'segmentation')
        source_uri: Source copick URI (supports patterns)
        target_uri: Target copick URI (use templates for patterns)
        run_name: Specific run name to operate on (None = all runs)
        overwrite: Allow overwriting existing objects
        log: Enable logging

    Returns:
        Dict with 'moved' count, 'mappings' list of (source, target) tuples, and 'errors' list

    Raises:
        ValueError: If URIs are invalid or incompatible
    """
    if object_type not in _TRANSFERABLE_TYPES:
        raise ValueError(f"Move operation not supported for object type: {object_type}")

    # Resolve source objects
    source_objects = resolve_copick_objects(source_uri, root, object_type, run_name)

    if not source_objects:
        if log:
            logger.warning(f"No objects found matching source URI: {source_uri}")
        return {"moved": 0, "mappings": [], "errors": []}

    # Validate target template
    _validate_target_template(source_uri, target_uri, object_type, len(source_objects))

    mappings = []
    errors = []

    for source_obj in source_objects:
        source_obj_uri = serialize_copick_uri(source_obj)

        try:
            # Generate target URI
            concrete_target_uri = _apply_template(target_uri, source_obj, object_type)
            if concrete_target_uri == source_obj_uri:
                # Moving an object onto itself would copy it to itself and then delete it.
                raise ValueError("Source and target are the same object; nothing to move.")

            # Parse target to get new parameters
            target_params = parse_copick_uri(concrete_target_uri, object_type)

            if object_type in _ACQUISITION_TYPES:
                _transfer_acquisition_object(source_obj, object_type, target_params, overwrite, move=True)
                mappings.append((source_obj_uri, concrete_target_uri))
                if log:
                    logger.info(f"Moved: {source_obj_uri} → {concrete_target_uri}")
                continue

            # Create new object with target parameters
            if object_type == "picks":
                target_obj = source_obj.run.new_picks(
                    object_name=target_params["object_name"],
                    session_id=target_params["session_id"],
                    user_id=target_params["user_id"],
                    exist_ok=overwrite,
                )
            elif object_type == "filaments":
                target_obj = source_obj.run.new_filaments(
                    object_name=target_params["object_name"],
                    session_id=target_params["session_id"],
                    user_id=target_params["user_id"],
                    exist_ok=overwrite,
                )
            elif object_type == "mesh":
                target_obj = source_obj.run.new_mesh(
                    object_name=target_params["object_name"],
                    session_id=target_params["session_id"],
                    user_id=target_params["user_id"],
                    exist_ok=overwrite,
                )
            elif object_type == "segmentation":
                voxel_spacing = target_params["voxel_spacing"]
                if isinstance(voxel_spacing, str):
                    voxel_spacing = float(voxel_spacing)

                _keep_segmentation_type(source_obj, target_params)
                target_obj = source_obj.run.new_segmentation(
                    name=target_params["name"],
                    session_id=target_params["session_id"],
                    user_id=target_params["user_id"],
                    voxel_size=voxel_spacing,
                    is_multilabel=source_obj.is_multilabel,
                    is_instance=source_obj.is_instance,
                    is_panoptic=source_obj.is_panoptic,
                    exist_ok=overwrite,
                )

            # Copy data
            if object_type == "picks":
                # For picks, copy the points
                source_obj.load()
                target_obj.points = source_obj.points
                target_obj.store()
            elif object_type == "filaments":
                source_obj.load()
                target_obj.filaments = source_obj.filaments
                target_obj.meta.voxel_spacing = source_obj.voxel_spacing
                target_obj.store()
            elif object_type == "mesh":
                # For meshes, copy the mesh geometry (trimesh object)
                source_obj.load()
                target_obj.mesh = source_obj.mesh
                target_obj.store()
            elif object_type == "segmentation":
                _copy_segmentation_store(source_obj, target_obj, verify_before_delete=True)

            # Delete source object
            source_obj.delete()

            mappings.append((source_obj_uri, concrete_target_uri))
            if log:
                logger.info(f"Moved: {source_obj_uri} → {concrete_target_uri}")

        except Exception as e:
            error_msg = f"Failed to move {source_obj_uri}: {e}"
            errors.append(error_msg)
            if log:
                logger.error(error_msg)

    return {"moved": len(mappings), "mappings": mappings, "errors": errors}


def copy_copick_objects(
    root: CopickRoot,
    object_type: str,
    source_uri: str,
    target_uri: str,
    run_name: Optional[str] = None,
    overwrite: bool = False,
    log: bool = False,
) -> Dict[str, Any]:
    """Copy/duplicate copick objects by URI.

    For pattern-based operations, target_uri must contain template placeholders.
    For single object operations, target_uri should be concrete.

    Args:
        root: CopickRoot instance
        object_type: Type of object ('picks', 'filaments', 'mesh', 'segmentation')
        source_uri: Source copick URI (supports patterns)
        target_uri: Target copick URI (use templates for patterns)
        run_name: Specific run name to operate on (None = all runs)
        overwrite: Allow overwriting existing objects
        log: Enable logging

    Returns:
        Dict with 'copied' count, 'mappings' list of (source, target) tuples, and 'errors' list

    Raises:
        ValueError: If URIs are invalid or incompatible
    """
    if object_type not in _TRANSFERABLE_TYPES:
        raise ValueError(f"Copy operation not supported for object type: {object_type}")

    # Resolve source objects
    source_objects = resolve_copick_objects(source_uri, root, object_type, run_name)

    if not source_objects:
        if log:
            logger.warning(f"No objects found matching source URI: {source_uri}")
        return {"copied": 0, "mappings": [], "errors": []}

    # Validate target template
    _validate_target_template(source_uri, target_uri, object_type, len(source_objects))

    mappings = []
    errors = []

    for source_obj in source_objects:
        source_obj_uri = serialize_copick_uri(source_obj)

        try:
            # Generate target URI
            concrete_target_uri = _apply_template(target_uri, source_obj, object_type)

            # Parse target to get new parameters
            target_params = parse_copick_uri(concrete_target_uri, object_type)

            if object_type in _ACQUISITION_TYPES:
                _transfer_acquisition_object(source_obj, object_type, target_params, overwrite, move=False)
                mappings.append((source_obj_uri, concrete_target_uri))
                if log:
                    logger.info(f"Copied: {source_obj_uri} → {concrete_target_uri}")
                continue

            # Create new object with target parameters
            if object_type == "picks":
                target_obj = source_obj.run.new_picks(
                    object_name=target_params["object_name"],
                    session_id=target_params["session_id"],
                    user_id=target_params["user_id"],
                    exist_ok=overwrite,
                )
            elif object_type == "filaments":
                target_obj = source_obj.run.new_filaments(
                    object_name=target_params["object_name"],
                    session_id=target_params["session_id"],
                    user_id=target_params["user_id"],
                    exist_ok=overwrite,
                )
            elif object_type == "mesh":
                target_obj = source_obj.run.new_mesh(
                    object_name=target_params["object_name"],
                    session_id=target_params["session_id"],
                    user_id=target_params["user_id"],
                    exist_ok=overwrite,
                )
            elif object_type == "segmentation":
                voxel_spacing = target_params["voxel_spacing"]
                if isinstance(voxel_spacing, str):
                    voxel_spacing = float(voxel_spacing)

                _keep_segmentation_type(source_obj, target_params)
                target_obj = source_obj.run.new_segmentation(
                    name=target_params["name"],
                    session_id=target_params["session_id"],
                    user_id=target_params["user_id"],
                    voxel_size=voxel_spacing,
                    is_multilabel=source_obj.is_multilabel,
                    is_instance=source_obj.is_instance,
                    is_panoptic=source_obj.is_panoptic,
                    exist_ok=overwrite,
                )

            # Copy data (same as move, but without deleting source)
            if object_type == "picks":
                # For picks, copy the points
                source_obj.load()
                target_obj.points = source_obj.points
                target_obj.store()
            elif object_type == "filaments":
                source_obj.load()
                target_obj.filaments = source_obj.filaments
                target_obj.meta.voxel_spacing = source_obj.voxel_spacing
                target_obj.store()
            elif object_type == "mesh":
                # For meshes, copy the mesh geometry (trimesh object)
                source_obj.load()
                target_obj.mesh = source_obj.mesh
                target_obj.store()
            elif object_type == "segmentation":
                _copy_segmentation_store(source_obj, target_obj, verify_before_delete=False)

            mappings.append((source_obj_uri, concrete_target_uri))
            if log:
                logger.info(f"Copied: {source_obj_uri} → {concrete_target_uri}")

        except Exception as e:
            error_msg = f"Failed to copy {source_obj_uri}: {e}"
            errors.append(error_msg)
            if log:
                logger.error(error_msg)

    return {"copied": len(mappings), "mappings": mappings, "errors": errors}


# ============================================================================
# Per-run batch operations for parallelization
# ============================================================================


def remove_copick_objects_per_run(
    run: CopickRun,
    object_type: str,
    uri: str,
    dry_run: bool = False,
    cascade: bool = False,
) -> Dict[str, Any]:
    """Remove copick objects matching a URI pattern within a single run.

    Worker function for parallel batch removal.

    Args:
        run: CopickRun instance to process
        object_type: Type of object ('picks', 'filaments', 'mesh', 'segmentation', 'tomogram', 'feature')
        uri: Copick URI (supports patterns)
        dry_run: If True, only list objects that would be deleted
        cascade: Also remove the alignments of removed tilt series

    Returns:
        Dict with 'deleted' count, 'objects' list (URIs), and 'errors' list
    """
    try:
        # Resolve objects within this run only
        objects = resolve_copick_objects(uri, run.root, object_type, run.name)

        if not objects:
            return {"deleted": 0, "objects": [], "errors": []}

        deleted_uris = []
        errors = []

        if dry_run:
            for obj in objects:
                obj_uri = serialize_copick_uri(obj)
                deleted_uris.append(obj_uri)
        else:
            for obj in objects:
                obj_uri = serialize_copick_uri(obj)
                try:
                    _delete_object(obj, cascade)
                    deleted_uris.append(obj_uri)
                except Exception as e:
                    errors.append(f"Failed to delete {obj_uri}: {e}")

        return {"deleted": len(deleted_uris), "objects": deleted_uris, "errors": errors}

    except Exception as e:
        logger.exception(f"Error in remove worker for run {run.name}: {e}")
        return {"deleted": 0, "objects": [], "errors": [f"Worker error in {run.name}: {e}"]}


def remove_copick_objects_batch(
    root: CopickRoot,
    object_type: str,
    uri: str,
    run_names: Optional[List[str]] = None,
    dry_run: bool = False,
    workers: int = 8,
    cascade: bool = False,
) -> Dict[str, Any]:
    """Remove copick objects in parallel across multiple runs.

    Args:
        root: CopickRoot instance
        object_type: Type of object ('picks', 'filaments', 'mesh', 'segmentation', 'tomogram', 'feature')
        uri: Copick URI (supports patterns)
        run_names: List of run names to process (None = all runs)
        dry_run: If True, only list objects that would be deleted
        workers: Number of parallel workers
        cascade: Also remove the alignments of removed tilt series

    Returns:
        Dict mapping run names to results
    """
    from copick.ops.run import map_runs

    runs_to_process = [run.name for run in root.runs] if run_names is None else run_names

    if not runs_to_process:
        return {}

    def run_worker(run: CopickRun) -> Dict[str, Any]:
        return remove_copick_objects_per_run(
            run=run,
            object_type=object_type,
            uri=uri,
            dry_run=dry_run,
            cascade=cascade,
        )

    task_desc = "[DRY RUN] Removing objects" if dry_run else "Removing objects"
    results = map_runs(
        callback=run_worker,
        root=root,
        runs=runs_to_process,
        workers=workers,
        task_desc=task_desc,
    )

    return results


def move_copick_objects_per_run(
    run: CopickRun,
    object_type: str,
    source_uri: str,
    target_uri: str,
    overwrite: bool = False,
) -> Dict[str, Any]:
    """Move/rename copick objects by URI within a single run.

    Worker function for parallel batch moving.

    Args:
        run: CopickRun instance to process
        object_type: Type of object ('picks', 'filaments', 'mesh', 'segmentation')
        source_uri: Source copick URI (supports patterns)
        target_uri: Target copick URI (may contain templates)
        overwrite: Allow overwriting existing objects

    Returns:
        Dict with 'moved' count, 'mappings' list, and 'errors' list
    """
    try:
        if object_type not in _TRANSFERABLE_TYPES:
            return {
                "moved": 0,
                "mappings": [],
                "errors": [f"Move operation not supported for object type: {object_type}"],
            }

        # Resolve source objects within this run only
        source_objects = resolve_copick_objects(source_uri, run.root, object_type, run.name)

        if not source_objects:
            return {"moved": 0, "mappings": [], "errors": []}

        mappings = []
        errors = []

        for source_obj in source_objects:
            source_obj_uri = serialize_copick_uri(source_obj)

            try:
                # Generate target URI (apply templates if present)
                concrete_target_uri = _apply_template(target_uri, source_obj, object_type)
                if concrete_target_uri == source_obj_uri:
                    # Moving an object onto itself would copy it to itself and then delete it.
                    raise ValueError("Source and target are the same object; nothing to move.")

                # Parse target to get new parameters
                target_params = parse_copick_uri(concrete_target_uri, object_type)

                if object_type in _ACQUISITION_TYPES:
                    _transfer_acquisition_object(source_obj, object_type, target_params, overwrite, move=True)
                    mappings.append((source_obj_uri, concrete_target_uri))
                    continue

                # Create new object with target parameters
                if object_type == "picks":
                    target_obj = source_obj.run.new_picks(
                        object_name=target_params["object_name"],
                        session_id=target_params["session_id"],
                        user_id=target_params["user_id"],
                        exist_ok=overwrite,
                    )
                elif object_type == "filaments":
                    target_obj = source_obj.run.new_filaments(
                        object_name=target_params["object_name"],
                        session_id=target_params["session_id"],
                        user_id=target_params["user_id"],
                        exist_ok=overwrite,
                    )
                elif object_type == "mesh":
                    target_obj = source_obj.run.new_mesh(
                        object_name=target_params["object_name"],
                        session_id=target_params["session_id"],
                        user_id=target_params["user_id"],
                        exist_ok=overwrite,
                    )
                elif object_type == "segmentation":
                    voxel_spacing = target_params["voxel_spacing"]
                    if isinstance(voxel_spacing, str):
                        voxel_spacing = float(voxel_spacing)

                    _keep_segmentation_type(source_obj, target_params)
                    target_obj = source_obj.run.new_segmentation(
                        name=target_params["name"],
                        session_id=target_params["session_id"],
                        user_id=target_params["user_id"],
                        voxel_size=voxel_spacing,
                        is_multilabel=source_obj.is_multilabel,
                        is_instance=source_obj.is_instance,
                        is_panoptic=source_obj.is_panoptic,
                        exist_ok=overwrite,
                    )

                # Copy data
                if object_type == "picks":
                    source_obj.load()
                    target_obj.points = source_obj.points
                    target_obj.store()
                elif object_type == "filaments":
                    source_obj.load()
                    target_obj.filaments = source_obj.filaments
                    target_obj.meta.voxel_spacing = source_obj.voxel_spacing
                    target_obj.store()
                elif object_type == "mesh":
                    source_obj.load()
                    target_obj.mesh = source_obj.mesh
                    target_obj.store()
                elif object_type == "segmentation":
                    _copy_segmentation_store(source_obj, target_obj, verify_before_delete=True)

                # Delete source object
                source_obj.delete()

                mappings.append((source_obj_uri, concrete_target_uri))

            except Exception as e:
                errors.append(f"Failed to move {source_obj_uri}: {e}")

        return {"moved": len(mappings), "mappings": mappings, "errors": errors}

    except Exception as e:
        logger.exception(f"Error in move worker for run {run.name}: {e}")
        return {"moved": 0, "mappings": [], "errors": [f"Worker error in {run.name}: {e}"]}


def move_copick_objects_batch(
    root: CopickRoot,
    object_type: str,
    source_uri: str,
    target_uri: str,
    run_names: Optional[List[str]] = None,
    overwrite: bool = False,
    workers: int = 8,
) -> Dict[str, Any]:
    """Move/rename copick objects in parallel across multiple runs.

    Args:
        root: CopickRoot instance
        object_type: Type of object ('picks', 'filaments', 'mesh', 'segmentation')
        source_uri: Source copick URI (supports patterns)
        target_uri: Target copick URI (may contain templates)
        run_names: List of run names to process (None = all runs)
        overwrite: Allow overwriting existing objects
        workers: Number of parallel workers

    Returns:
        Dict mapping run names to results
    """
    from copick.ops.run import map_runs

    runs_to_process = [run.name for run in root.runs] if run_names is None else run_names

    if not runs_to_process:
        return {}

    def run_worker(run: CopickRun) -> Dict[str, Any]:
        return move_copick_objects_per_run(
            run=run,
            object_type=object_type,
            source_uri=source_uri,
            target_uri=target_uri,
            overwrite=overwrite,
        )

    results = map_runs(
        callback=run_worker,
        root=root,
        runs=runs_to_process,
        workers=workers,
        task_desc="Moving objects",
    )

    return results


def copy_copick_objects_per_run(
    run: CopickRun,
    object_type: str,
    source_uri: str,
    target_uri: str,
    overwrite: bool = False,
) -> Dict[str, Any]:
    """Copy/duplicate copick objects by URI within a single run.

    Worker function for parallel batch copying.

    Args:
        run: CopickRun instance to process
        object_type: Type of object ('picks', 'filaments', 'mesh', 'segmentation')
        source_uri: Source copick URI (supports patterns)
        target_uri: Target copick URI (may contain templates)
        overwrite: Allow overwriting existing objects

    Returns:
        Dict with 'copied' count, 'mappings' list, and 'errors' list
    """
    try:
        if object_type not in _TRANSFERABLE_TYPES:
            return {
                "copied": 0,
                "mappings": [],
                "errors": [f"Copy operation not supported for object type: {object_type}"],
            }

        # Resolve source objects within this run only
        source_objects = resolve_copick_objects(source_uri, run.root, object_type, run.name)

        if not source_objects:
            return {"copied": 0, "mappings": [], "errors": []}

        mappings = []
        errors = []

        for source_obj in source_objects:
            source_obj_uri = serialize_copick_uri(source_obj)

            try:
                # Generate target URI (apply templates if present)
                concrete_target_uri = _apply_template(target_uri, source_obj, object_type)

                # Parse target to get new parameters
                target_params = parse_copick_uri(concrete_target_uri, object_type)

                if object_type in _ACQUISITION_TYPES:
                    _transfer_acquisition_object(source_obj, object_type, target_params, overwrite, move=False)
                    mappings.append((source_obj_uri, concrete_target_uri))
                    continue

                # Create new object with target parameters
                if object_type == "picks":
                    target_obj = source_obj.run.new_picks(
                        object_name=target_params["object_name"],
                        session_id=target_params["session_id"],
                        user_id=target_params["user_id"],
                        exist_ok=overwrite,
                    )
                elif object_type == "filaments":
                    target_obj = source_obj.run.new_filaments(
                        object_name=target_params["object_name"],
                        session_id=target_params["session_id"],
                        user_id=target_params["user_id"],
                        exist_ok=overwrite,
                    )
                elif object_type == "mesh":
                    target_obj = source_obj.run.new_mesh(
                        object_name=target_params["object_name"],
                        session_id=target_params["session_id"],
                        user_id=target_params["user_id"],
                        exist_ok=overwrite,
                    )
                elif object_type == "segmentation":
                    voxel_spacing = target_params["voxel_spacing"]
                    if isinstance(voxel_spacing, str):
                        voxel_spacing = float(voxel_spacing)

                    _keep_segmentation_type(source_obj, target_params)
                    target_obj = source_obj.run.new_segmentation(
                        name=target_params["name"],
                        session_id=target_params["session_id"],
                        user_id=target_params["user_id"],
                        voxel_size=voxel_spacing,
                        is_multilabel=source_obj.is_multilabel,
                        is_instance=source_obj.is_instance,
                        is_panoptic=source_obj.is_panoptic,
                        exist_ok=overwrite,
                    )

                # Copy data (same as move, but without deleting source)
                if object_type == "picks":
                    source_obj.load()
                    target_obj.points = source_obj.points
                    target_obj.store()
                elif object_type == "filaments":
                    source_obj.load()
                    target_obj.filaments = source_obj.filaments
                    target_obj.meta.voxel_spacing = source_obj.voxel_spacing
                    target_obj.store()
                elif object_type == "mesh":
                    source_obj.load()
                    target_obj.mesh = source_obj.mesh
                    target_obj.store()
                elif object_type == "segmentation":
                    _copy_segmentation_store(source_obj, target_obj, verify_before_delete=False)

                mappings.append((source_obj_uri, concrete_target_uri))

            except Exception as e:
                errors.append(f"Failed to copy {source_obj_uri}: {e}")

        return {"copied": len(mappings), "mappings": mappings, "errors": errors}

    except Exception as e:
        logger.exception(f"Error in copy worker for run {run.name}: {e}")
        return {"copied": 0, "mappings": [], "errors": [f"Worker error in {run.name}: {e}"]}


def copy_copick_objects_batch(
    root: CopickRoot,
    object_type: str,
    source_uri: str,
    target_uri: str,
    run_names: Optional[List[str]] = None,
    overwrite: bool = False,
    workers: int = 8,
) -> Dict[str, Any]:
    """Copy/duplicate copick objects in parallel across multiple runs.

    Args:
        root: CopickRoot instance
        object_type: Type of object ('picks', 'filaments', 'mesh', 'segmentation')
        source_uri: Source copick URI (supports patterns)
        target_uri: Target copick URI (may contain templates)
        run_names: List of run names to process (None = all runs)
        overwrite: Allow overwriting existing objects
        workers: Number of parallel workers

    Returns:
        Dict mapping run names to results
    """
    from copick.ops.run import map_runs

    runs_to_process = [run.name for run in root.runs] if run_names is None else run_names

    if not runs_to_process:
        return {}

    def run_worker(run: CopickRun) -> Dict[str, Any]:
        return copy_copick_objects_per_run(
            run=run,
            object_type=object_type,
            source_uri=source_uri,
            target_uri=target_uri,
            overwrite=overwrite,
        )

    results = map_runs(
        callback=run_worker,
        root=root,
        runs=runs_to_process,
        workers=workers,
        task_desc="Copying objects",
    )

    return results
