import glob
import os
from typing import Tuple

import click

from copick.cli.util import (
    add_config_option,
    add_create_overwrite_options,
    add_debug_option,
    add_max_workers_option,
    add_pyramid_create_options,
    add_run_options,
    add_user_session_options,
    add_volume_transform_options,
)
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
@add_run_options
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
@add_pyramid_create_options
@add_max_workers_option
@add_volume_transform_options
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
    run_name_prefix: str,
    tomo_type: str,
    file_type: str,
    voxel_size: float,
    create_pyramid: bool,
    pyramid_levels: int,
    chunk_size: str,
    max_workers: int,
    transpose: str,
    flip: str,
    path: str,
    create: bool,
    overwrite: bool,
    debug: bool,
):
    """
    Add a tomogram to the project.

    Imports a single tomogram, or many at once via a glob pattern, into one or more
    runs. The file format is inferred from the extension unless ``--file-type`` is
    given, and a multiscale pyramid is computed by default.

    Arguments:

        \b
        PATH: Path to the tomogram file (MRC, Zarr, TIFF, or EM) or a glob pattern.

    Examples:

        \b
        # Import a single tomogram
        copick add tomogram tomo.mrc -c config.json

        \b
        # Import every matching file via a glob pattern
        copick add tomogram "*.mrc" -c config.json

        \b
        # Import with an explicit run name
        copick add tomogram tomo.mrc -c config.json --run TS_001

        \b
        # Extract the run name from the filename with a regex
        copick add tomogram "TS*.mrc" -c config.json --run-regex "^(TS_\\d+)"

    See Also:

        \b
        copick add tomograms-dynamo: batch import from a Dynamo tomolist file
        copick add tomograms-relion: batch import from a RELION tomograms.star file
    """
    # Deferred imports for performance
    import copick
    from copick.ops.run import map_runs, report_results

    logger = get_logger(__name__, debug=debug)

    # Get root
    root = copick.from_file(config)

    # Handle glob patterns
    if "*" in path:
        if run:
            logger.warning("Run name is ignored when using glob patterns.")
            run = ""

        paths = glob.glob(path)
        if not paths:
            logger.error(f"No files found matching pattern: {path}")
            ctx.fail(f"No files found matching pattern: {path}")
    else:
        paths = [path]

    # Files extension validation
    if not file_type:
        for p in paths:
            ext = get_volume_format_from_extension(p)
            if ext not in ["mrc", "zarr", "tiff", "em"]:
                raise ValueError(
                    f"Unsupported file format for {p}. Supported formats are 'mrc', 'zarr', 'tiff', and 'em'.",
                )
            if not os.path.exists(p):
                raise FileNotFoundError(f"File not found: {p}")

    # Convert chunk arg
    chunk_size: Tuple[int, int, int] = tuple(map(int, chunk_size.split(",")[:3]))

    # Prepare runs and group files
    run_to_file = prepare_runs_from_paths(root, paths, run, run_regex, run_name_prefix, create, logger)

    def import_tomogram(run_obj, file_path, **kwargs):
        """Process one tomogram file for a single run"""
        from copick.ops.add import add_tomogram_from_file

        try:
            add_tomogram_from_file(
                root=root,
                run_name=run_obj.name,
                tomo_type=tomo_type,
                file_path=file_path,
                voxel_spacing=voxel_size,
                file_type=file_type,
                create_pyramid=create_pyramid,
                pyramid_levels=pyramid_levels,
                chunks=chunk_size,
                transpose=transpose,
                flip=flip,
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
    name="tomograms-dynamo",
    short_help="Add tomograms from a Dynamo tomolist file.",
    no_args_is_help=True,
)
@add_config_option
@click.option(
    "--tomolist",
    required=True,
    type=click.Path(exists=True),
    help="Path to Dynamo tomolist file (2-column TSV: index, MRC path).",
)
@click.option(
    "--index-map",
    required=False,
    type=click.Path(exists=True),
    default=None,
    help="Path to CSV/TSV mapping tomogram index to run name. If not provided, run names are extracted from filenames.",
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
    help="The file type of the tomogram. Will guess type based on extension if omitted.",
)
@click.option(
    "--voxel-size",
    required=False,
    type=float,
    default=None,
    show_default=True,
    help="Voxel size in Angstrom. Overrides voxel size in the tomogram header.",
)
@add_pyramid_create_options
@add_max_workers_option
@add_volume_transform_options
@add_create_overwrite_options
@add_debug_option
@click.pass_context
def tomogram_from_tomolist(
    ctx,
    config: str,
    tomolist: str,
    index_map: str,
    tomo_type: str,
    file_type: str,
    voxel_size: float,
    create_pyramid: bool,
    pyramid_levels: int,
    chunk_size: str,
    max_workers: int,
    transpose: str,
    flip: str,
    create: bool,
    overwrite: bool,
    debug: bool,
):
    """
    Add tomograms from a Dynamo tomolist file.

    Reads a Dynamo tomolist (a 2-column TSV of tomogram index and MRC path) and
    imports each listed tomogram into its own run. Run names are taken from the MRC
    filenames unless `--index-map` supplies an explicit index-to-run mapping. The
    file format is inferred from the extension unless `--file-type` is given, and a
    multiscale pyramid is computed by default.

    Examples:

        \b
        # Import from a Dynamo tomolist (run names from MRC filenames)
        copick add tomograms-dynamo -c config.json --tomolist tomograms.doc

        \b
        # Import with custom run names from an index map
        copick add tomograms-dynamo -c config.json --tomolist tomograms.doc \\
            --index-map run_mapping.csv

    See Also:

        \b
        copick add tomogram: import a single tomogram or a glob of files
        copick add tomograms-relion: batch import from a RELION tomograms.star file
    """
    import copick
    from copick.ops.run import map_runs, report_results
    from copick.util.formats import read_dynamo_tomolist, read_index_map

    logger = get_logger(__name__, debug=debug)
    root = copick.from_file(config)

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

    # Convert chunk arg
    chunk_size_tuple: Tuple[int, int, int] = tuple(map(int, chunk_size.split(",")[:3]))

    def import_tomogram(run_obj, file_path, **kwargs):
        """Process one tomogram file for a single run"""
        from copick.ops.add import add_tomogram_from_file

        try:
            add_tomogram_from_file(
                root=root,
                run_name=run_obj.name,
                tomo_type=tomo_type,
                file_path=file_path,
                voxel_spacing=voxel_size,
                file_type=file_type,
                create_pyramid=create_pyramid,
                pyramid_levels=pyramid_levels,
                chunks=chunk_size_tuple,
                transpose=transpose,
                flip=flip,
                create=create,
                exist_ok=overwrite,
                overwrite=overwrite,
                log=debug,
            )
            return {"processed": 1, "errors": []}
        except Exception as e:
            error_msg = f"Failed to process {file_path}: {e}"
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

    report_results(results, len(paths), logger)


