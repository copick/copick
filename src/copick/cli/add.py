import concurrent.futures
import glob
import os
from typing import Any, Callable, Dict, List, Tuple

import click
import tqdm

import copick
from copick.cli.util import add_config_option, add_create_overwrite_options, add_debug_option
from copick.ops.add import _add_tomogram_mrc, _add_tomogram_zarr, add_segmentation
from copick.util.log import get_logger


def process_files_parallel(
    paths: List[str],
    process_func: Callable,
    process_args: Dict[str, Any],
    input_run: str,
    max_workers: int = None,
    progress_desc: str = "Processing files",
    logger=None,
    debug: bool = False,
) -> List[str]:
    """
    Generic parallel file processor using ThreadPoolExecutor.

    Args:
        paths: List of file paths to process
        process_func: Function to process each file (must accept path as first argument)
        process_args: Dictionary of arguments to pass to process_func
        input_run: Run name (empty string means derive from filename)
        max_workers: Number of worker threads
        progress_desc: Description for progress bar
        logger: Logger instance
        debug: Debug mode flag

    Returns:
        List of error messages (empty if all succeeded)
    """

    # Auto-adjust workers for large files
    if max_workers is None:
        max_workers = min(4, os.cpu_count())
        if logger:
            logger.info(f"Auto-selected {max_workers} workers for large file processing")

    def process_single_file(path_item):
        """Process a single file"""
        try:
            # Get run name
            if input_run == "":
                filename = os.path.basename(path_item)
                current_run = filename.rsplit(".", 1)[0]
            else:
                current_run = input_run

            # Call the processing function with the path and run name
            process_func(path_item, current_run, **process_args)

            return {"success": True, "path": path_item, "message": f"Successfully processed: {path_item}"}

        except Exception as e:
            error_msg = f"Failed to process {path_item}: {e}"
            if logger:
                logger.critical(error_msg)
            return {"success": False, "path": path_item, "message": error_msg}

    if logger:
        logger.info(f"Processing {len(paths)} files with {max_workers} workers")

    errors = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_path = {executor.submit(process_single_file, path_item): path_item for path_item in paths}

        # Use tqdm to track progress as futures complete
        with tqdm.tqdm(total=len(paths), desc=progress_desc, unit="file") as pbar:
            for future in concurrent.futures.as_completed(future_to_path):
                try:
                    result = future.result()
                    if result["success"]:
                        pbar.set_postfix_str(f"✓ {os.path.basename(result['path'])}")
                        if debug and logger:
                            logger.info(result["message"])
                    else:
                        errors.append(result["message"])
                        pbar.set_postfix_str(f"✗ {os.path.basename(result['path'])}")
                except Exception as e:
                    path_item = future_to_path[future]
                    error_msg = f"Unexpected error processing {path_item}: {e}"
                    if logger:
                        logger.critical(error_msg)
                    errors.append(error_msg)
                    pbar.set_postfix_str(f"✗ {os.path.basename(path_item)}")
                finally:
                    pbar.update(1)

    return errors


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
    input_run = run

    def import_tomogram(
        path_item,
        current_run,
        root,
        tomo_type,
        file_type,
        voxel_size,
        create_pyramid,
        pyramid_levels,
        chunk_size,
        create,
        overwrite,
        debug,
    ):
        """Process a single tomogram file"""
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
                current_run,
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
                current_run,
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

    # Process tomograms in parallel
    process_args = {
        "root": root,
        "tomo_type": tomo_type,
        "file_type": file_type,
        "voxel_size": voxel_size,
        "create_pyramid": create_pyramid,
        "pyramid_levels": pyramid_levels,
        "chunk_size": chunk_size,
        "create": create,
        "overwrite": overwrite,
        "debug": debug,
    }

    errors = process_files_parallel(
        paths=paths,
        process_func=import_tomogram,
        process_args=process_args,
        input_run=input_run,
        max_workers=max_workers,
        progress_desc="Processing tomograms",
        logger=logger,
        debug=debug,
    )

    # Report results
    if errors:
        logger.error(f"Failed to process {len(errors)} tomograms:")
        for error in errors:
            logger.error(error)
        if len(errors) == len(paths):
            ctx.fail("All tomograms failed to process")
        else:
            logger.warning(f"Successfully processed {len(paths) - len(errors)} out of {len(paths)} tomograms")
    else:
        logger.info(f"Successfully processed all {len(paths)} tomograms")


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

    input_run = run

    def import_segmentation(
        path_item,
        current_run,
        root,
        voxel_size,
        name,
        user_id,
        session_id,
        create,
        overwrite,
        debug,
    ):
        """Process a single segmentation file"""
        add_segmentation(
            root,
            current_run,
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

    # Process segmentations in parallel
    process_args = {
        "root": root,
        "voxel_size": voxel_size,
        "name": name,
        "user_id": user_id,
        "session_id": session_id,
        "create": create,
        "overwrite": overwrite,
        "debug": debug,
    }

    errors = process_files_parallel(
        paths=paths,
        process_func=import_segmentation,
        process_args=process_args,
        input_run=input_run,
        max_workers=max_workers,
        progress_desc="Processing segmentations",
        logger=logger,
        debug=debug,
    )

    # Report results
    if errors:
        logger.error(f"Failed to process {len(errors)} segmentations:")
        for error in errors:
            logger.error(error)
        if len(errors) == len(paths):
            ctx.fail("All segmentations failed to process")
        else:
            logger.warning(f"Successfully processed {len(paths) - len(errors)} out of {len(paths)} segmentations")
    else:
        logger.info(f"Successfully processed all {len(paths)} segmentations")
