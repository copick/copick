"""CLI commands that import and export tilt series, alignments and CTF fits.

They are attached to the ``copick add`` and ``copick export`` groups (see the end of ``copick.cli.add`` and
``copick.cli.export``).
"""

import glob
from typing import Optional, Tuple

import click

from copick.cli.util import (
    add_config_option,
    add_create_overwrite_options,
    add_debug_option,
    add_export_common_options,
    add_max_workers_option,
    add_run_names_option,
    add_run_options,
    resolve_run_names,
)
from copick.util.log import get_logger

SECTION_MAP_HELP = (
    "How the rows of a file map to tilt-series sections: 'auto' (the file's default), 'index' (row i is section i), "
    "'sorted' (rows in ascending angle pair with sections in ascending nominal angle) or 'angle' (nearest nominal "
    "angle)."
)


def _section_map_options(func):
    func = click.option(
        "--angle-tolerance",
        type=float,
        default=1.0,
        show_default=True,
        help="Largest difference in degrees between a row's angle and the nominal angle of its section.",
    )(func)
    return click.option(
        "--section-map",
        type=click.Choice(["auto", "index", "sorted", "angle"], case_sensitive=False),
        default="auto",
        show_default=True,
        help=SECTION_MAP_HELP,
    )(func)


def _triple(value: Optional[str], what: str) -> Optional[Tuple[int, int, int]]:
    if value is None:
        return None
    parts = [p for p in value.replace("x", ",").split(",") if p.strip()]
    if len(parts) != 3:
        raise click.BadParameter(f"{what} must be three integers 'x,y,z', got {value!r}.")
    return tuple(int(p) for p in parts)


# ---------------------------------------------------------------------------------------------------------------------
# copick add tiltseries


