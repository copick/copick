"""Export a copick project to an mlcroissant manifest + CSV sidecars.

Writes ``<project_root>/Croissant/`` with:
    metadata.json
    runs.csv / voxel_spacings.csv / tomograms.csv / features.csv /
    picks.csv / meshes.csv / segmentations.csv / objects.csv

The exporter never modifies data files under ``ExperimentRuns/`` or ``Objects/``.
Zarr stores stay as directories; per-file sha256 is computed for picks and meshes.
"""

from __future__ import annotations

import csv
import datetime
import hashlib
import io
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from fsspec import AbstractFileSystem

from copick.impl.mlcroissant import (
    CROISSANT_CONTEXT,
    CSV_SCHEMA,
    RECORDSET_ORDER,
    _fs_for_url,
)
from copick.models import CopickRoot
from copick.util.log import get_logger
from copick.util.uri import resolve_copick_objects

logger = get_logger(__name__)


CONFORMS_TO = "http://mlcommons.org/croissant/1.1"

# Canonical S3 base URL for the CZ cryoET Data Portal public bucket. Portal URLs
# are of the form ``s3://cryoet-data-portal-public/<dataset_id>/...``.
CDP_PORTAL_BASE_URL = "s3://cryoet-data-portal-public/"


@dataclass
class _ExportFilters:
    """Per-artifact-type subset filters + reshape transforms for
    :func:`export_croissant` and :func:`append_croissant`.

    ``None`` means "include everything of this type" (no filter) for subset
    lists, and "no transform" for maps/templates.
    """

    # Subset filters (URI- or name-based)
    runs: Optional[List[str]] = None
    tomograms: Optional[List[str]] = None
    features: Optional[List[str]] = None
    picks: Optional[List[str]] = None
    meshes: Optional[List[str]] = None
    segmentations: Optional[List[str]] = None
    objects: Optional[List[str]] = None

    # Reshape transforms (applied at CSV emission time)
    tomo_type_map: Optional[Dict[str, str]] = None
    object_name_map: Optional[Dict[str, str]] = None
    session_id_template: Optional[str] = None

    # CDP metadata filters (applied via CDP accessors; None for non-CDP sources)
    picks_portal_meta: Optional[Dict[str, Any]] = None
    picks_author: Optional[List[str]] = None
    segmentations_portal_meta: Optional[Dict[str, Any]] = None
    segmentations_author: Optional[List[str]] = None
    tomograms_portal_meta: Optional[Dict[str, Any]] = None
    tomograms_author: Optional[List[str]] = None


CDP_ONLY_FILTER_ATTRS = (
    "session_id_template",
    "picks_portal_meta",
    "picks_author",
    "segmentations_portal_meta",
    "segmentations_author",
    "tomograms_portal_meta",
    "tomograms_author",
)


def _validate_filters_against_source(filters: _ExportFilters, source_type: str) -> None:
    """Raise ``ValueError`` when CDP-only filter/transform flags are set on a
    non-CDP source.
    """
    if source_type == "cryoet_data_portal":
        return
    bad = [name for name in CDP_ONLY_FILTER_ATTRS if getattr(filters, name)]
    if bad:
        raise ValueError(
            "The following export options require a CryoET Data Portal source "
            f"(config_type='cryoet_data_portal'): {', '.join(sorted(bad))}. "
            "Source is '" + source_type + "'.",
        )


def _remap(name: Optional[str], mapping: Optional[Dict[str, str]]) -> Optional[str]:
    """Return ``mapping[name]`` if present, else ``name`` unchanged."""
    if name is None or not mapping:
        return name
    return mapping.get(name, name)


def _resolve_session_id(
    template: Optional[str],
    artifact,
    fallback: str,
) -> str:
    """Resolve a ``session_id_template`` against a CDP pick/segmentation.

    ``artifact`` is expected to have ``.meta.portal_metadata.portal_annotation``
    (a pydantic ``_PortalAnnotation`` instance) and
    ``.meta.portal_metadata.portal_author_names`` (a list of author name
    strings). On any error (missing fields, non-CDP source) returns
    ``fallback`` unchanged.

    The resolved string is sanitized via
    :func:`copick.util.escape.sanitize_name` so it's always a valid copick
    session_id.
    """
    if not template:
        return fallback
    try:
        from copick.util.escape import sanitize_name

        portal_meta = getattr(artifact.meta, "portal_metadata", None)
        portal_ann = getattr(portal_meta, "portal_annotation", None) if portal_meta else None
        if portal_ann is None:
            return fallback
        ns: Dict[str, Any] = {}
        # Copy all scalar pydantic fields to the format namespace.
        for field_name in portal_ann.model_fields:
            val = getattr(portal_ann, field_name, None)
            ns[field_name] = "" if val is None else val
        # Author-related shortcuts.
        authors = getattr(portal_meta, "portal_author_names", None) or []
        ns["author"] = authors[0] if authors else ""
        ns["authors"] = ",".join(authors)
        # The original session_id fallback (annotation_file_id).
        ns.setdefault("annotation_file_id", fallback)

        # Default any missing format placeholder to "" so sparse portal
        # records don't raise KeyError.
        class _EmptyStrDefault(dict):
            def __missing__(self, key):  # noqa: D401
                return ""

        rendered = template.format_map(_EmptyStrDefault(ns))
        sanitized = sanitize_name(rendered)
        return sanitized or fallback
    except Exception:
        return fallback


