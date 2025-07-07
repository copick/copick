import logging
from typing import Any, Dict, Tuple, Union

import mrcfile
import numpy as np
import zarr
from ome_zarr.writer import write_multiscale

from copick.models import (
    CopickFeatures,
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
