"""Export operations for copick data to external formats.

This module provides functions to export copick data (picks, tomograms, segmentations)
to various external file formats used in cryo-ET workflows.
"""

import logging
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple, Union

import numpy as np
import zarr

from copick.util.log import get_logger
from copick.util.relion import FilamentPolarity
from copick.util.segmentation import PANOPTIC_CHANNELS

if TYPE_CHECKING:
    from copick.models import (
        CopickPicks,
        CopickRoot,
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
    include_optics: bool = True,
    run_name: Optional[str] = None,
    tomogram_index: int = 1,
    log: bool = False,
    tilt_series_pixel_size: Optional[float] = None,
    tomograms_star: Optional[str] = None,
    filament_columns: str = "auto",
    polarity_from_filaments: bool = True,
    filaments_uri: Optional[str] = None,
    tomo_type: Optional[str] = None,
    coordinates: str = "auto",
) -> str:
    """Export picks to an external format.

    Args:
        picks: The CopickPicks object to export.
        output_path: Path for the output file.
        output_format: Output format ("em", "star", "dynamo", "csv").
        voxel_spacing: Voxel spacing in Angstrom (required for em, star, dynamo).
        include_optics: Include optics group in STAR file output.
        run_name: Run name for CSV output (uses picks.run.name if not provided).
        tomogram_index: Tomogram index for EM/Dynamo formats (default: 1).
        log: Log the operation.
        tilt_series_pixel_size: STAR only: tilt-series pixel size in Angstrom; adds rlnCoordinateX/Y/Z in
            tilt-series pixels and an optics table.
        tomograms_star: STAR only: RELION tomograms.star giving the tomogram's centre, tilt-series pixel size and
            CTF parameters (takes precedence over the copick tomogram).
        filament_columns: STAR only: write RELION's filament columns ("on"), plain particle angles ("off"), or
            filament columns for objects declared a filament ("auto").
        polarity_from_filaments: STAR only: for filament columns, take each filament's polarity from a Filaments
            source, so that ``rlnAnglePsiFlipRatio`` is 0 for picks of filaments with ``polarity_known`` and 0.5 for
            the rest; with False, every filament pick gets 0.5.
        filaments_uri: STAR only: the Filaments source (``object:user/session``) for the polarity, matched by
            instance ID in each run. Default: the Filaments under the picks' own URI, when they exist.
        tomo_type: STAR only: type of the copick tomogram whose shape defines each run's center. Default: the first
            tomogram at ``voxel_spacing``.
        coordinates: STAR only: ``"auto"`` (centered coordinates and/or rlnCoordinateX/Y/Z in tilt-series pixels,
            whatever is known) or ``"centered"`` (centered coordinates only; a run without a center is an error).

    Returns:
        Path to the created output file.

    Raises:
        ValueError: If required parameters are missing for the output format.
    """
    output_format = output_format.lower()

    if output_format == "em":
        return _export_picks_em(
            picks,
            output_path,
            voxel_spacing,
            tomogram_index=tomogram_index,
            log=log,
        )
    elif output_format == "star":
        return _export_picks_star(
            picks,
            output_path,
            voxel_spacing,
            include_optics,
            log=log,
            tilt_series_pixel_size=tilt_series_pixel_size,
            tomograms_star=tomograms_star,
            filament_columns=filament_columns,
            polarity_from_filaments=polarity_from_filaments,
            filaments_uri=filaments_uri,
            tomo_type=tomo_type,
            coordinates=coordinates,
        )
    elif output_format == "dynamo":
        return _export_picks_dynamo(picks, output_path, voxel_spacing, tomogram_index=tomogram_index, log=log)
    elif output_format == "csv":
        run_name = run_name or picks.run.name
        return _export_picks_csv(picks, output_path, run_name, log=log)
    else:
        raise ValueError(f"Unsupported output format: {output_format}")


def _filament_mode(filament_columns: str):
    """``filament_columns`` ("auto", "on" or "off") as "auto", True or False."""
    modes = {"auto": "auto", "on": True, "off": False}
    if filament_columns not in modes:
        raise ValueError(f"filament_columns must be one of {sorted(modes)}, not {filament_columns!r}")
    return modes[filament_columns]


def _check_polarity_source(polarity_from_filaments: bool, filaments_uri: Optional[str]) -> None:
    if filaments_uri is not None and not polarity_from_filaments:
        raise ValueError("filaments_uri names a polarity source, but polarity_from_filaments is False.")


