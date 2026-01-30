import glob
import os
from typing import Tuple

import click

from copick.cli.util import add_config_option, add_create_overwrite_options, add_debug_option
from copick.util.formats import get_picks_format_from_extension, get_volume_format_from_extension
from copick.util.log import get_logger
from copick.util.path_util import prepare_runs_from_paths


@click.group()
@click.pass_context
def add(ctx):
    """Add entities to copick projects."""
    pass


@add.command(
    short_help="Add a tomogram to the project.",
    no_args_is_help=True,
)
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
    type=click.Choice(["mrc", "zarr", "tiff", "em"], case_sensitive=False),
    default=None,
    show_default=True,
    help="The file type of the tomogram ('mrc', 'zarr', 'tiff', or 'em'). Will guess type based on extension if omitted.",
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
@click.option(
    "--tomolist",
    required=False,
    type=click.Path(exists=True),
    default=None,
    help="Path to Dynamo tomolist file (2-column TSV: index, MRC path). "
    "Imports all tomograms listed, using filenames as run names. "
    "Mutually exclusive with PATH, --run, and --run-regex.",
)
@click.option(
    "--index-map",
    required=False,
    type=click.Path(exists=True),
    default=None,
    help="Path to CSV/TSV mapping tomogram index to run name. "
    "Only used with --tomolist to override filename-based run names.",
)
@add_create_overwrite_options
@add_debug_option
@click.argument(
    "path",
    required=False,
    type=str,
    default=None,
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
    max_workers: int,
    tomolist: str,
    index_map: str,
    path: str,
    create: bool,
    overwrite: bool,
    debug: bool,
):
    """
    Add a tomogram to the project.

    PATH: Path to the tomogram file (MRC or Zarr format) or glob pattern.
    Can be omitted if --tomolist is used.

    Examples:

    \b
    # Import single tomogram
    copick add tomogram tomo.mrc -c config.json

    \b
    # Import from glob pattern
    copick add tomogram "*.mrc" -c config.json

    \b
    # Import from Dynamo tomolist (run names from MRC filenames)
    copick add tomogram -c config.json --tomolist tomograms.doc

    \b
    # Import from tomolist with custom run names
    copick add tomogram -c config.json --tomolist tomograms.doc --index-map run_mapping.csv
    """
    # Deferred imports for performance
    import copick
    from copick.ops.add import _add_tomogram_mrc, _add_tomogram_zarr
    from copick.ops.run import map_runs, report_results

    logger = get_logger(__name__, debug=debug)

    # Get root
    root = copick.from_file(config)

    # Validate mutually exclusive options
    if tomolist:
        if run:
            ctx.fail("--run cannot be used with --tomolist")
        if run_regex != "(.*)":
            ctx.fail("--run-regex cannot be used with --tomolist")
        if path:
            ctx.fail("PATH argument cannot be used with --tomolist")
    elif not path:
        ctx.fail("Either PATH or --tomolist must be provided")

    if index_map and not tomolist:
        ctx.fail("--index-map can only be used with --tomolist")

    # Handle tomolist import
    if tomolist:
        from copick.util.formats import read_dynamo_tomolist, read_index_map

        # Parse tomolist to get index → path mapping
        index_to_path = {}
        with open(tomolist) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split("\t")
                if len(parts) >= 2:
                    idx = int(parts[0])
                    mrc_path = parts[1].strip()
                    index_to_path[idx] = mrc_path

        # Get run names (from index-map or from filenames)
        index_to_run = read_index_map(index_map) if index_map else read_dynamo_tomolist(tomolist)

        # Build paths list and run_to_file mapping
        paths = []
        run_to_file = {}
        for idx, mrc_path in index_to_path.items():
            if idx in index_to_run:
                run_name = index_to_run[idx]
                if not os.path.exists(mrc_path):
                    logger.warning(f"File not found: {mrc_path}, skipping")
                    continue
                paths.append(mrc_path)
                if run_name in run_to_file:
                    logger.warning(f"Duplicate run name {run_name}, skipping {mrc_path}")
                    continue
                run_to_file[run_name] = mrc_path
            else:
                logger.warning(f"Index {idx} not in mapping, skipping {mrc_path}")

        if not paths:
            ctx.fail("No valid tomograms found in tomolist")

        logger.info(f"Found {len(run_to_file)} tomograms to import from tomolist")

        # Create runs if they don't exist
        if create:
            for run_name in run_to_file:
                if not root.get_run(run_name):
                    root.new_run(run_name)
                    logger.info(f"Created run: {run_name}")

    elif "*" in path:
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

    # Files extension validation before processing (skip exists check for tomolist - already done)
    if not file_type:
        for p in paths:
            ext = get_volume_format_from_extension(p)
            if ext not in ["mrc", "zarr", "tiff", "em"]:
                raise ValueError(
                    f"Unsupported file format for {p}. Supported formats are 'mrc', 'zarr', 'tiff', and 'em'.",
                )
            if not tomolist and not os.path.exists(p):
                raise FileNotFoundError(f"File not found: {p}")

    # Convert chunk arg
    chunk_size: Tuple[int, int, int] = tuple(map(int, chunk_size.split(",")[:3]))

    # Prepare runs and group files (skip for tomolist - already built run_to_file)
    if not tomolist:
        run_to_file = prepare_runs_from_paths(root, paths, run, run_regex, create, logger)

    def import_tomogram(run_obj, file_path, **kwargs):
        """Process one tomogram file for a single run"""
        from copick.ops.add import _add_tomogram_em, _add_tomogram_tiff

        try:
            # Get file type
            ft = file_type.lower() if file_type else get_volume_format_from_extension(file_path)

            if ft == "mrc":
                _add_tomogram_mrc(
                    root,
                    run_obj.name,
                    tomo_type,
                    file_path,
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
                    file_path,
                    voxel_spacing=voxel_size,
                    create_pyramid=create_pyramid,
                    pyramid_levels=pyramid_levels,
                    chunks=chunk_size,
                    create=create,
                    overwrite=overwrite,
                    exist_ok=overwrite,
                    log=debug,
                )
            elif ft == "tiff":
                if voxel_size is None:
                    raise ValueError("--voxel-size is required for TIFF import.")
                _add_tomogram_tiff(
                    root,
                    run_obj.name,
                    tomo_type,
                    file_path,
                    voxel_spacing=voxel_size,
                    create_pyramid=create_pyramid,
                    pyramid_levels=pyramid_levels,
                    chunks=chunk_size,
                    create=create,
                    overwrite=overwrite,
                    exist_ok=overwrite,
                    log=debug,
                )
            elif ft == "em":
                if voxel_size is None:
                    raise ValueError("--voxel-size is required for EM import.")
                _add_tomogram_em(
                    root,
                    run_obj.name,
                    tomo_type,
                    file_path,
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


@add.command(
    short_help="Add a segmentation to the project.",
    no_args_is_help=True,
)
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
    "--file-type",
    required=False,
    type=click.Choice(["mrc", "zarr", "tiff", "em"], case_sensitive=False),
    default=None,
    show_default=True,
    help="File type ('mrc', 'zarr', 'tiff', or 'em'). Will guess type based on extension if omitted.",
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
    file_type: str,
    max_workers: int,
    path: str,
    create: bool,
    overwrite: bool,
    debug: bool,
):
    """
    Add a segmentation to the project.

    PATH: Path to the segmentation file (MRC, Zarr, TIFF, or EM format) or glob pattern.
    """
    # Deferred import for performance
    import copick
    from copick.ops.add import (
        _add_segmentation_em,
        _add_segmentation_tiff,
    )
    from copick.ops.add import (
        add_segmentation as add_segmentation_mrc,
    )
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

    def import_segmentation_callback(run_obj, file_path, **kwargs):
        """Process segmentation files for a single run"""
        try:
            # Determine file type
            ft = file_type.lower() if file_type else get_volume_format_from_extension(file_path)

            if ft == "mrc":
                add_segmentation_mrc(
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
            elif ft == "tiff":
                if voxel_size is None:
                    raise ValueError("--voxel-size is required for TIFF import.")
                _add_segmentation_tiff(
                    root,
                    run_obj.name,
                    file_path,
                    voxel_size,
                    name,
                    user_id,
                    session_id,
                    multilabel=True,
                    create=create,
                    exist_ok=overwrite,
                    overwrite=overwrite,
                    log=debug,
                )
            elif ft == "em":
                if voxel_size is None:
                    raise ValueError("--voxel-size is required for EM import.")
                _add_segmentation_em(
                    root,
                    run_obj.name,
                    file_path,
                    voxel_size,
                    name,
                    user_id,
                    session_id,
                    multilabel=True,
                    create=create,
                    exist_ok=overwrite,
                    overwrite=overwrite,
                    log=debug,
                )
            else:
                raise ValueError(f"Unsupported file format: {ft}")

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
        callback=import_segmentation_callback,
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


@add.command(
    short_help="Add a pickable object to the project configuration.",
    no_args_is_help=True,
)
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


@add.command(
    short_help="Add volume data to an existing pickable object.",
    no_args_is_help=True,
)
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


@add.command(
    short_help="Add picks from external formats (EM, STAR, Dynamo, CSV).",
    no_args_is_help=True,
)
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
    help="Regular expression to extract the run name from the filename. The regex should capture the run name in the first group.",
)
@click.option(
    "--object-name",
    required=True,
    type=str,
    help="Name of the pickable object (must exist in config).",
)
@click.option(
    "--user-id",
    required=False,
    type=str,
    default="copick",
    show_default=True,
    help="User ID for the picks.",
)
@click.option(
    "--session-id",
    required=False,
    type=str,
    default="1",
    show_default=True,
    help="Session ID for the picks.",
)
@click.option(
    "--voxel-size",
    required=False,
    type=float,
    default=None,
    show_default=True,
    help="Voxel size in Angstrom (required for EM, STAR, and Dynamo formats for coordinate conversion).",
)
@click.option(
    "--file-type",
    required=False,
    type=click.Choice(["em", "star", "dynamo", "csv"], case_sensitive=False),
    default=None,
    show_default=True,
    help="File type ('em', 'star', 'dynamo', 'csv'). Will guess type based on extension if omitted.",
)
@click.option(
    "--index-map",
    required=False,
    type=click.Path(exists=True),
    default=None,
    help="Path to a CSV/TSV file mapping tomogram index to run name (2 columns: index, run_name). "
    "Enables multi-tomogram import from Dynamo tables or EM motivelists. "
    "Mutually exclusive with --run and --run-regex.",
)
@click.option(
    "--tomolist",
    required=False,
    type=click.Path(exists=True),
    default=None,
    help="Path to a Dynamo tomolist file (2-column TSV: index, MRC path). "
    "Run names are extracted from MRC filenames. Only valid with --file-type dynamo.",
)
@click.option(
    "--tomo-index-row",
    required=False,
    type=int,
    default=4,
    show_default=True,
    help="Row index (0-based) for tomogram index in EM motivelists. "
    "Default is row 4 (Artiatomi convention). Only valid with --file-type em.",
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
def picks(
    ctx,
    config: str,
    run: str,
    run_regex: str,
    object_name: str,
    user_id: str,
    session_id: str,
    voxel_size: float,
    file_type: str,
    index_map: str,
    tomolist: str,
    tomo_index_row: int,
    max_workers: int,
    path: str,
    create: bool,
    overwrite: bool,
    debug: bool,
):
    """
    Add picks from external file formats.

    PATH: Path to the picks file (EM, STAR, Dynamo .tbl, or CSV) or glob pattern.

    Supported formats:
    - EM: TOM toolbox motivelist format (.em)
    - STAR: RELION particle STAR files (.star)
    - Dynamo: Dynamo table files (.tbl)
    - CSV: Copick CSV format with run_name column (.csv)

    Examples:

    \b
    # Import picks from a TOM toolbox EM motivelist
    copick add picks particles.em -c config.json --object-name ribosome \\
        --voxel-size 10.0 --run TS_001

    \b
    # Import picks from a RELION STAR file
    copick add picks particles.star -c config.json --object-name ribosome \\
        --voxel-size 10.0 --run TS_001

    \b
    # Import picks from a Dynamo table
    copick add picks table.tbl -c config.json --object-name ribosome \\
        --voxel-size 10.0 --run TS_001

    \b
    # Import picks from CSV (run names from file)
    copick add picks particles.csv -c config.json --object-name ribosome

    \b
    # Import from multiple files using glob pattern
    copick add picks "*.star" -c config.json --object-name ribosome --voxel-size 10.0

    \b
    # Import Dynamo table with multiple tomograms using index map
    copick add picks particles.tbl -c config.json --object-name ribosome \\
        --voxel-size 10.0 --index-map tomo_mapping.csv

    \b
    # Import Dynamo table using tomolist (run names from MRC filenames)
    copick add picks particles.tbl -c config.json --object-name ribosome \\
        --voxel-size 10.0 --tomolist tomograms.doc

    \b
    # Import EM motivelist with index map
    copick add picks motivelist.em -c config.json --object-name ribosome \\
        --voxel-size 10.0 --index-map tomo_mapping.csv

    For format-specific conventions (coordinate systems, Euler angle conventions),
    see the documentation or the docstrings in copick.util.formats.
    """
    import copick
    from copick.ops.add import add_picks as add_picks_op
    from copick.ops.run import map_runs, report_results

    logger = get_logger(__name__, debug=debug)

    # Get root
    root = copick.from_file(config)

    if "*" in path:
        # If glob pattern is used, the run name cannot be used
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

    # Validate voxel size for formats that require it
    ft = file_type.lower() if file_type else get_picks_format_from_extension(paths[0])
    if ft in ["em", "star", "dynamo"] and voxel_size is None:
        ctx.fail(f"--voxel-size is required for {ft.upper()} format import.")

    # Validate index mapping options
    if index_map or tomolist:
        if run:
            ctx.fail("--run cannot be used with --index-map or --tomolist")
        if run_regex != "(.*)":
            ctx.fail("--run-regex cannot be used with --index-map or --tomolist")

    if tomolist and ft != "dynamo":
        ctx.fail("--tomolist is only valid with --file-type dynamo")

    if tomo_index_row != 4 and ft != "em":
        ctx.fail("--tomo-index-row is only valid with --file-type em")

    # Handle grouped import (index-map or tomolist provided)
    if index_map or tomolist:
        from copick.ops.add import _add_picks_dynamo_grouped, _add_picks_em_grouped
        from copick.util.formats import read_dynamo_tomolist, read_index_map

        # Parse the index-to-run mapping
        if tomolist:
            index_to_run = read_dynamo_tomolist(tomolist)
            logger.info(f"Loaded tomolist with {len(index_to_run)} tomograms")
        else:
            index_to_run = read_index_map(index_map)
            logger.info(f"Loaded index map with {len(index_to_run)} entries")

        # Process each file with grouped import
        total_runs = set()
        for p in paths:
            try:
                if ft == "dynamo":
                    results = _add_picks_dynamo_grouped(
                        root=root,
                        path=p,
                        object_name=object_name,
                        user_id=user_id,
                        session_id=session_id,
                        voxel_spacing=voxel_size,
                        index_to_run=index_to_run,
                        create=create,
                        exist_ok=overwrite,
                        overwrite=overwrite,
                        log=debug,
                    )
                elif ft == "em":
                    results = _add_picks_em_grouped(
                        root=root,
                        path=p,
                        object_name=object_name,
                        user_id=user_id,
                        session_id=session_id,
                        voxel_spacing=voxel_size,
                        index_to_run=index_to_run,
                        tomo_index_row=tomo_index_row,
                        create=create,
                        exist_ok=overwrite,
                        overwrite=overwrite,
                        log=debug,
                    )
                else:
                    ctx.fail(f"Grouped import (--index-map/--tomolist) not supported for format: {ft}")

                total_runs.update(results.keys())
                logger.info(f"Imported picks from {p} to {len(results)} runs")
            except Exception as e:
                logger.error(f"Failed to import picks from {p}: {e}")

        logger.info(f"Successfully imported picks to {len(total_runs)} runs total")
        return

    # For CSV files, we handle them specially since they contain run_name column
    if ft == "csv":
        # CSV files contain run names in the file, so we process them directly
        for p in paths:
            try:
                results = add_picks_op(
                    root=root,
                    run_name="",  # Will be ignored for CSV
                    path=p,
                    object_name=object_name,
                    user_id=user_id,
                    session_id=session_id,
                    voxel_spacing=voxel_size,
                    file_type="csv",
                    create=create,
                    exist_ok=overwrite,
                    overwrite=overwrite,
                    log=debug,
                )
                logger.info(f"Successfully imported picks from {p}")
            except Exception as e:
                logger.error(f"Failed to import picks from {p}: {e}")
        return

    # Prepare runs and group files
    run_to_file = prepare_runs_from_paths(root, paths, run, run_regex, create, logger)

    def import_picks(run_obj, file_path, **kwargs):
        """Process one picks file for a single run"""
        try:
            add_picks_op(
                root=root,
                run_name=run_obj.name,
                path=file_path,
                object_name=object_name,
                user_id=user_id,
                session_id=session_id,
                voxel_spacing=voxel_size,
                file_type=ft,
                create=create,
                exist_ok=overwrite,
                overwrite=overwrite,
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

    # Process picks using map_runs
    results = map_runs(
        callback=import_picks,
        root=root,
        runs=run_names,
        workers=max_workers,
        parallelism="thread",
        run_args=run_args,
        show_progress=True,
        task_desc="Importing picks",
    )

    # Report Results
    report_results(results, len(paths), logger)