@add.command(
    name="tomograms-relion",
    short_help="Add tomograms from a RELION tomograms.star file.",
    no_args_is_help=True,
)
@add_config_option
@click.option(
    "--tomograms-star",
    required=True,
    type=click.Path(exists=True),
    help="Path to RELION tomograms.star file.",
)
@click.option(
    "--base-dir",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    help="RELION project root directory for resolving relative paths in the STAR file.",
)
@click.option(
    "--half",
    required=False,
    type=click.Choice(["half1", "half2"], case_sensitive=False),
    default="half1",
    show_default=True,
    help="Which reconstruction half to import (half1 or half2).",
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
    help="The file type of the tomogram. Will guess type based on extension if omitted.",
)
@click.option(
    "--voxel-size",
    required=False,
    type=float,
    default=None,
    show_default=True,
    help="Voxel size in Angstrom. Overrides voxel size from the star file.",
)
@add_pyramid_create_options
@add_max_workers_option
@add_volume_transform_options
@add_create_overwrite_options
@add_debug_option
@click.pass_context
def tomogram_from_star(
    ctx,
    config: str,
    tomograms_star: str,
    base_dir: str,
    half: str,
    tomo_type: str,
    file_type: str,
    voxel_size: float,
    create_pyramid: bool,
    pyramid_levels: int,
    chunk_size: str,
    max_workers: int,
    transpose: str,
    flip: str,
    create: bool,
    overwrite: bool,
    debug: bool,
):
    """
    Add tomograms from a RELION tomograms.star file.

    Reads a RELION tomograms.star file and imports each reconstruction into its own
    run, with run names taken from the `_rlnTomoName` column. Voxel sizes are read
    from the star file unless overridden with `--voxel-size`, and `--base-dir` sets
    the RELION project root used to resolve relative paths in the file. Use `--half`
    to choose which reconstruction half to import. A multiscale pyramid is computed
    by default.

    Examples:

        \b
        # Import the half1 reconstructions (default)
        copick add tomograms-relion -c config.json --tomograms-star tomograms.star \\
            --base-dir /path/to/relion_project

        \b
        # Import the half2 reconstructions instead
        copick add tomograms-relion -c config.json --tomograms-star tomograms.star \\
            --base-dir /path/to/relion_project --half half2

    See Also:

        \b
        copick add tomogram: import a single tomogram or a glob of files
        copick add tomograms-dynamo: batch import from a Dynamo tomolist file
    """
    import copick
    from copick.ops.run import map_runs, report_results
    from copick.util.formats import read_relion_tomograms_star

    logger = get_logger(__name__, debug=debug)
    root = copick.from_file(config)

    # Parse the star file
    tomo_data = read_relion_tomograms_star(tomograms_star, half=half, base_dir=base_dir)

    # Build paths list and run_to_file mapping
    paths = []
    run_to_file = {}
    run_to_voxel_size = {}

    for run_name, (mrc_path, vs) in tomo_data.items():
        if not os.path.exists(mrc_path):
            logger.warning(f"File not found: {mrc_path}, skipping")
            continue
        paths.append(mrc_path)
        run_to_file[run_name] = mrc_path
        run_to_voxel_size[run_name] = vs

    if not paths:
        ctx.fail("No valid tomograms found in tomograms.star")

    logger.info(f"Found {len(run_to_file)} tomograms to import from tomograms.star")

    # Create runs if they don't exist
    if create:
        for run_name in run_to_file:
            if not root.get_run(run_name):
                root.new_run(run_name)
                logger.info(f"Created run: {run_name}")

    # Convert chunk arg
    chunk_size_tuple: Tuple[int, int, int] = tuple(map(int, chunk_size.split(",")[:3]))

    def import_tomogram(run_obj, file_path, run_voxel_size=None, **kwargs):
        """Process one tomogram file for a single run"""
        from copick.ops.add import add_tomogram_from_file

        # Use CLI voxel size if provided, otherwise use star file value
        effective_voxel_size = voxel_size if voxel_size is not None else run_voxel_size

        try:
            add_tomogram_from_file(
                root=root,
                run_name=run_obj.name,
                tomo_type=tomo_type,
                file_path=file_path,
                voxel_spacing=effective_voxel_size,
                file_type=file_type,
                create_pyramid=create_pyramid,
                pyramid_levels=pyramid_levels,
                chunks=chunk_size_tuple,
                transpose=transpose,
                flip=flip,
                create=create,
                exist_ok=overwrite,
                overwrite=overwrite,
                log=debug,
            )
            return {"processed": 1, "errors": []}
        except Exception as e:
            error_msg = f"Failed to process {file_path}: {e}"
            logger.critical(error_msg)
            return {"processed": 0, "errors": [error_msg]}

    # Prepare run-specific arguments
    run_names = list(run_to_file.keys())
    run_args = [
        {"file_path": run_to_file[run_name], "run_voxel_size": run_to_voxel_size.get(run_name)}
        for run_name in run_names
    ]

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

    report_results(results, len(paths), logger)


