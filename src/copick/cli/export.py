"""CLI commands for exporting copick data to external formats."""

import click

from copick.cli.util import (
    add_config_option,
    add_debug_option,
    add_export_common_options,
    add_max_workers_option,
    add_pyramid_export_options,
)
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
    type=str,
    default=None,
    help="Output directory for per-run export (one file per run). Mutually exclusive with --output-file.",
    metavar="PATH",
)
@click.option(
    "--output-file",
    type=str,
    default=None,
    help="Output file for combined export (all runs in one file). Mutually exclusive with --output-dir.",
    metavar="PATH",
)
@click.option(
    "--run-names",
    type=str,
    default=None,
    help="Comma-separated list of run names to process.",
)
@click.option(
    "--output-format",
    required=True,
    type=click.Choice(["em", "star", "dynamo", "csv"], case_sensitive=False),
    help="Output format for picks.",
)
@click.option(
    "--voxel-size",
    type=float,
    default=None,
    help="Voxel size in Angstrom (required for EM, STAR, and Dynamo formats).",
)
@click.option(
    "--index-map",
    type=click.Path(exists=True),
    default=None,
    help="CSV/TSV file mapping tomogram index to run name. Required for combined EM/Dynamo export, optional for per-run.",
)
@click.option(
    "--include-optics/--no-include-optics",
    is_flag=True,
    default=True,
    show_default=True,
    help="Include optics group in STAR file output.",
)
@add_max_workers_option
@add_debug_option
@click.pass_context
def picks(
    ctx,
    config: str,
    picks_uri: str,
    output_dir: str,
    output_file: str,
    output_format: str,
    run_names: str,
    voxel_size: float,
    index_map: str,
    include_optics: bool,
    max_workers: int,
    debug: bool,
):
    """
    Export picks to external file formats.

    Two export modes are supported:

    \b
    PER-RUN MODE (--output-dir):
    Creates one file per run in the output directory. Use --index-map to
    specify tomogram indices for EM/Dynamo formats (defaults to 1 otherwise).

    \b
    COMBINED MODE (--output-file):
    Exports all runs to a single file. For EM/Dynamo formats, --index-map
    is required to specify tomogram indices. STAR/CSV use run names directly.

    Examples:

    \b
    # Per-run export: one file per run to EM format
    copick export picks -c config.json --picks-uri "ribosome:user1/*" \\
        --output-dir ./output --output-format em --voxel-size 10.0

    \b
    # Combined export: all runs to single STAR file
    copick export picks -c config.json --picks-uri "*:*/*" \\
        --output-file ./particles.star --output-format star --voxel-size 10.0

    \b
    # Combined export to Dynamo with index map
    copick export picks -c config.json --picks-uri "ribosome:*/*" \\
        --output-file ./particles.tbl --output-format dynamo \\
        --voxel-size 10.0 --index-map ./index_map.csv

    \b
    # Per-run export with index map for custom tomogram indices
    copick export picks -c config.json --picks-uri "ribosome:*/*" \\
        --output-dir ./output --output-format em --voxel-size 10.0 \\
        --index-map ./index_map.csv

    For format-specific conventions (coordinate systems, Euler angle conventions),
    see the documentation or the docstrings in copick.util.formats.
    """
    from copick.ops.export import export as export_op
    from copick.ops.export import export_picks_combined

    logger = get_logger(__name__, debug=debug)

    # Validate output mode: exactly one of output_dir or output_file must be provided
    if output_dir and output_file:
        ctx.fail("--output-dir and --output-file are mutually exclusive. Choose one.")
    if not output_dir and not output_file:
        ctx.fail("Either --output-dir (per-run) or --output-file (combined) is required.")

    # Validate voxel size for formats that require it
    if output_format.lower() in ["em", "star", "dynamo"] and voxel_size is None:
        ctx.fail(f"--voxel-size is required for {output_format.upper()} format export.")

    # Parse run names
    run_names_list = None
    if run_names:
        run_names_list = [name.strip() for name in run_names.split(",") if name.strip()]

    # Load index map if provided
    run_to_index = None
    if index_map:
        from copick.util.formats import read_index_map_inverse

        try:
            run_to_index = read_index_map_inverse(index_map)
            logger.debug(f"Loaded index map with {len(run_to_index)} entries")
        except Exception as e:
            ctx.fail(f"Failed to read index map: {e}")

    # Validate index map for combined EM/Dynamo export
    if output_file and output_format.lower() in ["em", "dynamo"] and run_to_index is None:
        ctx.fail(f"--index-map is required for combined {output_format.upper()} export.")

    try:
        if output_file:
            # Combined export mode
            export_picks_combined(
                config=config,
                output_file=output_file,
                picks_uri=picks_uri,
                output_format=output_format,
                voxel_spacing=voxel_size,
                run_names=run_names_list,
                run_to_index=run_to_index,
                include_optics=include_optics,
                log=debug,
            )
        else:
            # Per-run export mode
            export_op(
                config=config,
                output_dir=output_dir,
                run_names=run_names_list,
                picks_uri=picks_uri,
                output_format=output_format,
                voxel_spacing=voxel_size,
                include_optics=include_optics,
                run_to_index=run_to_index,
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
@add_export_common_options
@click.option(
    "--output-format",
    required=True,
    type=click.Choice(["mrc", "tiff", "zarr"], case_sensitive=False),
    help="Output format for tomograms.",
)
@add_pyramid_export_options
@add_max_workers_option
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
@add_export_common_options
@click.option(
    "--output-format",
    required=True,
    type=click.Choice(["mrc", "tiff", "zarr", "em"], case_sensitive=False),
    help="Output format for segmentations.",
)
@add_pyramid_export_options
@add_max_workers_option
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
