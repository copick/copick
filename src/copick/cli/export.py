"""CLI commands for exporting copick data to external formats."""

import click

from copick.cli.util import (
    add_config_option,
    add_debug_option,
    add_export_common_options,
    add_max_workers_option,
    add_pyramid_export_options,
    add_run_names_option,
    resolve_run_names,
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
@add_run_names_option
@click.option(
    "--picks-uri",
    required=True,
    type=str,
    help="URI to filter picks for export (e.g., 'ribosome:user1/*' or '*:*/*').",
)
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False, dir_okay=True),
    default=None,
    help="Output directory for per-run export (one file per run). Mutually exclusive with --output-file.",
    metavar="PATH",
)
@click.option(
    "--output-file",
    type=click.Path(dir_okay=False),
    default=None,
    help="Output file for combined export (all runs in one file). Mutually exclusive with --output-dir.",
    metavar="PATH",
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
    run_names,
    voxel_size: float,
    index_map: str,
    include_optics: bool,
    max_workers: int,
    debug: bool,
):
    """
    Export picks to external formats (EM, STAR, Dynamo, CSV).

    Selects picks with the `--picks-uri` filter (e.g. `ribosome:user1/*` or
    `*:*/*`) and writes them as TOM toolbox EM motivelists, RELION STAR files,
    Dynamo tables, or copick CSV. The EM, STAR, and Dynamo formats require
    `--voxel-size` (in Angstrom) to convert coordinates.

    Two output modes are mutually exclusive: per-run mode (`--output-dir`) writes
    one file per run, while combined mode (`--output-file`) writes all runs to a
    single file. Combined EM/Dynamo export requires `--index-map` to assign a
    tomogram index to each run; per-run EM/Dynamo default to index 1 unless an
    index map is supplied, and STAR/CSV reference runs by name. For coordinate
    and Euler-angle conventions, see the docstrings in `copick.util.formats`.

    Examples:

        \b
        # Per-run export: one EM file per run
        copick export picks -c config.json --picks-uri "ribosome:user1/*" \\
            --output-dir ./output --output-format em --voxel-size 10.0

        \b
        # Combined export: all runs to a single STAR file
        copick export picks -c config.json --picks-uri "*:*/*" \\
            --output-file ./particles.star --output-format star --voxel-size 10.0

        \b
        # Combined export to a Dynamo table using an index map
        copick export picks -c config.json --picks-uri "ribosome:*/*" \\
            --output-file ./particles.tbl --output-format dynamo \\
            --voxel-size 10.0 --index-map ./index_map.csv

    See Also:

        \b
        copick export tomogram: export tomograms to MRC, TIFF, or Zarr
        copick export segmentation: export segmentations to MRC, TIFF, Zarr, or EM
        copick add picks: import picks from external formats into a project
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

    # Resolve run names (repeatable; legacy comma-separated values tolerated with a warning)
    run_names_list = resolve_run_names(run_names, logger=logger)

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
@add_run_names_option
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
    run_names,
    level: int,
    compression: str,
    copy_all_levels: bool,
    max_workers: int,
    debug: bool,
):
    """
    Export tomograms to external formats (MRC, TIFF, Zarr).

    Selects tomograms with the `--tomogram-uri` filter (e.g. `wbp@10.0` or
    `*@*`, in `tomo-type@voxel-spacing` form) and writes each one to the chosen
    format under `--output-dir`. For MRC and TIFF the `--level` pyramid level is
    exported and TIFF supports `--compression`; for Zarr, `--copy-all-levels`
    writes the full multiscale pyramid. Restrict the export to specific runs with
    `--run-names`.

    Examples:

        \b
        # Export all wbp tomograms at 10A to MRC
        copick export tomogram -c config.json --tomogram-uri "wbp@10.0" \\
            --output-dir ./output --output-format mrc

        \b
        # Export tomograms to TIFF with LZW compression
        copick export tomogram -c config.json --tomogram-uri "wbp@10.0" \\
            --output-dir ./output --output-format tiff --compression lzw

        \b
        # Export to Zarr, copying the full multiscale pyramid
        copick export tomogram -c config.json --tomogram-uri "*@*" \\
            --output-dir ./output --output-format zarr --copy-all-levels

    See Also:

        \b
        copick export picks: export picks to EM, STAR, Dynamo, or CSV
        copick export segmentation: export segmentations to MRC, TIFF, Zarr, or EM
        copick add tomogram: import a tomogram into a project
    """
    from copick.ops.export import export as export_op

    logger = get_logger(__name__, debug=debug)

    # Resolve run names (repeatable; legacy comma-separated values tolerated with a warning)
    run_names_list = resolve_run_names(run_names, logger=logger)

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
    short_help="Export segmentations to MRC, TIFF, Zarr, or EM.",
    no_args_is_help=True,
)
@add_config_option
@add_run_names_option
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
    run_names,
    level: int,
    compression: str,
    copy_all_levels: bool,
    max_workers: int,
    debug: bool,
):
    """
    Export segmentations to MRC, TIFF, Zarr, or EM.

    Selects segmentations with the `--segmentation-uri` filter (e.g.
    `membrane:user1/*@10.0`, in `name:user/session@voxel-spacing` form) and
    writes each label map to the chosen format under `--output-dir`. For MRC,
    TIFF, and EM the `--level` pyramid level is exported and TIFF supports
    `--compression`; for Zarr, `--copy-all-levels` writes the full multiscale
    pyramid. Restrict the export to specific runs with `--run-names`.

    Examples:

        \b
        # Export all membrane segmentations at 10A to MRC
        copick export segmentation -c config.json \\
            --segmentation-uri "membrane:*/*@10.0" \\
            --output-dir ./output --output-format mrc

        \b
        # Export segmentations to TIFF with LZW compression
        copick export segmentation -c config.json \\
            --segmentation-uri "membrane:user1/*@10.0" \\
            --output-dir ./output --output-format tiff --compression lzw

        \b
        # Export to Zarr, copying the full multiscale pyramid
        copick export segmentation -c config.json --segmentation-uri "*:*/*@*" \\
            --output-dir ./output --output-format zarr --copy-all-levels

    See Also:

        \b
        copick export picks: export picks to EM, STAR, Dynamo, or CSV
        copick export tomogram: export tomograms to MRC, TIFF, or Zarr
        copick add segmentation: import a segmentation into a project
    """
    from copick.ops.export import export as export_op

    logger = get_logger(__name__, debug=debug)

    # Resolve run names (repeatable; legacy comma-separated values tolerated with a warning)
    run_names_list = resolve_run_names(run_names, logger=logger)

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
