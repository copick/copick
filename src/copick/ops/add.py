import logging
from typing import Any, Dict, Optional, Tuple, Union

import mrcfile
import numpy as np
import zarr

from copick.models import (
    CopickFeatures,
    CopickObject,
    CopickPicks,
    CopickRoot,
    CopickRun,
    CopickSegmentation,
    CopickTomogram,
    CopickVoxelSpacing,
    FilamentSpec,
)
from copick.util.ome import get_level_path, get_voxel_size_from_zarr, volume_pyramid, write_ome_zarr_3d


def _subset(values: Optional[np.ndarray], mask: np.ndarray) -> Optional[np.ndarray]:
    """``values[mask]``, or None when there are no values."""
    return None if values is None else np.asarray(values)[mask]


def _star_read_kwargs(
    root: CopickRoot,
    run_name: str,
    voxel_spacing: Optional[float],
    tilt_series_pixel_size: Optional[float],
    tomograms_star: Optional[str],
) -> Dict[str, Any]:
    """Keyword arguments locating a single-run STAR import: the tomograms.star entries if given, else the centre of
    the run's copick tomogram (at ``voxel_spacing`` if it has one there, else at its smallest voxel spacing with a
    tomogram)."""
    from copick.util.formats import get_tomogram_centers_from_copick, read_relion_tomograms

    kwargs: Dict[str, Any] = {"tilt_series_pixel_size": tilt_series_pixel_size}
    if tomograms_star:
        kwargs["tomograms"] = read_relion_tomograms(tomograms_star)
        return kwargs
    if root.get_run(run_name) is not None:
        centers = get_tomogram_centers_from_copick(root, [run_name], voxel_spacing)
        if run_name not in centers and voxel_spacing is not None:
            centers = get_tomogram_centers_from_copick(root, [run_name], None)
        if run_name in centers:
            kwargs["tomogram_center"] = centers[run_name]
    return kwargs


def _usable_scores(scores: Optional[np.ndarray], file_path: str, log: bool) -> Optional[np.ndarray]:
    """Scores read from a file, or None (every point keeps the default score) if any of them is not finite."""
    if scores is None:
        return None
    scores = np.asarray(scores, dtype=float)
    if not np.all(np.isfinite(scores)):
        if log:
            logging.warning(f"Ignoring scores in {file_path}: not all of them are finite.")
        return None
    return scores


def add_run(
    root: CopickRoot,
    name: str,
    exist_ok: bool = False,
    log: bool = False,
) -> CopickRun:
    """Import a run into copick.

    Args:
        root (CopickRoot): The copick root object.
        name (str): The name of the run.
        exist_ok (bool, optional): If True, do not raise an error if the run already exists. Defaults to False.
        log (bool, optional): Log the operation. Defaults to False.
    """
    run = root.new_run(name, exist_ok)  # , overwrite=overwrite)

    if log:
        logging.log(logging.INFO, f"Added run {name}.")

    return run


def get_or_create_run(
    root: CopickRoot,
    name: str,
    create: bool = True,
    log: bool = False,
) -> CopickRun:
    # Attempt to get
    run = root.get_run(name)

    # If the run does not exist, create it if requested
    if run is None:
        if create:
            run = add_run(root, name, exist_ok=False, log=log)
        else:
            e = ValueError(f"Could not find run {name}.")
            if log:
                logging.exception(e)
            raise e

    return run


def add_voxelspacing(
    root: CopickRoot,
    run: str,
    voxel_spacing: float,
    create: bool = True,
    exist_ok: bool = False,
    log: bool = False,
) -> CopickVoxelSpacing:
    """Import a voxel spacing into copick.

    Args:
        root (CopickRoot): The copick root object.
        run (str): The name of the run.
        voxel_spacing (float): The voxel spacing of the run.
        create (bool, optional): Create the object if it does not exist. Defaults to True.
        exist_ok (bool, optional): If True, do not raise an error if the voxel spacing already exists. Defaults to False.
        log (bool, optional): Log the operation. Defaults to False.
    """
    run = get_or_create_run(root, run, create=create, log=log)
    vs = run.new_voxel_spacing(voxel_spacing, exist_ok)

    if log:
        logging.log(logging.INFO, f"Added voxel spacing {voxel_spacing} to run {run.name}.")

    return vs


def get_or_create_voxelspacing(
    run: CopickRun,
    voxel_size: float,
    create: bool = True,
    log: bool = False,
) -> CopickVoxelSpacing:
    """Get or create a voxel spacing object.

    Args:
        run (CopickRun): The run object.
        voxel_size (float): The voxel size.
        create (bool, optional): Create the object if it does not exist. Defaults to True.
        log (bool, optional): Log the operation. Defaults to False.
    """
    voxel_spacing = run.get_voxel_spacing(voxel_size)

    if voxel_spacing is None:
        if create:
            voxel_spacing = add_voxelspacing(run.root, run.name, voxel_size, create=create, log=log)
        else:
            e = ValueError(f"Could not find voxel spacing {voxel_spacing} in run {run}.")
            if log:
                logging.exception(e)
            raise e

    return voxel_spacing


def add_tomogram(
    root: CopickRoot,
    run: str,
    tomo_type: str,
    volume: Union[np.ndarray, Dict[float, np.ndarray]],
    voxel_spacing: float = None,
    create: bool = True,
    exist_ok: bool = False,
    overwrite: bool = False,
    create_pyramid: bool = False,
    pyramid_levels: int = 3,
    chunks: Tuple[int, ...] = (128, 128, 128),
    transpose: Optional[str] = None,
    flip: Optional[str] = None,
    meta: Dict[str, Any] = None,
    log: bool = False,
) -> CopickTomogram:
    """Add a tomogram to a copick run.

    Args:
        root (CopickRoot): The copick root object.
        volume (Dict[float, np.ndarray]): Multi-scale pyramid of the tomogram. Keys are the voxel size in Angstroms.
        create (bool, optional): Create the object if it does not exist. Defaults to True.
        exist_ok (bool, optional): If True, do not raise an error if the volume already exists. Defaults to False.
        overwrite (bool, optional): Overwrite the object if it exists. Defaults to False.
        run (str, optional): The run the tomogram is part of. Default: Name of the input file.
        transpose (str, optional): Transpose axes. E.g., '2,1,0' to reverse all axes. Default: None.
        flip (str, optional): Flip axes. E.g., '0' to flip Z, '0,2' to flip Z and X. Default: None.
    """

    # Apply transpose if specified
    if transpose:
        axes = tuple(int(x.strip()) for x in transpose.split(","))
        if isinstance(volume, dict):
            volume = {k: np.transpose(v, axes) for k, v in volume.items()}
        else:
            volume = np.transpose(volume, axes)

    # Apply flip if specified (after transpose)
    if flip:
        flip_axes = tuple(int(x.strip()) for x in flip.split(","))
        if isinstance(volume, dict):
            for axis in flip_axes:
                volume = {k: np.flip(v, axis=axis) for k, v in volume.items()}
        else:
            for axis in flip_axes:
                volume = np.flip(volume, axis=axis)

    # Validate input
    if isinstance(volume, np.ndarray) and voxel_spacing is None:
        e = ValueError("Voxel spacing must be provided if volume is an array.")
        if log:
            logging.exception(e)
        raise e

    if isinstance(volume, dict):
        if voxel_spacing is None:
            voxel_spacing = min(volume.keys())
        else:
            if voxel_spacing not in volume:
                e = ValueError(
                    f"Voxel spacing {voxel_spacing} not found in provided pyramid (contains {list(volume.keys())}.",
                )
                if log:
                    logging.exception(e)
                raise e

    if not isinstance(volume, dict):
        volume = {voxel_spacing: volume}

    # Optional: create multiscale pyramid
    pyramid = volume_pyramid(volume[voxel_spacing], voxel_spacing, pyramid_levels) if create_pyramid else volume

    # Attempt to get run and voxel spacing
    runobj = get_or_create_run(root, run, create=create)
    vsobj = get_or_create_voxelspacing(runobj, voxel_spacing, create=create)

    # Create the tomogram
    tomogram = vsobj.new_tomogram(tomo_type, exist_ok=exist_ok)

    # Get the store
    loc = tomogram.zarr()
    write_ome_zarr_3d(
        loc,
        pyramid,
        chunk_size=chunks,
        overwrite=overwrite,
        metadata=meta,
    )

    if log:
        logging.log(logging.INFO, f"Added tomogram {tomo_type} to run {runobj.name}.")

    return tomogram


