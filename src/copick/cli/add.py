import glob
import os
from typing import Tuple

import click
import tqdm

import copick
from copick.cli.util import add_config_option, add_create_overwrite_options, add_debug_option
from copick.ops.add import _add_tomogram_mrc, _add_tomogram_zarr, add_segmentation
from copick.util.log import get_logger


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

    for path in tqdm.tqdm(paths, desc="Adding tomograms", unit="file", total=len(paths)):
        try:
            # Get run name
            if input_run == "":
                # Use os.path.basename for cross-platform compatibility
                filename = os.path.basename(path)
                run = filename.rsplit(".", 1)[0]
            else:
                run = input_run

            # Get file type
            ft = file_type.lower() if file_type else None
            if ft is None:
                if path.endswith(".mrc"):
                    ft = "mrc"
                elif path.endswith(".zarr"):
                    ft = "zarr"
                else:
                    ctx.fail(f"Could not determine file type from path: {path}")

            if ft == "mrc":
                _add_tomogram_mrc(
                    root,
                    run,
                    tomo_type,
                    path,
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
                    run,
                    tomo_type,
                    path,
                    voxel_spacing=voxel_size,
                    create_pyramid=create_pyramid,
                    pyramid_levels=pyramid_levels,
                    chunks=chunk_size,
                    create=create,
                    overwrite=overwrite,
                    log=debug,
                )
        except Exception as e:
            logger.critical(f"Failed to add tomogram: {e}")
            ctx.fail(f"Error adding tomogram: {e}")


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

    # Add segmentations
    for path in tqdm.tqdm(paths, desc="Adding Segmentations", unit="file", total=len(paths)):
        try:
            # Get run name
            if input_run == "":
                # Use os.path.basename for cross-platform compatibility
                filename = os.path.basename(path)
                run = filename.rsplit(".", 1)[0]
            else:
                run = input_run
            print(run)

            # Add segmentation
            add_segmentation(
                root,
                run,
                path,
                voxel_size,
                name,
                user_id,
                session_id,
                multilabel=True,
                create=create,
                overwrite=overwrite,
                log=debug,
            )
        except Exception as e:
            logger.critical(f"Failed to add tomogram: {e}")
            ctx.fail(f"Error adding tomogram: {e}")
