"""Export operations for copick data to external formats.

This module provides functions to export copick data (picks, tomograms, segmentations)
to various external file formats used in cryo-ET workflows.
"""

import logging
import os
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

import numpy as np
import zarr

from copick.util.log import get_logger

if TYPE_CHECKING:
    from copick.models import (
        CopickPicks,
        CopickRun,
        CopickSegmentation,
        CopickTomogram,
    )

logger = get_logger(__name__)


# =============================================================================
# Picks Export Functions
# =============================================================================


def export_picks(
    picks: "CopickPicks",
    output_path: str,
    output_format: str,
    voxel_spacing: Optional[float] = None,
    tomogram_dimensions: Optional[Tuple[int, int, int]] = None,
    include_optics: bool = True,
    run_name: Optional[str] = None,
    log: bool = False,
) -> str:
    """Export picks to an external format.

    Args:
        picks: The CopickPicks object to export.
        output_path: Path for the output file.
        output_format: Output format ("em", "star", "dynamo", "csv").
        voxel_spacing: Voxel spacing in Angstrom (required for em, star, dynamo).
        tomogram_dimensions: (X, Y, Z) dimensions in voxels (required for em, star).
        include_optics: Include optics group in STAR file output.
        run_name: Run name for CSV output (uses picks.run.name if not provided).
        log: Log the operation.

    Returns:
        Path to the created output file.

    Raises:
        ValueError: If required parameters are missing for the output format.
    """
    output_format = output_format.lower()

    if output_format == "em":
        return _export_picks_em(picks, output_path, voxel_spacing, tomogram_dimensions, log=log)
    elif output_format == "star":
        return _export_picks_star(picks, output_path, voxel_spacing, tomogram_dimensions, include_optics, log=log)
    elif output_format == "dynamo":
        return _export_picks_dynamo(picks, output_path, voxel_spacing, log=log)
    elif output_format == "csv":
        run_name = run_name or picks.run.name
        return _export_picks_csv(picks, output_path, run_name, log=log)
    else:
        raise ValueError(f"Unsupported output format: {output_format}")


def _export_picks_em(
    picks: "CopickPicks",
    output_path: str,
    voxel_spacing: float,
    tomogram_dimensions: Optional[Tuple[int, int, int]] = None,
    tomogram_index: int = 1,
    log: bool = False,
) -> str:
    """Export picks to TOM toolbox EM motivelist format.

    Args:
        picks: The CopickPicks object to export.
        output_path: Path for the output EM file.
        voxel_spacing: Voxel spacing in Angstrom.
        tomogram_dimensions: (X, Y, Z) dimensions in voxels.
        tomogram_index: Tomogram index for the motivelist.
        log: Log the operation.

    Returns:
        Path to the created output file.
    """
    from copick.util.formats import copick_to_em_transform, write_em_motivelist

    if voxel_spacing is None:
        raise ValueError("voxel_spacing is required for EM export.")

    # Get tomogram dimensions if not provided
    if tomogram_dimensions is None:
        tomogram_dimensions = _get_tomogram_dimensions(picks)

    # Get points and transforms
    points, transforms = picks.numpy()

    # Convert to EM format
    positions_px, eulers_deg = copick_to_em_transform(
        points,
        transforms,
        voxel_spacing,
        tomogram_dimensions,
    )

    # Write EM file
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    write_em_motivelist(
        output_path,
        positions_px,
        eulers_deg,
        tomogram_index=tomogram_index,
    )

    if log:
        logging.info(f"Exported {len(points)} picks to EM file: {output_path}")

    return output_path