def z_add_tomogram_mrc(
    root: CopickRoot,
    run: str,
    tomo_type: str,
    volume_file: str,
    voxel_spacing: float = None,
    create: bool = True,
    exist_ok: bool = False,
    overwrite: bool = False,
    create_pyramid: bool = False,
    pyramid_levels: int = 3,
    chunks: Tuple[int, ...] = (128, 128, 128),
    transpose: Optional[str] = None,
    flip: Optional[str] = None,
    meta: Dict[str, Any] = None,
    log: bool = False,
) -> CopickTomogram:
    """Add a tomogram to a copick run.

    Args:
        root (CopickRoot): The copick root object.
        volume_file (str): The path to the volume file.
        create (bool, optional): Create the object if it does not exist. Defaults to True.
        exist_ok (bool, optional): If True, do not raise an error if the volume already exists. Defaults to False.
        overwrite (bool, optional): Overwrite the object if it exists. Defaults to False.
        run (str, optional): The run the tomogram is part of. Default: Name of the input file.
        transpose (str, optional): Transpose axes. E.g., '2,1,0' to reverse all axes. Default: None.
        flip (str, optional): Flip axes. E.g., '0' to flip Z, '0,2' to flip Z and X. Default: None.
    """

    with mrcfile.open(volume_file) as mrc:
        volume = mrc.data
        voxel_size = float(mrc.voxel_size.x)

    if voxel_spacing:
        voxel_size = voxel_spacing

    return add_tomogram(
        root,
        run,
        tomo_type,
        volume,
        voxel_spacing=voxel_size,
        create=create,
        exist_ok=exist_ok,
        overwrite=overwrite,
        create_pyramid=create_pyramid,
        pyramid_levels=pyramid_levels,
        chunks=chunks,
        transpose=transpose,
        flip=flip,
        meta=meta,
        log=log,
    )


def _add_tomogram_zarr(
    root: CopickRoot,
    run: str,
    tomo_type: str,
    volume_file: str,
    voxel_spacing: float = None,
    create: bool = True,
    exist_ok: bool = False,
    overwrite: bool = False,
    create_pyramid: bool = False,
    pyramid_levels: int = 3,
    chunks: Tuple[int, int, int] = (128, 128, 128),
    transpose: Optional[str] = None,
    flip: Optional[str] = None,
    meta: Dict[str, Any] = None,
    log: bool = False,
) -> CopickTomogram:
    """Add a tomogram to a copick run.

    Args:
        root (CopickRoot): The copick root object.
        volume_file (str): The path to the volume file.
        create (bool, optional): Create the object if it does not exist. Defaults to True.
        exist_ok (bool, optional): If True, do not raise an error if the volume already exists. Defaults to False.
        overwrite (bool, optional): Overwrite the object if it exists. Defaults to False.
        run (str, optional): The run the tomogram is part of. Default: Name of the input file.
        transpose (str, optional): Transpose axes. E.g., '2,1,0' to reverse all axes. Default: None.
        flip (str, optional): Flip axes. E.g., '0' to flip Z, '0,2' to flip Z and X. Default: None.
    """

    zarr_group = zarr.open(volume_file, mode="r")
    # Get the first level data (level 0)
    volume = np.array(zarr_group[get_level_path(zarr_group, 0)])
    voxel_size = get_voxel_size_from_zarr(zarr_group)

    if voxel_spacing:
        voxel_size = voxel_spacing

    return add_tomogram(
        root,
        run,
        tomo_type,
        volume,
        voxel_spacing=voxel_size,
        create=create,
        exist_ok=exist_ok,
        overwrite=overwrite,
        create_pyramid=create_pyramid,
        pyramid_levels=pyramid_levels,
        chunks=chunks,
        transpose=transpose,
        flip=flip,
        meta=meta,
        log=log,
    )


def add_features(
    root: CopickRoot,
    run: str,
    voxel_spacing: float,
    tomo_type: str,
    feature_type: str,
    features_vol: np.ndarray,
    exist_ok: bool = False,
    overwrite: bool = False,
    chunks: Tuple[int, int, int] = (128, 128, 128),
    meta: Dict[str, Any] = None,
    log: bool = False,
    shards: Optional[Tuple[int, ...]] = None,
) -> CopickFeatures:
    """Add features to a copick run.

    Args:
        root (CopickRoot): The copick root object.
        features_vol: A 3D ``(z, y, x)`` volume or 4D ``(feature, z, y, x)`` array.
        run (str): The run the features are part of.
        voxel_spacing: Voxel spacing of the associated tomogram and spatial feature axes.
        tomo_type: Type of the associated tomogram.
        feature_type: Name of the feature map.
        exist_ok (bool, optional): If True, do not raise an error if the features already exist. Defaults to False.
        overwrite (bool, optional): Overwrite the object if it exists. Defaults to False.
        chunks: Inner chunks. A spatial 3-tuple is expanded with a leading one for 4D data.
        meta: Optional OME multiscale metadata.
        log (bool, optional): Log the operation. Defaults to False.
        shards: Optional dimension-matched shard shape.
    """
    runobj = get_or_create_run(root, run, create=False)
    vsobj = get_or_create_voxelspacing(runobj, voxel_spacing, create=False)
    tomogram = vsobj.get_tomogram(tomo_type)

    if tomogram is None:
        e = ValueError(f"Could not find tomogram {tomo_type} in run {run}.")
        if log:
            logging.exception(e)
        raise e

    # Create the features
    features = tomogram.new_features(feature_type, exist_ok=exist_ok)

    features.from_numpy(
        features_vol,
        chunks=chunks,
        shards=shards,
        metadata=meta,
        overwrite=overwrite,
    )

    # Log
    if log:
        logging.log(logging.INFO, f"Added features {feature_type} to tomogram {tomo_type} in run {run}.")

    return features


