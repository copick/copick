"""Export a copick project as a CETS ``Dataset`` document.

copick stores CETS-shaped metadata with each tilt series, alignment and tomogram (see ``copick.util.cets``). This
module assembles them into one CETS ``Dataset`` (one ``Region`` per run), for tools that read CETS. Identifiers are
prefixed with the run name, so they are unique across runs. Data CETS has no field for (copick extensions, alignment
identifiers, the reference volume of an alignment, tomogram links) is written to a companion file next to it.
"""

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

from copick.models import CopickAlignment, CopickRoot, CopickRun, CopickTiltSeries, CopickTomogram
from copick.util.cets import (
    CETS_TARGET,
    COPICK_ATTRS_KEY,
    section_to_projection_alignment,
    tilt_series_cets_id,
    tilt_series_to_attrs,
    volume_frame,
)
from copick.util.log import get_logger

logger = get_logger(__name__)

#: Schema of the companion file.
COMPANION_SCHEMA = "copick-cets-companion/1"


def _schema_path() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "cets" / CETS_TARGET["commit"] / "Dataset.schema.json"


def _url(fs: Any, path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    from copick.ops.croissant import _absolute_url

    return _absolute_url(fs, path)


def _tilt_series_url(ts: CopickTiltSeries) -> Optional[str]:
    portal_path = getattr(ts.meta, "portal_tiltseries_path", None)
    if portal_path and getattr(ts, "read_only", False):
        return portal_path
    if getattr(ts, "read_only", False) and getattr(ts, "static_path", None):
        return _url(getattr(ts, "fs_static", None) or ts.run.fs_static, ts.static_path)
    return _url(getattr(ts, "fs_overlay", None) or ts.run.fs_overlay, getattr(ts, "overlay_path", None))


def _tomogram_url(tomogram: CopickTomogram) -> Optional[str]:
    portal_path = getattr(tomogram.meta, "portal_tomo_path", None)
    if portal_path and getattr(tomogram, "read_only", False):
        return portal_path
    if getattr(tomogram, "read_only", False):
        return _url(tomogram.fs_static, tomogram.static_path)
    return _url(tomogram.fs_overlay, tomogram.overlay_path)


def _tomogram_size(tomogram: CopickTomogram) -> Optional[Tuple[int, int, int]]:
    """Size ``(x, y, z)`` of a tomogram in voxels, from portal metadata if it has it (no store access)."""
    portal = getattr(getattr(tomogram.meta, "portal_metadata", None), "portal_metadata", None)
    if portal is not None and getattr(tomogram, "read_only", False):
        sizes = (portal.size_x, portal.size_y, portal.size_z)
        if all(sizes):
            return tuple(int(n) for n in sizes)
    shape = tomogram.shape
    return None if shape is None else tuple(int(n) for n in reversed(shape))


def _run_region(
    run: CopickRun,
    include_tomograms: bool,
    with_paths: bool,
    dataset: Dict[str, List[Dict[str, Any]]],
    companion: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    prefix = f"{run.name}/"
    region: Dict[str, Any] = {"id": run.name, "tilt_series": [], "alignments": [], "tomograms": []}
    exported_tilt_series = set()

    for ts in run.tilt_series:
        metadata = ts.metadata
        if metadata is None:
            continue
        ts_id = prefix + ts.cets_id
        block = tilt_series_to_attrs(ts_id, metadata)[COPICK_ATTRS_KEY]
        tilt_series = dict(block["tilt_series"])
        if with_paths and (url := _tilt_series_url(ts)):
            tilt_series["path"] = url
        region["tilt_series"].append(tilt_series)
        dataset["instruments"].append(block["instrument"])
        dataset["acquisition_sessions"].append(block["acquisition_session"])
        companion["tilt_series"][ts_id] = block["extensions"]
        exported_tilt_series.add(ts_id)

    for alignment in run.alignments:
        _add_alignment(run, alignment, prefix, region, companion)

    if include_tomograms:
        for voxel_spacing in run.voxel_spacings:
            for tomogram in voxel_spacing.tomograms:
                _add_tomogram(tomogram, prefix, exported_tilt_series, with_paths, region, companion)

    return region


def _add_alignment(
    run: CopickRun,
    alignment: CopickAlignment,
    prefix: str,
    region: Dict[str, Any],
    companion: Dict[str, Dict[str, Any]],
) -> None:
    from copick.util.cets import alignment_to_document

    file = alignment.file
    if file.tilt_series is None:
        logger.warning(f"Run {run.name}: alignment {alignment.name} aligns no known tilt series; it is not exported.")
        return
    ts_id = prefix + tilt_series_cets_id(file.tilt_series, file.tilt_series_portal_id)
    region["alignments"].append(
        {
            "tilt_series_id": ts_id,
            "projection_alignments": [section_to_projection_alignment(s, ts_id, alignment.name) for s in file.sections],
        },
    )
    document = alignment_to_document(file)
    companion["alignments"][prefix + alignment.name] = {
        "position": len(region["alignments"]) - 1,
        "tilt_series_id": ts_id,
        "tomograms": [prefix + t for t in file.linked_tomograms],
        "extensions": document["extensions"],
    }


def _add_tomogram(
    tomogram: CopickTomogram,
    prefix: str,
    exported_tilt_series: set,
    with_paths: bool,
    region: Dict[str, Any],
    companion: Dict[str, Dict[str, Any]],
) -> None:
    tomo_id = prefix + tomogram.link_id
    entry: Dict[str, Any] = {"id": tomo_id}
    if with_paths and (url := _tomogram_url(tomogram)):
        entry["path"] = url
    size = _tomogram_size(tomogram)
    if size is not None:
        entry["width"], entry["height"], entry["depth"] = size
        entry["coordinate_systems"], entry["coordinate_transformations"] = volume_frame(
            size,
            tomogram.voxel_spacing.voxel_size,
        )

    link = tomogram.alignment_link
    if link is not None:
        if link.tilt_series is not None:
            ts_id = prefix + tilt_series_cets_id(link.tilt_series, link.tilt_series_portal_id)
            if ts_id in exported_tilt_series:
                entry["tilt_series_id"] = ts_id
        companion["tomograms"][tomo_id] = {
            "alignment_id": None if link.alignment is None else prefix + link.alignment,
            "reference_offset": None if link.reference_offset is None else list(link.reference_offset),
            "link_source": link.source,
        }
    region["tomograms"].append(entry)


def _validate(document: Dict[str, Any]) -> None:
    try:
        import jsonschema
    except ImportError:
        logger.warning("jsonschema is not installed (pip install 'copick[cets]'); the export is not validated.")
    else:
        schema = json.loads(_schema_path().read_text())
        jsonschema.Draft202012Validator(schema).validate(document)
    try:
        from cets_data_model.models.models import Dataset
    except ImportError:
        return
    Dataset.model_validate(document)


def export_cets(
    root: CopickRoot,
    output: Union[str, Path],
    runs: Optional[Iterable[str]] = None,
    include_tomograms: bool = True,
    with_paths: bool = True,
    validate: bool = True,
    companion: bool = True,
    name: Optional[str] = None,
) -> Path:
    """Export a copick project as a CETS ``Dataset`` JSON document.

    Each run becomes a ``Region`` holding its tilt series (with per-image acquisition data and CTF), its alignments
    (one ``ProjectionAlignment`` per aligned section) and, optionally, its tomograms (with their frames and the
    ``tilt_series_id`` they were reconstructed from). ``Instrument`` and ``AcquisitionSession`` objects are collected
    at the dataset level. Identifiers are prefixed with the run name.

    The companion file ``<output>.copick-companion.json`` holds what CETS has no field for: copick's extensions of
    each tilt series, each alignment's name, status, type, reference volume and source (by position in its region),
    and the alignment each tomogram was reconstructed with.

    Args:
        root: The copick project.
        output: Path of the JSON document to write.
        runs: Names of the runs to export. Default: all.
        include_tomograms: Whether to export the runs' tomograms.
        with_paths: Whether to record the URL of each tilt series and tomogram store.
        validate: Whether to validate the document against the targeted CETS schema (needs ``jsonschema``) and, if
            ``cets_data_model`` is installed, with its models.
        companion: Whether to write the companion file.
        name: Name of the dataset. Default: the project's name.

    Returns:
        Path: The path of the written document.
    """
    output = Path(output)
    selected = None if runs is None else set(runs)
    dataset: Dict[str, Any] = {
        "name": name or root.config.name or "copick",
        "instruments": [],
        "acquisition_sessions": [],
        "regions": [],
    }
    side: Dict[str, Dict[str, Any]] = {"tilt_series": {}, "alignments": {}, "tomograms": {}}

    for run in root.runs:
        if selected is not None and run.name not in selected:
            continue
        dataset["regions"].append(_run_region(run, include_tomograms, with_paths, dataset, side))

    if validate:
        _validate(dataset)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(dataset, indent=1) + "\n")
    if companion:
        companion_path = output.with_name(output.name + ".copick-companion.json")
        companion_path.write_text(
            json.dumps(
                {"schema": COMPANION_SCHEMA, "cets_target": dict(CETS_TARGET), "dataset": output.name, **side},
                indent=1,
            )
            + "\n",
        )
    logger.info(f"Wrote CETS dataset with {len(dataset['regions'])} regions to {output}")
    return output