@click.command(
    "tiltseries",
    short_help="Add a tilt series from a stack and its acquisition metadata.",
    no_args_is_help=True,
)
@add_config_option
@add_run_options
@click.option("--ts-type", type=str, default="raw", show_default=True, help="Type of the tilt series.")
@click.option(
    "--file-type",
    type=click.Choice(["mrc", "tiff", "zarr"], case_sensitive=False),
    default=None,
    help="Format of the stack. Default: from the extension (.mrc, .st, .mrcs, .ali, .tif, .tiff, .zarr).",
)
@click.option("--pixel-size", type=float, default=None, help="Pixel size in Angstrom, overriding the stack's header.")
@click.option(
    "--angles",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Tilt angles in stack order: IMOD .rawtlt/.tlt or AreTomo3 _TLT.txt.",
)
@click.option(
    "--angles-format",
    type=click.Choice(["rawtlt", "tlt", "aretomo3-tlt"], case_sensitive=False),
    default=None,
    help="Format of --angles. Default: from its name.",
)
@click.option(
    "--mdoc",
    type=str,
    default="auto",
    show_default=True,
    help="SerialEM mdoc: a path, 'auto' (the stack's sibling <stack>.mdoc or <stem>.mdoc) or 'none'.",
)
@click.option(
    "--ctf",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Per-image CTF fits: AreTomo3 _CTF.txt, CTFFIND4 output, Warp XML or RELION tomograms.star.",
)
@click.option(
    "--ctf-format",
    type=click.Choice(["aretomo3", "ctffind4", "warp", "relion"], case_sensitive=False),
    default=None,
    help="Format of --ctf. Default: from its name.",
)
@click.option("--dose-per-tilt", type=float, default=None, help="Dose of every image in e/Å², overriding the mdoc.")
@click.option("--voltage", type=float, default=None, help="Acceleration voltage in kV.")
@click.option("--cs", type=float, default=None, help="Spherical aberration in mm.")
@click.option("--amplitude-contrast", type=float, default=None, help="Amplitude contrast (e.g. 0.07).")
@click.option("--tilt-axis", type=float, default=None, help="Tilt-axis angle in degrees, overriding the mdoc.")
@click.option(
    "--handedness",
    type=click.Choice(["right_handed", "left_handed"]),
    default=None,
    help="Handedness of the acquisition geometry, if known.",
)
@_section_map_options
@click.option(
    "--sort-by-angle/--keep-order",
    default=False,
    show_default=True,
    help="Store the sections in ascending nominal tilt angle, or in the stack's order.",
)
@click.option("--is-aligned", is_flag=True, default=False, help="The images are already aligned.")
@click.option("--pyramid-levels", type=int, default=3, show_default=True, help="Number of pyramid levels.")
@click.option("--chunk-size", type=str, default="1,1024,1024", show_default=True, help="Chunk shape 'z,y,x'.")
@click.option(
    "--dtype",
    type=click.Choice(["float32", "float16", "int16", "uint16", "int8", "uint8", "keep"]),
    default="float32",
    show_default=True,
    help="Data type of the stored images ('keep': that of the stack).",
)
@add_max_workers_option
@add_create_overwrite_options
@add_debug_option
@click.argument("path", required=True, type=str, metavar="PATH")
@click.pass_context
def add_tiltseries(
    ctx,
    config,
    run,
    run_regex,
    run_name_prefix,
    ts_type,
    file_type,
    pixel_size,
    angles,
    angles_format,
    mdoc,
    ctf,
    ctf_format,
    dose_per_tilt,
    voltage,
    cs,
    amplitude_contrast,
    tilt_axis,
    handedness,
    section_map,
    angle_tolerance,
    sort_by_angle,
    is_aligned,
    pyramid_levels,
    chunk_size,
    dtype,
    max_workers,
    create,
    overwrite,
    debug,
    path,
):
    """
    Add a tilt series from a stack and its acquisition metadata.

    Imports an MRC, TIFF or Zarr stack as a multiscale tilt series, with the nominal tilt angles, acquisition order,
    dose, movies and CTF fits found in a SerialEM mdoc (next to the stack by default), an angle file and a CTF file.
    A glob pattern imports many stacks; the run name is then taken from each file name.

    Arguments:

        \b
        PATH: The stack (.mrc, .st, .mrcs, .ali, .tif, .zarr) or a glob pattern.

    Examples:

        \b
        # A SerialEM stack with its mdoc (TS_01.mrc.mdoc) next to it
        copick add tiltseries TS_01.mrc -c config.json --voltage 300 --cs 2.7

        \b
        # An AreTomo3 output stack with its angle and CTF files
        copick add tiltseries TS_01.mrc --angles TS_01_TLT.txt --ctf TS_01_CTF.txt -c config.json

        \b
        # Many stacks, run names from the file names
        copick add tiltseries "stacks/TS_*.st" -c config.json --run-regex "^(TS_\\d+)"

    See Also:

        \b
        copick add alignment: import an alignment of a tilt series
        copick export tiltseries: export a tilt series as a stack
    """
    import copick
    from copick.ops.acquisition import add_tilt_series_from_file
    from copick.ops.run import map_runs, report_results
    from copick.util.path_util import prepare_runs_from_paths

    logger = get_logger(__name__, debug=debug)
    root = copick.from_file(config)
    paths = sorted(glob.glob(path)) if "*" in path else [path]
    if not paths:
        ctx.fail(f"No files found matching pattern: {path}")
    if len(paths) > 1 and (run or angles or ctf or (mdoc not in ("auto", "none"))):
        ctx.fail("--run, --angles, --ctf and an mdoc path apply to a single stack, not a glob pattern.")
    chunks = tuple(int(c) for c in chunk_size.split(",")[:3])
    run_to_file = prepare_runs_from_paths(root, paths, run, run_regex, run_name_prefix, create, logger)

    def import_tilt_series(run_obj, file_path, **kwargs):
        try:
            add_tilt_series_from_file(
                root,
                run_obj.name,
                ts_type,
                file_path,
                file_type=file_type,
                pixel_size=pixel_size,
                angles=angles,
                angles_format=angles_format,
                mdoc=None if mdoc == "none" else mdoc,
                ctf=ctf,
                ctf_format=ctf_format,
                dose_per_tilt=dose_per_tilt,
                voltage=voltage,
                spherical_aberration=cs,
                amplitude_contrast=amplitude_contrast,
                tilt_axis_angle=tilt_axis,
                handedness=handedness,
                section_map=section_map,
                angle_tolerance=angle_tolerance,
                sort_by_angle=sort_by_angle,
                is_aligned=is_aligned,
                levels=pyramid_levels,
                chunks=chunks,
                dtype=None if dtype == "keep" else dtype,
                create=create,
                overwrite=overwrite,
            )
            return {"processed": 1, "errors": []}
        except Exception as e:
            message = f"Failed to process {file_path}: {e}"
            logger.critical(message)
            return {"processed": 0, "errors": [message]}

    run_names = list(run_to_file)
    results = map_runs(
        callback=import_tilt_series,
        root=root,
        runs=run_names,
        workers=max_workers,
        parallelism="thread",
        run_args=[{"file_path": run_to_file[name]} for name in run_names],
        show_progress=True,
        task_desc="Adding tilt series",
    )
    report_results(results, len(paths), logger)
    if any(r is None or r.get("errors") for r in results.values()):
        ctx.exit(1)