def add_segmentation(
    root: CopickRoot,
    run: str,
    mask_path: str,
    voxel_spacing: float,
    name: str,
    user_id: str,
    session_id: str,
    multilabel: bool = False,
    instance: bool = False,
    transpose: Optional[str] = None,
    flip: Optional[str] = None,
    create: bool = True,
    exist_ok: bool = False,
    overwrite: bool = False,
    log: bool = False,
):
    """
    Add a segmentation to a copick run.

    Args:
        root (CopickRoot): The copick root object.
        segmentation_file (str): The path to the segmentation file.
        multilabel (bool, optional): Whether this is a multilabel segmentation. Defaults to False.
        instance (bool, optional): Whether this is an instance segmentation (voxel = instance ID of the object
            `name`). Defaults to False.
        create (bool, optional): Create the object if it does not exist. Defaults to True.
        exist_ok (bool, optional): If True, do not raise an error if the segmentation already exists. Defaults to False.
        overwrite (bool, optional): Overwrite the object if it exists. Defaults to False.
        transpose (str, optional): Transpose axes. E.g., '2,1,0' to reverse all axes. Default: None.
        flip (str, optional): Flip axes. E.g., '0' to flip Z, '0,2' to flip Z and X. Default: None.
    """

    # Read the Segmentation Mask
    if mask_path.endswith(".mrc"):
        with mrcfile.open(mask_path) as mrc:
            volume = mrc.data
    else:
        raise ValueError(f"Unsupported file type: {mask_path}")

    # Apply transpose if specified
    if transpose:
        axes = tuple(int(x.strip()) for x in transpose.split(","))
        volume = np.transpose(volume, axes)

    # Apply flip if specified (after transpose)
    if flip:
        flip_axes = tuple(int(x.strip()) for x in flip.split(","))
        for axis in flip_axes:
            volume = np.flip(volume, axis=axis)

    # Attempt to get run and voxel spacing
    runobj = get_or_create_run(root, run, create=create)

    # Create a new segmentation
    segmentation = runobj.new_segmentation(
        name=name,
        user_id=user_id,
        is_multilabel=multilabel,
        is_instance=instance,
        voxel_size=voxel_spacing,
        session_id=session_id,
        exist_ok=exist_ok,
        overwrite=overwrite,
    )

    # Write the segmentation data
    segmentation.from_numpy(volume)

    if log:
        logging.log(logging.INFO, f"Added segmentation {name} to run {runobj.name}.")

    return segmentation


def add_object(
    root: CopickRoot,
    name: str,
    is_particle: bool,
    label: Optional[int] = None,
    color: Optional[Tuple[int, int, int, int]] = None,
    emdb_id: Optional[str] = None,
    pdb_id: Optional[str] = None,
    identifier: Optional[str] = None,
    map_threshold: Optional[float] = None,
    radius: Optional[float] = None,
    volume: Optional[np.ndarray] = None,
    voxel_size: Optional[float] = None,
    metadata: Optional[Dict[str, Any]] = None,
    exist_ok: bool = False,
    save_config: bool = False,
    config_path: Optional[str] = None,
    log: bool = False,
    filament: Union[FilamentSpec, Dict[str, Any], None] = None,
) -> CopickObject:
    """Add a new pickable object to the copick root configuration.

    Args:
        root: The copick root object.
        name: Name of the object.
        is_particle: Whether this object should be represented by points (True) or segmentation masks (False).
        label: Numeric label/id for the object. If None, will use the next available label.
        color: RGBA color for the object. If None, will use a default color.
        emdb_id: EMDB ID for the object.
        pdb_id: PDB ID for the object.
        identifier: Identifier for the object (e.g. Gene Ontology ID or UniProtKB accession).
        map_threshold: Threshold to apply to the map when rendering the isosurface.
        radius: Radius of the particle, when displaying as a sphere.
        volume: Optional volume data to associate with the object.
        voxel_size: Voxel size for the volume data. Required if volume is provided.
        metadata: Optional metadata dictionary to associate with the object.
        exist_ok: Whether existing objects with the same name should be overwritten..
        save_config: Whether to save the configuration to disk after adding the object.
        config_path: Path to save the configuration. Required if save_config is True.
        log: Whether to log the operation.
        filament: Declare the object a filament (see ``copick.models.FilamentSpec``); stored as
            ``metadata["copick"]["filament"]``. Requires ``is_particle=True``.

    Returns:
        CopickObject: The newly created object.

    Raises:
        ValueError: If volume is provided but voxel_size is not, or if save_config is True but config_path is not provided.
    """
    if volume is not None and voxel_size is None:
        e = ValueError("voxel_size must be provided if volume is provided.")
        if log:
            logging.exception(e)
        raise e

    if save_config and config_path is None:
        e = ValueError("config_path must be provided if save_config is True.")
        if log:
            logging.exception(e)
        raise e

    # Create the object
    obj = root.new_object(
        name=name,
        is_particle=is_particle,
        label=label,
        color=color,
        emdb_id=emdb_id,
        pdb_id=pdb_id,
        identifier=identifier,
        map_threshold=map_threshold,
        radius=radius,
        metadata=metadata or {},
        exist_ok=exist_ok,
        filament=filament,
    )

    # Add volume data if provided
    if volume is not None:
        obj.from_numpy(volume, voxel_size)

    # Save configuration if requested
    if save_config:
        root.save_config(config_path)

    if log:
        logging.log(logging.INFO, f"Added object {name} to root configuration.")

    return obj


def add_object_volume(
    root: CopickRoot,
    object_name: str,
    volume: np.ndarray,
    voxel_size: float,
    log: bool = False,
) -> CopickObject:
    """Add volume data to an existing pickable object.

    Args:
        root: The copick root object.
        object_name: Name of the existing object.
        volume: Volume data to add.
        voxel_size: Voxel size of the volume data.
        log: Whether to log the operation.

    Returns:
        CopickObject: The updated object.

    Raises:
        ValueError: If the object does not exist or if the object is not a particle.
    """
    obj = root.get_object(object_name)
    if obj is None:
        e = ValueError(f"Object {object_name} not found in root configuration.")
        if log:
            logging.exception(e)
        raise e

    if not obj.is_particle:
        e = ValueError(f"Object {object_name} is not a particle object and cannot have volume data.")
        if log:
            logging.exception(e)
        raise e

    # Check if the object is read-only
    if obj.read_only:
        e = ValueError(
            f"Object {object_name} is read-only and cannot be modified. Volume data cannot be added to read-only objects.",
        )
        if log:
            logging.exception(e)
        raise e

    obj.from_numpy(volume, voxel_size)

    if log:
        logging.log(logging.INFO, f"Added volume data to object {object_name}.")

    return obj


# =============================================================================
# Picks Import Functions
# =============================================================================


def add_picks(
    root: CopickRoot,
    run_name: str,
    path: str,
    object_name: str,
    user_id: str,
    session_id: str,
    voxel_spacing: float,
    file_type: Optional[str] = None,
    tomogram_dimensions: Optional[Tuple[int, int, int]] = None,
    create: bool = True,
    exist_ok: bool = False,
    overwrite: bool = False,
    log: bool = False,
) -> CopickPicks:
    """Add picks to a copick run from various file formats.

    Args:
        root: The copick root object.
        run_name: Name of the run to add picks to.
        path: Path to the picks file.
        object_name: Name of the pickable object.
        user_id: User ID for the picks.
        session_id: Session ID for the picks.
        voxel_spacing: Voxel spacing in Angstrom (for coordinate conversion).
        file_type: File type ("em", "star", "dynamo", "csv"). Auto-detected if None.
        tomogram_dimensions: (X, Y, Z) dimensions in voxels (required for EM format).
        create: Create the run if it doesn't exist.
        exist_ok: Don't raise error if picks already exist.
        overwrite: Overwrite existing picks.
        log: Log the operation.

    Returns:
        The created CopickPicks object.

    Raises:
        ValueError: If file type cannot be determined or is unsupported.
    """
    from copick.util.formats import get_picks_format_from_extension

    # Auto-detect file type if not provided
    if file_type is None:
        file_type = get_picks_format_from_extension(path)
        if file_type is None:
            e = ValueError(f"Could not determine file type from path: {path}")
            if log:
                logging.exception(e)
            raise e

    file_type = file_type.lower()

    if file_type == "em":
        return _add_picks_em(
            root=root,
            run_name=run_name,
            path=path,
            object_name=object_name,
            user_id=user_id,
            session_id=session_id,
            voxel_spacing=voxel_spacing,
            create=create,
            exist_ok=exist_ok,
            overwrite=overwrite,
            log=log,
        )
    elif file_type == "star":
        return _add_picks_star(
            root=root,
            run_name=run_name,
            path=path,
            object_name=object_name,
            user_id=user_id,
            session_id=session_id,
            voxel_spacing=voxel_spacing,
            create=create,
            exist_ok=exist_ok,
            overwrite=overwrite,
            log=log,
        )
    elif file_type == "dynamo":
        return _add_picks_dynamo(
            root=root,
            run_name=run_name,
            path=path,
            object_name=object_name,
            user_id=user_id,
            session_id=session_id,
            voxel_spacing=voxel_spacing,
            create=create,
            exist_ok=exist_ok,
            overwrite=overwrite,
            log=log,
        )
    elif file_type == "csv":
        # CSV returns a dict of picks by run_name, return the one for specified run
        results = _add_picks_csv(
            root=root,
            path=path,
            object_name=object_name,
            user_id=user_id,
            session_id=session_id,
            create=create,
            exist_ok=exist_ok,
            overwrite=overwrite,
            log=log,
        )
        if run_name in results:
            return results[run_name]
        elif len(results) == 1:
            return list(results.values())[0]
        else:
            e = ValueError(f"Run {run_name} not found in CSV file. Available runs: {list(results.keys())}")
            if log:
                logging.exception(e)
            raise e
    else:
        e = ValueError(f"Unsupported file type: {file_type}")
        if log:
            logging.exception(e)
        raise e