def _resolve_allowed_keys(
    uri_list: Optional[List[str]],
    root: CopickRoot,
    object_type: str,
    run_name: str,
    key_fn,
) -> Optional[Set[Tuple]]:
    """Resolve a list of URIs scoped to one run and return the set of key tuples.

    Returns ``None`` when ``uri_list`` is ``None`` (the "no filter" sentinel).
    """
    if uri_list is None:
        return None
    allowed: Set[Tuple] = set()
    for uri in uri_list:
        for obj in resolve_copick_objects(uri, root, object_type, run_name=run_name):
            allowed.add(key_fn(obj))
    return allowed


def _strip_proto(url: str) -> str:
    """Strip ``file://`` prefix if present."""
    if url.startswith("file://"):
        return url[len("file://") :]
    return url


def _relpath(base: str, target: str) -> str:
    """Return ``target`` expressed relative to ``base``, using URL-style forward slashes."""
    base = _strip_proto(base).rstrip("/")
    target = _strip_proto(target).rstrip("/")
    if not base:
        return target
    if target == base:
        return ""
    if target.startswith(base + "/"):
        return target[len(base) + 1 :]
    # Fall back to absolute URL if target is outside base
    return target


def _sha256_file(fs: AbstractFileSystem, path: str) -> str:
    h = hashlib.sha256()
    with fs.open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _serialize_csv(recordset_id: str, rows: List[Dict[str, Any]]) -> bytes:
    schema = CSV_SCHEMA[recordset_id]
    columns = schema["columns"]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        out = {}
        for col in columns:
            val = row.get(col)
            if isinstance(val, bool):
                out[col] = "true" if val else "false"
            elif val is None:
                out[col] = ""
            else:
                out[col] = val
        writer.writerow(out)
    return buf.getvalue().encode("utf-8")


def _build_field_list(recordset_id: str) -> List[Dict[str, Any]]:
    schema = CSV_SCHEMA[recordset_id]
    fields = []
    for col in schema["columns"]:
        fields.append(
            {
                "@type": "cr:Field",
                "@id": f"{recordset_id}/{col}",
                "dataType": schema["types"][col],
                "source": {
                    "fileObject": {"@id": schema["file_object_id"]},
                    "extract": {"column": col},
                },
            },
        )
    return fields