def _export_picks_star(
    picks: "CopickPicks",
    output_path: str,
    voxel_spacing: float,
    tomogram_dimensions: Optional[Tuple[int, int, int]] = None,
    include_optics: bool = True,
    log: bool = False,
) -> str:
    """Export picks to RELION STAR format.

    Args:
        picks: The CopickPicks object to export.
        output_path: Path for the output STAR file.
        voxel_spacing: Voxel spacing in Angstrom.
        tomogram_dimensions: (X, Y, Z) dimensions in voxels.
        include_optics: Include optics group in output.
        log: Log the operation.

    Returns:
        Path to the created output file.
    """
    from copick.util.formats import write_star_particles
    from copick.util.relion import picks_to_df_relion

    if voxel_spacing is None:
        raise ValueError("voxel_spacing is required for STAR export.")

    # Convert to RELION DataFrame
    df = picks_to_df_relion(picks)

    # Create optics group if requested
    optics_group = None
    if include_optics:
        optics_group = {
            "rlnOpticsGroupName": "opticsGroup1",
            "rlnOpticsGroup": 1,
            "rlnImagePixelSize": voxel_spacing,
            "rlnVoltage": 300.0,
            "rlnSphericalAberration": 2.7,
            "rlnAmplitudeContrast": 0.1,
        }

    # Write STAR file
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    write_star_particles(output_path, df, optics_group)

    if log:
        logging.info(f"Exported {len(df)} picks to STAR file: {output_path}")

    return output_path


def _export_picks_dynamo(
    picks: "CopickPicks",
    output_path: str,
    voxel_spacing: float,
    tomogram_index: int = 1,
    log: bool = False,
) -> str:
    """Export picks to Dynamo table format.

    Args:
        picks: The CopickPicks object to export.
        output_path: Path for the output .tbl file.
        voxel_spacing: Voxel spacing in Angstrom.
        tomogram_index: Tomogram index for the table.
        log: Log the operation.

    Returns:
        Path to the created output file.
    """
    from copick.util.formats import copick_to_dynamo_transform, write_dynamo_table

    if voxel_spacing is None:
        raise ValueError("voxel_spacing is required for Dynamo export.")

    # Get points and transforms
    points, transforms = picks.numpy()

    # Convert to Dynamo format
    positions_px, eulers_deg, shifts_px = copick_to_dynamo_transform(
        points,
        transforms,
        voxel_spacing,
    )

    # Write Dynamo table
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    write_dynamo_table(
        output_path,
        positions_px,
        eulers_deg,
        shifts_px,
        tomogram_index=tomogram_index,
    )

    if log:
        logging.info(f"Exported {len(points)} picks to Dynamo table: {output_path}")

    return output_path


def _export_picks_csv(
    picks: "CopickPicks",
    output_path: str,
    run_name: str,
    log: bool = False,
) -> str:
    """Export picks to copick CSV format.

    Args:
        picks: The CopickPicks object to export.
        output_path: Path for the output CSV file.
        run_name: Run name to include in the CSV.
        log: Log the operation.

    Returns:
        Path to the created output file.
    """
    from copick.util.formats import write_picks_csv

    # Get points and transforms
    points, transforms = picks.numpy()

    # Get scores if available
    scores = None
    if picks.points:
        scores = np.array([p.score for p in picks.points])

    # Get instance IDs if available
    instance_ids = None
    if picks.points and hasattr(picks.points[0], "instance_id"):
        instance_ids = np.array([p.instance_id for p in picks.points if hasattr(p, "instance_id")])
        if len(instance_ids) != len(points):
            instance_ids = None

    # Write CSV file
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    write_picks_csv(output_path, run_name, points, transforms, scores, instance_ids)

    if log:
        logging.info(f"Exported {len(points)} picks to CSV: {output_path}")

    return output_path


def _get_tomogram_dimensions(picks: "CopickPicks") -> Tuple[int, int, int]:
    """Get tomogram dimensions from the run associated with picks."""
    vs_with_tomo = [vs for vs in picks.run.voxel_spacings if vs.tomograms]
    if not vs_with_tomo:
        raise ValueError("Cannot determine tomogram dimensions: no tomograms found in run.")

    # Use smallest voxel spacing
    vs = min(vs_with_tomo, key=lambda x: x.voxel_size)
    tomo = vs.tomograms[0]
    z, y, x = zarr.open(tomo.zarr())["0"].shape
    return (x, y, z)


