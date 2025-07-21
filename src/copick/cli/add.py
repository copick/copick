import glob
import os
from typing import Tuple

import click

from copick.cli.util import add_config_option, add_create_overwrite_options, add_debug_option
from copick.util.log import get_logger
from copick.util.path_util import get_format_from_extension, prepare_runs_from_paths


@click.group()
@click.pass_context
def add(ctx):
    """Add entities to copick projects."""
    pass


@add.command(short_help="Add a tomogram to the project.")
@add_config_option
@click.option(
    "--run",
    required=False,
    type=str,
    help="The name of the run. If not specified, will use the name of the file (stripping extension), "
    "ignored if PATH is glob pattern.",
    show_default=True,
    default="",
)
@click.option(
    "--run-regex",
    required=False,
    type=str,
    default="(.*)",
    show_default=True,
    help="Regular expression to extract the run name from the filename. If not provided, will use the file name "
    "without extension. The regex should capture the run name in the first group.",
)
@click.option(
    "--tomo-type",
    required=False,
    type=str,
    help="The name of the tomogram (e.g. wbp).",
    show_default=True,
    default="wbp",
)
@click.option(
    "--file-type",
    required=False,
    type=str,
    default=None,
    show_default=True,
    help="The file type of the tomogram ('mrc' or 'zarr'). Will guess type based on extension if omitted.",
)
@click.option(
    "--voxel-size",
    required=False,
    type=float,
    default=None,
    show_default=True,
    help="Voxel size in Angstrom. Overrides voxel size in the tomogram header.",
)
@click.option(
    "--create-pyramid/--no-create-pyramid",
    is_flag=True,
    required=False,
    type=bool,
    default=True,
    show_default=True,
    help="Compute the multiscale pyramid.",
)
@click.option(
    "--pyramid-levels",
    required=False,
    type=int,
    default=3,
    show_default=True,
    help="Number of pyramid levels (each level corresponds to downscaling by factor two).",
)
@click.option(
    "--chunk-size",
    required=False,
    type=str,
    default="256,256,256",
    show_default=True,
    help="Chunk size for the output Zarr file.",
)
@click.option(
    "--max-workers",
    required=False,
    type=int,
    default=4,
    show_default=True,
    help="Maximum number of worker threads.",
)
@add_create_overwrite_options
@add_debug_option
@click.argument(
    "path",
    required=True,
    type=str,
    metavar="PATH",
)
@click.pass_context
def tomogram(
    ctx,
    config: str,
    run: str,
    run_regex: str,
    tomo_type: str,
    file_type: str,
    voxel_size: float,
    create_pyramid: bool,
    pyramid_levels: int,
    chunk_size: str,
    path: str,
    max_workers: int,
    create: bool,
    overwrite: bool,
    debug: bool,
):
    """
    Add a tomogram to the project.

    PATH: Path to the tomogram file (MRC or Zarr format) or glob pattern.
    """
    # Deferred imports for performance
    import copick
    from copick.ops.add import _add_tomogram_mrc, _add_tomogram_zarr
    from copick.ops.run import map_runs, report_results

    logger = get_logger(__name__, debug=debug)

    # Get root
    root = copick.from_file(config)

    if "*" in path:
        # If glob pattern is used, the run name can not be used
        if run:
            logger.warning("Run name is ignored when using glob patterns.")
            run = ""

        # Handle glob patterns
        paths = glob.glob(path)
        if not paths:
            logger.error(f"No files found matching pattern: {path}")
            ctx.fail(f"No files found matching pattern: {path}")

    else:
        # Single file path
        paths = [path]

    # Files extension validation before processing
    if not file_type:
        for p in paths:
            ext = get_format_from_extension(p)
            if ext not in ["mrc", "zarr"]:
                raise ValueError(f"Unsupported file format for {p}. Supported formats are 'mrc' and 'zarr'.")
            if not os.path.exists(p):
                raise FileNotFoundError(f"File not found: {p}")

    # Convert chunk arg
    chunk_size: Tuple[int, int, int] = tuple(map(int, chunk_size.split(",")[:3]))

    # Prepare runs and group files
    run_to_file = prepare_runs_from_paths(root, paths, run, run_regex, create, logger)

    def import_tomogram(run_obj, file_path, **kwargs):
        """Process one tomogram file for a single run"""
        try:
            # Get file type
            ft = file_type.lower() if file_type else get_format_from_extension(file_path)

            if ft == "mrc":
                _add_tomogram_mrc(
                    root,
                    run_obj.name,
                    tomo_type,
                    file_path,  # Single file, not a list
                    voxel_spacing=voxel_size,
                    create_pyramid=create_pyramid,
                    pyramid_levels=pyramid_levels,
                    chunks=chunk_size,
                    create=create,
                    overwrite=overwrite,
                    exist_ok=overwrite,
                    log=debug,
                )
            elif ft == "zarr":
                _add_tomogram_zarr(
                    root,
                    run_obj.name,
                    tomo_type,
                    file_path,  # Single file, not a list
                    voxel_spacing=voxel_size,
                    create_pyramid=create_pyramid,
                    pyramid_levels=pyramid_levels,
                    chunks=chunk_size,
                    create=create,
                    overwrite=overwrite,
                    exist_ok=overwrite,
                    log=debug,
                )
            else:
                raise ValueError(f"Could not determine file type from path: {file_path}")

            return {"processed": 1, "errors": []}

        except Exception as e:
            error_msg = f"Failed to process {file_path}: {e}"
            if logger:
                logger.critical(error_msg)
            return {"processed": 0, "errors": [error_msg]}

    # Prepare run-specific arguments
    run_names = list(run_to_file.keys())
    run_args = [{"file_path": run_to_file[run_name]} for run_name in run_names]

    # Process tomograms using map_runs
    results = map_runs(
        callback=import_tomogram,
        root=root,
        runs=run_names,
        workers=max_workers,
        parallelism="thread",
        run_args=run_args,
        show_progress=True,
        task_desc="Processing tomograms",
    )

    # Report Results
    report_results(results, len(paths), logger)