def _add_picks_em(
    root: CopickRoot,
    run_name: str,
    path: str,
    object_name: str,
    user_id: str,
    session_id: str,
    voxel_spacing: float,
    create: bool = True,
    exist_ok: bool = False,
    overwrite: bool = False,
    log: bool = False,
) -> CopickPicks:
    """Add picks from a TOM toolbox EM motivelist file.

    Args:
        root: The copick root object.
        run_name: Name of the run.
        path: Path to the EM file.
        object_name: Name of the pickable object.
        user_id: User ID for the picks.
        session_id: Session ID for the picks.
        voxel_spacing: Voxel spacing in Angstrom.
        create: Create run if it doesn't exist.
        exist_ok: Don't raise error if picks exist.
        overwrite: Overwrite existing picks.
        log: Log the operation.

    Returns:
        The created CopickPicks object.
    """
    from copick.util.formats import em_to_copick_transform, read_em_motivelist

    # Read the EM file
    positions_px, eulers_deg, scores, shifts_px = read_em_motivelist(path, include_shifts=True)

    # Get or create run
    runobj = get_or_create_run(root, run_name, create=create, log=log)

    # Convert to copick format (no tomogram dimensions needed - TOM uses corner-origin)
    points_angstrom, transforms = em_to_copick_transform(
        positions_px,
        eulers_deg,
        voxel_spacing,
        shifts_px=shifts_px,
    )

    # Create the picks
    picks = runobj.new_picks(
        object_name=object_name,
        user_id=user_id,
        session_id=session_id,
        exist_ok=exist_ok or overwrite,
    )

    picks.from_numpy(points_angstrom, transforms, scores=_usable_scores(scores, path, log))

    if log:
        logging.info(f"Added {len(points_angstrom)} picks from EM file to run {run_name}.")

    return picks


def _add_picks_star(
    root: CopickRoot,
    run_name: str,
    path: str,
    object_name: str,
    user_id: str,
    session_id: str,
    voxel_spacing: float,
    create: bool = True,
    exist_ok: bool = False,
    overwrite: bool = False,
    log: bool = False,
) -> CopickPicks:
    """Add picks from a RELION STAR file.

    Args:
        root: The copick root object.
        run_name: Name of the run.
        path: Path to the STAR file.
        object_name: Name of the pickable object.
        user_id: User ID for the picks.
        session_id: Session ID for the picks.
        voxel_spacing: Voxel spacing in Angstrom (for coordinate conversion).
        create: Create run if it doesn't exist.
        exist_ok: Don't raise error if picks exist.
        overwrite: Overwrite existing picks.
        log: Log the operation.

    Returns:
        The created CopickPicks object.
    """
    from copick.util.handlers.picks.star import star_handler

    # Read the STAR file: coordinates, orientations and shifts as in RELION (see STARPicksHandler)
    positions_angstrom, transforms, _, instance_ids = star_handler.read(path, voxel_spacing, tomo_name=run_name)

    # Get or create run
    runobj = get_or_create_run(root, run_name, create=create, log=log)

    # Create the picks
    picks = runobj.new_picks(
        object_name=object_name,
        user_id=user_id,
        session_id=session_id,
        exist_ok=exist_ok or overwrite,
    )

    picks.from_numpy(positions_angstrom, transforms, instance_ids=instance_ids)

    if log:
        logging.info(f"Added {len(positions_angstrom)} picks from STAR file to run {run_name}.")

    return picks


def _add_picks_dynamo(
    root: CopickRoot,
    run_name: str,
    path: str,
    object_name: str,
    user_id: str,
    session_id: str,
    voxel_spacing: float,
    create: bool = True,
    exist_ok: bool = False,
    overwrite: bool = False,
    log: bool = False,
) -> CopickPicks:
    """Add picks from a Dynamo table file.

    Args:
        root: The copick root object.
        run_name: Name of the run.
        path: Path to the .tbl file.
        object_name: Name of the pickable object.
        user_id: User ID for the picks.
        session_id: Session ID for the picks.
        voxel_spacing: Voxel spacing in Angstrom.
        create: Create run if it doesn't exist.
        exist_ok: Don't raise error if picks exist.
        overwrite: Overwrite existing picks.
        log: Log the operation.

    Returns:
        The created CopickPicks object.
    """
    from copick.util.formats import dynamo_to_copick_transform, read_dynamo_table

    # Read the Dynamo table
    positions_px, eulers_deg, shifts_px, scores = read_dynamo_table(path)

    # Convert to copick format
    points_angstrom, transforms = dynamo_to_copick_transform(
        positions_px,
        eulers_deg,
        shifts_px,
        voxel_spacing,
    )

    # Get or create run
    runobj = get_or_create_run(root, run_name, create=create, log=log)

    # Create the picks
    picks = runobj.new_picks(
        object_name=object_name,
        user_id=user_id,
        session_id=session_id,
        exist_ok=exist_ok or overwrite,
    )

    picks.from_numpy(points_angstrom, transforms, scores=_usable_scores(scores, path, log))

    if log:
        logging.info(f"Added {len(points_angstrom)} picks from Dynamo table to run {run_name}.")

    return picks