# =============================================================================
# Tomogram Export Functions
# =============================================================================


def export_tomogram(
    tomogram: "CopickTomogram",
    output_path: str,
    output_format: str,
    level: int = 0,
    compression: Optional[str] = None,
    copy_all_levels: bool = True,
    log: bool = False,
) -> str:
    """Export a tomogram to an external format.

    Args:
        tomogram: The CopickTomogram object to export.
        output_path: Path for the output file.
        output_format: Output format ("mrc", "tiff", "zarr").
        level: Pyramid level to export (for mrc/tiff).
        compression: Compression method for TIFF output.
        copy_all_levels: Copy all pyramid levels for Zarr output.
        log: Log the operation.

    Returns:
        Path to the created output file.
    """
    output_format = output_format.lower()

    if output_format == "mrc":
        return _export_tomogram_mrc(tomogram, output_path, level, log=log)
    elif output_format == "tiff":
        return _export_tomogram_tiff(tomogram, output_path, level, compression, log=log)
    elif output_format == "zarr":
        return _export_tomogram_zarr(tomogram, output_path, copy_all_levels, log=log)
    else:
        raise ValueError(f"Unsupported output format: {output_format}")


def _export_tomogram_mrc(
    tomogram: "CopickTomogram",
    output_path: str,
    level: int = 0,
    log: bool = False,
) -> str:
    """Export tomogram to MRC format.

    Args:
        tomogram: The CopickTomogram object to export.
        output_path: Path for the output MRC file.
        level: Pyramid level to export.
        log: Log the operation.

    Returns:
        Path to the created output file.
    """
    import mrcfile

    # Get the data
    zarr_group = zarr.open(tomogram.zarr())
    volume = np.array(zarr_group[str(level)])

    # Get voxel size (scales with pyramid level)
    voxel_size = tomogram.voxel_spacing.voxel_size * (2**level)

    # Write MRC file
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with mrcfile.new(output_path, overwrite=True) as mrc:
        mrc.set_data(volume.astype(np.float32))
        mrc.voxel_size = voxel_size

    if log:
        logging.info(f"Exported tomogram to MRC: {output_path}")

    return output_path


def _export_tomogram_tiff(
    tomogram: "CopickTomogram",
    output_path: str,
    level: int = 0,
    compression: Optional[str] = None,
    log: bool = False,
) -> str:
    """Export tomogram to TIFF stack format.

    Args:
        tomogram: The CopickTomogram object to export.
        output_path: Path for the output TIFF file.
        level: Pyramid level to export.
        compression: Compression method.
        log: Log the operation.

    Returns:
        Path to the created output file.
    """
    from copick.util.formats import write_tiff_volume

    # Get the data
    zarr_group = zarr.open(tomogram.zarr())
    volume = np.array(zarr_group[str(level)])

    # Write TIFF file
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    write_tiff_volume(output_path, volume, compression)

    if log:
        logging.info(f"Exported tomogram to TIFF: {output_path}")

    return output_path


def _export_tomogram_zarr(
    tomogram: "CopickTomogram",
    output_path: str,
    copy_all_levels: bool = True,
    log: bool = False,
) -> str:
    """Export tomogram to OME-Zarr format.

    Args:
        tomogram: The CopickTomogram object to export.
        output_path: Path for the output Zarr directory.
        copy_all_levels: Copy all pyramid levels (if False, only level 0).
        log: Log the operation.

    Returns:
        Path to the created output directory.
    """
    import shutil

    # Get source zarr
    source = tomogram.zarr()

    # Copy the zarr store
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    if copy_all_levels:
        # Copy entire zarr store
        if isinstance(source, str):
            shutil.copytree(source, output_path)
        else:
            # For fsspec stores, copy using zarr
            source_group = zarr.open(source, mode="r")
            dest_group = zarr.open(output_path, mode="w")
            zarr.copy_store(source_group.store, dest_group.store)
    else:
        # Copy only level 0
        source_group = zarr.open(source, mode="r")
        dest_group = zarr.open(output_path, mode="w")
        zarr.copy(source_group["0"], dest_group, name="0")
        # Copy metadata
        dest_group.attrs.update(source_group.attrs)

    if log:
        logging.info(f"Exported tomogram to Zarr: {output_path}")

    return output_path


