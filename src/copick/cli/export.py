"""CLI commands for exporting copick data to external formats."""

import click

from copick.cli.util import add_config_option, add_debug_option
from copick.util.log import get_logger


@click.group()
@click.pass_context
def export(ctx):
    """Export copick data to external formats."""
    pass


@export.command(
    short_help="Export picks to external formats (EM, STAR, Dynamo, CSV).",
    no_args_is_help=True,
)
@add_config_option
@click.option(
    "--picks-uri",
    required=True,
    type=str,
    help="URI to filter picks for export (e.g., 'ribosome:user1/*' or '*:*/*').",
)
@click.option(
    "--output-dir",
    required=True,
    type=str,
    help="Output directory for exported files.",
    metavar="PATH",
)
@click.option(
    "--output-format",
    required=True,
    type=click.Choice(["em", "star", "dynamo", "csv"], case_sensitive=False),
    help="Output format for picks.",
)
@click.option(
    "--run-names",
    type=str,
    default="",
    help="Comma-separated list of run names to export. If not specified, exports from all runs.",
)
@click.option(
    "--voxel-size",
    type=float,
    default=None,
    help="Voxel size in Angstrom (required for EM, STAR, and Dynamo formats).",
)
@click.option(
    "--include-optics/--no-include-optics",
    is_flag=True,
    default=True,
    show_default=True,
    help="Include optics group in STAR file output.",
)
@click.option(
    "--max-workers",
    type=int,
    default=8,
    show_default=True,
    help="Number of parallel workers.",
)
@add_debug_option
@click.pass_context
def picks(
    ctx,
    config: str,
    picks_uri: str,
    output_dir: str,
    output_format: str,
    run_names: str,
    voxel_size: float,
    include_optics: bool,
    max_workers: int,
    debug: bool,
):
    """
    Export picks to external file formats.

    Examples:

    \b
    # Export all picks from user1 to EM format
    copick export picks -c config.json --picks-uri "ribosome:user1/*" \\
        --output-dir ./output --output-format em --voxel-size 10.0

    \b
    # Export all picks to STAR format with optics
    copick export picks -c config.json --picks-uri "*:*/*" \\
        --output-dir ./output --output-format star --voxel-size 10.0 --include-optics

    \b
    # Export specific runs to Dynamo table format
    copick export picks -c config.json --picks-uri "ribosome:*/*" \\
        --output-dir ./output --output-format dynamo --voxel-size 10.0 \\
        --run-names "TS_001,TS_002"

    \b
    # Export all picks to CSV format
    copick export picks -c config.json --picks-uri "*:*/*" \\
        --output-dir ./output --output-format csv

    For format-specific conventions (coordinate systems, Euler angle conventions),
    see the documentation or the docstrings in copick.util.formats.
    """
    from copick.ops.export import export as export_op

    logger = get_logger(__name__, debug=debug)

    # Validate voxel size for formats that require it
    if output_format.lower() in ["em", "star", "dynamo"] and voxel_size is None:
        ctx.fail(f"--voxel-size is required for {output_format.upper()} format export.")

    # Parse run names
    run_names_list = None
    if run_names:
        run_names_list = [name.strip() for name in run_names.split(",") if name.strip()]

    try:
        export_op(
            config=config,
            output_dir=output_dir,
            run_names=run_names_list,
            picks_uri=picks_uri,
            output_format=output_format,
            voxel_spacing=voxel_size,
            include_optics=include_optics,
            n_workers=max_workers,
            log=debug,
        )
        logger.info("Export completed successfully.")
    except Exception as e:
        logger.critical(f"Export failed: {e}")
        ctx.fail(f"Export failed: {e}")


