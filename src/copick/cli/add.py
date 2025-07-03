from typing import Tuple

import click

import copick
from copick.cli.util import add_config_option, add_create_overwrite_options, add_debug_option
from copick.ops.add import _add_tomogram_mrc, _add_tomogram_zarr
from copick.util.log import get_logger


@click.group()
def add(ctx):
    pass


@add.command(short_help="Add a tomogram to the project.")
@add_config_option
@click.option(
    "--run",
    required=False,
    type=str,
    help="The name of the run. If not specified, will use the name of the file (stripping extension).",
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
    "--voxel_size",
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
def tomogram(
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
    Add a tomogram to a run.

    PATH: Path to the tomogram file (MRC or Zarr format).
    """
    get_logger(__name__, debug=debug)

    # Get root
    root = copick.from_file(config)

    # Get run name
    if run == "":
        run = path.split("/")[-1].rsplit(".", 1)[0]

    # Get file type
    if file_type is None:
        if path.endswith(".mrc"):
            file_type = "mrc"
        elif path.endswith(".zarr"):
            file_type = "zarr"
        else:
            raise ValueError(f"Could not determine file type from path: {path}")

    # Convert chunk arg
    chunk_size: Tuple[int, int, int] = tuple(map(int, chunk_size.split(",")[:3]))

    if file_type == "mrc":
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
    elif file_type == "zarr":
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