def export_croissant(
    root: CopickRoot,
    project_root: str,
    *,
    base_url: Optional[str] = None,
    dataset_name: Optional[str] = None,
    description: Optional[str] = None,
    license: Optional[str] = None,
    cite_as: Optional[str] = None,
    date_published: Optional[str] = None,
    validate: bool = True,
    compute_file_sha256: bool = True,
    force: bool = False,
    runs: Optional[Iterable[str]] = None,
    tomograms: Optional[Iterable[str]] = None,
    features: Optional[Iterable[str]] = None,
    picks: Optional[Iterable[str]] = None,
    meshes: Optional[Iterable[str]] = None,
    segmentations: Optional[Iterable[str]] = None,
    objects: Optional[Iterable[str]] = None,
    tomo_type_map: Optional[Dict[str, str]] = None,
    object_name_map: Optional[Dict[str, str]] = None,
    session_id_template: Optional[str] = None,
    picks_portal_meta: Optional[Dict[str, Any]] = None,
    picks_author: Optional[Iterable[str]] = None,
    segmentations_portal_meta: Optional[Dict[str, Any]] = None,
    segmentations_author: Optional[Iterable[str]] = None,
    tomograms_portal_meta: Optional[Dict[str, Any]] = None,
    tomograms_author: Optional[Iterable[str]] = None,
) -> str:
    """Export ``root`` to ``<project_root>/Croissant/``.

    Args:
        root: A loaded copick project (filesystem, CDP, or mlcroissant source).
        project_root: Absolute path / URL of the copick project root. The
            exporter writes ``<project_root>/Croissant/metadata.json`` + CSVs.
        base_url: Required for filesystem sources; absolute URL that resolves
            to ``project_root`` at consumer-read time. Ignored for CDP sources
            (common portal-URL prefix is used instead).
        dataset_name: Dataset title (defaults to ``root.config.name``).
        description: Dataset description.
        license: Dataset license string.
        cite_as: Citation.
        date_published: ISO date string. Defaults to today.
        validate: Run the Croissant validator after assembly. Raises on errors.
        compute_file_sha256: Compute sha256 per picks JSON / mesh GLB (O(N) reads).
        runs: Optional iterable of run names to include. If ``None`` (default),
            every run is exported. Names that don't exist in ``root`` are
            silently skipped.
        tomograms: Optional iterable of copick URIs (e.g. ``"wbp@10.0"``) to
            filter tomograms. Each URI is resolved via
            :func:`copick.util.uri.resolve_copick_objects` and the results are
            unioned. ``None`` means no filter.
        features: Optional iterable of copick URIs (e.g. ``"wbp@10.0:sobel"``).
        picks: Optional iterable of copick URIs (e.g. ``"ribosome:*/*"``).
        meshes: Optional iterable of copick URIs (e.g. ``"ribosome:*/*"``).
        segmentations: Optional iterable of copick URIs (e.g.
            ``"membrane:*/*@10.0"``).
        objects: Optional iterable of pickable-object names to include in the
            object density map CSV. ``copick:config.pickable_objects`` is
            unaffected.
        force: When ``True``, overwrite an existing ``Croissant/metadata.json``
            under ``project_root``. When ``False`` (default) and a manifest
            already exists, raise ``FileExistsError`` instead of clobbering it.
        tomo_type_map: Optional ``{src_tomo_type: dst_tomo_type}`` remap
            applied to ``tomograms.csv`` / ``features.csv`` ``tomo_type``
            columns at emission time. Universally applicable.
        object_name_map: Optional ``{src: dst}`` remap applied to
            ``object_name`` in picks / meshes / segmentations, the objects.csv
            ``name`` column, and ``copick:config.pickable_objects[].name``.
            Renamed pickable objects carry the original portal name in
            ``metadata["portal_original_name"]``. Universally applicable.
        session_id_template: Python ``str.format`` template for synthesizing
            picks / segmentations ``session_id`` values from CDP annotation
            metadata. Placeholders are any scalar field of ``_PortalAnnotation``
            plus ``{author}``, ``{authors}``, ``{annotation_file_id}``. CDP-only;
            raises on non-CDP sources.
        picks_portal_meta: Dict passed to
            ``run.get_picks(portal_meta_query=...)``; CDP-only.
        picks_author: List passed to
            ``run.get_picks(portal_author_query=...)``; CDP-only.
        segmentations_portal_meta: ditto for segmentations; CDP-only.
        segmentations_author: ditto for segmentations; CDP-only.
        tomograms_portal_meta: ditto for tomograms; CDP-only.
        tomograms_author: ditto for tomograms; CDP-only.

    Returns:
        The path to the written metadata.json.
    """
    filters = _ExportFilters(
        runs=list(runs) if runs is not None else None,
        tomograms=list(tomograms) if tomograms is not None else None,
        features=list(features) if features is not None else None,
        picks=list(picks) if picks is not None else None,
        meshes=list(meshes) if meshes is not None else None,
        segmentations=list(segmentations) if segmentations is not None else None,
        objects=list(objects) if objects is not None else None,
        tomo_type_map=dict(tomo_type_map) if tomo_type_map else None,
        object_name_map=dict(object_name_map) if object_name_map else None,
        session_id_template=session_id_template or None,
        picks_portal_meta=dict(picks_portal_meta) if picks_portal_meta else None,
        picks_author=list(picks_author) if picks_author else None,
        segmentations_portal_meta=dict(segmentations_portal_meta) if segmentations_portal_meta else None,
        segmentations_author=list(segmentations_author) if segmentations_author else None,
        tomograms_portal_meta=dict(tomograms_portal_meta) if tomograms_portal_meta else None,
        tomograms_author=list(tomograms_author) if tomograms_author else None,
    )

    source_type = getattr(root.config, "config_type", "filesystem")
    _validate_filters_against_source(filters, source_type)
    project_root_str = _strip_proto(project_root)
    croissant_dir = os.path.join(project_root_str, "Croissant")

    # Figure out fsspec filesystem for the Croissant directory
    croissant_fs, _ = _fs_for_url(croissant_dir)
    existing_metadata = os.path.join(croissant_dir, "metadata.json")
    if croissant_fs.exists(existing_metadata) and not force:
        raise FileExistsError(
            f"Croissant already exists at {existing_metadata}. Pass force=True "
            "(--force on the CLI) to overwrite, or use append_croissant(...) to "
            "merge additional rows in.",
        )
    if not croissant_fs.exists(croissant_dir):
        croissant_fs.makedirs(croissant_dir, exist_ok=True)

    # Detect URL prefix by source
    if source_type == "cryoet_data_portal":
        copick_base_url = CDP_PORTAL_BASE_URL
    else:
        if base_url is None:
            raise ValueError(
                "base_url is required for filesystem-backed sources. "
                "Pass the absolute URL that will resolve to `project_root` at read time.",
            )
        copick_base_url = base_url

    # Walk the project and build per-type row lists
    rows = _walk_project(
        root,
        copick_base_url,
        source_type=source_type,
        compute_file_sha256=compute_file_sha256,
        filters=filters,
    )

    # Write CSVs
    csv_bytes: Dict[str, bytes] = {}
    for rs_id in RECORDSET_ORDER:
        schema = CSV_SCHEMA[rs_id]
        data = _serialize_csv(rs_id, rows[rs_id])
        csv_path = os.path.join(croissant_dir, schema["csv_name"])
        with croissant_fs.open(csv_path, "wb") as f:
            f.write(data)
        csv_bytes[rs_id] = data

    # Build Croissant JSON-LD
    doc = _build_croissant_doc(
        root=root,
        copick_base_url=copick_base_url,
        csv_bytes=csv_bytes,
        dataset_name=dataset_name,
        description=description,
        license=license,
        cite_as=cite_as,
        date_published=date_published,
        object_name_map=filters.object_name_map,
    )

    metadata_path = os.path.join(croissant_dir, "metadata.json")
    metadata_bytes = json.dumps(doc, indent=2).encode("utf-8")
    with croissant_fs.open(metadata_path, "wb") as f:
        f.write(metadata_bytes)

    if validate:
        _validate_metadata(metadata_path, doc, croissant_dir)

    logger.info("Wrote Croissant to %s", metadata_path)
    return metadata_path


# -----------------------------------------------------------------------------
# Project walk — emit rows per type
# -----------------------------------------------------------------------------


def _portal_annotation_fields(artifact) -> Dict[str, Any]:
    """Return {portal_object_name, portal_annotation_id, portal_annotation_file_id}
    for a CDP pick/segmentation. All values are string-typed (empty if absent)
    so they serialize cleanly into the CSV.
    """
    out = {
        "portal_object_name": "",
        "portal_annotation_id": "",
        "portal_annotation_file_id": "",
    }
    portal_meta = getattr(artifact.meta, "portal_metadata", None)
    if portal_meta is None:
        return out
    portal_ann = getattr(portal_meta, "portal_annotation", None)
    if portal_ann is not None:
        out["portal_object_name"] = str(getattr(portal_ann, "object_name", "") or "")
        ann_id = getattr(portal_ann, "id", None)
        out["portal_annotation_id"] = "" if ann_id is None else str(ann_id)
    portal_ann_file = getattr(portal_meta, "portal_annotation_file", None)
    if portal_ann_file is not None:
        ann_file_id = getattr(portal_ann_file, "id", None)
        out["portal_annotation_file_id"] = "" if ann_file_id is None else str(ann_file_id)
    return out


