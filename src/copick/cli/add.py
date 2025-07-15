import glob
import os
from typing import Dict, List, Tuple

import click

import copick
from copick.cli.util import add_config_option, add_create_overwrite_options, add_debug_option
from copick.ops.add import _add_tomogram_mrc, _add_tomogram_zarr, add_segmentation
from copick.ops.run import map_runs, report_results
from copick.util.log import get_logger


def prepare_runs_from_paths(
    root,
    paths: List[str],
    input_run: str,
    create: bool = True,
    logger=None,
) -> Dict[str, List[str]]:
    """
    Prepare runs from file paths, creating runs if necessary.

    Args:
        root: Copick root
        paths: List of file paths
        input_run: Run name (empty string means derive from filename)
        create: Whether to create runs if they don't exist
        logger: Logger instance

    Returns:
        Dictionary mapping run names to lists of file paths
    """
    run_to_files = {}

    # Group files by run name
    for path in paths:
        if input_run == "":
            filename = os.path.basename(path)
            current_run = filename.rsplit(".", 1)[0]
        else:
            current_run = input_run

        if current_run not in run_to_files:
            run_to_files[current_run] = []
        run_to_files[current_run].append(path)

    # Create runs if they don't exist
    for run_name in run_to_files:
        if not root.get_run(run_name):
            if create:
                root.new_run(run_name)
                if logger:
                    logger.info(f"Created run: {run_name}")
            else:
                if logger:
                    logger.warning(f"Run {run_name} does not exist and create=False")

    return run_to_files


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

    # Convert chunk arg
    chunk_size: Tuple[int, int, int] = tuple(map(int, chunk_size.split(",")[:3]))

    # Prepare runs and group files
    run_to_files = prepare_runs_from_paths(root, paths, run, create, logger)

    def import_tomogram(run_obj, file_paths, **kwargs):
        """Process tomogram files for a single run"""
        errors = []
        processed = 0

        for path_item in file_paths:
            try:
                # Get file type
                ft = file_type.lower() if file_type else None
                if ft is None:
                    if path_item.endswith(".mrc"):
                        ft = "mrc"
                    elif path_item.endswith(".zarr"):
                        ft = "zarr"
                    else:
                        raise ValueError(f"Could not determine file type from path: {path_item}")

                if ft == "mrc":
                    _add_tomogram_mrc(
                        root,
                        run_obj.name,
                        tomo_type,
                        path_item,
                        voxel_spacing=voxel_size,
                        create_pyramid=create_pyramid,
                        pyramid_levels=pyramid_levels,
                        chunks=chunk_size,
                        create=create,
                        overwrite=overwrite,
                        log=debug,
                    )
                elif ft == "zarr":
                    _add_tomogram_zarr(
                        root,
                        run_obj.name,
                        tomo_type,
                        path_item,
                        voxel_spacing=voxel_size,
                        create_pyramid=create_pyramid,
                        pyramid_levels=pyramid_levels,
                        chunks=chunk_size,
                        create=create,
                        overwrite=overwrite,
                        log=debug,
                    )
                processed += 1

            except Exception as e:
                error_msg = f"Failed to process {path_item}: {e}"
                errors.append(error_msg)
                if logger:
                    logger.critical(error_msg)

        return {"processed": processed, "errors": errors}

    # Prepare run-specific arguments
    run_names = list(run_to_files.keys())
    run_args = [{"file_paths": run_to_files[run_name]} for run_name in run_names]

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
    run_to_files = prepare_runs_from_paths(root, paths, run, create, logger)

    def import_segmentation(run_obj, file_paths, **kwargs):
        """Process segmentation files for a single run"""
        errors = []
        processed = 0

        for path_item in file_paths:
            try:
                add_segmentation(
                    root,
                    run_obj.name,
                    path_item,
                    voxel_size,
                    name,
                    user_id,
                    session_id,
                    multilabel=True,
                    create=create,
                    overwrite=overwrite,
                    log=debug,
                )
                processed += 1

            except Exception as e:
                error_msg = f"Failed to process {path_item}: {e}"
                errors.append(error_msg)
                if logger:
                    logger.critical(error_msg)

        return {"processed": processed, "errors": errors}

    # Prepare run-specific arguments
    run_names = list(run_to_files.keys())
    run_args = [{"file_paths": run_to_files[run_name]} for run_name in run_names]

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