def _add_picks_dynamo_grouped(
    root: CopickRoot,
    path: str,
    object_name: str,
    user_id: str,
    session_id: str,
    voxel_spacing: float,
    index_to_run: Dict[int, str],
    create: bool = True,
    exist_ok: bool = False,
    overwrite: bool = False,
    log: bool = False,
) -> Dict[str, CopickPicks]:
    """Add picks from a Dynamo table file, grouping by tomogram index.

    Args:
        root: The copick root object.
        path: Path to the .tbl file.
        object_name: Name of the pickable object.
        user_id: User ID for the picks.
        session_id: Session ID for the picks.
        voxel_spacing: Voxel spacing in Angstrom.
        index_to_run: Mapping from tomogram index to run name.
        create: Create run if it doesn't exist.
        exist_ok: Don't raise error if picks exist.
        overwrite: Overwrite existing picks.
        log: Log the operation.

    Returns:
        Dictionary mapping run names to created CopickPicks objects.
    """
    from copick.util.formats import dynamo_to_copick_transform, read_dynamo_table

    # Read the Dynamo table with tomogram indices
    positions_px, eulers_deg, shifts_px, scores, tomo_indices = read_dynamo_table(
        path,
        include_tomo_index=True,
    )

    # Group particles by tomogram index
    unique_indices = np.unique(tomo_indices)
    results = {}
    skipped_count = 0

    for tomo_idx in unique_indices:
        tomo_idx = int(tomo_idx)

        # Check if this index is in the mapping
        if tomo_idx not in index_to_run:
            mask = tomo_indices == tomo_idx
            skipped_count += np.sum(mask)
            if log:
                logging.warning(
                    f"Tomogram index {tomo_idx} not found in mapping, skipping {np.sum(mask)} particles.",
                )
            continue

        run_name = index_to_run[tomo_idx]

        # Get particles for this tomogram
        mask = tomo_indices == tomo_idx
        pos_subset = positions_px[mask]
        euler_subset = eulers_deg[mask]
        shift_subset = shifts_px[mask]

        # Convert to copick format
        points_angstrom, transforms = dynamo_to_copick_transform(
            pos_subset,
            euler_subset,
            shift_subset,
            voxel_spacing,
        )

        # Get or create run
        runobj = get_or_create_run(root, run_name, create=create, log=log)

        # Create the picks
        picks = runobj.new_picks(
            object_name=object_name,
            user_id=user_id,
            session_id=session_id,
            exist_ok=exist_ok or overwrite,
        )

        picks.from_numpy(points_angstrom, transforms, scores=_usable_scores(_subset(scores, mask), path, log))
        results[run_name] = picks

        if log:
            logging.info(
                f"Added {len(points_angstrom)} picks from Dynamo table to run {run_name}.",
            )

    if skipped_count > 0 and log:
        logging.warning(f"Total skipped particles due to unmapped indices: {skipped_count}")

    return results


def _add_picks_em_grouped(
    root: CopickRoot,
    path: str,
    object_name: str,
    user_id: str,
    session_id: str,
    voxel_spacing: float,
    index_to_run: Dict[int, str],
    tomo_index_row: int = 4,
    create: bool = True,
    exist_ok: bool = False,
    overwrite: bool = False,
    log: bool = False,
) -> Dict[str, CopickPicks]:
    """Add picks from a TOM toolbox EM motivelist file, grouping by tomogram index.

    Args:
        root: The copick root object.
        path: Path to the EM file.
        object_name: Name of the pickable object.
        user_id: User ID for the picks.
        session_id: Session ID for the picks.
        voxel_spacing: Voxel spacing in Angstrom.
        index_to_run: Mapping from tomogram index to run name.
        tomo_index_row: Row index (0-based) containing tomogram indices (default: 4).
        create: Create run if it doesn't exist.
        exist_ok: Don't raise error if picks exist.
        overwrite: Overwrite existing picks.
        log: Log the operation.

    Returns:
        Dictionary mapping run names to created CopickPicks objects.
    """
    from copick.util.formats import em_to_copick_transform, read_em_motivelist

    # Read the EM file with tomogram indices and shifts
    positions_px, eulers_deg, scores, tomo_indices, shifts_px = read_em_motivelist(
        path,
        include_tomo_index=True,
        tomo_index_row=tomo_index_row,
        include_shifts=True,
    )

    # Group particles by tomogram index
    unique_indices = np.unique(tomo_indices)
    results = {}
    skipped_count = 0

    for tomo_idx in unique_indices:
        tomo_idx = int(tomo_idx)

        # Check if this index is in the mapping
        if tomo_idx not in index_to_run:
            mask = tomo_indices == tomo_idx
            skipped_count += np.sum(mask)
            if log:
                logging.warning(
                    f"Tomogram index {tomo_idx} not found in mapping, skipping {np.sum(mask)} particles.",
                )
            continue

        run_name = index_to_run[tomo_idx]

        # Get particles for this tomogram
        mask = tomo_indices == tomo_idx
        pos_subset = positions_px[mask]
        euler_subset = eulers_deg[mask]

        # Get or create run
        runobj = get_or_create_run(root, run_name, create=create, log=log)

        # Convert to copick format (no tomogram dimensions needed - TOM uses corner-origin)
        points_angstrom, transforms = em_to_copick_transform(
            pos_subset,
            euler_subset,
            voxel_spacing,
            shifts_px=shifts_px[mask],
        )

        # Create the picks
        picks = runobj.new_picks(
            object_name=object_name,
            user_id=user_id,
            session_id=session_id,
            exist_ok=exist_ok or overwrite,
        )

        picks.from_numpy(points_angstrom, transforms, scores=_usable_scores(_subset(scores, mask), path, log))
        results[run_name] = picks

        if log:
            logging.info(f"Added {len(points_angstrom)} picks from EM file to run {run_name}.")

    if skipped_count > 0 and log:
        logging.warning(f"Total skipped particles due to unmapped indices: {skipped_count}")

    return results


def _add_picks_csv(
    root: CopickRoot,
    path: str,
    object_name: str,
    user_id: str,
    session_id: str,
    create: bool = True,
    exist_ok: bool = False,
    overwrite: bool = False,
    log: bool = False,
) -> Dict[str, CopickPicks]:
    """Add picks from a copick CSV file.

    The CSV file contains a run_name column, so picks are grouped by run.

    Args:
        root: The copick root object.
        path: Path to the CSV file.
        object_name: Name of the pickable object.
        user_id: User ID for the picks.
        session_id: Session ID for the picks.
        create: Create runs if they don't exist.
        exist_ok: Don't raise error if picks exist.
        overwrite: Overwrite existing picks.
        log: Log the operation.

    Returns:
        Dictionary mapping run names to created CopickPicks objects.
    """
    from copick.util.formats import csv_to_copick_arrays, read_picks_csv
    from copick.util.handlers import unpack_picks_data

    # Read the CSV file
    df = read_picks_csv(path)

    # Convert to copick arrays grouped by run
    run_data = csv_to_copick_arrays(df, include_instance_ids="instance_id" in df.columns)

    results = {}
    for run_name, arrays in run_data.items():
        positions, transforms, scores, instance_ids = unpack_picks_data(arrays)
        # Get or create run
        runobj = get_or_create_run(root, run_name, create=create, log=log)

        # Create the picks
        picks = runobj.new_picks(
            object_name=object_name,
            user_id=user_id,
            session_id=session_id,
            exist_ok=exist_ok or overwrite,
        )

        picks.from_numpy(positions, transforms, instance_ids=instance_ids, scores=_usable_scores(scores, path, log))
        results[run_name] = picks

        if log:
            logging.info(f"Added {len(positions)} picks from CSV to run {run_name}.")

    return results


# =============================================================================
# Extended Tomogram Import Functions
# =============================================================================