# ---------------------------------------------------------------------------------------------------------------------
# copick add alignment


@click.command(
    "alignment",
    short_help="Add an alignment of a tilt series from AreTomo3, Warp, RELION or IMOD files.",
    no_args_is_help=True,
)
@add_config_option
@click.option("--run", required=True, type=str, help="The run.")
@click.option(
    "--format",
    "fmt",
    required=True,
    type=click.Choice(["aretomo3", "warp", "relion", "imod"], case_sensitive=False),
    help="Format of PATH.",
)
@click.option("--ts-type", type=str, default="raw", show_default=True, help="The tilt series the alignment aligns.")
@click.option("--name", type=str, default=None, help="Name of the alignment. Default: the format.")
@click.option("--tomo-name", type=str, default=None, help="RELION: the tomogram, if the file lists several.")
@click.option(
    "--reference-tomogram",
    type=str,
    default=None,
    help="The tomogram ('tomo_type@voxel_size') the tool reconstructed with this alignment; it becomes the reference "
    "volume and is linked.",
)
@click.option(
    "--volume-size",
    type=str,
    default=None,
    help="Size 'x,y,z' of the tool's reconstruction in pixels of the aligned stack, overriding the files.",
)
@click.option(
    "--thickness",
    type=int,
    default=None,
    help="Thickness of the tool's reconstruction in pixels (AreTomo3 -VolZ), overriding the files.",
)
@click.option(
    "--native-pixel-size",
    type=float,
    default=None,
    help="Pixel size of the stack the tool aligned, if not that of the tilt series (e.g. a binned stack).",
)
@click.option(
    "--link-tomogram",
    "link_tomograms",
    type=str,
    multiple=True,
    help="A tomogram ('tomo_type@voxel_size') reconstructed with this alignment. Repeatable.",
)
@click.option("--preferred", is_flag=True, default=False, help="Prefer this alignment over the tilt series' others.")
@click.option(
    "--ctf",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="CTF fits to store on the tilt series (e.g. the AreTomo3 _CTF.txt).",
)
@click.option(
    "--ctf-format",
    type=click.Choice(["aretomo3", "ctffind4", "warp", "relion"], case_sensitive=False),
    default=None,
    help="Format of --ctf. Default: from its name.",
)
@click.option(
    "--tlt",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="AreTomo3 _TLT.txt whose acquisition order and dose to store on the tilt series.",
)
@click.option(
    "--update-tilt-series/--no-update-tilt-series",
    default=True,
    show_default=True,
    help="Store --ctf and --tlt on the tilt series (writable tilt series only).",
)
@_section_map_options
@click.option(
    "--assume-frame",
    type=click.Choice(["half", "floor"]),
    default=None,
    help="IMOD only: centre convention (N/2 or floor(N/2)) for odd image or volume sizes.",
)
@click.option(
    "--rigid-only",
    is_flag=True,
    default=False,
    help="Import the rigid part of a local (patch) AreTomo3 alignment; the local part is lost.",
)
@click.option(
    "--allow-varying-grids",
    is_flag=True,
    default=False,
    help="Warp only: drop spatially varying deformation grids; only the rigid part is kept.",
)
@click.option("--overwrite/--no-overwrite", default=False, show_default=True, help="Replace an existing alignment.")
@add_debug_option
@click.argument("path", required=True, type=str, metavar="PATH")
@click.pass_context
def add_alignment(
    ctx,
    config,
    run,
    fmt,
    ts_type,
    name,
    tomo_name,
    reference_tomogram,
    volume_size,
    thickness,
    native_pixel_size,
    link_tomograms,
    preferred,
    ctf,
    ctf_format,
    tlt,
    update_tilt_series,
    section_map,
    angle_tolerance,
    assume_frame,
    rigid_only,
    allow_varying_grids,
    overwrite,
    debug,
    path,
):
    """
    Add an alignment of a tilt series from AreTomo3, Warp, RELION or IMOD files.

    Converts the tool's per-image tilt, rotation and shift to copick's CETS frame, mapping the tool's rows to the
    sections of the tilt series (by default AreTomo3 by ascending angle, Warp and RELION by nominal angle, IMOD by
    index). Only rigid alignments are stored; local ones need --rigid-only (AreTomo3) or --allow-varying-grids (Warp).

    Arguments:

        \b
        PATH: AreTomo3 .aln, Warp tilt-series .xml, RELION tomograms.star, or IMOD basename / .xf.

    Examples:

        \b
        # An AreTomo3 alignment with its CTF fits; the reconstruction is linked
        copick add alignment TS_01.aln --format aretomo3 --run TS_01 --ctf TS_01_CTF.txt \\
            --tlt TS_01_TLT.txt --reference-tomogram aretomo3@7.7 -c config.json

        \b
        # A RELION 5 alignment
        copick add alignment tomograms.star --format relion --run TS_01 --tomo-name TS_01 -c config.json

    See Also:

        \b
        copick export alignment: export an alignment to another tool
        copick new link: link a tomogram to an alignment
    """
    import copick
    from copick.ops.acquisition import add_alignment_from_file

    logger = get_logger(__name__, debug=debug)
    root = copick.from_file(config)
    try:
        alignment = add_alignment_from_file(
            root,
            run,
            path,
            fmt.lower(),
            ts_type,
            name=name,
            tomo_name=tomo_name,
            native_pixel_size=native_pixel_size,
            volume_size=_triple(volume_size, "--volume-size"),
            thickness=thickness,
            reference_tomogram=reference_tomogram,
            link_tomograms=link_tomograms,
            preferred=preferred,
            ctf=ctf,
            ctf_format=ctf_format,
            tlt=tlt,
            update_tilt_series=update_tilt_series,
            section_map=section_map,
            angle_tolerance=angle_tolerance,
            assume_frame=assume_frame,
            rigid_only=rigid_only,
            allow_varying_grids=allow_varying_grids,
            overwrite=overwrite,
        )
    except (ValueError, PermissionError) as e:
        logger.critical(str(e))
        ctx.fail(str(e))
    logger.info(f"Added alignment {alignment.name} to run {run}.")