# =============================================================================
# Segmentation Export Functions
# =============================================================================


def export_segmentation(
    segmentation: "CopickSegmentation",
    output_path: str,
    output_format: str,
    level: int = 0,
    compression: Optional[str] = None,
    copy_all_levels: bool = True,
    log: bool = False,
) -> str:
    """Export a segmentation to an external format.

    Args:
        segmentation: The CopickSegmentation object to export.
        output_path: Path for the output file.
        output_format: Output format ("mrc", "tiff", "zarr").
        level: Pyramid level to export (for mrc/tiff).
        compression: Compression method for TIFF output.
        copy_all_levels: Copy all pyramid levels for Zarr output.
        log: Log the operation.

    Returns:
        Path to the created output file.
    """
    output_format = output_format.lower()

    if output_format == "mrc":
        return _export_segmentation_mrc(segmentation, output_path, level, log=log)
    elif output_format == "tiff":
        return _export_segmentation_tiff(segmentation, output_path, level, compression, log=log)
    elif output_format == "zarr":
        return _export_segmentation_zarr(segmentation, output_path, copy_all_levels, log=log)
    elif output_format == "em":
        return _export_segmentation_em(segmentation, output_path, level, log=log)
    else:
        raise ValueError(f"Unsupported output format: {output_format}")


def _export_segmentation_mrc(
    segmentation: "CopickSegmentation",
    output_path: str,
    level: int = 0,
    log: bool = False,
) -> str:
    """Export segmentation to MRC format.

    Args:
        segmentation: The CopickSegmentation object to export.
        output_path: Path for the output MRC file.
        level: Pyramid level to export.
        log: Log the operation.

    Returns:
        Path to the created output file.
    """
    import mrcfile

    # Get the data
    zarr_group = zarr.open(segmentation.zarr())
    volume = np.array(zarr_group[str(level)])

    # Get voxel size (scales with pyramid level)
    voxel_size = segmentation.voxel_size * (2**level)

    # Write MRC file
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with mrcfile.new(output_path, overwrite=True) as mrc:
        # Cast to appropriate type for segmentation
        if volume.dtype in [np.float32, np.float64]:
            mrc.set_data(volume.astype(np.float32))
        else:
            mrc.set_data(volume.astype(np.int16))
        mrc.voxel_size = voxel_size

    if log:
        logging.info(f"Exported segmentation to MRC: {output_path}")

    return output_path


def _export_segmentation_tiff(
    segmentation: "CopickSegmentation",
    output_path: str,
    level: int = 0,
    compression: Optional[str] = None,
    log: bool = False,
) -> str:
    """Export segmentation to TIFF stack format.

    Args:
        segmentation: The CopickSegmentation object to export.
        output_path: Path for the output TIFF file.
        level: Pyramid level to export.
        compression: Compression method.
        log: Log the operation.

    Returns:
        Path to the created output file.
    """
    from copick.util.formats import write_tiff_volume

    # Get the data
    zarr_group = zarr.open(segmentation.zarr())
    volume = np.array(zarr_group[str(level)])

    # Write TIFF file
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    write_tiff_volume(output_path, volume, compression)

    if log:
        logging.info(f"Exported segmentation to TIFF: {output_path}")

    return output_path


def _export_segmentation_em(
    segmentation: "CopickSegmentation",
    output_path: str,
    level: int = 0,
    log: bool = False,
) -> str:
    """Export segmentation to TOM toolbox EM format.

    Args:
        segmentation: The CopickSegmentation object to export.
        output_path: Path for the output EM file.
        level: Pyramid level to export.
        log: Log the operation.

    Returns:
        Path to the created output file.
    """
    from copick.util.formats import write_em_volume

    # Get the data
    zarr_group = zarr.open(segmentation.zarr())
    volume = np.array(zarr_group[str(level)])

    # Write EM file
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    write_em_volume(output_path, volume)

    if log:
        logging.info(f"Exported segmentation to EM: {output_path}")

    return output_path