def _portal_tomogram_fields(tomo) -> Dict[str, Any]:
    """Return {portal_tomogram_id} for a CDP tomogram. Empty if non-CDP."""
    out = {"portal_tomogram_id": ""}
    tid = getattr(tomo.meta, "portal_tomo_id", None)
    if tid is not None:
        out["portal_tomogram_id"] = str(tid)
    return out


def _portal_run_id(run) -> str:
    """Return the portal run id for a CDP run, or empty string."""
    rid = getattr(run.meta, "portal_run_id", None)
    return "" if rid is None else str(rid)


def _iter_tomograms_filtered(
    run,
    is_cdp: bool,
    portal_meta: Optional[Dict[str, Any]],
    portal_author: Optional[List[str]],
):
    """Yield (vs, tomo) pairs from a run, honouring CDP portal-meta filters.

    Applies CDP's ``get_tomograms(portal_meta_query=..., portal_author_query=...)``
    path when any portal filter is set, else iterates natively.
    """
    if is_cdp and (portal_meta or portal_author):
        for vs in run.voxel_spacings:
            for tomo in vs.get_tomograms(
                portal_meta_query=portal_meta or None,
                portal_author_query=portal_author or None,
            ):
                yield vs, tomo
    else:
        for vs in run.voxel_spacings:
            for tomo in vs.tomograms:
                yield vs, tomo


def _iter_picks_filtered(run, is_cdp, portal_meta, portal_author):
    if is_cdp and (portal_meta or portal_author):
        yield from run.get_picks(
            portal_meta_query=portal_meta or None,
            portal_author_query=portal_author or None,
        )
    else:
        yield from run.picks


def _iter_segmentations_filtered(run, is_cdp, portal_meta, portal_author):
    if is_cdp and (portal_meta or portal_author):
        yield from run.get_segmentations(
            portal_meta_query=portal_meta or None,
            portal_author_query=portal_author or None,
        )
    else:
        yield from run.segmentations


