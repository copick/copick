import logging
from typing import Any, Dict, Optional, Tuple, Union

import mrcfile
import numpy as np
import zarr
from ome_zarr.writer import write_multiscale

from copick.models import (
    CopickFeatures,
    CopickObject,
    CopickRoot,
    CopickRun,
    CopickTomogram,
    CopickVoxelSpacing,
)
from copick.util.ome import get_voxel_size_from_zarr, ome_metadata, volume_pyramid


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
    chunks: Tuple[int, ...] = (256, 256, 256),
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
    """

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

    # Multiscale metadata
    ome_meta = ome_metadata(pyramid)

    # Attempt to get run and voxel spacing
    runobj = get_or_create_run(root, run, create=create)
    vsobj = get_or_create_voxelspacing(runobj, voxel_spacing, create=create)

    # Create the tomogram
    tomogram = vsobj.new_tomogram(tomo_type, exist_ok=exist_ok)

    # Get the store
    loc = tomogram.zarr()
    root_group = zarr.group(loc, overwrite=overwrite)

    # Write the pyramid
    write_multiscale(
        list(pyramid.values()),
        group=root_group,
        axes=ome_meta["axes"],
        coordinate_transformations=ome_meta["coordinate_transformations"],
        storage_options=dict(chunks=chunks, overwrite=overwrite),
        compute=True,
        metadata=meta,
    )

    if log:
        logging.log(logging.INFO, f"Added tomogram {tomo_type} to run {runobj.name}.")

    return tomogram


def _add_tomogram_mrc(
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
    chunks: Tuple[int, ...] = (256, 256, 256),
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
    chunks: Tuple[int, int, int] = (256, 256, 256),
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
    """

    zarr_group = zarr.open(volume_file)
    # Get the first level data (level 0)
    volume = np.array(zarr_group["0"])
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
    chunks: Tuple[int, int, int] = (256, 256, 256),
    meta: Dict[str, Any] = None,
    log: bool = False,
) -> CopickFeatures:
    """Add features to a copick run.

    Args:
        root (CopickRoot): The copick root object.
        features (Dict[str, Any]): The features to add.
        run (str): The run the features are part of.
        exist_ok (bool, optional): If True, do not raise an error if the features already exist. Defaults to False.
        overwrite (bool, optional): Overwrite the object if it exists. Defaults to False.
        log (bool, optional): Log the operation. Defaults to False.
    """
    runobj = get_or_create_run(root, run, create=False)
    vsobj = get_or_create_voxelspacing(runobj, 1.0, create=False)
    tomogram = vsobj.get_tomogram(tomo_type)

    if tomogram is None:
        e = ValueError(f"Could not find tomogram {tomo_type} in run {run}.")
        if log:
            logging.exception(e)
        raise e

    # Create the features
    features = tomogram.new_features(feature_type, exist_ok=exist_ok)

    # Multiscale metadata
    ome_meta = ome_metadata({voxel_spacing: features_vol})

    # Get the store
    loc = features.zarr()
    root_group = zarr.group(loc, overwrite=overwrite)

    write_multiscale(
        [features_vol],
        group=root_group,
        axes=ome_meta["axes"],
        coordinate_transformations=ome_meta["coordinate_transformations"],
        storage_options=dict(chunks=chunks, overwrite=overwrite),
        compute=True,
        metadata=meta,
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
        create (bool, optional): Create the object if it does not exist. Defaults to True.
        exist_ok (bool, optional): If True, do not raise an error if the segmentation already exists. Defaults to False.
        overwrite (bool, optional): Overwrite the object if it exists. Defaults to False.
    """

    # Read the Segmentation Mask
    if mask_path.endswith(".mrc"):
        with mrcfile.open(mask_path) as mrc:
            volume = mrc.data
    else:
        raise ValueError(f"Unsupported file type: {mask_path}")

    # Attempt to get run and voxel spacing
    runobj = get_or_create_run(root, run, create=create)

    # Create a new segmentation
    segmentation = runobj.new_segmentation(
        name=name,
        user_id=user_id,
        is_multilabel=multilabel,
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