@add.command(short_help="Add a segmentation to the project.")
@add_config_option
@click.option(
    "--run",
    required=False,
    type=str,
    help="The name of the run. If not specified, will use the name of the file (stripping extension), "
    "ignored if PATH is glob pattern.",
    show_default=True,
    default="",
)
@click.option(
    "--run-regex",
    required=False,
    type=str,
    default="(.*)",
    show_default=True,
    help="Regular expression to extract the run name from the filename. If not provided, will use the file name "
    "without extension. The regex should capture the run name in the first group.",
)
@click.option(
    "--voxel-size",
    required=False,
    type=float,
    default=None,
    show_default=True,
    help="Voxel size in Angstrom. Overrides voxel size in the tomogram header.",
)
@click.option(
    "--name",
    required=False,
    type=str,
    default=None,
    show_default=True,
    help="Name of the segmentation.",
)
@click.option(
    "--user-id",
    required=False,
    type=str,
    default="copick",
    show_default=True,
    help="User ID of the segmentation.",
)
@click.option(
    "--session-id",
    required=False,
    type=str,
    default="1",
    show_default=True,
    help="Session ID of the segmentation.",
)
@click.option(
    "--max-workers",
    required=False,
    type=int,
    default=4,
    show_default=True,
    help="Maximum number of worker threads.",
)
@add_create_overwrite_options
@add_debug_option
@click.argument(
    "path",
    required=True,
    type=str,
    metavar="PATH",
)
@click.pass_context
def segmentation(
    ctx,
    config: str,
    run: str,
    run_regex: str,
    voxel_size: float,
    name: str,
    user_id: str,
    session_id: str,
    max_workers: int,
    path: str,
    create: bool,
    overwrite: bool,
    debug: bool,
):
    """
    Add a segmentation to the project.

    PATH: Path to the segmentation file (MRC or Zarr format) or glob pattern.
    """
    # Deferred import for performance
    import copick
    from copick.ops.add import add_segmentation
    from copick.ops.run import map_runs, report_results

    logger = get_logger(__name__, debug=debug)

    # Get root
    root = copick.from_file(config)

    if "*" in path:
        # If glob pattern is used, the run name can not be used
        if run:
            logger.warning("Run name is ignored when using glob patterns.")
            run = ""

        # Handle glob patterns
        paths = glob.glob(path)
        if not paths:
            logger.error(f"No files found matching pattern: {path}")
            ctx.fail(f"No files found matching pattern: {path}")

    else:
        # Single file path
        paths = [path]

    # Prepare runs and group files
    run_to_file = prepare_runs_from_paths(root, paths, run, run_regex, create, logger)

    def import_segmentation(run_obj, file_path, **kwargs):
        """Process segmentation files for a single run"""
        try:
            add_segmentation(
                root,
                run_obj.name,
                file_path,
                voxel_size,
                name,
                user_id,
                session_id,
                multilabel=True,
                create=create,
                overwrite=overwrite,
                exist_ok=overwrite,
                log=debug,
            )

            return {"processed": 1, "errors": []}

        except Exception as e:
            error_msg = f"Failed to process {file_path}: {e}"
            if logger:
                logger.critical(error_msg)
            return {"processed": 0, "errors": [error_msg]}

    # Prepare run-specific arguments
    run_names = list(run_to_file.keys())
    run_args = [{"file_path": run_to_file[run_name]} for run_name in run_names]

    # Process segmentations using map_runs
    results = map_runs(
        callback=import_segmentation,
        root=root,
        runs=run_names,
        workers=max_workers,
        parallelism="thread",
        run_args=run_args,
        show_progress=True,
        task_desc="Processing segmentations",
    )

    # Report Results
    report_results(results, len(paths), logger)


