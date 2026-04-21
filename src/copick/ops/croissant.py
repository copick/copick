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
from typing import Any, Dict, List, Optional

from fsspec import AbstractFileSystem

from copick.impl.mlcroissant import (
    CROISSANT_CONTEXT,
    CSV_SCHEMA,
    RECORDSET_ORDER,
    _fs_for_url,
)
from copick.models import CopickRoot
from copick.util.log import get_logger

logger = get_logger(__name__)


CONFORMS_TO = "http://mlcommons.org/croissant/1.1"

# Canonical S3 base URL for the CZ cryoET Data Portal public bucket. Portal URLs
# are of the form ``s3://cryoet-data-portal-public/<dataset_id>/...``.
CDP_PORTAL_BASE_URL = "s3://cryoet-data-portal-public/"


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

    Returns:
        The path to the written metadata.json.
    """
    project_root_str = _strip_proto(project_root)
    croissant_dir = os.path.join(project_root_str, "Croissant")

    # Figure out fsspec filesystem for the Croissant directory
    croissant_fs, _ = _fs_for_url(croissant_dir)
    if not croissant_fs.exists(croissant_dir):
        croissant_fs.makedirs(croissant_dir, exist_ok=True)

    # Detect source type + URL prefix
    source_type = getattr(root.config, "config_type", "filesystem")
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
    rows = _walk_project(root, copick_base_url, source_type=source_type, compute_file_sha256=compute_file_sha256)

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


def _walk_project(
    root: CopickRoot,
    copick_base_url: str,
    *,
    source_type: str,
    compute_file_sha256: bool,
) -> Dict[str, List[Dict[str, Any]]]:
    rows: Dict[str, List[Dict[str, Any]]] = {rs_id: [] for rs_id in RECORDSET_ORDER}
    is_cdp = source_type == "cryoet_data_portal"

    for run in root.runs:
        rows["copick/runs"].append({"name": run.name})

        for vs in run.voxel_spacings:
            rows["copick/voxel_spacings"].append(
                {"run": run.name, "voxel_size": float(vs.voxel_size)},
            )
            for tomo in vs.tomograms:
                tomo_url = _tomo_url(run, vs, tomo, copick_base_url, is_cdp)
                rows["copick/tomograms"].append(
                    {
                        "run": run.name,
                        "voxel_size": float(vs.voxel_size),
                        "tomo_type": tomo.tomo_type,
                        "url": tomo_url,
                    },
                )
                for feat in tomo.features:
                    feat_url = _feat_url(run, vs, tomo, feat, copick_base_url, is_cdp)
                    rows["copick/features"].append(
                        {
                            "run": run.name,
                            "voxel_size": float(vs.voxel_size),
                            "tomo_type": tomo.tomo_type,
                            "feature_type": feat.feature_type,
                            "url": feat_url,
                        },
                    )

        for pick in run.picks:
            pick_url, sha = _pick_url_and_sha(run, pick, copick_base_url, is_cdp, compute_file_sha256)
            rows["copick/picks"].append(
                {
                    "run": run.name,
                    "user_id": pick.user_id,
                    "session_id": pick.session_id,
                    "object_name": pick.pickable_object_name,
                    "url": pick_url,
                    "sha256": sha,
                },
            )

        for mesh in run.meshes:
            mesh_url, sha = _mesh_url_and_sha(run, mesh, copick_base_url, is_cdp, compute_file_sha256)
            rows["copick/meshes"].append(
                {
                    "run": run.name,
                    "user_id": mesh.user_id,
                    "session_id": mesh.session_id,
                    "object_name": mesh.pickable_object_name,
                    "url": mesh_url,
                    "sha256": sha,
                },
            )

        for seg in run.segmentations:
            seg_url = _seg_url(run, seg, copick_base_url, is_cdp)
            rows["copick/segmentations"].append(
                {
                    "run": run.name,
                    "voxel_size": float(seg.voxel_size),
                    "user_id": seg.user_id,
                    "session_id": seg.session_id,
                    "name": seg.name,
                    "is_multilabel": bool(seg.is_multilabel),
                    "url": seg_url,
                },
            )

    for obj in root.pickable_objects:
        if not obj.is_particle:
            continue
        try:
            z = obj.zarr()
        except Exception:
            z = None
        if z is None:
            continue
        obj_url = _object_url(obj, copick_base_url, is_cdp)
        rows["copick/objects"].append({"name": obj.name, "url": obj_url})

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
    copick_config = {
        "name": cfg.name,
        "description": cfg.description,
        "version": cfg.version,
        "user_id": cfg.user_id,
        "session_id": cfg.session_id,
        "pickable_objects": [po.model_dump() for po in cfg.pickable_objects],
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