def _walk_project(
    root: CopickRoot,
    copick_base_url: str,
    *,
    source_type: str,
    compute_file_sha256: bool,
    filters: _ExportFilters,
) -> Dict[str, List[Dict[str, Any]]]:
    rows: Dict[str, List[Dict[str, Any]]] = {rs_id: [] for rs_id in RECORDSET_ORDER}
    is_cdp = source_type == "cryoet_data_portal"

    # Top-level run filter: restrict which runs we walk at all.
    all_runs = list(root.runs)
    if filters.runs is not None:
        allowed_run_names = set(filters.runs)
        runs_iter = [r for r in all_runs if r.name in allowed_run_names]
    else:
        runs_iter = all_runs

    for run in runs_iter:
        rows["copick/runs"].append(
            {"name": run.name, "portal_run_id": _portal_run_id(run) if is_cdp else ""},
        )

        # Resolve per-run allow-sets for URI-filtered artifact types.
        allowed_tomos = _resolve_allowed_keys(
            filters.tomograms,
            root,
            "tomogram",
            run.name,
            lambda t: (float(t.voxel_spacing.voxel_size), t.tomo_type),
        )
        allowed_feats = _resolve_allowed_keys(
            filters.features,
            root,
            "feature",
            run.name,
            lambda f: (
                float(f.tomogram.voxel_spacing.voxel_size),
                f.tomogram.tomo_type,
                f.feature_type,
            ),
        )
        allowed_picks = _resolve_allowed_keys(
            filters.picks,
            root,
            "picks",
            run.name,
            lambda p: (p.user_id, p.session_id, p.pickable_object_name),
        )
        allowed_meshes = _resolve_allowed_keys(
            filters.meshes,
            root,
            "mesh",
            run.name,
            lambda m: (m.user_id, m.session_id, m.pickable_object_name),
        )
        allowed_segs = _resolve_allowed_keys(
            filters.segmentations,
            root,
            "segmentation",
            run.name,
            lambda s: (
                float(s.voxel_size),
                s.user_id,
                s.session_id,
                s.name,
                bool(s.is_multilabel),
            ),
        )

        # Voxel spacings are derived: emit a VS row only when at least one
        # surviving tomogram / feature / segmentation sits at that (run, vs).
        vs_emitted: Set[float] = set()

        # --- Tomograms + features (honouring CDP portal-meta filters) ---
        # Group the pre-filtered tomograms by vs so we can iterate features
        # within the same structure as before.
        tomos_by_vs: Dict[float, List[Tuple[Any, Any]]] = {}
        for vs, tomo in _iter_tomograms_filtered(
            run,
            is_cdp,
            filters.tomograms_portal_meta,
            filters.tomograms_author,
        ):
            tomos_by_vs.setdefault(float(vs.voxel_size), []).append((vs, tomo))

        for vs_size in sorted(tomos_by_vs.keys()):
            for vs, tomo in tomos_by_vs[vs_size]:
                tomo_key = (vs_size, tomo.tomo_type)
                if allowed_tomos is not None and tomo_key not in allowed_tomos:
                    continue
                if vs_size not in vs_emitted:
                    vs_emitted.add(vs_size)
                    rows["copick/voxel_spacings"].append(
                        {"run": run.name, "voxel_size": vs_size},
                    )
                tomo_url = _tomo_url(run, vs, tomo, copick_base_url, is_cdp)
                original_tomo_type = tomo.tomo_type
                remapped_tomo_type = _remap(original_tomo_type, filters.tomo_type_map) or original_tomo_type
                tomo_row = {
                    "run": run.name,
                    "voxel_size": vs_size,
                    "tomo_type": remapped_tomo_type,
                    "url": tomo_url,
                    "portal_tomo_type": original_tomo_type
                    if (is_cdp and remapped_tomo_type != original_tomo_type)
                    else "",
                }
                if is_cdp:
                    tomo_row.update(_portal_tomogram_fields(tomo))
                rows["copick/tomograms"].append(tomo_row)

                for feat in tomo.features:
                    feat_key = (vs_size, tomo.tomo_type, feat.feature_type)
                    if allowed_feats is not None and feat_key not in allowed_feats:
                        continue
                    if vs_size not in vs_emitted:
                        vs_emitted.add(vs_size)
                        rows["copick/voxel_spacings"].append(
                            {"run": run.name, "voxel_size": vs_size},
                        )
                    feat_url = _feat_url(run, vs, tomo, feat, copick_base_url, is_cdp)
                    rows["copick/features"].append(
                        {
                            "run": run.name,
                            "voxel_size": vs_size,
                            "tomo_type": remapped_tomo_type,
                            "feature_type": feat.feature_type,
                            "url": feat_url,
                        },
                    )

        # --- Picks (honouring CDP portal-meta filters + remap + session template) ---
        for pick in _iter_picks_filtered(
            run,
            is_cdp,
            filters.picks_portal_meta,
            filters.picks_author,
        ):
            key = (pick.user_id, pick.session_id, pick.pickable_object_name)
            if allowed_picks is not None and key not in allowed_picks:
                continue
            pick_url, sha = _pick_url_and_sha(run, pick, copick_base_url, is_cdp, compute_file_sha256)
            original_object_name = pick.pickable_object_name
            original_session_id = pick.session_id
            remapped_object_name = _remap(original_object_name, filters.object_name_map) or original_object_name
            resolved_session_id = _resolve_session_id(
                filters.session_id_template,
                pick,
                original_session_id,
            )
            pick_row = {
                "run": run.name,
                "user_id": pick.user_id,
                "session_id": resolved_session_id,
                "object_name": remapped_object_name,
                "url": pick_url,
                "sha256": sha,
                "portal_object_name": original_object_name
                if (is_cdp and remapped_object_name != original_object_name)
                else "",
                "portal_session_id": original_session_id
                if (is_cdp and resolved_session_id != original_session_id)
                else "",
            }
            if is_cdp:
                pick_row.update(_portal_annotation_fields(pick))
            rows["copick/picks"].append(pick_row)

        for mesh in run.meshes:
            key = (mesh.user_id, mesh.session_id, mesh.pickable_object_name)
            if allowed_meshes is not None and key not in allowed_meshes:
                continue
            mesh_url, sha = _mesh_url_and_sha(run, mesh, copick_base_url, is_cdp, compute_file_sha256)
            original_object_name = mesh.pickable_object_name
            remapped_object_name = _remap(original_object_name, filters.object_name_map) or original_object_name
            rows["copick/meshes"].append(
                {
                    "run": run.name,
                    "user_id": mesh.user_id,
                    "session_id": mesh.session_id,
                    "object_name": remapped_object_name,
                    "url": mesh_url,
                    "sha256": sha,
                },
            )

        # --- Segmentations (honouring CDP portal-meta filters + remap + session template) ---
        for seg in _iter_segmentations_filtered(
            run,
            is_cdp,
            filters.segmentations_portal_meta,
            filters.segmentations_author,
        ):
            key = (
                float(seg.voxel_size),
                seg.user_id,
                seg.session_id,
                seg.name,
                bool(seg.is_multilabel),
            )
            if allowed_segs is not None and key not in allowed_segs:
                continue
            seg_vs = float(seg.voxel_size)
            if seg_vs not in vs_emitted:
                vs_emitted.add(seg_vs)
                rows["copick/voxel_spacings"].append(
                    {"run": run.name, "voxel_size": seg_vs},
                )
            seg_url = _seg_url(run, seg, copick_base_url, is_cdp)
            original_name = seg.name
            original_session_id = seg.session_id
            remapped_name = _remap(original_name, filters.object_name_map) or original_name
            resolved_session_id = _resolve_session_id(
                filters.session_id_template,
                seg,
                original_session_id,
            )
            seg_row = {
                "run": run.name,
                "voxel_size": seg_vs,
                "user_id": seg.user_id,
                "session_id": resolved_session_id,
                "name": remapped_name,
                "is_multilabel": bool(seg.is_multilabel),
                "url": seg_url,
                "portal_object_name": original_name if (is_cdp and remapped_name != original_name) else "",
                "portal_session_id": original_session_id
                if (is_cdp and resolved_session_id != original_session_id)
                else "",
            }
            if is_cdp:
                seg_row.update(_portal_annotation_fields(seg))
            rows["copick/segmentations"].append(seg_row)

    # Object density maps. The filter targets pickable-object names; the
    # ``copick:config.pickable_objects`` blob is NOT filtered here so picks/
    # meshes/segmentations referring to other objects stay internally
    # consistent (pickable-object-name remap for the embedded config happens
    # in ``_build_croissant_doc``).
    allowed_objects: Optional[Set[str]] = set(filters.objects) if filters.objects is not None else None
    for obj in root.pickable_objects:
        if not obj.is_particle:
            continue
        if allowed_objects is not None and obj.name not in allowed_objects:
            continue
        try:
            z = obj.zarr()
        except Exception:
            z = None
        if z is None:
            continue
        obj_url = _object_url(obj, copick_base_url, is_cdp)
        remapped_obj_name = _remap(obj.name, filters.object_name_map) or obj.name
        rows["copick/objects"].append({"name": remapped_obj_name, "url": obj_url})

    return rows