@add.command(short_help="Add a pickable object to the project configuration.")
@add_config_option
@click.option(
    "--name",
    type=str,
    required=True,
    help="Name of the object to add.",
)
@click.option(
    "--object-type",
    type=click.Choice(["particle", "segmentation"], case_sensitive=False),
    default="particle",
    help="Type of object: 'particle' for point annotations or 'segmentation' for mask annotations.",
    show_default=True,
)
@click.option(
    "--label",
    type=int,
    default=None,
    help="Numeric label/id for the object. If not provided, will use the next available label.",
    show_default=True,
)
@click.option(
    "--color",
    type=str,
    default=None,
    help="RGBA color for the object as comma-separated values (e.g. '255,0,0,255' for red).",
    metavar="R,G,B,A",
)
@click.option(
    "--emdb-id",
    type=str,
    default=None,
    help="EMDB ID for the object.",
)
@click.option(
    "--pdb-id",
    type=str,
    default=None,
    help="PDB ID for the object.",
)
@click.option(
    "--identifier",
    type=str,
    default=None,
    help="Identifier for the object (e.g. Gene Ontology ID or UniProtKB accession).",
)
@click.option(
    "--map-threshold",
    type=float,
    default=None,
    help="Threshold to apply to the map when rendering the isosurface.",
)
@click.option(
    "--radius",
    type=float,
    default=50,
    help="Radius of the particle, when displaying as a sphere.",
    show_default=True,
)
@click.option(
    "--metadata",
    type=str,
    default=None,
    help="Additional metadata values to associate with the object, in JSON format.",
)
@click.option(
    "--volume",
    type=str,
    default=None,
    help="Path to volume file to associate with the object.",
    metavar="PATH",
)
@click.option(
    "--volume-format",
    type=click.Choice(["mrc", "zarr", "map"], case_sensitive=False),
    default=None,
    help="Format of the volume file ('mrc' or 'zarr'). Will guess from extension if not provided.",
    show_default=True,
)
@click.option(
    "--exist-ok/--no-exist-ok",
    is_flag=True,
    default=False,
    help="Whether existing objects with the same name should be overwritten.",
    show_default=True,
)
@click.option(
    "--voxel-size",
    type=float,
    default=None,
    help="Voxel size for the volume data. Required if volume is provided.",
)
@add_debug_option
@click.pass_context
def object(
    ctx,
    config: str,
    name: str,
    object_type: str,
    label: int,
    color: str,
    emdb_id: str,
    pdb_id: str,
    identifier: str,
    map_threshold: float,
    radius: float,
    metadata: str,
    volume: str,
    volume_format: str,
    voxel_size: float,
    exist_ok: bool,
    debug: bool,
):
    """
    Add a pickable object to the project configuration.
    """
    # Deferred import for performance
    import copick
    from copick.ops.add import add_object
    from copick.util.path_util import get_data_from_file, get_format_from_extension

    logger = get_logger(__name__, debug=debug)

    # Get root
    root = copick.from_file(config)

    # Convert object type to is_particle boolean
    is_particle = object_type.lower() == "particle"

    # Parse color if provided
    color_tuple = None
    if color:
        try:
            color_values = [int(x.strip()) for x in color.split(",")]
            if len(color_values) != 4:
                ctx.fail("Color must be provided as four comma-separated values (R,G,B,A).")
            color_tuple = tuple(color_values)
        except ValueError:
            ctx.fail("Color values must be integers between 0 and 255.")

    # Parse metadata if provided
    metadata_dict = {}
    if metadata:
        try:
            import json

            metadata_dict = json.loads(metadata)
        except json.JSONDecodeError:
            ctx.fail("Metadata must be valid JSON format.")

    # Load volume if provided
    volume_data = None
    voxel_spacing = None
    if volume:
        # Determine format
        fmt = volume_format.lower() if volume_format else get_format_from_extension(volume)

        if fmt is None:
            ctx.fail("Could not determine volume format from extension. Please specify --volume-format.")

        try:
            volume_data, voxel_spacing = get_data_from_file(volume, fmt)
        except Exception as e:
            logger.critical(f"Failed to load volume: {e}")
            ctx.fail(f"Error loading volume: {e}")

        if voxel_size is not None:
            voxel_spacing = voxel_size

    try:
        # Add object
        obj = add_object(
            root=root,
            name=name,
            is_particle=is_particle,
            label=label,
            color=color_tuple,
            emdb_id=emdb_id,
            pdb_id=pdb_id,
            identifier=identifier,
            map_threshold=map_threshold,
            radius=radius,
            volume=volume_data,
            voxel_size=voxel_spacing,
            metadata=metadata_dict,
            exist_ok=exist_ok,
            save_config=True,
            config_path=config,
            log=debug,
        )

        logger.info(f"Successfully added {object_type} object '{name}' with label {obj.label}")

    except Exception as e:
        logger.critical(f"Failed to add object: {e}")
        ctx.fail(f"Error adding object: {e}")