@add.command(
    short_help="Add a segmentation to the project.",
    no_args_is_help=True,
)
@add_config_option
@add_run_options
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
@add_user_session_options
@click.option(
    "--file-type",
    required=False,
    type=click.Choice(["mrc", "zarr", "tiff", "em"], case_sensitive=False),
    default=None,
    show_default=True,
    help="File type ('mrc', 'zarr', 'tiff', or 'em'). Will guess type based on extension if omitted.",
)
@add_max_workers_option
@add_volume_transform_options
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
    run_name_prefix: str,
    voxel_size: float,
    name: str,
    user_id: str,
    session_id: str,
    file_type: str,
    max_workers: int,
    transpose: str,
    flip: str,
    path: str,
    create: bool,
    overwrite: bool,
    debug: bool,
):
    """
    Add a segmentation to the project.

    Imports a single segmentation, or many at once via a glob pattern, into one or
    more runs. The file format is inferred from the extension unless `--file-type`
    is given. Segmentations are imported as multilabel volumes and may be tagged
    with a name, user ID, and session ID.

    Arguments:

        \b
        PATH: Path to the segmentation file (MRC, Zarr, TIFF, or EM) or a glob pattern.

    Examples:

        \b
        # Import a single segmentation into a named run
        copick add segmentation seg.mrc -c config.json --run TS_001 --name membrane

        \b
        # Import every matching file via a glob pattern
        copick add segmentation "*.mrc" -c config.json --name membrane

        \b
        # Extract the run name from the filename with a regex
        copick add segmentation "TS*.mrc" -c config.json --name membrane \\
            --run-regex "^(TS_\\d+)"

    See Also:

        \b
        copick add tomogram: import a tomogram volume into a run
        copick add object: register a pickable object in the project configuration
    """
    # Deferred import for performance
    import copick
    from copick.ops.add import add_segmentation_from_file
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
    run_to_file = prepare_runs_from_paths(root, paths, run, run_regex, run_name_prefix, create, logger)

    def import_segmentation_callback(run_obj, file_path, **kwargs):
        """Process segmentation files for a single run"""
        try:
            add_segmentation_from_file(
                root=root,
                run_name=run_obj.name,
                file_path=file_path,
                voxel_spacing=voxel_size,
                name=name,
                user_id=user_id,
                session_id=session_id,
                file_type=file_type,
                multilabel=True,
                transpose=transpose,
                flip=flip,
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

    Registers a new pickable object (a particle for point annotations or a
    segmentation for mask annotations) and writes it back to the configuration
    file. Optional metadata such as a numeric label, RGBA color, EMDB/PDB IDs, an
    ontology identifier, a display radius, and a density map (via `--volume`) can be
    attached to the object.

    Examples:

        \b
        # Add a particle object with a display radius
        copick add object -c config.json --name ribosome --object-type particle \\
            --radius 120

        \b
        # Add a particle with a PDB reference and a custom color
        copick add object -c config.json --name ribosome --object-type particle \\
            --radius 120 --pdb-id 4V9D --color "255,0,0,255"

        \b
        # Add a segmentation object with an explicit label
        copick add object -c config.json --name membrane --object-type segmentation \\
            --label 1 --color "0,255,0,128"

    See Also:

        \b
        copick add object-volume: attach a density map to an existing object
        copick add picks: import picks for a registered object
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

    Loads a density map from disk and attaches it to an object that already exists
    in the project configuration. The volume format is inferred from the file
    extension unless `--volume-format` is given, and `--voxel-size` records the
    voxel size of the map in Angstrom.

    Examples:

        \b
        # Attach an MRC density map to an existing object
        copick add object-volume -c config.json --object-name ribosome \\
            --volume-path data/ribosome_volume.mrc

        \b
        # Attach a Zarr volume with an explicit voxel size
        copick add object-volume -c config.json --object-name proteasome \\
            --volume-path data/proteasome.zarr --voxel-size 8.0

    See Also:

        \b
        copick add object: register a pickable object in the project configuration
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
@add_run_options
@click.option(
    "--object-name",
    required=True,
    type=str,
    help="Name of the pickable object (must exist in config).",
)
@add_user_session_options
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
@add_max_workers_option
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
    run_name_prefix: str,
    object_name: str,
    user_id: str,
    session_id: str,
    voxel_size: float,
    file_type: str,
    max_workers: int,
    path: str,
    create: bool,
    overwrite: bool,
    debug: bool,
):
    """
    Add picks from external formats (EM, STAR, Dynamo, CSV).

    Imports particle picks from a single file, or many at once via a glob pattern,
    into one or more runs. The format is inferred from the extension unless
    `--file-type` is given. Supported formats are TOM toolbox EM motivelists
    (.em), RELION particle STAR files (.star), Dynamo tables (.tbl), and copick CSV
    files (.csv). A voxel size is required for the EM, STAR, and Dynamo formats so
    coordinates can be converted; CSV files carry a `run_name` column and are
    grouped automatically.

    For batch imports from a single file that spans many tomograms, use the
    dedicated commands `copick add picks-em`, `copick add picks-dynamo`, or
    `copick add picks-relion` instead. For format-specific conventions (coordinate
    systems, Euler angle conventions), see the docstrings in `copick.util.formats`.

    Arguments:

        \b
        PATH: Path to the picks file (EM, STAR, Dynamo .tbl, or CSV) or a glob pattern.

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
        # Import picks from a CSV (run names come from the file)
        copick add picks particles.csv -c config.json --object-name ribosome

        \b
        # Import from multiple files via a glob (run names from filenames)
        copick add picks "*.star" -c config.json --object-name ribosome \\
            --voxel-size 10.0

    See Also:

        \b
        copick add picks-em: batch import an EM motivelist spanning many tomograms
        copick add picks-dynamo: batch import a Dynamo table spanning many tomograms
        copick add picks-relion: batch import a RELION STAR file with _rlnTomoName
    """
    import copick
    from copick.ops.add import add_picks_from_file
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

    # For CSV files, we handle them specially since they contain run_name column
    if ft == "csv":
        # CSV files contain run names in the file, so we use grouped import
        from copick.ops.add import add_picks_grouped_from_file

        for p in paths:
            try:
                results = add_picks_grouped_from_file(
                    root=root,
                    file_path=p,
                    object_name=object_name,
                    user_id=user_id,
                    session_id=session_id,
                    voxel_spacing=voxel_size or 1.0,  # CSV uses Angstrom coordinates
                    index_to_run={},  # Not used for CSV (uses run_name column)
                    file_type="csv",
                    create=create,
                    exist_ok=overwrite,
                    overwrite=overwrite,
                    log=debug,
                )
                logger.info(f"Successfully imported picks from {p} to {len(results)} runs")
            except Exception as e:
                logger.error(f"Failed to import picks from {p}: {e}")
        return

    # Prepare runs and group files
    run_to_file = prepare_runs_from_paths(root, paths, run, run_regex, run_name_prefix, create, logger)

    def import_picks(run_obj, file_path, **kwargs):
        """Process one picks file for a single run"""
        try:
            add_picks_from_file(
                root=root,
                run_name=run_obj.name,
                file_path=file_path,
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


@add.command(
    name="picks-em",
    short_help="Add picks from EM motivelist files containing multiple tomograms.",
    no_args_is_help=True,
)
@add_config_option
@click.option(
    "--object-name",
    required=True,
    type=str,
    help="Name of the pickable object (must exist in config).",
)
@add_user_session_options
@click.option(
    "--voxel-size",
    required=True,
    type=float,
    help="Voxel size in Angstrom (required for coordinate conversion).",
)
@click.option(
    "--index-map",
    required=True,
    type=click.Path(exists=True),
    help="Path to a CSV/TSV file mapping tomogram index to run name (2 columns: index, run_name).",
)
@click.option(
    "--tomo-index-row",
    required=False,
    type=int,
    default=4,
    show_default=True,
    help="Row index (0-based) for tomogram index in EM motivelists. Default is row 4 (Artiatomi convention).",
)
@add_max_workers_option
@add_create_overwrite_options
@add_debug_option
@click.argument(
    "path",
    required=True,
    type=str,
    metavar="PATH",
)
@click.pass_context
def picks_em(
    ctx,
    config: str,
    object_name: str,
    user_id: str,
    session_id: str,
    voxel_size: float,
    index_map: str,
    tomo_index_row: int,
    max_workers: int,
    path: str,
    create: bool,
    overwrite: bool,
    debug: bool,
):
    """
    Add picks from EM motivelist files containing multiple tomograms.

    Imports particle picks from one or more TOM toolbox EM motivelists, where a
    single file can hold picks from many tomograms. Each particle's tomogram is
    identified by an index stored in a configurable motivelist row
    (`--tomo-index-row`, default 4 for the Artiatomi convention), and `--index-map`
    provides a 2-column CSV/TSV that maps those indices to copick run names (e.g.
    `1,TS_001`). A voxel size is required to convert coordinates.

    Arguments:

        \b
        PATH: Path to the EM motivelist file (.em) or a glob pattern.

    Examples:

        \b
        # Import an EM motivelist with an index map
        copick add picks-em motivelist.em -c config.json --object-name ribosome \\
            --voxel-size 10.0 --index-map tomo_mapping.csv

        \b
        # Import with a custom tomogram-index row
        copick add picks-em motivelist.em -c config.json --object-name ribosome \\
            --voxel-size 10.0 --index-map tomo_mapping.csv --tomo-index-row 5

        \b
        # Import multiple files via a glob pattern
        copick add picks-em "*.em" -c config.json --object-name ribosome \\
            --voxel-size 10.0 --index-map tomo_mapping.csv

    See Also:

        \b
        copick add picks: import picks from a single file into one run
        copick add picks-dynamo: batch import a Dynamo table spanning many tomograms
        copick add picks-relion: batch import a RELION STAR file with _rlnTomoName
    """
    import copick
    from copick.ops.add import add_picks_grouped_from_file
    from copick.util.formats import read_index_map

    logger = get_logger(__name__, debug=debug)

    # Get root
    root = copick.from_file(config)

    # Handle glob patterns
    if "*" in path:
        paths = glob.glob(path)
        if not paths:
            logger.error(f"No files found matching pattern: {path}")
            ctx.fail(f"No files found matching pattern: {path}")
    else:
        paths = [path]

    # Load index map
    index_to_run = read_index_map(index_map)
    logger.info(f"Loaded index map with {len(index_to_run)} entries")

    # Process each file with grouped import
    total_runs = set()
    for p in paths:
        try:
            results = add_picks_grouped_from_file(
                root=root,
                file_path=p,
                object_name=object_name,
                user_id=user_id,
                session_id=session_id,
                voxel_spacing=voxel_size,
                index_to_run=index_to_run,
                file_type="em",
                tomo_index_row=tomo_index_row,
                create=create,
                exist_ok=overwrite,
                overwrite=overwrite,
                log=debug,
            )

            total_runs.update(results.keys())
            logger.info(f"Imported picks from {p} to {len(results)} runs")
        except Exception as e:
            logger.error(f"Failed to import picks from {p}: {e}")

    logger.info(f"Successfully imported picks to {len(total_runs)} runs total")


@add.command(
    name="picks-dynamo",
    short_help="Add picks from Dynamo table files containing multiple tomograms.",
    no_args_is_help=True,
)
@add_config_option
@click.option(
    "--object-name",
    required=True,
    type=str,
    help="Name of the pickable object (must exist in config).",
)
@add_user_session_options
@click.option(
    "--voxel-size",
    required=True,
    type=float,
    help="Voxel size in Angstrom (required for coordinate conversion).",
)
@click.option(
    "--index-map",
    required=False,
    type=click.Path(exists=True),
    default=None,
    help="Path to a CSV/TSV file mapping tomogram index to run name. Mutually exclusive with --tomolist.",
)
@click.option(
    "--tomolist",
    required=False,
    type=click.Path(exists=True),
    default=None,
    help="Path to a Dynamo tomolist file (2-column TSV: index, MRC path). "
    "Run names are extracted from MRC filenames. Mutually exclusive with --index-map.",
)
@add_max_workers_option
@add_create_overwrite_options
@add_debug_option
@click.argument(
    "path",
    required=True,
    type=str,
    metavar="PATH",
)
@click.pass_context
def picks_dynamo(
    ctx,
    config: str,
    object_name: str,
    user_id: str,
    session_id: str,
    voxel_size: float,
    index_map: str,
    tomolist: str,
    max_workers: int,
    path: str,
    create: bool,
    overwrite: bool,
    debug: bool,
):
    """
    Add picks from Dynamo table files containing multiple tomograms.

    Imports particle picks from one or more Dynamo table files, where a single file
    can hold picks from many tomograms (the tomogram index is read from column 20).
    Provide exactly one of `--index-map` (a 2-column CSV/TSV mapping tomogram index
    to run name, e.g. `1,TS_001`) or `--tomolist` (a Dynamo tomolist whose run names
    come from the MRC filenames) to map indices to copick runs. A voxel size is
    required to convert coordinates.

    Arguments:

        \b
        PATH: Path to the Dynamo table file (.tbl) or a glob pattern.

    Examples:

        \b
        # Import using an index map
        copick add picks-dynamo particles.tbl -c config.json --object-name ribosome \\
            --voxel-size 10.0 --index-map tomo_mapping.csv

        \b
        # Import using a Dynamo tomolist (run names from MRC filenames)
        copick add picks-dynamo particles.tbl -c config.json --object-name ribosome \\
            --voxel-size 10.0 --tomolist tomograms.doc

        \b
        # Import multiple files via a glob pattern
        copick add picks-dynamo "*.tbl" -c config.json --object-name ribosome \\
            --voxel-size 10.0 --index-map tomo_mapping.csv

    See Also:

        \b
        copick add picks: import picks from a single file into one run
        copick add picks-em: batch import an EM motivelist spanning many tomograms
        copick add picks-relion: batch import a RELION STAR file with _rlnTomoName
    """
    import copick
    from copick.ops.add import add_picks_grouped_from_file
    from copick.util.formats import read_dynamo_tomolist, read_index_map

    logger = get_logger(__name__, debug=debug)

    # Validate mutually exclusive options
    if index_map and tomolist:
        ctx.fail("--index-map and --tomolist are mutually exclusive. Provide only one.")
    if not index_map and not tomolist:
        ctx.fail("Either --index-map or --tomolist must be provided.")

    # Get root
    root = copick.from_file(config)

    # Handle glob patterns
    if "*" in path:
        paths = glob.glob(path)
        if not paths:
            logger.error(f"No files found matching pattern: {path}")
            ctx.fail(f"No files found matching pattern: {path}")
    else:
        paths = [path]

    # Load index-to-run mapping
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
            results = add_picks_grouped_from_file(
                root=root,
                file_path=p,
                object_name=object_name,
                user_id=user_id,
                session_id=session_id,
                voxel_spacing=voxel_size,
                index_to_run=index_to_run,
                file_type="dynamo",
                create=create,
                exist_ok=overwrite,
                overwrite=overwrite,
                log=debug,
            )
            total_runs.update(results.keys())
            logger.info(f"Imported picks from {p} to {len(results)} runs")
        except Exception as e:
            logger.error(f"Failed to import picks from {p}: {e}")

    logger.info(f"Successfully imported picks to {len(total_runs)} runs total")


@add.command(
    name="picks-relion",
    short_help="Add picks from RELION STAR files containing multiple tomograms.",
    no_args_is_help=True,
)
@add_config_option
@click.option(
    "--object-name",
    required=True,
    type=str,
    help="Name of the pickable object (must exist in config).",
)
@add_user_session_options
@click.option(
    "--voxel-size",
    required=True,
    type=float,
    help="Voxel size in Angstrom (required for coordinate conversion).",
)
@click.option(
    "--tomograms-star",
    required=False,
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
    default=None,
    help="Path to RELION tomograms.star file for RELION 5.0 coordinate conversion. "
    "If not provided and RELION 5.0 format is detected, tomogram dimensions will be "
    "read from existing tomograms in the copick project.",
)
@click.option(
    "--relion-version",
    required=False,
    type=click.Choice(["auto", "relion4", "relion5"], case_sensitive=False),
    default="auto",
    show_default=True,
    help="RELION version for coordinate format. 'auto' detects from column names.",
)
@add_max_workers_option
@add_create_overwrite_options
@add_debug_option
@click.argument(
    "path",
    required=True,
    type=str,
    metavar="PATH",
)
@click.pass_context
def picks_relion(
    ctx,
    config: str,
    object_name: str,
    user_id: str,
    session_id: str,
    voxel_size: float,
    tomograms_star: str,
    relion_version: str,
    max_workers: int,
    path: str,
    create: bool,
    overwrite: bool,
    debug: bool,
):
    """
    Add picks from RELION STAR files containing multiple tomograms.

    Imports particle picks from one or more RELION particle STAR files that carry
    the `_rlnTomoName` column identifying each particle's tomogram; run names are
    extracted from that column automatically. Both RELION 4.x (pixel coordinates in
    `rlnCoordinateX/Y/Z`) and RELION 5.0 (centered Angstrom coordinates in
    `rlnCenteredCoordinateX/Y/ZAngst`) formats are supported, with the version
    auto-detected from the column names unless overridden by `--relion-version`.

    For RELION 5.0, tomogram dimensions are needed to convert centered coordinates
    to absolute coordinates. Supply them with `--tomograms-star`, or omit it to read
    the dimensions from tomograms already present in the copick project.

    Arguments:

        \b
        PATH: Path to the RELION particles STAR file (.star) or a glob pattern.

    Examples:

        \b
        # Import RELION 4.x particles
        copick add picks-relion particles.star -c config.json --object-name ribosome \\
            --voxel-size 10.0

        \b
        # Import RELION 5.0 particles using a tomograms.star for dimensions
        copick add picks-relion particles.star -c config.json --object-name ribosome \\
            --voxel-size 5.0 --tomograms-star tomograms.star

        \b
        # Import RELION 5.0 particles using existing copick tomogram dimensions
        copick add picks-relion particles.star -c config.json --object-name ribosome \\
            --voxel-size 5.0

    See Also:

        \b
        copick add picks: import picks from a single file into one run
        copick add picks-em: batch import an EM motivelist spanning many tomograms
        copick add picks-dynamo: batch import a Dynamo table spanning many tomograms
    """
    import copick
    from copick.ops.add import add_picks_grouped_from_file
    from copick.util.formats import (
        detect_relion_version,
        get_tomogram_centers_from_copick,
        read_relion5_tomogram_centers,
        read_star_particles,
    )

    logger = get_logger(__name__, debug=debug)

    # Get root
    root = copick.from_file(config)

    # Handle glob patterns
    if "*" in path:
        paths = glob.glob(path)
        if not paths:
            logger.error(f"No files found matching pattern: {path}")
            ctx.fail(f"No files found matching pattern: {path}")
    else:
        paths = [path]

    # Process each file with grouped import
    total_runs = set()
    for p in paths:
        try:
            # Read STAR file to detect version
            df = read_star_particles(p)
            detected_version = relion_version if relion_version != "auto" else detect_relion_version(df)
            logger.info(f"Detected RELION version: {detected_version}")

            # Get tomogram centers for RELION 5.0
            tomogram_centers = None
            if detected_version == "relion5":
                if tomograms_star:
                    # Option A: Use tomograms.star file
                    logger.info(f"Loading tomogram centers from {tomograms_star}")
                    tomogram_centers = read_relion5_tomogram_centers(tomograms_star)
                else:
                    # Option B: Use existing copick project tomograms
                    run_names = df["rlnTomoName"].unique().tolist() if "rlnTomoName" in df.columns else []
                    logger.info(f"Loading tomogram centers from copick project for {len(run_names)} runs")
                    tomogram_centers = get_tomogram_centers_from_copick(root, run_names, voxel_size)

                    if not tomogram_centers:
                        ctx.fail(
                            "RELION 5.0 coordinates require tomogram dimensions. Either:\n"
                            "  1. Provide --tomograms-star with tomogram metadata, or\n"
                            "  2. Import tomograms first so dimensions can be read from copick project",
                        )

            results = add_picks_grouped_from_file(
                root=root,
                file_path=p,
                object_name=object_name,
                user_id=user_id,
                session_id=session_id,
                voxel_spacing=voxel_size,
                index_to_run={},  # Not used for STAR files
                file_type="star",
                create=create,
                exist_ok=overwrite,
                overwrite=overwrite,
                log=debug,
                tomogram_centers=tomogram_centers,
                relion_version=detected_version,
            )
            total_runs.update(results.keys())
            logger.info(f"Imported picks from {p} to {len(results)} runs")
        except (SystemExit, click.UsageError):
            # Re-raise click exceptions from ctx.fail()
            raise
        except Exception as e:
            logger.error(f"Failed to import picks from {p}: {e}")

    logger.info(f"Successfully imported picks to {len(total_runs)} runs total")
