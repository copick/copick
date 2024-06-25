import click

from copick.ops.add import _add_tomogram_mrc, _add_tomogram_zarr, add_run, add_voxelspacing
from copick.ops.open import from_file


def common_options(func):
    opts = [
        click.Option(
            ("-c", "--config"),
            type=str,
            help="Path to the configuration file.",
            required=True,
            metavar="PATH",
            envvar="COPICK_CONFIG",
            show_envvar=True,
        ),
        click.Option(
            ("--create/--no-create",),
            is_flag=True,
            help="Create the object if it does not exist.",
            default=True,
            show_default=True,
        ),
        click.Option(
            ("--overwrite/--no-overwrite",),
            is_flag=True,
            help="Overwrite the object if it exists.",
            default=False,
            show_default=True,
        ),
        click.Option(
            ("-v", "--verbose"),
            count=True,
        ),
    ]

    for opt in opts:
        func = opt(func)

    return func


@click.group()
def add(ctx):
    pass


@click.command()
@common_options
@click.argument("name", required=True, type=str)
def run(
    config: str,
    name: str,
    create: bool,
    overwrite: bool,
    verbose: int,
) -> int:
    root = from_file(config)
    add_run(root, name, overwrite=overwrite, log=verbose > 0)

    return 0


@click.command()
@common_options
@click.option("run", required=True, type=str)
@click.argument("voxel_spacing", required=True, type=float)
def voxelspacing(
    config: str,
    run: str,
    voxel_spacing: float,
    create: bool,
    overwrite: bool,
    verbose: int,
) -> int:
    root = from_file(config)
    add_voxelspacing(root, run, voxel_spacing, create=create, overwrite=overwrite, log=verbose > 0)

    return 0


@click.command()
@common_options
@click.option(
    "--run",
    required=True,
    type=str,
    help="The name of the run.",
)
@click.option(
    "--tomo-type",
    required=True,
    type=str,
    help="The name of the tomogram (e.g. wbp).",
)
@click.option(
    "--file-type",
    required=False,
    type=str,
    default=None,
    help="The file type of the tomogram ('mrc' or 'zarr'). Will guess type based on extension if omitted.",
)
@click.option(
    "--voxel_size",
    required=False,
    type=float,
    default=None,
    show_default=True,
    help="Overrides voxel size in the tomogram header.",
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
@click.argument(
    "path",
    required=True,
    type=str,
    help="Path to the tomogram file.",
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
    verbose: int,
) -> int:
    # Get root
    root = from_file(config)

    # Get file type
    if file_type is None:
        if path.endswith(".mrc"):
            file_type = "mrc"
        elif path.endswith(".zarr"):
            file_type = "zarr"
        else:
            raise ValueError(f"Could not determine file type from path: {path}")

    # Convert chunk arg
    chunk_size = tuple(map(int, chunk_size.split(",")))

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
            log=verbose > 0,
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
            log=verbose > 0,
        )