# -----------------------------------------------------------------------------
# URL helpers
# -----------------------------------------------------------------------------


def _get_artifact_url(artifact) -> Optional[str]:
    """Best-effort extraction of the absolute URL a copick artifact points at."""
    for attr in ("static_path", "path", "overlay_path"):
        url = getattr(artifact, attr, None)
        if url:
            return url
    return None


def _tomo_url(run, vs, tomo, base_url: str, is_cdp: bool) -> str:
    if is_cdp:
        url = _get_artifact_url(tomo)
        if url:
            rel = _relpath(base_url, url)
            return rel or url
    return f"ExperimentRuns/{run.name}/VoxelSpacing{vs.voxel_size:.3f}/{tomo.tomo_type}.zarr"


def _feat_url(run, vs, tomo, feat, base_url: str, is_cdp: bool) -> str:
    if is_cdp:
        url = _get_artifact_url(feat)
        if url:
            rel = _relpath(base_url, url)
            return rel or url
    return (
        f"ExperimentRuns/{run.name}/VoxelSpacing{vs.voxel_size:.3f}/"
        f"{tomo.tomo_type}_{feat.feature_type}_features.zarr"
    )


def _pick_url_and_sha(run, pick, base_url: str, is_cdp: bool, compute_sha: bool) -> tuple:
    if is_cdp:
        abs_url = getattr(pick, "path", None)
        rel_url = _relpath(base_url, abs_url) if abs_url else None
        rel = rel_url or abs_url or ""
    else:
        rel = f"ExperimentRuns/{run.name}/Picks/{pick.user_id}_{pick.session_id}_{pick.pickable_object_name}.json"

    sha = ""
    if compute_sha:
        try:
            fs = getattr(pick, "fs", None)
            abs_path = getattr(pick, "path", None)
            if fs is not None and abs_path and fs.exists(abs_path):
                sha = _sha256_file(fs, abs_path)
        except Exception as e:
            logger.warning("Could not compute sha256 for pick %s: %s", rel, e)
    return rel, sha


def _mesh_url_and_sha(run, mesh, base_url: str, is_cdp: bool, compute_sha: bool) -> tuple:
    if is_cdp:
        abs_url = getattr(mesh, "path", None)
        rel_url = _relpath(base_url, abs_url) if abs_url else None
        rel = rel_url or abs_url or ""
    else:
        rel = f"ExperimentRuns/{run.name}/Meshes/{mesh.user_id}_{mesh.session_id}_{mesh.pickable_object_name}.glb"

    sha = ""
    if compute_sha:
        try:
            fs = getattr(mesh, "fs", None)
            abs_path = getattr(mesh, "path", None)
            if fs is not None and abs_path and fs.exists(abs_path):
                sha = _sha256_file(fs, abs_path)
        except Exception as e:
            logger.warning("Could not compute sha256 for mesh %s: %s", rel, e)
    return rel, sha


def _seg_url(run, seg, base_url: str, is_cdp: bool) -> str:
    if is_cdp:
        url = _get_artifact_url(seg)
        if url:
            rel = _relpath(base_url, url)
            return rel or url
    if seg.is_multilabel:
        fname = f"{seg.voxel_size:.3f}_{seg.user_id}_{seg.session_id}_{seg.name}-multilabel.zarr"
    else:
        fname = f"{seg.voxel_size:.3f}_{seg.user_id}_{seg.session_id}_{seg.name}.zarr"
    return f"ExperimentRuns/{run.name}/Segmentations/{fname}"


def _object_url(obj, base_url: str, is_cdp: bool) -> str:
    if is_cdp:
        url = _get_artifact_url(obj)
        if url:
            rel = _relpath(base_url, url)
            return rel or url
    return f"Objects/{obj.name}.zarr"


# -----------------------------------------------------------------------------
# CDP source helpers
# -----------------------------------------------------------------------------


# -----------------------------------------------------------------------------
# Croissant JSON-LD assembly
# -----------------------------------------------------------------------------