# ---------------------------------------------------------------------------------------------------------------------
# copick add ctf


@click.command("ctf", short_help="Set the CTF fits of a tilt series from a file.", no_args_is_help=True)
@add_config_option
@click.option("--run", required=True, type=str, help="The run.")
@click.option("--ts-type", type=str, default="raw", show_default=True, help="The tilt series.")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["aretomo3", "ctffind4", "warp", "relion"], case_sensitive=False),
    default=None,
    help="Format of PATH. Default: from its name (_CTF.txt, .txt, .xml, .star).",
)
@click.option("--tomo-name", type=str, default=None, help="RELION: the tomogram. Default: the run name.")
@_section_map_options
@add_debug_option
@click.argument("path", required=True, type=click.Path(exists=True, dir_okay=False), metavar="PATH")
@click.pass_context
def add_ctf(ctx, config, run, ts_type, fmt, tomo_name, section_map, angle_tolerance, debug, path):
    """
    Set the CTF fits of a tilt series from a file.

    Reads per-image defocus, astigmatism and phase shift from an AreTomo3 _CTF.txt, a CTFFIND4 output file, a Warp
    tilt-series XML or a RELION tomograms.star, and stores them on the matching sections of a writable tilt series.

    Arguments:

        \b
        PATH: The CTF file.

    Examples:

        \b
        copick add ctf TS_01_CTF.txt --run TS_01 -c config.json
    """
    import copick
    from copick.ops.acquisition import add_ctf_from_file

    logger = get_logger(__name__, debug=debug)
    root = copick.from_file(config)
    try:
        add_ctf_from_file(
            root,
            run,
            ts_type,
            path,
            ctf_format=fmt,
            section_map=section_map,
            angle_tolerance=angle_tolerance,
            tomo_name=tomo_name,
        )
    except (ValueError, PermissionError) as e:
        logger.critical(str(e))
        ctx.fail(str(e))