def _picks_polarity(picks: "CopickPicks", polarity_from_filaments: bool, filaments_uri: Optional[str]) -> np.ndarray:
    """Per pick, whether its filament's polarity is known (all False unless read from Filaments)."""
    from copick.util.relion import filament_polarity_known

    if not polarity_from_filaments:
        return np.zeros(len(picks.instance_ids()), dtype=bool)
    return filament_polarity_known(picks, filaments_uri)


def _export_picks_em(
    picks: "CopickPicks",
    output_path: str,
    voxel_spacing: float,
    tomogram_index: int = 1,
    log: bool = False,
) -> str:
    """Export picks to TOM toolbox EM motivelist format.

    Args:
        picks: The CopickPicks object to export.
        output_path: Path for the output EM file.
        voxel_spacing: Voxel spacing in Angstrom.
        tomogram_index: Tomogram index for the motivelist.
        log: Log the operation.

    Returns:
        Path to the created output file.
    """
    from copick.util.handlers.picks.em import em_picks_handler

    if voxel_spacing is None:
        raise ValueError("voxel_spacing is required for EM export.")

    # Get points and transforms
    points, transforms = picks.numpy()

    # Write EM file (transform translations become the motivelist shifts)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    em_picks_handler.write(
        output_path,
        points,
        transforms,
        voxel_spacing,
        scores=picks.scores(),
        tomogram_index=tomogram_index,
    )

    if log:
        logging.info(f"Exported {len(points)} picks to EM file: {output_path}")

    return output_path


def _export_picks_star(
    picks: "CopickPicks",
    output_path: str,
    voxel_spacing: float,
    include_optics: bool = True,
    log: bool = False,
    tilt_series_pixel_size: Optional[float] = None,
    tomograms_star: Optional[str] = None,
    filament_columns: str = "auto",
    polarity_from_filaments: bool = True,
    filaments_uri: Optional[str] = None,
    tomo_type: Optional[str] = None,
    coordinates: str = "auto",
) -> str:
    """Export picks to RELION STAR format.

    The file carries rlnTomoName, angles, centred coordinates relative to the tomogram centre (from
    ``tomograms_star`` or the copick tomogram at ``voxel_spacing``) and, when the tilt-series pixel size is known,
    rlnCoordinateX/Y/Z in tilt-series pixels with an optics table (see ``copick.util.formats.build_relion_star_tables``).

    Args:
        picks: The CopickPicks object to export.
        output_path: Path for the output STAR file.
        voxel_spacing: Voxel spacing in Angstrom; selects the copick tomogram that defines the centre.
        include_optics: Include optics group in output.
        log: Log the operation.
        tilt_series_pixel_size: Tilt-series pixel size in Angstrom.
        tomograms_star: RELION tomograms.star with this run's tomogram.
        filament_columns: "on", "off", or "auto" (filament columns for objects declared a filament).
        polarity_from_filaments: Take the filaments' polarity from Filaments (see ``export_picks``).
        filaments_uri: The Filaments source; default: the picks' own URI.
        tomo_type: Type of the copick tomogram whose shape defines the center.
        coordinates: ``"auto"`` or ``"centered"`` (centered coordinates only).

    Returns:
        Path to the created output file.
    """
    from copick.util.formats import read_relion_tomograms
    from copick.util.handlers.picks.star import star_handler
    from copick.util.relion import copick_tomogram_center, is_filament_export

    if voxel_spacing is None:
        raise ValueError("voxel_spacing is required for STAR export.")
    _check_polarity_source(polarity_from_filaments, filaments_uri)

    run_name = picks.run.name
    tomogram = None
    if tomograms_star:
        tomogram = read_relion_tomograms(tomograms_star).get(run_name)
        if tomogram is None:
            logging.warning(f"{run_name} is not in {tomograms_star}; using the copick tomogram for its centre.")
    if tomogram is not None:
        center = tomogram.center_angstrom
    else:
        center = copick_tomogram_center(picks, voxel_spacing, tomo_type)

    points, transforms = picks.numpy()
    filament = is_filament_export(picks, _filament_mode(filament_columns))

    # Write STAR file
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    star_handler.write(
        output_path,
        points,
        transforms,
        voxel_spacing,
        include_optics,
        tomo_name=run_name,
        tomogram_center=center,
        tilt_series_pixel_size=tilt_series_pixel_size,
        tomogram=tomogram,
        instance_ids=picks.instance_ids(),
        filament=filament,
        polarity_known=_picks_polarity(picks, polarity_from_filaments, filaments_uri) if filament else False,
        coordinates=coordinates,
    )

    if log:
        logging.info(f"Exported {len(points)} picks to STAR file: {output_path}")

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
    from copick.util.handlers.picks.dynamo import dynamo_handler

    if voxel_spacing is None:
        raise ValueError("voxel_spacing is required for Dynamo export.")

    # Get points and transforms
    points, transforms = picks.numpy()

    # Write Dynamo table (transform translations become the table shifts)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    dynamo_handler.write(
        output_path,
        points,
        transforms,
        voxel_spacing,
        scores=picks.scores(),
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