@export.command(
    short_help="Export tomograms to external formats (MRC, TIFF, Zarr).",
    no_args_is_help=True,
)
@add_config_option
@click.option(
    "--tomogram-uri",
    required=True,
    type=str,
    help="URI to filter tomograms for export (e.g., 'wbp@10.0' or '*@*').",
)
@click.option(
    "--output-dir",
    required=True,
    type=str,
    help="Output directory for exported files.",
    metavar="PATH",
)
@click.option(
    "--output-format",
    required=True,
    type=click.Choice(["mrc", "tiff", "zarr"], case_sensitive=False),
    help="Output format for tomograms.",
)
@click.option(
    "--run-names",
    type=str,
    default="",
    help="Comma-separated list of run names to export. If not specified, exports from all runs.",
)
@click.option(
    "--level",
    type=int,
    default=0,
    show_default=True,
    help="Pyramid level to export (for MRC and TIFF).",
)
@click.option(
    "--compression",
    type=click.Choice(["lzw", "zlib", "jpeg", "none"], case_sensitive=False),
    default=None,
    help="Compression method for TIFF output.",
)
@click.option(
    "--copy-all-levels/--level-only",
    is_flag=True,
    default=True,
    show_default=True,
    help="Copy all pyramid levels for Zarr output.",
)
@click.option(
    "--max-workers",
    type=int,
    default=8,
    show_default=True,
    help="Number of parallel workers.",
)
@add_debug_option
@click.pass_context
def tomogram(
    ctx,
    config: str,
    tomogram_uri: str,
    output_dir: str,
    output_format: str,
    run_names: str,
    level: int,
    compression: str,
    copy_all_levels: bool,
    max_workers: int,
    debug: bool,
):
    """
    Export tomograms to external file formats.

    Examples:

    \b
    # Export all wbp tomograms at 10A to MRC
    copick export tomogram -c config.json --tomogram-uri "wbp@10.0" \\
        --output-dir ./output --output-format mrc

    \b
    # Export tomograms to TIFF with compression
    copick export tomogram -c config.json --tomogram-uri "wbp@10.0" \\
        --output-dir ./output --output-format tiff --compression lzw

    \b
    # Export tomograms to Zarr (copy all levels)
    copick export tomogram -c config.json --tomogram-uri "*@*" \\
        --output-dir ./output --output-format zarr --copy-all-levels

    \b
    # Export specific level from specific runs
    copick export tomogram -c config.json --tomogram-uri "wbp@10.0" \\
        --output-dir ./output --output-format mrc --level 1 \\
        --run-names "TS_001,TS_002"
    """
    from copick.ops.export import export as export_op

    logger = get_logger(__name__, debug=debug)

    # Parse run names
    run_names_list = None
    if run_names:
        run_names_list = [name.strip() for name in run_names.split(",") if name.strip()]

    # Handle compression
    compression_value = compression if compression and compression.lower() != "none" else None

    try:
        export_op(
            config=config,
            output_dir=output_dir,
            run_names=run_names_list,
            tomogram_uri=tomogram_uri,
            output_format=output_format,
            level=level,
            compression=compression_value,
            n_workers=max_workers,
            log=debug,
        )
        logger.info("Export completed successfully.")
    except Exception as e:
        logger.critical(f"Export failed: {e}")
        ctx.fail(f"Export failed: {e}")


@export.command(
    short_help="Export segmentations to external formats (MRC, TIFF, Zarr, EM).",
    no_args_is_help=True,
)
@add_config_option
@click.option(
    "--segmentation-uri",
    required=True,
    type=str,
    help="URI to filter segmentations for export (e.g., 'membrane:user1/*@10.0').",
)
@click.option(
    "--output-dir",
    required=True,
    type=str,
    help="Output directory for exported files.",
    metavar="PATH",
)
@click.option(
    "--output-format",
    required=True,
    type=click.Choice(["mrc", "tiff", "zarr", "em"], case_sensitive=False),
    help="Output format for segmentations.",
)
@click.option(
    "--run-names",
    type=str,
    default="",
    help="Comma-separated list of run names to export. If not specified, exports from all runs.",
)
@click.option(
    "--level",
    type=int,
    default=0,
    show_default=True,
    help="Pyramid level to export (for MRC and TIFF).",
)
@click.option(
    "--compression",
    type=click.Choice(["lzw", "zlib", "jpeg", "none"], case_sensitive=False),
    default=None,
    help="Compression method for TIFF output.",
)
@click.option(
    "--copy-all-levels/--level-only",
    is_flag=True,
    default=True,
    show_default=True,
    help="Copy all pyramid levels for Zarr output.",
)
@click.option(
    "--max-workers",
    type=int,
    default=8,
    show_default=True,
    help="Number of parallel workers.",
)
@add_debug_option
@click.pass_context
def segmentation(
    ctx,
    config: str,
    segmentation_uri: str,
    output_dir: str,
    output_format: str,
    run_names: str,
    level: int,
    compression: str,
    copy_all_levels: bool,
    max_workers: int,
    debug: bool,
):
    """
    Export segmentations to external file formats.

    Examples:

    \b
    # Export all membrane segmentations to MRC
    copick export segmentation -c config.json --segmentation-uri "membrane:*/*@10.0" \\
        --output-dir ./output --output-format mrc

    \b
    # Export segmentations to TIFF with compression
    copick export segmentation -c config.json --segmentation-uri "membrane:user1/*@10.0" \\
        --output-dir ./output --output-format tiff --compression lzw

    \b
    # Export segmentations to Zarr (copy all levels)
    copick export segmentation -c config.json --segmentation-uri "*:*/*@*" \\
        --output-dir ./output --output-format zarr --copy-all-levels

    \b
    # Export specific level from specific runs
    copick export segmentation -c config.json --segmentation-uri "membrane:*/*@10.0" \\
        --output-dir ./output --output-format mrc --level 0 \\
        --run-names "TS_001,TS_002"
    """
    from copick.ops.export import export as export_op

    logger = get_logger(__name__, debug=debug)

    # Parse run names
    run_names_list = None
    if run_names:
        run_names_list = [name.strip() for name in run_names.split(",") if name.strip()]

    # Handle compression
    compression_value = compression if compression and compression.lower() != "none" else None

    try:
        export_op(
            config=config,
            output_dir=output_dir,
            run_names=run_names_list,
            segmentation_uri=segmentation_uri,
            output_format=output_format,
            level=level,
            compression=compression_value,
            n_workers=max_workers,
            log=debug,
        )
        logger.info("Export completed successfully.")
    except Exception as e:
        logger.critical(f"Export failed: {e}")
        ctx.fail(f"Export failed: {e}")