@add.command(short_help="Add volume data to an existing pickable object.")
@add_config_option
@click.option(
    "--object-name",
    type=str,
    required=True,
    help="Name of the existing object.",
)
@click.option(
    "--volume-path",
    type=str,
    required=True,
    help="Path to the volume file.",
    metavar="PATH",
)
@click.option(
    "--volume-format",
    type=click.Choice(["mrc", "zarr"], case_sensitive=False),
    default=None,
    help="Format of the volume file ('mrc' or 'zarr'). Will guess from extension if not provided.",
    show_default=True,
)
@click.option(
    "--voxel-size",
    type=float,
    required=False,
    default=None,
    help="Voxel size of the volume data in Angstrom.",
)
@add_debug_option
@click.pass_context
def object_volume(
    ctx,
    config: str,
    object_name: str,
    volume_path: str,
    volume_format: str,
    voxel_size: float,
    debug: bool,
):
    """
    Add volume data to an existing pickable object.
    """
    # Deferred import for performance
    import copick
    from copick.ops.add import add_object_volume
    from copick.util.path_util import get_data_from_file, get_format_from_extension

    logger = get_logger(__name__, debug=debug)

    # Get root
    root = copick.from_file(config)

    # Determine format
    fmt = volume_format.lower() if volume_format else get_format_from_extension(volume_path)

    if fmt is None:
        ctx.fail("Could not determine volume format from extension. Please specify --volume-format.")

    # Load volume
    try:
        volume_data, voxel_spacing = get_data_from_file(volume_path, fmt)
    except Exception as e:
        logger.critical(f"Failed to load volume: {e}")
        ctx.fail(f"Error loading volume: {e}")
        raise e

    if voxel_size is not None:
        voxel_spacing = voxel_size

    try:
        # Add volume to object
        add_object_volume(
            root=root,
            object_name=object_name,
            volume=volume_data,
            voxel_size=voxel_spacing,
            log=debug,
        )

        logger.info(f"Successfully added volume data to object '{object_name}'")

    except Exception as e:
        logger.critical(f"Failed to add volume to object: {e}")
        ctx.fail(f"Error adding volume to object: {e}")