@dataclass
class RelionExport:
    """What ``export_relion_particles`` wrote.

    Attributes:
        path: The particle STAR file, or the index for the ``"import"`` layout.
        layout: ``"particles"`` or ``"import"``.
        files: For the ``"import"`` layout, each run's coordinate file as written in the index; else empty.
        rows: Particles written per run, for every run considered (0 for a run without picks).
        filament: Whether RELION's filament columns were written.
        polarity: For filament exports, how each run's polarity was resolved (runs with picks only). A run whose
            picks come from several picks sets sums their counts and joins their sources with ", ".
    """

    path: str
    layout: str
    files: Dict[str, str] = field(default_factory=dict)
    rows: Dict[str, int] = field(default_factory=dict)
    filament: bool = False
    polarity: Dict[str, FilamentPolarity] = field(default_factory=dict)


#: STAR layouts of ``export_relion_particles``.
RELION_LAYOUTS = ("particles", "import")

#: Columns of a particle file without particles.
_EMPTY_PARTICLE_COLUMNS = (
    "rlnTomoName",
    "rlnCenteredCoordinateXAngst",
    "rlnCenteredCoordinateYAngst",
    "rlnCenteredCoordinateZAngst",
    "rlnAngleRot",
    "rlnAngleTilt",
    "rlnAnglePsi",
)


def _merge_polarity(summaries: List[FilamentPolarity]) -> FilamentPolarity:
    sources = sorted({p.source for p in summaries if p.source is not None})
    return FilamentPolarity(
        source=", ".join(sources) if sources else None,
        known=sum(p.known for p in summaries),
        unknown=sum(p.unknown for p in summaries),
    )


def _run_polarity(
    picks_list: List["CopickPicks"],
    polarity_from_filaments: bool,
    filaments_uri: Optional[str],
) -> Tuple[np.ndarray, FilamentPolarity]:
    """Per pick polarity and its summary for the picks sets of one run, in order."""
    from copick.util.relion import filament_polarity

    results = []
    for picks in picks_list:
        if polarity_from_filaments:
            results.append(filament_polarity(picks, filaments_uri))
        else:
            ids = np.asarray(picks.instance_ids())
            results.append((np.zeros(len(ids), dtype=bool), FilamentPolarity(None, 0, len(set(ids.tolist())))))
    return np.concatenate([known for known, _ in results]), _merge_polarity([summary for _, summary in results])