def _export_segmentation_zarr(
    segmentation: "CopickSegmentation",
    output_path: str,
    copy_all_levels: bool = True,
    log: bool = False,
) -> str:
    """Export segmentation to OME-Zarr format.

    Args:
        segmentation: The CopickSegmentation object to export.
        output_path: Path for the output Zarr directory.
        copy_all_levels: Copy all pyramid levels (if False, only level 0).
        log: Log the operation.

    Returns:
        Path to the created output directory.
    """
    import shutil

    # Get source zarr
    source = segmentation.zarr()

    # Copy the zarr store
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    if copy_all_levels:
        # Copy entire zarr store
        if isinstance(source, str):
            shutil.copytree(source, output_path)
        else:
            # For fsspec stores, copy using zarr
            source_group = zarr.open(source, mode="r")
            dest_group = zarr.open(output_path, mode="w")
            zarr.copy_store(source_group.store, dest_group.store)
    else:
        # Copy only level 0
        source_group = zarr.open(source, mode="r")
        dest_group = zarr.open(output_path, mode="w")
        zarr.copy(source_group["0"], dest_group, name="0")
        # Copy metadata
        dest_group.attrs.update(source_group.attrs)

    if log:
        logging.info(f"Exported segmentation to Zarr: {output_path}")

    return output_path


# =============================================================================
# Batch Export Functions
# =============================================================================


def export_run(
    run: "CopickRun",
    output_dir: str,
    picks_uri: Optional[str] = None,
    segmentation_uri: Optional[str] = None,
    tomogram_uri: Optional[str] = None,
    output_format: str = None,
    voxel_spacing: Optional[float] = None,
    level: int = 0,
    compression: Optional[str] = None,
    include_optics: bool = True,
    log: bool = False,
) -> Dict[str, int]:
    """Export data from a single run.

    Args:
        run: The CopickRun object to export from.
        output_dir: Base output directory.
        picks_uri: URI to filter picks for export.
        segmentation_uri: URI to filter segmentations for export.
        tomogram_uri: URI to filter tomograms for export.
        output_format: Output format for all exports.
        voxel_spacing: Voxel spacing for coordinate conversion.
        level: Pyramid level for volume exports.
        compression: Compression method for TIFF exports.
        include_optics: Include optics in STAR exports.
        log: Log operations.

    Returns:
        Dictionary with counts of exported items.
    """
    from copick.util.uri import resolve_copick_objects

    results = {"picks": 0, "segmentations": 0, "tomograms": 0, "errors": []}
    run_output_dir = os.path.join(output_dir, run.name)

    # Export picks
    if picks_uri:
        try:
            picks_list = resolve_copick_objects(picks_uri, run.root, "picks", run.name)
            for picks in picks_list:
                # Determine output filename
                filename = f"{picks.pickable_object_name}_{picks.user_id}_{picks.session_id}"
                ext = {"em": ".em", "star": ".star", "dynamo": ".tbl", "csv": ".csv"}.get(output_format, ".csv")
                output_path = os.path.join(run_output_dir, "Picks", filename + ext)

                export_picks(
                    picks,
                    output_path,
                    output_format,
                    voxel_spacing=voxel_spacing,
                    include_optics=include_optics,
                    run_name=run.name,
                    log=log,
                )
                results["picks"] += 1
        except Exception as e:
            results["errors"].append(f"Error exporting picks: {e}")
            if log:
                logging.error(f"Error exporting picks from {run.name}: {e}")

    # Export segmentations
    if segmentation_uri:
        try:
            segs_list = resolve_copick_objects(segmentation_uri, run.root, "segmentation", run.name)
            for seg in segs_list:
                filename = f"{seg.name}_{seg.user_id}_{seg.session_id}"
                ext = {"mrc": ".mrc", "tiff": ".tiff", "zarr": ".zarr"}.get(output_format, ".zarr")
                output_path = os.path.join(run_output_dir, "Segmentations", filename + ext)

                export_segmentation(
                    seg,
                    output_path,
                    output_format,
                    level=level,
                    compression=compression,
                    log=log,
                )
                results["segmentations"] += 1
        except Exception as e:
            results["errors"].append(f"Error exporting segmentations: {e}")
            if log:
                logging.error(f"Error exporting segmentations from {run.name}: {e}")

    # Export tomograms
    if tomogram_uri:
        try:
            tomos_list = resolve_copick_objects(tomogram_uri, run.root, "tomogram", run.name)
            for tomo in tomos_list:
                voxel_dir = f"VoxelSpacing{tomo.voxel_spacing.voxel_size:.3f}"
                filename = tomo.tomo_type
                ext = {"mrc": ".mrc", "tiff": ".tiff", "zarr": ".zarr"}.get(output_format, ".zarr")
                output_path = os.path.join(run_output_dir, voxel_dir, filename + ext)

                export_tomogram(
                    tomo,
                    output_path,
                    output_format,
                    level=level,
                    compression=compression,
                    log=log,
                )
                results["tomograms"] += 1
        except Exception as e:
            results["errors"].append(f"Error exporting tomograms: {e}")
            if log:
                logging.error(f"Error exporting tomograms from {run.name}: {e}")

    return results