def _build_croissant_doc(
    *,
    root: CopickRoot,
    copick_base_url: str,
    csv_bytes: Dict[str, bytes],
    dataset_name: Optional[str],
    description: Optional[str],
    license: Optional[str],
    cite_as: Optional[str],
    date_published: Optional[str],
    object_name_map: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    name = dataset_name or root.config.name or "copick-project"
    description = description or root.config.description or "Copick project exported as Croissant."
    cite_as = cite_as or ""
    license = license or "CC-BY-4.0"
    date_published = date_published or datetime.datetime.now(tz=datetime.timezone.utc).date().isoformat()

    # Build distribution entries (one FileObject per CSV)
    distribution = []
    for rs_id in RECORDSET_ORDER:
        schema = CSV_SCHEMA[rs_id]
        fo_id = schema["file_object_id"]
        csv_rel = f"Croissant/{schema['csv_name']}"
        content_url = _abs_csv_url(copick_base_url, csv_rel)
        distribution.append(
            {
                "@type": "cr:FileObject",
                "@id": fo_id,
                "name": fo_id,
                "contentUrl": content_url,
                "encodingFormat": "text/csv",
                "sha256": _sha256_bytes(csv_bytes[rs_id]),
            },
        )

    # Build recordSet entries (one per type)
    record_sets = []
    for rs_id in RECORDSET_ORDER:
        schema = CSV_SCHEMA[rs_id]
        record_sets.append(
            {
                "@type": "cr:RecordSet",
                "@id": rs_id,
                "name": schema["recordset_name"],
                "field": _build_field_list(rs_id),
            },
        )

    # Serialise copick:config (PickableObjects etc.)
    cfg = root.config
    pickable_objects_dumped = [po.model_dump() for po in cfg.pickable_objects]
    if object_name_map:
        for po in pickable_objects_dumped:
            src_name = po.get("name")
            if src_name in object_name_map:
                new_name = object_name_map[src_name]
                if new_name != src_name:
                    po["name"] = new_name
                    md = po.get("metadata") or {}
                    md.setdefault("portal_original_name", src_name)
                    po["metadata"] = md
    copick_config = {
        "name": cfg.name,
        "description": cfg.description,
        "version": cfg.version,
        "user_id": cfg.user_id,
        "session_id": cfg.session_id,
        "pickable_objects": pickable_objects_dumped,
    }

    doc = {
        "@context": dict(CROISSANT_CONTEXT),
        "@type": "sc:Dataset",
        "name": name,
        "description": description,
        "conformsTo": CONFORMS_TO,
        "version": cfg.version or "0.1.0",
        "license": license,
        "citeAs": cite_as or f"copick project {name}",
        "datePublished": date_published,
        "copick:baseUrl": copick_base_url,
        "copick:config": copick_config,
        "distribution": distribution,
        "recordSet": record_sets,
    }
    return doc


def _abs_csv_url(base_url: str, rel: str) -> str:
    if not base_url:
        return rel
    if base_url.endswith("/"):
        return base_url + rel
    return base_url + "/" + rel


# -----------------------------------------------------------------------------
# Append
# -----------------------------------------------------------------------------


def _source_base_url_for_root(source_root: CopickRoot) -> str:
    """Return the base URL that relative URL values in the walk are relative to."""
    source_type = getattr(source_root.config, "config_type", "filesystem")
    if source_type == "cryoet_data_portal":
        return CDP_PORTAL_BASE_URL
    if source_type == "mlcroissant":
        return getattr(source_root.index, "base_url", "") or ""
    cfg = source_root.config
    return getattr(cfg, "static_root", None) or getattr(cfg, "overlay_root", "") or ""


def _absolutize_row_urls(rows: Dict[str, List[Dict[str, Any]]], base_url: str) -> None:
    """Rewrite each ``url`` column in-place from relative-to-base into absolute.

    Rows coming out of :func:`_walk_project` contain relative paths against
    ``base_url``. When appending into a destination Croissant (which may have
    a different ``copick:baseUrl``), we promote everything to absolute so the
    destination CSV is self-sufficient.
    """
    from copick.impl.mlcroissant import _join_url

    if not base_url:
        return
    for rs_id, row_list in rows.items():
        schema = CSV_SCHEMA[rs_id]
        if "url" not in schema["columns"]:
            continue
        for row in row_list:
            url = row.get("url")
            if url:
                row["url"] = _join_url(base_url, url)


def _union_pickable_objects(
    dest_index,
    source_root: CopickRoot,
    object_name_map: Optional[Dict[str, str]],
) -> None:
    """Union ``source_root``'s pickable_objects into the destination's
    ``copick:config.pickable_objects`` block.

    When a source object's name collides with an existing destination entry,
    the destination wins (no overwrite); a warning is logged so the mismatch
    is visible.

    Applies ``object_name_map`` to source object names and records the original
    portal name in ``metadata["portal_original_name"]`` (idempotent).
    """
    import warnings

    cfg_block = dest_index.config_block
    if not isinstance(cfg_block, dict):
        return
    existing = cfg_block.setdefault("pickable_objects", [])
    existing_by_name = {po.get("name"): po for po in existing}

    for po in source_root.config.pickable_objects:
        po_dump = po.model_dump()
        src_name = po_dump.get("name")
        if object_name_map and src_name in object_name_map:
            new_name = object_name_map[src_name]
            if new_name != src_name:
                po_dump["name"] = new_name
                md = po_dump.get("metadata") or {}
                md.setdefault("portal_original_name", src_name)
                po_dump["metadata"] = md

        name = po_dump.get("name")
        if name in existing_by_name:
            dest_entry = existing_by_name[name]
            if dest_entry.get("label") != po_dump.get("label") or dest_entry.get("color") != po_dump.get("color"):
                warnings.warn(
                    f"Pickable object '{name}' already present in destination with "
                    "different attributes; destination wins.",
                    stacklevel=2,
                )
            continue
        existing.append(po_dump)
        existing_by_name[name] = po_dump

    cfg_block["pickable_objects"] = existing
    dest_index.doc["copick:config"] = cfg_block
    # Mark metadata.json dirty indirectly — committing any CSV flushes the doc.
    # Add all currently dirty recordsets plus a "runs" no-op so metadata.json
    # is rewritten even when no recordset is dirty.
    dest_index.mark_dirty("copick/runs")


def append_croissant(
    dest_metadata_path: str,
    source_root: CopickRoot,
    *,
    runs: Optional[Iterable[str]] = None,
    tomograms: Optional[Iterable[str]] = None,
    features: Optional[Iterable[str]] = None,
    picks: Optional[Iterable[str]] = None,
    meshes: Optional[Iterable[str]] = None,
    segmentations: Optional[Iterable[str]] = None,
    objects: Optional[Iterable[str]] = None,
    tomo_type_map: Optional[Dict[str, str]] = None,
    object_name_map: Optional[Dict[str, str]] = None,
    session_id_template: Optional[str] = None,
    picks_portal_meta: Optional[Dict[str, Any]] = None,
    picks_author: Optional[Iterable[str]] = None,
    segmentations_portal_meta: Optional[Dict[str, Any]] = None,
    segmentations_author: Optional[Iterable[str]] = None,
    tomograms_portal_meta: Optional[Dict[str, Any]] = None,
    tomograms_author: Optional[Iterable[str]] = None,
    compute_file_sha256: bool = True,
) -> str:
    """Union filtered rows from ``source_root`` into an existing Croissant.

    Opens the destination at ``dest_metadata_path`` in Mode A (writable
    ``copick:baseUrl``), walks ``source_root`` with the same filter/reshape
    kwargs as :func:`export_croissant`, and merges the resulting rows via
    :meth:`CroissantIndex.add_row` (replace-on-key-collision). URLs from the
    source are absolutized before being written to the destination CSVs, so
    appended rows remain resolvable regardless of the destination's base URL.

    The destination's top-level metadata (name, description, license, etc.) is
    preserved verbatim. ``copick:config.pickable_objects`` is unioned — new
    objects appended, existing ones kept as-is (with a warning on attribute
    drift).

    Args:
        dest_metadata_path: Absolute path / URL of the destination
            ``Croissant/metadata.json``. Must exist and be writable.
        source_root: A loaded copick project (filesystem, CDP, or mlcroissant).
        runs, tomograms, features, picks, meshes, segmentations, objects:
            Subset filters, same semantics as :func:`export_croissant`.
        tomo_type_map, object_name_map, session_id_template: Reshape transforms.
        picks_portal_meta, picks_author, segmentations_portal_meta,
        segmentations_author, tomograms_portal_meta, tomograms_author:
            CDP-only metadata filters.
        compute_file_sha256: Same as :func:`export_croissant`.

    Returns:
        The path to the destination ``metadata.json``.
    """
    from copick.impl.mlcroissant import CopickConfigMLCroissant, CopickRootMLC

    filters = _ExportFilters(
        runs=list(runs) if runs is not None else None,
        tomograms=list(tomograms) if tomograms is not None else None,
        features=list(features) if features is not None else None,
        picks=list(picks) if picks is not None else None,
        meshes=list(meshes) if meshes is not None else None,
        segmentations=list(segmentations) if segmentations is not None else None,
        objects=list(objects) if objects is not None else None,
        tomo_type_map=dict(tomo_type_map) if tomo_type_map else None,
        object_name_map=dict(object_name_map) if object_name_map else None,
        session_id_template=session_id_template or None,
        picks_portal_meta=dict(picks_portal_meta) if picks_portal_meta else None,
        picks_author=list(picks_author) if picks_author else None,
        segmentations_portal_meta=dict(segmentations_portal_meta) if segmentations_portal_meta else None,
        segmentations_author=list(segmentations_author) if segmentations_author else None,
        tomograms_portal_meta=dict(tomograms_portal_meta) if tomograms_portal_meta else None,
        tomograms_author=list(tomograms_author) if tomograms_author else None,
    )

    source_type = getattr(source_root.config, "config_type", "filesystem")
    _validate_filters_against_source(filters, source_type)

    # Open destination in Mode A
    dest_cfg = CopickConfigMLCroissant(croissant_url=dest_metadata_path)
    dest = CopickRootMLC(dest_cfg)
    if not dest.index._writable:
        raise PermissionError(
            f"Destination Croissant at {dest_metadata_path} is not writable. "
            "Append requires a Mode A (writable copick:baseUrl) destination.",
        )

    # Walk source rows using the source's native base URL so URL helpers
    # produce consistent relative paths, then absolutize for the destination.
    source_base_url = _source_base_url_for_root(source_root)
    rows = _walk_project(
        source_root,
        source_base_url,
        source_type=source_type,
        compute_file_sha256=compute_file_sha256,
        filters=filters,
    )
    _absolutize_row_urls(rows, source_base_url)

    # Merge rows + pickable_objects into the destination in one commit.
    with dest.batch():
        for rs_id in RECORDSET_ORDER:
            for row in rows[rs_id]:
                dest.index.add_row(rs_id, row)
        _union_pickable_objects(dest.index, source_root, filters.object_name_map)

    logger.info("Appended %s rows into %s", sum(len(v) for v in rows.values()), dest_metadata_path)
    return dest_metadata_path


# -----------------------------------------------------------------------------
# Validation
# -----------------------------------------------------------------------------


def _validate_metadata(metadata_path: str, doc: Dict[str, Any], croissant_dir: str) -> None:
    """Run mlcroissant's validator on the generated document.

    For validation we point distribution contentUrls at the local CSVs so that
    mlcroissant can resolve them without network access.
    """
    try:
        import copy

        import mlcroissant as mlc
    except ImportError as e:
        raise ImportError(
            "mlcroissant is required for export validation. Install with `pip install mlcroissant`.",
        ) from e

    local_doc = copy.deepcopy(doc)
    for entry in local_doc.get("distribution", []):
        if entry.get("@type") == "cr:FileObject":
            fo_id = entry.get("@id", "")
            for schema in CSV_SCHEMA.values():
                if schema["file_object_id"] == fo_id:
                    entry["contentUrl"] = os.path.join(croissant_dir, schema["csv_name"])
                    break
    try:
        ds = mlc.Dataset(jsonld=local_doc)
        errors = list(ds.metadata.ctx.issues.errors)
        warnings = list(ds.metadata.ctx.issues.warnings)
        if errors:
            raise ValueError(f"Croissant validation failed at {metadata_path}: {errors}")
        if warnings:
            logger.warning("Croissant validation warnings at %s: %s", metadata_path, warnings)
    except mlc.ValidationError as e:
        raise ValueError(f"Croissant validation failed at {metadata_path}: {e}") from e