def export_relion_particles(
    root: Union[str, "CopickRoot"],
    picks_uri: str,
    output_path: str,
    *,
    voxel_spacing: Optional[float] = None,
    run_names: Optional[List[str]] = None,
    layout: str = "particles",
    tomo_type: Optional[str] = None,
    tomogram_centers: Optional[Dict[str, Tuple[float, float, float]]] = None,
    tilt_series_pixel_size: Union[None, float, Dict[str, float]] = None,
    tomograms_star: Optional[str] = None,
    coordinates: str = "auto",
    include_optics: bool = True,
    filament_columns: str = "auto",
    polarity_from_filaments: bool = True,
    filaments_uri: Optional[str] = None,
    allow_empty: bool = False,
) -> RelionExport:
    """Export the picks matching a URI from several runs to RELION, and report what was written.

    The picks of each run are concatenated in the order the URI resolves them, each in its own point order; the
    particle rows follow ``copick.util.formats.build_relion_star_tables``. Errors are raised, never skipped per run.

    Two layouts:

    - ``"particles"``: one STAR file with a particles table and, when the tilt-series pixel size is known (and
      ``include_optics``), an optics table with one group per run.
    - ``"import"``: the input of RELION's tomography Import Coordinates job. ``output_path`` is an index naming one
      coordinate file per run, in ``coordinates/`` beside it (``copick.util.formats.write_relion_import_bundle``).

    A run's tomogram center comes from ``tomograms_star``, else ``tomogram_centers``, else the shape of the copick
    tomogram (``tomo_type`` at ``voxel_spacing``). Copick tomograms are opened only for runs whose center is not given.

    Args:
        root: Copick root, or the path of its configuration file.
        picks_uri: Picks URI (e.g. ``microtubule:sampler/1``).
        output_path: Output STAR file (the index for the ``"import"`` layout).
        voxel_spacing: Voxel spacing of the copick tomograms that define the centers; also the unit of the legacy
            coordinates written when neither a center nor the tilt-series pixel size is known.
        run_names: Runs to export (default: all). An unknown name is an error.
        layout: ``"particles"`` or ``"import"``.
        tomo_type: Type of the copick tomogram whose shape defines each run's center.
        tomogram_centers: Tomogram center in Angstrom (copick's frame) per run.
        tilt_series_pixel_size: Tilt-series pixel size in Angstrom, for every run or per run (a dict).
        tomograms_star: RELION tomograms.star with the runs' centers, tilt-series pixel sizes and CTF parameters.
        coordinates: ``"auto"`` or ``"centered"`` (centered coordinates only; a run without a center is an error).
        include_optics: ``"particles"`` layout: write the optics table when the tilt-series pixel size is known.
        filament_columns: ``"on"``, ``"off"`` or ``"auto"`` (filament columns when every exported object is declared
            a filament).
        polarity_from_filaments: For filament columns, read each filament's polarity from Filaments (see
            ``copick.util.relion.filament_polarity``); with False every pick gets ``rlnAnglePsiFlipRatio`` = 0.5.
        filaments_uri: The Filaments that state the polarity. Default: those under each picks set's own URI.
        allow_empty: Without picks, write an empty particle table (or index) instead of raising.

    Returns:
        A ``RelionExport``.

    Raises:
        ValueError: For an unknown layout, coordinate mode or run name; no picks (unless ``allow_empty``); a run
            without a center with ``coordinates="centered"``; a ``filaments_uri`` matching no or several Filaments in
            a run; or a pick whose filament is not in the Filaments (see ``copick.util.relion.filament_polarity``).
    """
    import pandas as pd

    import copick
    from copick.util.formats import (
        build_relion_star_tables,
        get_tomogram_centers_from_copick,
        read_relion_tomograms,
        write_relion_import_bundle,
        write_star_particles,
    )
    from copick.util.uri import resolve_copick_objects

    if layout not in RELION_LAYOUTS:
        raise ValueError(f"layout must be one of {RELION_LAYOUTS}, not {layout!r}")
    _check_polarity_source(polarity_from_filaments, filaments_uri)
    mode = _filament_mode(filament_columns)
    if isinstance(root, (str, os.PathLike)):
        root = copick.from_file(str(root))

    if run_names is None:
        runs = list(root.runs)
    else:
        unknown = [name for name in run_names if root.get_run(name) is None]
        if unknown:
            raise ValueError(f"Unknown runs: {', '.join(unknown)}")
        runs = [root.get_run(name) for name in run_names]

    positions: Dict[str, List[np.ndarray]] = {}
    transforms: Dict[str, List[np.ndarray]] = {}
    instance_ids: Dict[str, List[np.ndarray]] = {}
    picks_sets: Dict[str, List["CopickPicks"]] = {}
    rows: Dict[str, int] = {}
    filament_objects = []
    for run in runs:
        rows[run.name] = 0
        for picks in resolve_copick_objects(picks_uri, root, "picks", run.name):
            points, matrices = picks.numpy()
            if len(points) == 0:
                continue
            positions.setdefault(run.name, []).append(points)
            transforms.setdefault(run.name, []).append(matrices)
            instance_ids.setdefault(run.name, []).append(np.asarray(picks.instance_ids(), dtype=np.int64))
            picks_sets.setdefault(run.name, []).append(picks)
            rows[run.name] += len(points)
            obj = root.get_object(picks.pickable_object_name)
            filament_objects.append(bool(obj is not None and obj.is_filament))

    if not positions and not allow_empty:
        raise ValueError("No picks found to export")

    if mode == "auto":
        filament = bool(filament_objects) and all(filament_objects)
        if any(filament_objects) and not filament:
            logger.warning(
                "Exporting filament and non-filament objects to one STAR file: writing plain particle angles. "
                "Export filament objects separately to get RELION's filament columns.",
            )
    else:
        filament = mode

    tomograms = read_relion_tomograms(tomograms_star) if tomograms_star else {}
    centers = dict(tomogram_centers or {})
    from_copick = [name for name in positions if name not in centers and name not in tomograms]
    if from_copick:
        centers.update(get_tomogram_centers_from_copick(root, from_copick, voxel_spacing, tomo_type))

    polarity_known: Dict[str, np.ndarray] = {}
    polarity: Dict[str, FilamentPolarity] = {}
    if filament:
        for name, picks_list in picks_sets.items():
            polarity_known[name], polarity[name] = _run_polarity(picks_list, polarity_from_filaments, filaments_uri)

    particles, optics = build_relion_star_tables(
        {name: (np.vstack(positions[name]), np.vstack(transforms[name])) for name in positions},
        voxel_spacing=voxel_spacing,
        tomogram_centers=centers,
        tilt_series_pixel_size=tilt_series_pixel_size,
        tomograms=tomograms,
        include_optics=include_optics and layout == "particles",
        instance_ids={name: np.concatenate(ids) for name, ids in instance_ids.items()},
        filament=filament,
        polarity_known=polarity_known,
        coordinates=coordinates,
    )

    files: Dict[str, str] = {}
    if layout == "import":
        output_path, files = write_relion_import_bundle(output_path, particles)
    else:
        if not len(particles.columns):
            particles = pd.DataFrame(columns=list(_EMPTY_PARTICLE_COLUMNS))
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        write_star_particles(output_path, particles, optics)

    logger.info(
        f"Exported {sum(rows.values())} particles from {len(positions)} of {len(rows)} runs to RELION "
        f"({layout} layout): {output_path}",
    )
    return RelionExport(path=output_path, layout=layout, files=files, rows=rows, filament=filament, polarity=polarity)