def _add_tomogram_tiff(
    root: CopickRoot,
    run: str,
    tomo_type: str,
    volume_file: str,
    voxel_spacing: float,
    create: bool = True,
    exist_ok: bool = False,
    overwrite: bool = False,
    create_pyramid: bool = False,
    pyramid_levels: int = 3,
    chunks: Tuple[int, ...] = (128, 128, 128),
    transpose: Optional[str] = None,
    flip: Optional[str] = None,
    meta: Dict[str, Any] = None,
    log: bool = False,
) -> CopickTomogram:
    """Add a tomogram from a TIFF stack to a copick run.

    Args:
        root: The copick root object.
        run: The name of the run.
        tomo_type: The type of tomogram.
        volume_file: Path to the TIFF file.
        voxel_spacing: Voxel spacing in Angstrom (required for TIFF).
        create: Create the object if it doesn't exist.
        exist_ok: Don't raise error if volume exists.
        overwrite: Overwrite if exists.
        create_pyramid: Create multiscale pyramid.
        pyramid_levels: Number of pyramid levels.
        chunks: Chunk size for Zarr store.
        transpose: Transpose axes. E.g., '2,1,0' to reverse all axes. Default: None.
        flip: Flip axes. E.g., '0' to flip Z, '0,2' to flip Z and X. Default: None.
        meta: Optional metadata.
        log: Log the operation.

    Returns:
        The created CopickTomogram object.
    """
    from copick.util.formats import read_tiff_volume

    if voxel_spacing is None:
        e = ValueError("voxel_spacing must be provided for TIFF import.")
        if log:
            logging.exception(e)
        raise e

    volume = read_tiff_volume(volume_file)

    return add_tomogram(
        root,
        run,
        tomo_type,
        volume,
        voxel_spacing=voxel_spacing,
        create=create,
        exist_ok=exist_ok,
        overwrite=overwrite,
        create_pyramid=create_pyramid,
        pyramid_levels=pyramid_levels,
        chunks=chunks,
        transpose=transpose,
        flip=flip,
        meta=meta,
        log=log,
    )


def _add_tomogram_em(
    root: CopickRoot,
    run: str,
    tomo_type: str,
    volume_file: str,
    voxel_spacing: float,
    create: bool = True,
    exist_ok: bool = False,
    overwrite: bool = False,
    create_pyramid: bool = False,
    pyramid_levels: int = 3,
    chunks: Tuple[int, ...] = (128, 128, 128),
    transpose: Optional[str] = None,
    flip: Optional[str] = None,
    meta: Dict[str, Any] = None,
    log: bool = False,
) -> CopickTomogram:
    """Add a tomogram from a TOM toolbox EM volume to a copick run.

    Args:
        root: The copick root object.
        run: The name of the run.
        tomo_type: The type of tomogram.
        volume_file: Path to the EM file.
        voxel_spacing: Voxel spacing in Angstrom (required for EM).
        create: Create the object if it doesn't exist.
        exist_ok: Don't raise error if volume exists.
        overwrite: Overwrite if exists.
        create_pyramid: Create multiscale pyramid.
        pyramid_levels: Number of pyramid levels.
        chunks: Chunk size for Zarr store.
        transpose: Transpose axes. E.g., '2,1,0' to reverse all axes. Default: None.
        flip: Flip axes. E.g., '0' to flip Z, '0,2' to flip Z and X. Default: None.
        meta: Optional metadata.
        log: Log the operation.

    Returns:
        The created CopickTomogram object.
    """
    from copick.util.formats import read_em_volume

    if voxel_spacing is None:
        e = ValueError("voxel_spacing must be provided for EM import.")
        if log:
            logging.exception(e)
        raise e

    volume = read_em_volume(volume_file)

    return add_tomogram(
        root,
        run,
        tomo_type,
        volume,
        voxel_spacing=voxel_spacing,
        create=create,
        exist_ok=exist_ok,
        overwrite=overwrite,
        create_pyramid=create_pyramid,
        pyramid_levels=pyramid_levels,
        chunks=chunks,
        transpose=transpose,
        flip=flip,
        meta=meta,
        log=log,
    )


# =============================================================================
# Extended Segmentation Import Functions
# =============================================================================


def _add_segmentation_from_array(
    root: CopickRoot,
    run: str,
    volume: np.ndarray,
    voxel_spacing: float,
    name: str,
    user_id: str,
    session_id: str,
    multilabel: bool = False,
    instance: bool = False,
    transpose: Optional[str] = None,
    flip: Optional[str] = None,
    create: bool = True,
    exist_ok: bool = False,
    overwrite: bool = False,
    log: bool = False,
) -> CopickSegmentation:
    """Add a segmentation from a numpy array.

    Args:
        root: The copick root object.
        run: The name of the run.
        volume: The segmentation volume as numpy array.
        voxel_spacing: Voxel spacing in Angstrom.
        name: Name of the segmentation.
        user_id: User ID for the segmentation.
        session_id: Session ID for the segmentation.
        multilabel: Whether this is a multilabel segmentation.
        instance: Whether this is an instance segmentation (voxel = instance ID of the object `name`).
        transpose: Transpose axes. E.g., '2,1,0' to reverse all axes. Default: None.
        flip: Flip axes. E.g., '0' to flip Z, '0,2' to flip Z and X. Default: None.
        create: Create run if it doesn't exist.
        exist_ok: Don't raise error if segmentation exists.
        overwrite: Overwrite if exists.
        log: Log the operation.

    Returns:
        The created CopickSegmentation object.
    """
    # Apply transpose if specified
    if transpose:
        axes = tuple(int(x.strip()) for x in transpose.split(","))
        volume = np.transpose(volume, axes)

    # Apply flip if specified (after transpose)
    if flip:
        flip_axes = tuple(int(x.strip()) for x in flip.split(","))
        for axis in flip_axes:
            volume = np.flip(volume, axis=axis)

    runobj = get_or_create_run(root, run, create=create)

    segmentation = runobj.new_segmentation(
        name=name,
        user_id=user_id,
        is_multilabel=multilabel,
        is_instance=instance,
        voxel_size=voxel_spacing,
        session_id=session_id,
        exist_ok=exist_ok,
        overwrite=overwrite,
    )

    segmentation.from_numpy(volume)

    if log:
        logging.info(f"Added segmentation {name} to run {run}.")

    return segmentation


def _add_segmentation_tiff(
    root: CopickRoot,
    run: str,
    volume_file: str,
    voxel_spacing: float,
    name: str,
    user_id: str,
    session_id: str,
    multilabel: bool = False,
    instance: bool = False,
    transpose: Optional[str] = None,
    flip: Optional[str] = None,
    create: bool = True,
    exist_ok: bool = False,
    overwrite: bool = False,
    log: bool = False,
) -> CopickSegmentation:
    """Add a segmentation from a TIFF stack.

    Args:
        root: The copick root object.
        run: The name of the run.
        volume_file: Path to the TIFF file.
        voxel_spacing: Voxel spacing in Angstrom.
        name: Name of the segmentation.
        user_id: User ID for the segmentation.
        session_id: Session ID for the segmentation.
        multilabel: Whether this is a multilabel segmentation.
        instance: Whether this is an instance segmentation (voxel = instance ID of the object `name`).
        transpose: Transpose axes. E.g., '2,1,0' to reverse all axes. Default: None.
        flip: Flip axes. E.g., '0' to flip Z, '0,2' to flip Z and X. Default: None.
        create: Create run if it doesn't exist.
        exist_ok: Don't raise error if segmentation exists.
        overwrite: Overwrite if exists.
        log: Log the operation.

    Returns:
        The created CopickSegmentation object.
    """
    from copick.util.formats import read_tiff_volume

    if voxel_spacing is None:
        e = ValueError("voxel_spacing must be provided for TIFF import.")
        if log:
            logging.exception(e)
        raise e

    volume = read_tiff_volume(volume_file)

    return _add_segmentation_from_array(
        root=root,
        run=run,
        volume=volume,
        voxel_spacing=voxel_spacing,
        name=name,
        user_id=user_id,
        session_id=session_id,
        multilabel=multilabel,
        instance=instance,
        transpose=transpose,
        flip=flip,
        create=create,
        exist_ok=exist_ok,
        overwrite=overwrite,
        log=log,
    )