def export(
    config: str,
    output_dir: str,
    run_names: Optional[List[str]] = None,
    picks_uri: Optional[str] = None,
    segmentation_uri: Optional[str] = None,
    tomogram_uri: Optional[str] = None,
    output_format: str = None,
    voxel_spacing: Optional[float] = None,
    level: int = 0,
    compression: Optional[str] = None,
    include_optics: bool = True,
    n_workers: int = 8,
    log: bool = False,
) -> None:
    """Export data from a copick project.

    Args:
        config: Path to the copick configuration file.
        output_dir: Base output directory.
        run_names: List of run names to export (None for all).
        picks_uri: URI to filter picks for export.
        segmentation_uri: URI to filter segmentations for export.
        tomogram_uri: URI to filter tomograms for export.
        output_format: Output format for all exports.
        voxel_spacing: Voxel spacing for coordinate conversion.
        level: Pyramid level for volume exports.
        compression: Compression method for TIFF exports.
        include_optics: Include optics in STAR exports.
        n_workers: Number of parallel workers.
        log: Log operations.
    """
    import copick
    from copick.ops.run import map_runs

    root = copick.from_file(config)

    # Get runs to process
    runs = root.runs if run_names is None else [root.get_run(name) for name in run_names]

    # Build run_args
    run_args = [
        {
            "output_dir": output_dir,
            "picks_uri": picks_uri,
            "segmentation_uri": segmentation_uri,
            "tomogram_uri": tomogram_uri,
            "output_format": output_format,
            "voxel_spacing": voxel_spacing,
            "level": level,
            "compression": compression,
            "include_optics": include_optics,
            "log": log,
        }
        for _ in runs
    ]

    # Process runs in parallel
    results = map_runs(
        callback=export_run,
        root=root,
        runs=runs,
        workers=n_workers,
        run_args=run_args,
        show_progress=True,
        task_desc="Exporting data",
    )

    # Report results
    total_picks = sum(r.get("picks", 0) for r in results.values() if r)
    total_segs = sum(r.get("segmentations", 0) for r in results.values() if r)
    total_tomos = sum(r.get("tomograms", 0) for r in results.values() if r)
    all_errors = []
    for r in results.values():
        if r and "errors" in r:
            all_errors.extend(r["errors"])

    if log or all_errors:
        if all_errors:
            logging.error(f"Export completed with {len(all_errors)} errors:")
            for err in all_errors:
                logging.error(f"  {err}")

        logging.info(f"Exported: {total_picks} picks, {total_segs} segmentations, {total_tomos} tomograms")