# ---------------------------------------------------------------------------------------------------------------------
# copick export tiltseries / alignment / ctf


def _tilt_series_of(root, uri, run_names):
    from copick.util.uri import resolve_copick_objects

    runs = run_names if run_names is not None else [r.name for r in root.runs]
    for run_name in runs:
        found = resolve_copick_objects(uri, root, "tiltseries", run_name)
        if len(found) > 1:
            raise ValueError(f"{uri} selects {len(found)} tilt series of run {run_name}; select one per run.")
        yield from found


@click.command("tiltseries", short_help="Export tilt series as MRC, TIFF or Zarr stacks.", no_args_is_help=True)
@add_config_option
@add_run_names_option
@click.option("--tiltseries-uri", required=True, type=str, help="Tilt series to export (e.g. 'raw').")
@add_export_common_options
@click.option(
    "--output-format",
    type=click.Choice(["mrc", "tiff", "zarr"], case_sensitive=False),
    default="mrc",
    show_default=True,
    help="Format of the stack.",
)
@click.option("--level", type=int, default=0, show_default=True, help="Pyramid level (mrc, tiff).")
@click.option(
    "--angles",
    type=click.Choice(["rawtlt", "tlt", "aretomo3-tlt", "none"], case_sensitive=False),
    default="rawtlt",
    show_default=True,
    help="Angle file to write next to the stack.",
)
@click.option(
    "--ctf-format",
    type=click.Choice(["aretomo3", "ctffind4", "none"], case_sensitive=False),
    default="none",
    show_default=True,
    help="CTF file to write next to the stack.",
)
@add_debug_option
@click.pass_context
def export_tiltseries(
    ctx,
    config,
    run_names,
    tiltseries_uri,
    output_dir,
    output_format,
    level,
    angles,
    ctf_format,
    debug,
):
    """
    Export tilt series as MRC, TIFF or Zarr stacks.

    Writes each selected tilt series as '<run>.mrc' (or .tif, .zarr) with its nominal tilt angles ('<run>.rawtlt',
    '<run>.tlt' or AreTomo3's '<run>_TLT.txt' with acquisition order and dose) and, optionally, its CTF fits.

    Examples:

        \b
        copick export tiltseries -c config.json --tiltseries-uri raw --output-dir out --angles aretomo3-tlt \\
            --ctf-format aretomo3
    """
    import copick
    from copick.ops.acquisition import export_tilt_series

    logger = get_logger(__name__, debug=debug)
    root = copick.from_file(config)
    try:
        for tilt_series in _tilt_series_of(root, tiltseries_uri, resolve_run_names(run_names, logger=logger)):
            written = export_tilt_series(
                tilt_series,
                output_dir,
                output_format=output_format.lower(),
                level=level,
                angles=None if angles == "none" else angles,
                ctf_format=None if ctf_format == "none" else ctf_format,
            )
            logger.info(f"Run {tilt_series.run.name}: wrote {', '.join(str(p) for p in written)}")
    except (ValueError, PermissionError) as e:
        logger.critical(str(e))
        ctx.fail(str(e))