def _add_segmentation_em(
    root: CopickRoot,
    run: str,
    volume_file: str,
    voxel_spacing: float,
    name: str,
    user_id: str,
    session_id: str,
    multilabel: bool = False,
    instance: bool = False,
    transpose: Optional[str] = None,
    flip: Optional[str] = None,
    create: bool = True,
    exist_ok: bool = False,
    overwrite: bool = False,
    log: bool = False,
) -> CopickSegmentation:
    """Add a segmentation from a TOM toolbox EM volume.

    Args:
        root: The copick root object.
        run: The name of the run.
        volume_file: Path to the EM file.
        voxel_spacing: Voxel spacing in Angstrom.
        name: Name of the segmentation.
        user_id: User ID for the segmentation.
        session_id: Session ID for the segmentation.
        multilabel: Whether this is a multilabel segmentation.
        instance: Whether this is an instance segmentation (voxel = instance ID of the object `name`).
        transpose: Transpose axes. E.g., '2,1,0' to reverse all axes. Default: None.
        flip: Flip axes. E.g., '0' to flip Z, '0,2' to flip Z and X. Default: None.
        create: Create run if it doesn't exist.
        exist_ok: Don't raise error if segmentation exists.
        overwrite: Overwrite if exists.
        log: Log the operation.

    Returns:
        The created CopickSegmentation object.
    """
    from copick.util.formats import read_em_volume

    if voxel_spacing is None:
        e = ValueError("voxel_spacing must be provided for EM import.")
        if log:
            logging.exception(e)
        raise e

    volume = read_em_volume(volume_file)

    return _add_segmentation_from_array(
        root=root,
        run=run,
        volume=volume,
        voxel_spacing=voxel_spacing,
        name=name,
        user_id=user_id,
        session_id=session_id,
        multilabel=multilabel,
        instance=instance,
        transpose=transpose,
        flip=flip,
        create=create,
        exist_ok=exist_ok,
        overwrite=overwrite,
        log=log,
    )


# =============================================================================
# Unified Entry Points using Handler Registry
# =============================================================================


def add_tomogram_from_file(
    root: CopickRoot,
    run_name: str,
    tomo_type: str,
    file_path: str,
    voxel_spacing: Optional[float] = None,
    file_type: Optional[str] = None,
    create_pyramid: bool = True,
    pyramid_levels: int = 3,
    chunks: Tuple[int, int, int] = (128, 128, 128),
    transpose: Optional[str] = None,
    flip: Optional[str] = None,
    create: bool = True,
    exist_ok: bool = False,
    overwrite: bool = False,
    log: bool = False,
) -> CopickTomogram:
    """Add a tomogram from any supported file format using the handler registry.

    This is a unified entry point that automatically detects the file format
    and uses the appropriate handler to read the volume.

    Args:
        root: The copick root object.
        run_name: The name of the run.
        tomo_type: Type of the tomogram (e.g., 'wbp', 'denoised').
        file_path: Path to the tomogram file.
        voxel_spacing: Voxel spacing in Angstrom. If None, will try to read from file.
        file_type: File type override (e.g., 'mrc', 'zarr', 'tiff', 'em').
                   If None, auto-detected from file extension.
        create_pyramid: Whether to create a multiscale pyramid.
        pyramid_levels: Number of pyramid levels.
        chunks: Chunk size for the output Zarr file.
        transpose: Transpose axes. E.g., '2,1,0' to reverse all axes.
        flip: Flip axes. E.g., '0' to flip Z, '0,2' to flip Z and X.
        create: Create run if it doesn't exist.
        exist_ok: Don't raise error if tomogram exists.
        overwrite: Overwrite if exists.
        log: Log the operation.

    Returns:
        The created CopickTomogram object.

    Raises:
        ValueError: If the format is not supported or voxel spacing cannot be determined.
    """
    from copick.util.handlers import FormatRegistry

    # Get handler
    handler = FormatRegistry.get_volume_handler(file_type or file_path)
    if handler is None:
        raise ValueError(f"Unsupported volume format for: {file_path}")

    # Read volume
    volume, file_voxel_size = handler.read(file_path)

    # Determine effective voxel spacing
    effective_voxel_spacing = voxel_spacing if voxel_spacing is not None else file_voxel_size
    if effective_voxel_spacing is None:
        raise ValueError(
            f"Voxel spacing not provided and cannot be determined from {handler.format_name} file. "
            f"Please specify --voxel-size.",
        )

    # Apply transforms
    if transpose is not None:
        transpose_order = tuple(map(int, transpose.split(",")))
        volume = np.transpose(volume, transpose_order)

    if flip is not None:
        flip_axes = tuple(map(int, flip.split(",")))
        for axis in flip_axes:
            volume = np.flip(volume, axis=axis)

    # Use the existing add_tomogram function
    return add_tomogram(
        root=root,
        run=run_name,
        tomo_type=tomo_type,
        volume=volume,
        voxel_spacing=effective_voxel_spacing,
        create_pyramid=create_pyramid,
        pyramid_levels=pyramid_levels,
        chunks=chunks,
        create=create,
        exist_ok=exist_ok,
        overwrite=overwrite,
        log=log,
    )


def add_picks_from_file(
    root: CopickRoot,
    run_name: str,
    file_path: str,
    object_name: str,
    user_id: str,
    session_id: str,
    voxel_spacing: Optional[float] = None,
    file_type: Optional[str] = None,
    create: bool = True,
    exist_ok: bool = False,
    overwrite: bool = False,
    log: bool = False,
    tilt_series_pixel_size: Optional[float] = None,
    tomograms_star: Optional[str] = None,
    relion_version: Optional[str] = None,
) -> CopickPicks:
    """Add picks from any supported file format using the handler registry.

    This is a unified entry point that automatically detects the file format
    and uses the appropriate handler to read the picks.

    Args:
        root: The copick root object.
        run_name: The name of the run.
        file_path: Path to the picks file.
        object_name: Name of the pickable object.
        user_id: User ID for the picks.
        session_id: Session ID for the picks.
        voxel_spacing: Voxel spacing in Angstrom (required for most formats).
        file_type: File type override (e.g., 'star', 'em', 'dynamo', 'csv').
                   If None, auto-detected from file extension.
        create: Create run if it doesn't exist.
        exist_ok: Don't raise error if picks exist.
        overwrite: Overwrite if exists.
        log: Log the operation.
        tilt_series_pixel_size: STAR only: tilt-series pixel size in Angstrom, the unit of rlnCoordinateX/Y/Z
            (read from the file's optics table when absent).
        tomograms_star: STAR only: RELION tomograms.star giving each tomogram's centre and tilt-series pixel size.
        relion_version: STAR only: force centred ("relion5") or pixel ("relion4") coordinates.

    Returns:
        The created CopickPicks object.

    Raises:
        ValueError: If the format is not supported.
    """
    from copick.util.handlers import FormatRegistry, unpack_picks_data

    # Get handler
    handler = FormatRegistry.get_picks_handler(file_type or file_path)
    if handler is None:
        raise ValueError(f"Unsupported picks format for: {file_path}")

    if handler.format_name == "star":
        # STAR coordinates are resolved from the file, the tomogram and the tilt-series pixel size; the voxel size is
        # needed only for legacy tomogram-pixel coordinates, and the reader says so if it is missing.
        read_kwargs = _star_read_kwargs(root, run_name, voxel_spacing, tilt_series_pixel_size, tomograms_star)
        read_kwargs["relion_version"] = relion_version
        data = handler.read(file_path, voxel_spacing, tomo_name=run_name, **read_kwargs)
    else:
        # Validate voxel spacing for formats that need it
        if handler.capabilities.supports_voxel_size and voxel_spacing is None:
            raise ValueError(
                f"Voxel spacing is required for {handler.format_name} format. Please specify --voxel-size.",
            )
        data = handler.read(file_path, voxel_spacing if voxel_spacing else 1.0)

    # Read picks
    positions, transforms, scores, instance_ids = unpack_picks_data(data)

    # Get or create run
    run = get_or_create_run(root, run_name, create=create, log=log)

    # Create picks
    picks = run.new_picks(
        object_name=object_name,
        user_id=user_id,
        session_id=session_id,
        exist_ok=exist_ok,
    )

    # Handle overwrite
    if overwrite and picks.points is not None and len(picks.points) > 0:
        picks.points = []

    # Convert to copick format and store
    picks.from_numpy(
        positions,
        transforms,
        instance_ids=instance_ids,
        scores=_usable_scores(scores, file_path, log),
    )

    # Store picks
    picks.store()

    if log:
        logging.info(f"Added {len(positions)} picks to run {run_name}")

    return picks