def export_picks_combined(
    config: str,
    output_file: str,
    picks_uri: str,
    output_format: str,
    voxel_spacing: Optional[float] = None,
    run_names: Optional[List[str]] = None,
    run_to_index: Optional[Dict[str, int]] = None,
    include_optics: bool = True,
    log: bool = False,
    tilt_series_pixel_size: Optional[float] = None,
    tomograms_star: Optional[str] = None,
    filament_columns: str = "auto",
    polarity_from_filaments: bool = True,
    filaments_uri: Optional[str] = None,
    tomo_type: Optional[str] = None,
    coordinates: str = "auto",
    star_layout: str = "particles",
) -> str:
    """Export picks from multiple runs to a single combined file.

    This function collects picks from all specified runs and writes them
    to a single output file using the format handler's write_grouped method.
    STAR files are written by ``export_relion_particles``, which raises rather than skipping a run that fails.

    Args:
        config: Path to the copick configuration file.
        output_file: Path for the output file.
        picks_uri: URI to filter picks for export.
        output_format: Output format ("em", "star", "dynamo", "csv").
        voxel_spacing: Voxel spacing in Angstrom (required for em, star, dynamo).
        run_names: List of run names to export (None for all runs).
        run_to_index: Mapping from run name to tomogram index (required for em/dynamo).
        include_optics: Include optics group in STAR file output.
        log: Log the operation.
        tilt_series_pixel_size: STAR only: tilt-series pixel size in Angstrom for every run.
        tomograms_star: STAR only: RELION tomograms.star giving each run's tomogram centre, tilt-series pixel size
            and CTF parameters (takes precedence over the copick tomograms).
        filament_columns: STAR only: "on", "off", or "auto": filament columns when every exported object is declared
            a filament (one table cannot mix filament and particle columns).
        polarity_from_filaments: STAR only: for filament columns, take each filament's polarity from a Filaments
            source, so that ``rlnAnglePsiFlipRatio`` is 0 for picks of filaments with ``polarity_known`` and 0.5 for
            the rest; with False, every filament pick gets 0.5.
        filaments_uri: STAR only: the Filaments source (``object:user/session``) for the polarity, matched by
            instance ID in each run. Default: the Filaments under the picks' own URI, when they exist.
        tomo_type: STAR only: type of the copick tomogram whose shape defines each run's center. Default: the first
            tomogram at ``voxel_spacing``.
        coordinates: STAR only: ``"auto"`` (centered coordinates and/or rlnCoordinateX/Y/Z in tilt-series pixels,
            whatever is known) or ``"centered"`` (centered coordinates only; a run without a center is an error).
        star_layout: STAR only: ``"particles"`` (one particle file) or ``"import"`` (``output_file`` is the index of
            per-run coordinate files for RELION's Import Coordinates job; see ``export_relion_particles``).

    Returns:
        Path to the created output file.

    Raises:
        ValueError: If required parameters are missing for the output format.
    """
    import copick
    from copick.util.handlers import FormatRegistry
    from copick.util.uri import resolve_copick_objects

    output_format = output_format.lower()

    # Get the handler and validate capabilities
    handler = FormatRegistry.get_picks_handler(output_format)
    if not handler.capabilities.supports_grouped_export:
        raise ValueError(f"Format '{output_format}' does not support combined/grouped export")

    # Validate index map for formats that need it
    if output_format in ("em", "dynamo") and run_to_index is None:
        raise ValueError(f"run_to_index mapping is required for combined {output_format.upper()} export")

    # Validate voxel spacing for formats that need it
    if output_format in ("em", "star", "dynamo") and voxel_spacing is None:
        raise ValueError(f"voxel_spacing is required for {output_format.upper()} export")

    # Load copick project
    root = copick.from_file(config)

    if output_format == "star":
        if run_names is not None:  # unknown runs are skipped here, as for the other formats
            run_names = [name for name in run_names if root.get_run(name) is not None]
        return export_relion_particles(
            root,
            picks_uri,
            output_file,
            voxel_spacing=voxel_spacing,
            run_names=run_names,
            layout=star_layout,
            tomo_type=tomo_type,
            tilt_series_pixel_size=tilt_series_pixel_size,
            tomograms_star=tomograms_star,
            coordinates=coordinates,
            include_optics=include_optics,
            filament_columns=filament_columns,
            polarity_from_filaments=polarity_from_filaments,
            filaments_uri=filaments_uri,
        ).path

    # Get runs to process
    runs = root.runs if run_names is None else [root.get_run(name) for name in run_names if root.get_run(name)]

    # Collect picks from all runs
    grouped_data: Dict[str, Tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]] = {}
    grouped_instance_ids: Dict[str, np.ndarray] = {}
    total_particles = 0

    for run in runs:
        try:
            picks_list = resolve_copick_objects(picks_uri, root, "picks", run.name)
            for picks in picks_list:
                points, transforms = picks.numpy()
                if len(points) == 0:
                    continue

                # Get scores if available
                scores = None
                if picks.points:
                    scores = np.array([p.score for p in picks.points])
                instance_ids = picks.instance_ids()

                # Accumulate data for this run
                if run.name in grouped_data:
                    existing_pos, existing_trans, existing_scores = grouped_data[run.name]
                    grouped_data[run.name] = (
                        np.vstack([existing_pos, points]),
                        np.vstack([existing_trans, transforms]),
                        (
                            np.concatenate([existing_scores, scores])
                            if scores is not None and existing_scores is not None
                            else None
                        ),
                    )
                else:
                    grouped_data[run.name] = (points, transforms, scores)
                if run.name in grouped_instance_ids:
                    grouped_instance_ids[run.name] = np.concatenate([grouped_instance_ids[run.name], instance_ids])
                else:
                    grouped_instance_ids[run.name] = instance_ids
                total_particles += len(points)
        except Exception as e:
            if log:
                logging.warning(f"Error collecting picks from {run.name}: {e}")

    if not grouped_data:
        raise ValueError("No picks found to export")

    # Create output directory if needed
    os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)

    # Write using the handler's write_grouped method
    handler.write_grouped(
        path=output_file,
        grouped_data=grouped_data,
        voxel_spacing=voxel_spacing or 1.0,
        run_to_index=run_to_index,
        include_optics=include_optics,
        grouped_instance_ids=grouped_instance_ids,
    )

    if log:
        logging.info(
            f"Exported {total_particles} particles from {len(grouped_data)} runs to {output_format.upper()}: {output_file}",
        )

    return output_file


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
            # For fsspec stores, copy into a fresh DirectoryStore
            source_group = zarr.open(source, mode="r")
            dest_store = zarr.DirectoryStore(output_path)
            zarr.copy_store(source_group.store, dest_store)
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
    channel: Optional[str] = None,
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
        channel: Panoptic segmentations only: the channel ("label" or "instance") to write to MRC, TIFF or EM,
            which hold one volume each. Zarr output keeps both channels.

    Returns:
        Path to the created output file.
    """
    output_format = output_format.lower()

    if output_format == "zarr":
        if channel is not None:
            raise ValueError("Zarr output keeps every channel; channel applies to MRC, TIFF and EM output.")
        return _export_segmentation_zarr(segmentation, output_path, copy_all_levels, log=log)
    if output_format not in ("mrc", "tiff", "em"):
        raise ValueError(f"Unsupported output format: {output_format}")

    volume = _segmentation_volume(segmentation, level, channel)
    if output_format == "mrc":
        return _export_segmentation_mrc(segmentation, output_path, level, log=log, volume=volume)
    elif output_format == "tiff":
        return _export_segmentation_tiff(segmentation, output_path, level, compression, log=log, volume=volume)
    return _export_segmentation_em(segmentation, output_path, level, log=log, volume=volume)


def _segmentation_volume(segmentation: "CopickSegmentation", level: int, channel: Optional[str]) -> np.ndarray:
    """The single volume an MRC, TIFF or EM file holds: the segmentation, or one channel of a panoptic one."""
    if segmentation.is_panoptic:
        if channel is None:
            raise ValueError(
                "A panoptic segmentation has two channels; pass channel='label' or 'instance' (CLI: --channel) to "
                "write one to MRC, TIFF or EM, or export to Zarr.",
            )
        return segmentation.numpy(zarr_group=str(level), channel=channel)
    if channel is not None:
        raise ValueError(f"{segmentation} is a {segmentation.segmentation_type} segmentation; it has no channels.")
    return np.array(zarr.open(segmentation.zarr())[str(level)])


# float32 holds every integer up to 2**24 exactly; past that, labels would merge.
_FLOAT32_EXACT = 2**24


def _label_range(volume: np.ndarray) -> Tuple[int, int]:
    return (int(volume.min()), int(volume.max())) if volume.size else (0, 0)


def _segmentation_volume_for_mrc(volume: np.ndarray) -> np.ndarray:
    """Cast a segmentation for MRC, which has no 32-bit integer mode, without changing any label."""
    if volume.dtype.kind == "f":
        return volume.astype(np.float32)
    lo, hi = _label_range(volume)
    if lo >= -32768 and hi <= 32767:
        return volume.astype(np.int16)
    if lo >= 0 and hi <= 65535:
        return volume.astype(np.uint16)
    if -_FLOAT32_EXACT <= lo and hi <= _FLOAT32_EXACT:
        logger.warning(f"Segmentation values up to {hi} exceed MRC's integer modes; writing float32 (exact).")
        return volume.astype(np.float32)
    raise ValueError(
        f"Segmentation values in [{lo}, {hi}] cannot be written to MRC without changing labels; "
        "export to TIFF or Zarr instead.",
    )


def _segmentation_em_dtype(volume: np.ndarray) -> np.dtype:
    """The EM dtype for a segmentation: float32 as before while it is exact, int32 above that."""
    if volume.dtype.kind == "f":
        return np.dtype(np.float32)
    lo, hi = _label_range(volume)
    if -_FLOAT32_EXACT <= lo and hi <= _FLOAT32_EXACT:
        return np.dtype(np.float32)
    info = np.iinfo(np.int32)
    if info.min <= lo and hi <= info.max:
        return np.dtype(np.int32)
    raise ValueError(
        f"Segmentation values in [{lo}, {hi}] cannot be written to EM without changing labels; "
        "export to TIFF or Zarr instead.",
    )


def _export_segmentation_mrc(
    segmentation: "CopickSegmentation",
    output_path: str,
    level: int = 0,
    log: bool = False,
    volume: Optional[np.ndarray] = None,
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
    if volume is None:
        volume = _segmentation_volume(segmentation, level, None)

    # Get voxel size (scales with pyramid level)
    voxel_size = segmentation.voxel_size * (2**level)

    # Write MRC file
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with mrcfile.new(output_path, overwrite=True) as mrc:
        mrc.set_data(_segmentation_volume_for_mrc(volume))
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
    volume: Optional[np.ndarray] = None,
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
    if volume is None:
        volume = _segmentation_volume(segmentation, level, None)

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
    volume: Optional[np.ndarray] = None,
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
    if volume is None:
        volume = _segmentation_volume(segmentation, level, None)

    # Write EM file
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    write_em_volume(output_path, volume, dtype=_segmentation_em_dtype(volume))

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
            # For fsspec stores, copy into a fresh DirectoryStore
            source_group = zarr.open(source, mode="r")
            dest_store = zarr.DirectoryStore(output_path)
            zarr.copy_store(source_group.store, dest_store)
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
    run_to_index: Optional[Dict[str, int]] = None,
    log: bool = False,
    tilt_series_pixel_size: Optional[float] = None,
    tomograms_star: Optional[str] = None,
    filament_columns: str = "auto",
    channel: Optional[str] = None,
    polarity_from_filaments: bool = True,
    filaments_uri: Optional[str] = None,
    tomo_type: Optional[str] = None,
    coordinates: str = "auto",
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
        run_to_index: Optional mapping from run name to tomogram index for EM/Dynamo.
        log: Log operations.
        tilt_series_pixel_size: STAR only: tilt-series pixel size in Angstrom.
        tomograms_star: STAR only: RELION tomograms.star with the runs' tomograms.
        filament_columns: STAR only: "on", "off", or "auto" (filament columns for objects declared a filament).
        channel: Panoptic segmentations only: the channel ("label" or "instance") to write to MRC, TIFF or EM.
            Without one, each channel goes to its own file (``<name>_label``, ``<name>_instance``).
        polarity_from_filaments: STAR only: take the filaments' polarity from Filaments (see ``export_picks``).
        filaments_uri: STAR only: the Filaments source; default: the picks' own URI.
        tomo_type: STAR only: type of the copick tomogram whose shape defines each run's center. Default: the first
            tomogram at ``voxel_spacing``.
        coordinates: STAR only: ``"auto"`` (centered coordinates and/or rlnCoordinateX/Y/Z in tilt-series pixels,
            whatever is known) or ``"centered"`` (centered coordinates only; a run without a center is an error).

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

            # Look up tomogram index for this run
            tomogram_index = 1  # default
            if run_to_index and run.name in run_to_index:
                tomogram_index = run_to_index[run.name]

            for picks in picks_list:
                # Determine output filename (flat structure: run_object_user_session.ext)
                filename = f"{run.name}_{picks.pickable_object_name}_{picks.user_id}_{picks.session_id}"
                ext = {"em": ".em", "star": ".star", "dynamo": ".tbl", "csv": ".csv"}.get(output_format, ".csv")
                output_path = os.path.join(output_dir, filename + ext)

                export_picks(
                    picks,
                    output_path,
                    output_format,
                    voxel_spacing=voxel_spacing,
                    include_optics=include_optics,
                    run_name=run.name,
                    tomogram_index=tomogram_index,
                    log=log,
                    tilt_series_pixel_size=tilt_series_pixel_size,
                    tomograms_star=tomograms_star,
                    filament_columns=filament_columns,
                    polarity_from_filaments=polarity_from_filaments,
                    filaments_uri=filaments_uri,
                    tomo_type=tomo_type,
                    coordinates=coordinates,
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
                # A panoptic segmentation goes to MRC, TIFF or EM one file per channel, unless one is chosen.
                channels = [None]
                if seg.is_panoptic and output_format != "zarr":
                    channels = [channel] if channel else list(PANOPTIC_CHANNELS)
                for seg_channel in channels:
                    suffix = f"_{seg_channel}" if seg_channel else ""
                    output_path = os.path.join(run_output_dir, seg.directory, filename + suffix + ext)

                    export_segmentation(
                        seg,
                        output_path,
                        output_format,
                        level=level,
                        compression=compression,
                        log=log,
                        channel=seg_channel,
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
    run_to_index: Optional[Dict[str, int]] = None,
    n_workers: int = 8,
    log: bool = False,
    tilt_series_pixel_size: Optional[float] = None,
    tomograms_star: Optional[str] = None,
    filament_columns: str = "auto",
    channel: Optional[str] = None,
    polarity_from_filaments: bool = True,
    filaments_uri: Optional[str] = None,
    tomo_type: Optional[str] = None,
    coordinates: str = "auto",
) -> List[str]:
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
        run_to_index: Optional mapping from run name to tomogram index for EM/Dynamo.
        n_workers: Number of parallel workers.
        log: Log operations.
        tilt_series_pixel_size: STAR only: tilt-series pixel size in Angstrom.
        tomograms_star: STAR only: RELION tomograms.star with the runs' tomograms.
        filament_columns: STAR only: "on", "off", or "auto" (filament columns for objects declared a filament).
        channel: Panoptic segmentations only: the channel ("label" or "instance") to write to MRC, TIFF or EM.
        polarity_from_filaments: STAR only: take the filaments' polarity from Filaments (see ``export_picks``).
        filaments_uri: STAR only: the Filaments source; default: the picks' own URI.
        tomo_type: STAR only: type of the copick tomogram whose shape defines each run's center. Default: the first
            tomogram at ``voxel_spacing``.
        coordinates: STAR only: ``"auto"`` (centered coordinates and/or rlnCoordinateX/Y/Z in tilt-series pixels,
            whatever is known) or ``"centered"`` (centered coordinates only; a run without a center is an error).

    Returns:
        The errors, one message per failed export (empty if there were none).
    """
    import copick
    from copick.ops.run import map_runs

    _check_polarity_source(polarity_from_filaments, filaments_uri)
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
            "run_to_index": run_to_index,
            "log": log,
            "tilt_series_pixel_size": tilt_series_pixel_size,
            "tomograms_star": tomograms_star,
            "filament_columns": filament_columns,
            "channel": channel,
            "polarity_from_filaments": polarity_from_filaments,
            "filaments_uri": filaments_uri,
            "tomo_type": tomo_type,
            "coordinates": coordinates,
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

    return all_errors