@click.command(
    "alignment",
    short_help="Export alignments to AreTomo3, Warp, RELION, IMOD or the CryoET Data Portal format.",
    no_args_is_help=True,
)
@add_config_option
@add_run_names_option
@click.option(
    "--alignment-uri",
    required=True,
    type=str,
    help="Alignments to export, one per run (e.g. 'aretomo3' or '*@raw?default=true').",
)
@add_export_common_options
@click.option(
    "--output-format",
    required=True,
    type=click.Choice(["aretomo3", "warp", "relion", "imod", "cdp"], case_sensitive=False),
    help="Format to write.",
)
@click.option(
    "--reference-tomogram",
    type=str,
    default=None,
    help="Each run's tomogram ('tomo_type@voxel_size') the tool should reconstruct. Default: the alignment's "
    "reference volume.",
)
@click.option("--include-ctf", is_flag=True, default=False, help="Also write the CTF fits of the tilt series.")
@click.option(
    "--drop-x-tilt",
    is_flag=True,
    default=False,
    help="AreTomo3: drop the tilt about x, which .aln files cannot represent.",
)
@click.option("--hand", type=float, default=-1.0, show_default=True, help="RELION: rlnTomoHand.")
@click.option(
    "--relion-tomo-name",
    type=str,
    default=None,
    help="RELION: rlnTomoName of a single exported run. Default: the run name.",
)
@click.option(
    "--assume-frame",
    type=click.Choice(["half", "floor"]),
    default=None,
    help="IMOD only: centre convention for odd image or volume sizes.",
)
@add_debug_option
@click.pass_context
def export_alignment(
    ctx,
    config,
    run_names,
    alignment_uri,
    output_dir,
    output_format,
    reference_tomogram,
    include_ctf,
    drop_x_tilt,
    hand,
    relion_tomo_name,
    assume_frame,
    debug,
):
    """
    Export alignments to AreTomo3, Warp, RELION, IMOD or the CryoET Data Portal format.

    Converts each run's selected alignment from copick's CETS frame to the tool's frame and row order: AreTomo3
    '<run>.aln' with '<run>_TLT.txt', Warp '<run>.xml', RELION 'tomograms.star' with 'tilt_series/<run>.star' for all
    runs, IMOD '<run>/<run>.xf/.tlt/.xtilt' with tilt.com and newst.com, or '<run>_alignment.json'. RELION's
    rlnTomoNominalStageTiltAngle holds the nominal tilt angles, and its pre-exposure the accumulated dose.

    Examples:

        \b
        # The default alignment of every run's raw tilt series, for RELION 5 with CTF
        copick export alignment -c config.json --alignment-uri "*@raw?default=true" --output-dir relion \\
            --output-format relion --include-ctf
    """
    import copick
    from copick.ops.acquisition import export_alignments

    logger = get_logger(__name__, debug=debug)
    root = copick.from_file(config)
    run_names_list = resolve_run_names(run_names, logger=logger)
    kwargs = dict(
        include_ctf=include_ctf,
        drop_x_tilt=drop_x_tilt,
        hand=hand,
        assume_frame=assume_frame,
    )
    if relion_tomo_name is not None:
        if run_names_list is None or len(run_names_list) != 1:
            ctx.fail("--relion-tomo-name needs exactly one run (-r).")
        kwargs["relion_tomo_name"] = relion_tomo_name
    try:
        written = export_alignments(
            root,
            alignment_uri,
            output_dir,
            output_format.lower(),
            run_names=run_names_list,
            reference_tomogram=reference_tomogram,
            **kwargs,
        )
    except (ValueError, PermissionError) as e:
        logger.critical(str(e))
        ctx.fail(str(e))
    logger.info(f"Wrote {len(written)} files to {output_dir}.")


@click.command("ctf", short_help="Export the CTF fits of tilt series.", no_args_is_help=True)
@add_config_option
@add_run_names_option
@click.option("--tiltseries-uri", required=True, type=str, help="Tilt series whose CTF fits to export (e.g. 'raw').")
@add_export_common_options
@click.option(
    "--output-format",
    type=click.Choice(["aretomo3", "ctffind4"], case_sensitive=False),
    default="aretomo3",
    show_default=True,
    help="'aretomo3': '<run>_CTF.txt' in ascending tilt angle; 'ctffind4': '<run>_ctffind4.txt' in stack order.",
)
@add_debug_option
@click.pass_context
def export_ctf(ctx, config, run_names, tiltseries_uri, output_dir, output_format, debug):
    """
    Export the CTF fits of tilt series.

    Examples:

        \b
        copick export ctf -c config.json --tiltseries-uri raw --output-dir out
    """
    import copick
    from copick.ops.acquisition import export_ctf as export_ctf_op

    logger = get_logger(__name__, debug=debug)
    root = copick.from_file(config)
    try:
        for tilt_series in _tilt_series_of(root, tiltseries_uri, resolve_run_names(run_names, logger=logger)):
            path = export_ctf_op(tilt_series, output_dir, fmt=output_format.lower())
            logger.info(f"Run {tilt_series.run.name}: wrote {path}")
    except (ValueError, PermissionError) as e:
        logger.critical(str(e))
        ctx.fail(str(e))