def add_segmentation_from_file(
    root: CopickRoot,
    run_name: str,
    file_path: str,
    voxel_spacing: Optional[float],
    name: str,
    user_id: str,
    session_id: str,
    file_type: Optional[str] = None,
    multilabel: Optional[bool] = None,
    instance: bool = False,
    transpose: Optional[str] = None,
    flip: Optional[str] = None,
    create: bool = True,
    exist_ok: bool = False,
    overwrite: bool = False,
    log: bool = False,
) -> CopickSegmentation:
    """Add a segmentation from any supported file format using the handler registry.

    This is a unified entry point that automatically detects the file format
    and uses the appropriate handler to read the volume.

    Args:
        root: The copick root object.
        run_name: The name of the run.
        file_path: Path to the segmentation file.
        voxel_spacing: Voxel spacing in Angstrom.
        name: Name of the segmentation.
        user_id: User ID for the segmentation.
        session_id: Session ID for the segmentation.
        file_type: File type override (e.g., 'mrc', 'tiff', 'em').
                   If None, auto-detected from file extension.
        multilabel: Whether this is a multilabel segmentation. ``None`` (the default) means multilabel unless
            ``instance`` is set.
        instance: Whether this is an instance segmentation (voxel = instance ID of the object `name`).
        transpose: Transpose axes. E.g., '2,1,0' to reverse all axes.
        flip: Flip axes. E.g., '0' to flip Z, '0,2' to flip Z and X.
        create: Create run if it doesn't exist.
        exist_ok: Don't raise error if segmentation exists.
        overwrite: Overwrite if exists.
        log: Log the operation.

    Returns:
        The created CopickSegmentation object.

    Raises:
        ValueError: If the format is not supported.
    """
    from copick.util.handlers import FormatRegistry

    if multilabel is None:
        multilabel = not instance

    # Get handler
    handler = FormatRegistry.get_volume_handler(file_type or file_path)
    if handler is None:
        raise ValueError(f"Unsupported volume format for: {file_path}")

    # Read volume
    volume, file_voxel_size = handler.read(file_path)

    # Determine effective voxel spacing
    effective_voxel_spacing = voxel_spacing if voxel_spacing is not None else file_voxel_size
    if effective_voxel_spacing is None:
        raise ValueError(
            f"Voxel spacing not provided and cannot be determined from {handler.format_name} file. "
            f"Please specify --voxel-size.",
        )

    return _add_segmentation_from_array(
        root=root,
        run=run_name,
        volume=volume,
        voxel_spacing=effective_voxel_spacing,
        name=name,
        user_id=user_id,
        session_id=session_id,
        multilabel=multilabel,
        instance=instance,
        transpose=transpose,
        flip=flip,
        create=create,
        exist_ok=exist_ok,
        overwrite=overwrite,
        log=log,
    )


def add_picks_grouped_from_file(
    root: CopickRoot,
    file_path: str,
    object_name: str,
    user_id: str,
    session_id: str,
    voxel_spacing: float,
    index_to_run: Dict[int, str],
    file_type: Optional[str] = None,
    tomo_index_row: int = 4,
    create: bool = True,
    exist_ok: bool = False,
    overwrite: bool = False,
    log: bool = False,
    tomogram_centers: Optional[Dict[str, Tuple[float, float, float]]] = None,
    relion_version: Optional[str] = None,
    tilt_series_pixel_size: Optional[float] = None,
    tomograms: Optional[Dict[str, Any]] = None,
) -> Dict[str, CopickPicks]:
    """Add picks from a file containing multiple tomograms using the handler registry.

    This is a unified entry point for grouped picks imports where a single file
    contains picks from multiple tomograms, identified by an index column.

    Args:
        root: The copick root object.
        file_path: Path to the picks file.
        object_name: Name of the pickable object.
        user_id: User ID for the picks.
        session_id: Session ID for the picks.
        voxel_spacing: Voxel spacing in Angstrom.
        index_to_run: Mapping from tomogram index to run name.
        file_type: File type override (e.g., 'em', 'dynamo').
                   If None, auto-detected from file extension.
        tomo_index_row: Row index for tomogram number in EM files (default: 4).
        create: Create runs if they don't exist.
        exist_ok: Don't raise error if picks exist.
        overwrite: Overwrite if exists.
        log: Log the operation.
        tomogram_centers: Dict mapping tomo_name to (center_x, center_y, center_z) in Angstrom.
            Required for RELION 5.0 centered coordinate conversion.
        relion_version: Force centred ("relion5") or pixel ("relion4") coordinates. If None, centred
            coordinates are used where tomogram centres are known.
        tilt_series_pixel_size: STAR only: tilt-series pixel size in Angstrom, the unit of rlnCoordinateX/Y/Z.
        tomograms: STAR only: ``copick.util.formats.read_relion_tomograms`` entries (centres and pixel sizes).

    Returns:
        Dictionary mapping run names to created CopickPicks objects.

    Raises:
        ValueError: If the format is not supported or doesn't support grouped import.
    """
    from copick.util.handlers import FormatRegistry, unpack_picks_data

    # Get handler
    handler = FormatRegistry.get_picks_handler(file_type or file_path)
    if handler is None:
        raise ValueError(f"Unsupported picks format for: {file_path}")

    if not handler.capabilities.supports_grouped_import:
        raise ValueError(
            f"Format {handler.format_name} does not support grouped import. "
            f"Use add_picks_from_file() for single-tomogram imports.",
        )

    # Read grouped picks (pass RELION-specific parameters if this is a STAR file)
    grouped_data = handler.read_grouped(
        file_path,
        voxel_spacing,
        index_to_run,
        tomo_index_row=tomo_index_row,
        tomogram_centers=tomogram_centers,
        relion_version=relion_version,
        tilt_series_pixel_size=tilt_series_pixel_size,
        tomograms=tomograms,
    )

    # Create picks for each run
    results = {}
    for run_name, run_data in grouped_data.items():
        positions, transforms, scores, instance_ids = unpack_picks_data(run_data)
        # Get or create run
        run = get_or_create_run(root, run_name, create=create, log=log)
        if run is None:
            if log:
                logging.warning(f"Skipping run {run_name}: run not found and create=False")
            continue

        # Create picks
        picks = run.new_picks(
            object_name=object_name,
            user_id=user_id,
            session_id=session_id,
            exist_ok=exist_ok,
        )

        # Handle overwrite
        if overwrite and picks.points is not None and len(picks.points) > 0:
            picks.points = []

        # Convert to copick format and store
        picks.from_numpy(
            positions,
            transforms,
            instance_ids=instance_ids,
            scores=_usable_scores(scores, file_path, log),
        )
        picks.store()

        results[run_name] = picks

        if log:
            logging.info(f"Added {len(positions)} picks to run {run_name}")

    if log:
        logging.info(f"Successfully imported picks to {len(results)} runs from {file_path}")

    return results
