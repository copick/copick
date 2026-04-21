"""mlcroissant-backed copick storage backend.

Reads project structure from a Croissant JSON-LD manifest + CSV sidecars
living under `<project_root>/Croissant/`:

    <project_root>/
      Croissant/
        metadata.json
        runs.csv / voxel_spacings.csv / tomograms.csv / features.csv /
        picks.csv / meshes.csv / segmentations.csv / objects.csv
      ExperimentRuns/
      Objects/

Zarr/JSON/GLB URLs are values in CSV `url` columns (not spec-level resources).
The Croissant `distribution` contains only the CSV FileObjects.

Two operational modes:
  - Mode A (self-contained): writable ``copick:baseUrl``. Writes go to the
    project tree and auto-sync to the Croissant CSVs.
  - Mode B (remote + overlay): read-only ``copick:baseUrl`` plus explicit
    ``overlay_root`` for local edits; writes land in the overlay only.
"""

import contextlib
import csv
import hashlib
import io
import json
import os
import threading
import weakref
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple, Type, Union
from urllib.parse import urlparse

import fsspec
import zarr
from fsspec import AbstractFileSystem
from fsspec.implementations.local import LocalFileSystem

from copick.impl.overlay import (
    CopickFeaturesOverlay,
    CopickMeshOverlay,
    CopickObjectOverlay,
    CopickPicksOverlay,
    CopickRunOverlay,
    CopickSegmentationOverlay,
    CopickTomogramOverlay,
    CopickVoxelSpacingOverlay,
)
from copick.models import (
    CopickConfig,
    CopickFeatures,
    CopickFeaturesMeta,
    CopickMeshMeta,
    CopickPicksFile,
    CopickRoot,
    CopickRunMeta,
    CopickSegmentationMeta,
    CopickTomogramMeta,
    CopickVoxelSpacingMeta,
    PickableObject,
)
from copick.util.log import get_logger

if TYPE_CHECKING:
    from trimesh.parent import Geometry

logger = get_logger(__name__)


# -----------------------------------------------------------------------------
# Croissant @context (canonical Croissant 1.1 + copick additions)
# -----------------------------------------------------------------------------

CROISSANT_CONTEXT = {
    "@language": "en",
    "@vocab": "https://schema.org/",
    "citeAs": "cr:citeAs",
    "column": "cr:column",
    "conformsTo": "dct:conformsTo",
    "containedIn": "cr:containedIn",
    "copick": "https://copick.org/schema/",
    "copick:baseUrl": "copick:baseUrl",
    "copick:config": {"@id": "copick:config", "@type": "@json"},
    "cr": "http://mlcommons.org/croissant/",
    "rai": "http://mlcommons.org/croissant/RAI/",
    "data": {"@id": "cr:data", "@type": "@json"},
    "dataType": {"@id": "cr:dataType", "@type": "@vocab"},
    "dct": "http://purl.org/dc/terms/",
    "examples": {"@id": "cr:examples", "@type": "@json"},
    "extract": "cr:extract",
    "field": "cr:field",
    "fileProperty": "cr:fileProperty",
    "fileObject": "cr:fileObject",
    "fileSet": "cr:fileSet",
    "format": "cr:format",
    "includes": "cr:includes",
    "isLiveDataset": "cr:isLiveDataset",
    "jsonPath": "cr:jsonPath",
    "key": "cr:key",
    "md5": "cr:md5",
    "parentField": "cr:parentField",
    "path": "cr:path",
    "recordSet": "cr:recordSet",
    "references": "cr:references",
    "regex": "cr:regex",
    "repeated": "cr:repeated",
    "replace": "cr:replace",
    "samplingRate": "cr:samplingRate",
    "sc": "https://schema.org/",
    "separator": "cr:separator",
    "source": "cr:source",
    "subField": "cr:subField",
    "transform": "cr:transform",
}


# CSV / RecordSet schema — one entry per artifact type.
# columns: the CSV header, in order.
# key_fields: the columns that uniquely identify a row (for update/remove lookups).
CSV_SCHEMA: Dict[str, Dict[str, Any]] = {
    "copick/runs": {
        "csv_name": "runs.csv",
        "file_object_id": "runs-csv",
        "recordset_name": "runs",
        "columns": ["name"],
        "key_fields": ("name",),
        "types": {"name": "sc:Text"},
    },
    "copick/voxel_spacings": {
        "csv_name": "voxel_spacings.csv",
        "file_object_id": "voxel-spacings-csv",
        "recordset_name": "voxel_spacings",
        "columns": ["run", "voxel_size"],
        "key_fields": ("run", "voxel_size"),
        "types": {"run": "sc:Text", "voxel_size": "sc:Float"},
    },
    "copick/tomograms": {
        "csv_name": "tomograms.csv",
        "file_object_id": "tomograms-csv",
        "recordset_name": "tomograms",
        "columns": ["run", "voxel_size", "tomo_type", "url"],
        "key_fields": ("run", "voxel_size", "tomo_type"),
        "types": {
            "run": "sc:Text",
            "voxel_size": "sc:Float",
            "tomo_type": "sc:Text",
            "url": "sc:Text",
        },
    },
    "copick/features": {
        "csv_name": "features.csv",
        "file_object_id": "features-csv",
        "recordset_name": "features",
        "columns": ["run", "voxel_size", "tomo_type", "feature_type", "url"],
        "key_fields": ("run", "voxel_size", "tomo_type", "feature_type"),
        "types": {
            "run": "sc:Text",
            "voxel_size": "sc:Float",
            "tomo_type": "sc:Text",
            "feature_type": "sc:Text",
            "url": "sc:Text",
        },
    },
    "copick/picks": {
        "csv_name": "picks.csv",
        "file_object_id": "picks-csv",
        "recordset_name": "picks",
        "columns": ["run", "user_id", "session_id", "object_name", "url", "sha256"],
        "key_fields": ("run", "user_id", "session_id", "object_name"),
        "types": {
            "run": "sc:Text",
            "user_id": "sc:Text",
            "session_id": "sc:Text",
            "object_name": "sc:Text",
            "url": "sc:Text",
            "sha256": "sc:Text",
        },
    },
    "copick/meshes": {
        "csv_name": "meshes.csv",
        "file_object_id": "meshes-csv",
        "recordset_name": "meshes",
        "columns": ["run", "user_id", "session_id", "object_name", "url", "sha256"],
        "key_fields": ("run", "user_id", "session_id", "object_name"),
        "types": {
            "run": "sc:Text",
            "user_id": "sc:Text",
            "session_id": "sc:Text",
            "object_name": "sc:Text",
            "url": "sc:Text",
            "sha256": "sc:Text",
        },
    },
    "copick/segmentations": {
        "csv_name": "segmentations.csv",
        "file_object_id": "segmentations-csv",
        "recordset_name": "segmentations",
        "columns": ["run", "voxel_size", "user_id", "session_id", "name", "is_multilabel", "url"],
        "key_fields": ("run", "voxel_size", "user_id", "session_id", "name", "is_multilabel"),
        "types": {
            "run": "sc:Text",
            "voxel_size": "sc:Float",
            "user_id": "sc:Text",
            "session_id": "sc:Text",
            "name": "sc:Text",
            "is_multilabel": "sc:Boolean",
            "url": "sc:Text",
        },
    },
    "copick/objects": {
        "csv_name": "objects.csv",
        "file_object_id": "objects-csv",
        "recordset_name": "objects",
        "columns": ["name", "url"],
        "key_fields": ("name",),
        "types": {"name": "sc:Text", "url": "sc:Text"},
    },
}


RECORDSET_ORDER = [
    "copick/runs",
    "copick/voxel_spacings",
    "copick/tomograms",
    "copick/features",
    "copick/picks",
    "copick/meshes",
    "copick/segmentations",
    "copick/objects",
]


# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------


class CopickConfigMLCroissant(CopickConfig):
    """Copick configuration for mlcroissant-backed storage.

    Attributes:
        croissant_url: URL / path to the Croissant metadata.json.
        croissant_base_url: Optional override for ``copick:baseUrl``. Used when the
            dataset has been moved from its published location.
        overlay_root: Optional writable overlay. When provided, the Croissant is
            treated as read-only and writes land in the overlay (Mode B). When
            omitted, the Croissant's base URL is used as the write target (Mode A).
        overlay_fs_args: Extra fsspec kwargs for the overlay filesystem.
        croissant_fs_args: Extra fsspec kwargs for fetching metadata.json and CSVs.
    """

    config_type: str = "mlcroissant"
    croissant_url: str
    croissant_base_url: Optional[str] = None
    overlay_root: Optional[str] = None
    overlay_fs_args: Optional[Dict[str, Any]] = {}
    croissant_fs_args: Optional[Dict[str, Any]] = {}


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _has_protocol(url: str) -> bool:
    """True if the string looks like a URL with a scheme."""
    if not url:
        return False
    parsed = urlparse(url)
    return bool(parsed.scheme) and parsed.scheme not in ("", "c")  # avoid treating C:\ on windows


def _join_url(base: str, relative: str) -> str:
    """Join a base URL and a relative path.

    If ``relative`` already has a protocol, return it unchanged. Otherwise join
    with a single ``/`` separator.
    """
    if _has_protocol(relative):
        return relative
    if not base:
        return relative
    if base.endswith("/"):
        return base + relative.lstrip("/")
    return base + "/" + relative.lstrip("/")


def _fs_for_url(url: str, **kwargs) -> Tuple[AbstractFileSystem, str]:
    """Return an fsspec filesystem and stripped path for ``url``.

    Handles ``file://`` prefix, plain local paths, and protocol URLs. Extra
    kwargs (e.g. ``auto_mkdir=True``) are forwarded to the filesystem
    constructor.
    """
    if url.startswith("file://"):
        path = url[len("file://") :]
        return fsspec.filesystem("file", **kwargs), path
    if _has_protocol(url):
        fs, path = fsspec.url_to_fs(url, **kwargs)
        return fs, path
    # Plain local path
    return fsspec.filesystem("file", **kwargs), url


def _strip_includes_glob(includes: str) -> str:
    """Strip a trailing ``/**`` (or ``**``) pattern from a FileSet includes glob."""
    if includes.endswith("/**"):
        return includes[:-3]
    if includes.endswith("/**/*"):
        return includes[:-5]
    if includes.endswith("**"):
        return includes[:-2].rstrip("/")
    return includes


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_path(fs: AbstractFileSystem, path: str) -> str:
    with fs.open(path, "rb") as f:
        h = hashlib.sha256()
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _coerce_cell(value: Any, type_hint: str) -> Any:
    """Coerce a CSV cell into the correct Python type for a given Field dataType."""
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if type_hint == "sc:Float":
        if value == "" or value is None:
            return None
        return float(value)
    if type_hint == "sc:Integer":
        if value == "" or value is None:
            return None
        return int(value)
    if type_hint == "sc:Boolean":
        if isinstance(value, bool):
            return value
        if value == "" or value is None:
            return None
        return str(value).strip().lower() in ("true", "1", "yes")
    return value if value != "" else None


# -----------------------------------------------------------------------------
# CroissantIndex
# -----------------------------------------------------------------------------


@dataclass
class CroissantIndex:
    """In-memory index of a Croissant manifest + its CSV sidecars.

    Holds both the read side (materialised rows per artifact type) and the
    write-tracking state (dirty CSVs, auto-commit toggle).
    """

    doc: Dict[str, Any]  # the parsed Croissant JSON-LD
    croissant_dir: str  # absolute path/URL of the Croissant directory containing metadata.json
    croissant_fs: AbstractFileSystem  # fsspec fs for the Croissant directory
    base_url: str = ""
    config_block: Dict[str, Any] = field(default_factory=dict)

    # Materialised rows per RecordSet
    runs_by_name: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    voxel_spacings: List[Dict[str, Any]] = field(default_factory=list)
    tomograms: List[Dict[str, Any]] = field(default_factory=list)
    features: List[Dict[str, Any]] = field(default_factory=list)
    picks: List[Dict[str, Any]] = field(default_factory=list)
    meshes: List[Dict[str, Any]] = field(default_factory=list)
    segmentations: List[Dict[str, Any]] = field(default_factory=list)
    objects: List[Dict[str, Any]] = field(default_factory=list)

    # Write-side state
    _dirty: Set[str] = field(default_factory=set)
    _auto_commit: bool = True
    _writable: bool = False
    _metadata_path: str = "metadata.json"
    _write_lock: threading.RLock = field(default_factory=threading.RLock)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def from_url(
        cls,
        croissant_url: str,
        *,
        base_url_override: Optional[str] = None,
        fs_args: Optional[Dict[str, Any]] = None,
    ) -> "CroissantIndex":
        """Fetch and parse the Croissant manifest at ``croissant_url``."""
        fs_args = fs_args or {}
        croissant_fs, croissant_path = _fs_for_url(croissant_url, **fs_args)

        with croissant_fs.open(croissant_path, "rb") as f:
            raw = f.read()
        doc = json.loads(raw.decode("utf-8"))

        # Determine base URL
        base_url = base_url_override
        if not base_url:
            base_url = doc.get("copick:baseUrl", "")
        if not base_url:
            # Default: project root = parent of Croissant/ = parent of metadata.json's parent
            # If croissant_url is .../Croissant/metadata.json, project root is .../
            parent = os.path.dirname(croissant_path)
            project_root = os.path.dirname(parent)
            # Re-attach protocol if present
            if croissant_url.startswith("file://"):
                base_url = "file://" + project_root
            elif _has_protocol(croissant_url):
                parsed = urlparse(croissant_url)
                project_path = os.path.dirname(os.path.dirname(parsed.path))
                base_url = f"{parsed.scheme}://{parsed.netloc}{project_path}"
            else:
                base_url = project_root

        # Directory that holds metadata.json + the CSV sidecars
        croissant_dir = os.path.dirname(croissant_path) or "."

        index = cls(
            doc=doc,
            croissant_dir=croissant_dir,
            croissant_fs=croissant_fs,
            base_url=base_url,
            config_block=doc.get("copick:config", {}),
            _metadata_path=croissant_path,
        )

        # Decide writability by probing the fs
        index._writable = _fs_writable(croissant_fs, croissant_dir)

        # Materialise CSV rows via mlcroissant
        index._load_records()

        return index

    def _load_records(self) -> None:
        """Load all 8 CSVs into typed Python dicts via mlcroissant.Dataset.records()."""
        try:
            import mlcroissant as mlc
        except ImportError as e:
            raise ImportError(
                "mlcroissant is required for the mlcroissant copick backend. "
                "Install it with `pip install mlcroissant`.",
            ) from e

        # Before calling mlcroissant, rewrite CSV FileObject contentUrls to local
        # paths where possible — mlcroissant uses these to download + iterate,
        # and it rejects file:// prefixes for local files.
        local_doc = self._prepare_doc_for_mlcroissant()

        # mlcroissant resolves relative file references against ctx.folder, which
        # is only populated when loading from a file path. Write the rewritten doc
        # to a temp file next to the Croissant so resolution succeeds.
        local_mode = isinstance(self.croissant_fs, LocalFileSystem)
        if local_mode:
            tmp_path = os.path.join(self.croissant_dir, ".copick-tmp-metadata.json")
            try:
                with open(tmp_path, "w") as tmp:
                    json.dump(local_doc, tmp)
                try:
                    dataset = mlc.Dataset(jsonld=tmp_path)
                except Exception as e:
                    raise ValueError(f"Failed to load Croissant at {self._metadata_path}: {e}") from e
            finally:
                with contextlib.suppress(OSError):
                    os.unlink(tmp_path)
        else:
            try:
                dataset = mlc.Dataset(jsonld=local_doc)
            except Exception as e:
                raise ValueError(f"Failed to load Croissant at {self._metadata_path}: {e}") from e

        for rs_id, schema in CSV_SCHEMA.items():
            target = self._get_list_for(rs_id)
            target.clear() if isinstance(target, list) else target.clear()

            try:
                records = dataset.records(rs_id)
            except Exception:
                # RecordSet may be missing or empty — treat as no rows
                continue

            types = schema["types"]
            prefix = rs_id + "/"

            for rec in records:
                row = {}
                for col in schema["columns"]:
                    key = prefix + col
                    raw = rec.get(key, None)
                    row[col] = _coerce_cell(raw, types[col])
                if rs_id == "copick/runs":
                    if row.get("name"):
                        self.runs_by_name[row["name"]] = row
                else:
                    target.append(row)

    def _prepare_doc_for_mlcroissant(self) -> Dict[str, Any]:
        """Return a copy of ``self.doc`` with CSV FileObject contentUrls rewritten
        to filesystem-accessible paths.

        mlcroissant downloads referenced FileObjects to resolve records — for
        local files it requires plain absolute paths (no ``file://`` prefix).
        For local Croissants we always rewrite to absolute paths inside
        ``self.croissant_dir``; for remote Croissants we leave the original
        URLs (mlcroissant handles http/s3 via etils/epath downloading).
        """
        import copy

        doc = copy.deepcopy(self.doc)
        distribution = doc.get("distribution", [])
        # If the Croissant is local on disk, point CSVs at the local dir
        local_mode = isinstance(self.croissant_fs, LocalFileSystem)

        for entry in distribution:
            if entry.get("@type") != "cr:FileObject":
                continue
            fo_id = entry.get("@id", "")
            schema_entry = _find_schema_by_file_object_id(fo_id)
            if schema_entry is None:
                continue
            csv_name = schema_entry["csv_name"]
            if local_mode:
                local_path = os.path.join(self.croissant_dir, csv_name)
                entry["contentUrl"] = local_path
        return doc

    def _get_list_for(self, recordset_id: str):
        return {
            "copick/runs": self.runs_by_name,
            "copick/voxel_spacings": self.voxel_spacings,
            "copick/tomograms": self.tomograms,
            "copick/features": self.features,
            "copick/picks": self.picks,
            "copick/meshes": self.meshes,
            "copick/segmentations": self.segmentations,
            "copick/objects": self.objects,
        }[recordset_id]

    # ------------------------------------------------------------------
    # URL resolution
    # ------------------------------------------------------------------

    def resolve_url(self, url_value: str, **fs_args) -> Tuple[AbstractFileSystem, str]:
        """Resolve a CSV ``url`` column value into (fsspec_fs, absolute_path)."""
        absolute = _join_url(self.base_url, url_value)
        fs, path = _fs_for_url(absolute, **fs_args)
        return fs, path

    # ------------------------------------------------------------------
    # Write-side API
    # ------------------------------------------------------------------

    def mark_dirty(self, recordset_id: str) -> None:
        with self._write_lock:
            self._dirty.add(recordset_id)

    def add_row(self, recordset_id: str, row: Dict[str, Any]) -> None:
        schema = CSV_SCHEMA[recordset_id]
        key_fields = schema["key_fields"]

        with self._write_lock:
            if recordset_id == "copick/runs":
                self.runs_by_name[row["name"]] = row
            else:
                target = self._get_list_for(recordset_id)
                # Replace if key already exists
                for i, existing in enumerate(target):
                    if all(existing.get(k) == row.get(k) for k in key_fields):
                        target[i] = row
                        break
                else:
                    target.append(row)

            self._dirty.add(recordset_id)
            if self._auto_commit:
                self._commit_locked()

    def remove_row(self, recordset_id: str, key: Dict[str, Any]) -> None:
        schema = CSV_SCHEMA[recordset_id]
        key_fields = schema["key_fields"]
        with self._write_lock:
            if recordset_id == "copick/runs":
                self.runs_by_name.pop(key.get("name"), None)
            else:
                target = self._get_list_for(recordset_id)
                target[:] = [row for row in target if not all(row.get(k) == key.get(k) for k in key_fields)]

            self._dirty.add(recordset_id)
            if self._auto_commit:
                self._commit_locked()

    def commit(self) -> None:
        """Write dirty CSVs and update metadata.json.

        Uses atomic temp-file-and-rename on the local filesystem. For remote
        filesystems, relies on fsspec's ``pipe``/``open("wb")`` atomicity
        (best effort).
        """
        with self._write_lock:
            self._commit_locked()

    def reload(self) -> None:
        """Re-read metadata.json and CSVs from disk.

        Use this to pick up changes made by another process / root instance.
        Any unflushed dirty state is discarded — callers relying on
        ``batch()``-deferred commits should ``commit()`` before ``reload()``.
        """
        with self._write_lock:
            with self.croissant_fs.open(self._metadata_path, "rb") as f:
                raw = f.read()
            self.doc = json.loads(raw.decode("utf-8"))
            self.config_block = self.doc.get("copick:config", {})
            self.runs_by_name.clear()
            self.voxel_spacings.clear()
            self.tomograms.clear()
            self.features.clear()
            self.picks.clear()
            self.meshes.clear()
            self.segmentations.clear()
            self.objects.clear()
            self._dirty.clear()
            self._load_records()

    def _commit_locked(self) -> None:
        """Internal commit; caller must hold ``self._write_lock``."""
        if not self._dirty:
            return
        if not self._writable:
            raise PermissionError(
                f"Croissant at {self._metadata_path} is not writable; cannot commit.",
            )

        # Rewrite each dirty CSV and recompute its sha256
        new_sha = {}
        for rs_id in sorted(self._dirty):
            schema = CSV_SCHEMA[rs_id]
            csv_path = os.path.join(self.croissant_dir, schema["csv_name"])
            csv_bytes = self._serialize_csv(rs_id)
            self._atomic_write_bytes(csv_path, csv_bytes)
            new_sha[schema["file_object_id"]] = _sha256_bytes(csv_bytes)

        # Patch metadata.json distribution sha256s
        for entry in self.doc.get("distribution", []):
            if entry.get("@type") == "cr:FileObject":
                fo_id = entry.get("@id")
                if fo_id in new_sha:
                    entry["sha256"] = new_sha[fo_id]

        metadata_bytes = json.dumps(self.doc, indent=2).encode("utf-8")
        self._atomic_write_bytes(self._metadata_path, metadata_bytes)

        self._dirty.clear()

    def _serialize_csv(self, recordset_id: str) -> bytes:
        schema = CSV_SCHEMA[recordset_id]
        columns = schema["columns"]
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()

        if recordset_id == "copick/runs":
            rows = sorted(self.runs_by_name.values(), key=lambda r: r["name"])
        else:
            rows = self._get_list_for(recordset_id)

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
        return buffer.getvalue().encode("utf-8")

    def _atomic_write_bytes(self, path: str, data: bytes) -> None:
        """Write ``data`` to ``path`` atomically (temp file + rename on local FS)."""
        fs = self.croissant_fs
        if isinstance(fs, LocalFileSystem):
            tmp_path = path + ".tmp"
            with open(tmp_path, "wb") as f:
                f.write(data)
                f.flush()
                with contextlib.suppress(OSError):
                    os.fsync(f.fileno())
            os.replace(tmp_path, path)
        else:
            with fs.open(path, "wb") as f:
                f.write(data)

    # ------------------------------------------------------------------
    # Batch context manager helpers (called by root.batch())
    # ------------------------------------------------------------------

    def defer_commit(self) -> None:
        self._auto_commit = False

    def resume_commit(self) -> None:
        self._auto_commit = True


def _find_schema_by_file_object_id(fo_id: str) -> Optional[Dict[str, Any]]:
    for schema in CSV_SCHEMA.values():
        if schema["file_object_id"] == fo_id:
            return schema
    return None


def _fs_writable(fs: AbstractFileSystem, path: str) -> bool:
    """Best-effort check that ``path`` is writable via ``fs``."""
    if isinstance(fs, LocalFileSystem):
        return os.access(path, os.W_OK) if os.path.exists(path) else os.access(os.path.dirname(path) or ".", os.W_OK)
    # For remote filesystems (s3, http), pessimistically assume not writable unless
    # overlay is also configured. The caller (CopickRootMLC) handles the fallback.
    # We can't reliably probe without attempting a write.
    proto = getattr(fs, "protocol", "")
    if isinstance(proto, (list, tuple)):
        proto = proto[0] if proto else ""
    return proto not in ("http", "https", "github")


# -----------------------------------------------------------------------------
# Picks
# -----------------------------------------------------------------------------


class CopickPicksMLC(CopickPicksOverlay):
    """Picks file backed by an mlcroissant manifest (static) + optional overlay."""

    run: "CopickRunMLC"

    @property
    def _index(self) -> CroissantIndex:
        return self.run.root.index

    def _find_row(self) -> Optional[Dict[str, Any]]:
        key = {
            "run": self.run.name,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "object_name": self.pickable_object_name,
        }
        for row in self._index.picks:
            if all(row.get(k) == v for k, v in key.items()):
                return row
        return None

    @property
    def path(self) -> str:
        if self.read_only:
            row = self._find_row()
            if row is None:
                raise FileNotFoundError(f"No Croissant row for pick {self}")
            return _join_url(self._index.base_url, row["url"])
        # Writable overlay path
        return f"{self.run.overlay_path}/Picks/{self.user_id}_{self.session_id}_{self.pickable_object_name}.json"

    @property
    def directory(self) -> str:
        if self.read_only:
            raise RuntimeError("Read-only pick has no writable directory.")
        return f"{self.run.overlay_path}/Picks/"

    @property
    def fs(self) -> AbstractFileSystem:
        if self.read_only:
            fs, _ = _fs_for_url(self.path)
            return fs
        return self.run.fs_overlay

    def _load(self) -> CopickPicksFile:
        if self.read_only:
            fs, abs_path = self._index.resolve_url(self._find_row()["url"])
            if not fs.exists(abs_path):
                raise FileNotFoundError(f"Pick file not found: {abs_path}")
            with fs.open(abs_path, "r") as f:
                data = json.load(f)
        else:
            path = self.path
            fs = self.fs
            if not fs.exists(path):
                raise FileNotFoundError(f"Pick file not found: {path}")
            with fs.open(path, "r") as f:
                data = json.load(f)
        return CopickPicksFile(**data)

    def _store(self) -> None:
        fs = self.fs
        # Ensure directory exists
        if not fs.exists(self.directory):
            fs.makedirs(self.directory, exist_ok=True)
        # Write JSON
        json_bytes = json.dumps(self.meta.model_dump(), indent=4).encode("utf-8")
        with fs.open(self.path, "wb") as f:
            f.write(json_bytes)

        # Live-sync to Croissant (Mode A only — the root decides based on overlay_root)
        if self.run.root.mode == "A":
            rel = self._relative_url()
            row = {
                "run": self.run.name,
                "user_id": self.user_id,
                "session_id": self.session_id,
                "object_name": self.pickable_object_name,
                "url": rel,
                "sha256": _sha256_bytes(json_bytes),
            }
            self._index.add_row("copick/picks", row)

    def _delete_data(self) -> None:
        fs = self.fs
        if fs.exists(self.path):
            fs.rm(self.path)
        else:
            raise FileNotFoundError(f"File not found: {self.path}")

        if self.run.root.mode == "A":
            key = {
                "run": self.run.name,
                "user_id": self.user_id,
                "session_id": self.session_id,
                "object_name": self.pickable_object_name,
            }
            self._index.remove_row("copick/picks", key)

    def _relative_url(self) -> str:
        """Return the url column value (relative to base_url) for this artifact."""
        return (
            f"ExperimentRuns/{self.run.name}/Picks/"
            f"{self.user_id}_{self.session_id}_{self.pickable_object_name}.json"
        )


# -----------------------------------------------------------------------------
# Meshes
# -----------------------------------------------------------------------------


class CopickMeshMLC(CopickMeshOverlay):
    run: "CopickRunMLC"

    @property
    def _index(self) -> CroissantIndex:
        return self.run.root.index

    def _find_row(self) -> Optional[Dict[str, Any]]:
        key = {
            "run": self.run.name,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "object_name": self.pickable_object_name,
        }
        for row in self._index.meshes:
            if all(row.get(k) == v for k, v in key.items()):
                return row
        return None

    @property
    def path(self) -> str:
        if self.read_only:
            row = self._find_row()
            if row is None:
                raise FileNotFoundError(f"No Croissant row for mesh {self}")
            return _join_url(self._index.base_url, row["url"])
        return f"{self.run.overlay_path}/Meshes/{self.user_id}_{self.session_id}_{self.pickable_object_name}.glb"

    @property
    def directory(self) -> str:
        if self.read_only:
            raise RuntimeError("Read-only mesh has no writable directory.")
        return f"{self.run.overlay_path}/Meshes/"

    @property
    def fs(self) -> AbstractFileSystem:
        if self.read_only:
            fs, _ = _fs_for_url(self.path)
            return fs
        return self.run.fs_overlay

    def _load(self) -> "Geometry":
        import trimesh

        if self.read_only:
            fs, abs_path = self._index.resolve_url(self._find_row()["url"])
            if not fs.exists(abs_path):
                raise FileNotFoundError(f"Mesh file not found: {abs_path}")
            with fs.open(abs_path, "rb") as f:
                scene = trimesh.load(f, file_type="glb")
        else:
            path = self.path
            fs = self.fs
            if not fs.exists(path):
                raise FileNotFoundError(f"Mesh file not found: {path}")
            with fs.open(path, "rb") as f:
                scene = trimesh.load(f, file_type="glb")
        return scene

    def _store(self) -> None:
        fs = self.fs
        if not fs.exists(self.directory):
            fs.makedirs(self.directory, exist_ok=True)

        # Export via trimesh, capture bytes for sha256
        buf = io.BytesIO()
        self._mesh.export(buf, file_type="glb")
        data = buf.getvalue()
        with fs.open(self.path, "wb") as f:
            f.write(data)

        if self.run.root.mode == "A":
            rel = self._relative_url()
            row = {
                "run": self.run.name,
                "user_id": self.user_id,
                "session_id": self.session_id,
                "object_name": self.pickable_object_name,
                "url": rel,
                "sha256": _sha256_bytes(data),
            }
            self._index.add_row("copick/meshes", row)

    def _delete_data(self) -> None:
        fs = self.fs
        if fs.exists(self.path):
            fs.rm(self.path)
        else:
            raise FileNotFoundError(f"File not found: {self.path}")
        if self.run.root.mode == "A":
            key = {
                "run": self.run.name,
                "user_id": self.user_id,
                "session_id": self.session_id,
                "object_name": self.pickable_object_name,
            }
            self._index.remove_row("copick/meshes", key)

    def _relative_url(self) -> str:
        return (
            f"ExperimentRuns/{self.run.name}/Meshes/"
            f"{self.user_id}_{self.session_id}_{self.pickable_object_name}.glb"
        )


# -----------------------------------------------------------------------------
# Segmentations
# -----------------------------------------------------------------------------


class CopickSegmentationMLC(CopickSegmentationOverlay):
    run: "CopickRunMLC"

    @property
    def _index(self) -> CroissantIndex:
        return self.run.root.index

    def _find_row(self) -> Optional[Dict[str, Any]]:
        key = {
            "run": self.run.name,
            "voxel_size": float(self.voxel_size),
            "user_id": self.user_id,
            "session_id": self.session_id,
            "name": self.name,
            "is_multilabel": bool(self.is_multilabel),
        }
        for row in self._index.segmentations:
            if all(row.get(k) == v for k, v in key.items()):
                return row
        return None

    @property
    def filename(self) -> str:
        if self.is_multilabel:
            return f"{self.voxel_size:.3f}_{self.user_id}_{self.session_id}_{self.name}-multilabel.zarr"
        return f"{self.voxel_size:.3f}_{self.user_id}_{self.session_id}_{self.name}.zarr"

    @property
    def path(self) -> str:
        if self.read_only:
            row = self._find_row()
            if row is None:
                raise FileNotFoundError(f"No Croissant row for segmentation {self}")
            return _join_url(self._index.base_url, row["url"])
        return f"{self.run.overlay_path}/Segmentations/{self.filename}"

    @property
    def fs(self) -> AbstractFileSystem:
        if self.read_only:
            fs, _ = _fs_for_url(self.path)
            return fs
        return self.run.fs_overlay

    def zarr(self) -> zarr.storage.FSStore:
        if self.read_only:
            fs, abs_path = self._index.resolve_url(self._find_row()["url"])
            return zarr.storage.FSStore(
                abs_path,
                fs=fs,
                mode="r",
                key_separator="/",
                dimension_separator="/",
                create=False,
            )
        fs = self.fs
        path = self.path
        create = not fs.exists(path)
        store = zarr.storage.FSStore(
            path,
            fs=fs,
            mode="w",
            key_separator="/",
            dimension_separator="/",
            create=create,
        )
        # Live-sync row (only on creation; subsequent writes reuse the row)
        if create and self.run.root.mode == "A":
            rel = self._relative_url()
            row = {
                "run": self.run.name,
                "voxel_size": float(self.voxel_size),
                "user_id": self.user_id,
                "session_id": self.session_id,
                "name": self.name,
                "is_multilabel": bool(self.is_multilabel),
                "url": rel,
            }
            self._index.add_row("copick/segmentations", row)
        return store

    def _delete_data(self) -> None:
        fs = self.fs
        if fs.exists(self.path):
            fs.rm(self.path, recursive=True)
        else:
            raise FileNotFoundError(f"File not found: {self.path}")
        if self.run.root.mode == "A":
            key = {
                "run": self.run.name,
                "voxel_size": float(self.voxel_size),
                "user_id": self.user_id,
                "session_id": self.session_id,
                "name": self.name,
                "is_multilabel": bool(self.is_multilabel),
            }
            self._index.remove_row("copick/segmentations", key)

    def _relative_url(self) -> str:
        return f"ExperimentRuns/{self.run.name}/Segmentations/{self.filename}"


# -----------------------------------------------------------------------------
# Features
# -----------------------------------------------------------------------------


class CopickFeaturesMLC(CopickFeaturesOverlay):
    tomogram: "CopickTomogramMLC"

    @property
    def _index(self) -> CroissantIndex:
        return self.tomogram.voxel_spacing.run.root.index

    def _find_row(self) -> Optional[Dict[str, Any]]:
        key = {
            "run": self.tomogram.voxel_spacing.run.name,
            "voxel_size": float(self.tomogram.voxel_spacing.voxel_size),
            "tomo_type": self.tomogram.tomo_type,
            "feature_type": self.feature_type,
        }
        for row in self._index.features:
            if all(row.get(k) == v for k, v in key.items()):
                return row
        return None

    @property
    def path(self) -> str:
        if self.read_only:
            row = self._find_row()
            if row is None:
                raise FileNotFoundError(f"No Croissant row for features {self}")
            return _join_url(self._index.base_url, row["url"])
        return f"{self.tomogram.overlay_stem}_{self.feature_type}_features.zarr"

    @property
    def fs(self) -> AbstractFileSystem:
        if self.read_only:
            fs, _ = _fs_for_url(self.path)
            return fs
        return self.tomogram.fs_overlay

    def zarr(self) -> zarr.storage.FSStore:
        if self.read_only:
            fs, abs_path = self._index.resolve_url(self._find_row()["url"])
            return zarr.storage.FSStore(
                abs_path,
                fs=fs,
                mode="r",
                key_separator="/",
                dimension_separator="/",
                create=False,
            )
        fs = self.fs
        path = self.path
        create = not fs.exists(path)
        store = zarr.storage.FSStore(
            path,
            fs=fs,
            mode="w",
            key_separator="/",
            dimension_separator="/",
            create=create,
        )
        if create and self.tomogram.voxel_spacing.run.root.mode == "A":
            rel = self._relative_url()
            row = {
                "run": self.tomogram.voxel_spacing.run.name,
                "voxel_size": float(self.tomogram.voxel_spacing.voxel_size),
                "tomo_type": self.tomogram.tomo_type,
                "feature_type": self.feature_type,
                "url": rel,
            }
            self._index.add_row("copick/features", row)
        return store

    def _delete_data(self) -> None:
        fs = self.fs
        if fs.exists(self.path):
            fs.rm(self.path, recursive=True)
        else:
            raise FileNotFoundError(f"File not found: {self.path}")
        if self.tomogram.voxel_spacing.run.root.mode == "A":
            key = {
                "run": self.tomogram.voxel_spacing.run.name,
                "voxel_size": float(self.tomogram.voxel_spacing.voxel_size),
                "tomo_type": self.tomogram.tomo_type,
                "feature_type": self.feature_type,
            }
            self._index.remove_row("copick/features", key)

    def _relative_url(self) -> str:
        run = self.tomogram.voxel_spacing.run.name
        vs = self.tomogram.voxel_spacing.voxel_size
        return f"ExperimentRuns/{run}/VoxelSpacing{vs:.3f}/{self.tomogram.tomo_type}_{self.feature_type}_features.zarr"


# -----------------------------------------------------------------------------
# Tomograms
# -----------------------------------------------------------------------------


class CopickTomogramMLC(CopickTomogramOverlay):
    voxel_spacing: "CopickVoxelSpacingMLC"

    def _feature_factory(self) -> Tuple[Type[CopickFeatures], Type[CopickFeaturesMeta]]:
        return CopickFeaturesMLC, CopickFeaturesMeta

    @property
    def _index(self) -> CroissantIndex:
        return self.voxel_spacing.run.root.index

    def _find_row(self) -> Optional[Dict[str, Any]]:
        key = {
            "run": self.voxel_spacing.run.name,
            "voxel_size": float(self.voxel_spacing.voxel_size),
            "tomo_type": self.tomo_type,
        }
        for row in self._index.tomograms:
            if all(row.get(k) == v for k, v in key.items()):
                return row
        return None

    @property
    def static_path(self) -> str:
        row = self._find_row()
        if row is None:
            return None
        return _join_url(self._index.base_url, row["url"])

    @property
    def overlay_path(self) -> str:
        return f"{self.voxel_spacing.overlay_path}/{self.tomo_type}.zarr"

    @property
    def static_stem(self) -> str:
        sp = self.static_path
        if sp and sp.endswith(".zarr"):
            return sp[:-5]
        return sp or ""

    @property
    def overlay_stem(self) -> str:
        return f"{self.voxel_spacing.overlay_path}/{self.tomo_type}"

    @property
    def fs_static(self) -> AbstractFileSystem:
        sp = self.static_path
        if sp is None:
            return None
        fs, _ = _fs_for_url(sp)
        return fs

    @property
    def fs_overlay(self) -> AbstractFileSystem:
        return self.voxel_spacing.fs_overlay

    @property
    def static_is_overlay(self) -> bool:
        return self.voxel_spacing.static_is_overlay

    def _query_static_features(self) -> List[CopickFeaturesMLC]:
        # Mode A: static_is_overlay — everything is in the overlay query.
        if self.voxel_spacing.run.root.mode == "A":
            return []
        results = []
        for row in self._index.features:
            if (
                row.get("run") == self.voxel_spacing.run.name
                and row.get("voxel_size") == float(self.voxel_spacing.voxel_size)
                and row.get("tomo_type") == self.tomo_type
            ):
                results.append(
                    CopickFeaturesMLC(
                        tomogram=self,
                        meta=CopickFeaturesMeta(tomo_type=self.tomo_type, feature_type=row["feature_type"]),
                        read_only=True,
                    ),
                )
        return results

    def _query_overlay_features(self) -> List[CopickFeaturesMLC]:
        if self.voxel_spacing.run.root.mode == "A":
            # Mode A: the Croissant index is the authoritative list of writable features.
            return [
                CopickFeaturesMLC(
                    tomogram=self,
                    meta=CopickFeaturesMeta(tomo_type=self.tomo_type, feature_type=row["feature_type"]),
                    read_only=False,
                )
                for row in self._index.features
                if row.get("run") == self.voxel_spacing.run.name
                and row.get("voxel_size") == float(self.voxel_spacing.voxel_size)
                and row.get("tomo_type") == self.tomo_type
            ]
        fs = self.fs_overlay
        if fs is None:
            return []
        feat_loc = self.overlay_path.replace(".zarr", "_")
        try:
            paths = fs.glob(feat_loc + "*_features.zarr") + fs.glob(feat_loc + "*_features.zarr/")
        except FileNotFoundError:
            return []
        paths = [p.rstrip("/") for p in paths if fs.isdir(p)]
        feature_types = [n.replace(feat_loc, "").replace("_features.zarr", "") for n in paths]
        feature_types = [ft for ft in feature_types if not ft.startswith(".")]
        feature_types = list(set(feature_types))
        return [
            CopickFeaturesMLC(
                tomogram=self,
                meta=CopickFeaturesMeta(tomo_type=self.tomo_type, feature_type=ft),
                read_only=False,
            )
            for ft in feature_types
        ]

    def zarr(self) -> zarr.storage.FSStore:
        if self.read_only:
            fs, abs_path = self._index.resolve_url(self._find_row()["url"])
            return zarr.storage.FSStore(
                abs_path,
                fs=fs,
                mode="r",
                key_separator="/",
                dimension_separator="/",
                create=False,
            )
        fs = self.fs_overlay
        path = self.overlay_path
        create = not fs.exists(path)
        store = zarr.storage.FSStore(
            path,
            fs=fs,
            mode="w",
            key_separator="/",
            dimension_separator="/",
            create=create,
        )
        if create and self.voxel_spacing.run.root.mode == "A":
            rel = self._relative_url()
            row = {
                "run": self.voxel_spacing.run.name,
                "voxel_size": float(self.voxel_spacing.voxel_size),
                "tomo_type": self.tomo_type,
                "url": rel,
            }
            self._index.add_row("copick/tomograms", row)
        return store

    def _delete_data(self) -> None:
        if self.fs_overlay.exists(self.overlay_path):
            self.fs_overlay.rm(self.overlay_path, recursive=True)
        else:
            raise FileNotFoundError(f"File not found: {self.overlay_path}")
        if self.voxel_spacing.run.root.mode == "A":
            key = {
                "run": self.voxel_spacing.run.name,
                "voxel_size": float(self.voxel_spacing.voxel_size),
                "tomo_type": self.tomo_type,
            }
            self._index.remove_row("copick/tomograms", key)

    def _relative_url(self) -> str:
        run = self.voxel_spacing.run.name
        vs = self.voxel_spacing.voxel_size
        return f"ExperimentRuns/{run}/VoxelSpacing{vs:.3f}/{self.tomo_type}.zarr"


# -----------------------------------------------------------------------------
# Voxel spacings
# -----------------------------------------------------------------------------


class CopickVoxelSpacingMLC(CopickVoxelSpacingOverlay):
    run: "CopickRunMLC"

    def _tomogram_factory(self) -> Tuple[Type[CopickTomogramMLC], Type[CopickTomogramMeta]]:
        return CopickTomogramMLC, CopickTomogramMeta

    @property
    def _index(self) -> CroissantIndex:
        return self.run.root.index

    @property
    def static_path(self) -> str:
        # For display / compatibility
        return f"{_join_url(self._index.base_url, 'ExperimentRuns')}/{self.run.name}/VoxelSpacing{self.voxel_size:.3f}"

    @property
    def overlay_path(self) -> str:
        return f"{self.run.overlay_path}/VoxelSpacing{self.voxel_size:.3f}"

    @property
    def fs_static(self) -> AbstractFileSystem:
        fs, _ = _fs_for_url(self.static_path)
        return fs

    @property
    def fs_overlay(self) -> AbstractFileSystem:
        return self.run.fs_overlay

    @property
    def static_is_overlay(self) -> bool:
        return self.run.root.mode == "A"

    def _query_static_tomograms(self) -> List[CopickTomogramMLC]:
        # Mode A: static_is_overlay — everything is in the overlay query.
        if self.run.root.mode == "A":
            return []
        results = []
        for row in self._index.tomograms:
            if row.get("run") == self.run.name and row.get("voxel_size") == float(self.voxel_size):
                results.append(
                    CopickTomogramMLC(
                        voxel_spacing=self,
                        meta=CopickTomogramMeta(tomo_type=row["tomo_type"]),
                        read_only=True,
                    ),
                )
        return results

    def _query_overlay_tomograms(self) -> List[CopickTomogramMLC]:
        if self.run.root.mode == "A":
            # Mode A: the Croissant index is the authoritative list of writable tomograms.
            return [
                CopickTomogramMLC(
                    voxel_spacing=self,
                    meta=CopickTomogramMeta(tomo_type=row["tomo_type"]),
                    read_only=False,
                )
                for row in self._index.tomograms
                if row.get("run") == self.run.name and row.get("voxel_size") == float(self.voxel_size)
            ]
        fs = self.fs_overlay
        if fs is None:
            return []
        tomo_loc = f"{self.overlay_path}/"
        try:
            paths = fs.glob(tomo_loc + "*.zarr") + fs.glob(tomo_loc + "*.zarr/")
        except FileNotFoundError:
            return []
        paths = [p.rstrip("/") for p in paths if fs.isdir(p)]
        tomo_types = [n.replace(tomo_loc, "").replace(".zarr", "") for n in paths]
        tomo_types = [t for t in tomo_types if "features" not in t and not t.startswith(".")]
        tomo_types = list(set(tomo_types))
        return [
            CopickTomogramMLC(
                voxel_spacing=self,
                meta=CopickTomogramMeta(tomo_type=tt),
                read_only=False,
            )
            for tt in tomo_types
        ]

    def ensure(self, create: bool = False) -> bool:
        exists = any(
            row.get("run") == self.run.name and row.get("voxel_size") == float(self.voxel_size)
            for row in self._index.voxel_spacings
        )
        if not exists and self.run.root.mode == "B":
            exists = self.fs_overlay.exists(self.overlay_path)

        if not exists and create:
            # Create directory in the overlay / project tree
            fs = self.fs_overlay
            fs.makedirs(self.overlay_path, exist_ok=True)
            if self.run.root.mode == "A":
                self._index.add_row(
                    "copick/voxel_spacings",
                    {"run": self.run.name, "voxel_size": float(self.voxel_size)},
                )
            return True
        return exists

    def _delete_data(self) -> None:
        if self.fs_overlay.exists(self.overlay_path):
            self.fs_overlay.rm(self.overlay_path, recursive=True)
        if self.run.root.mode == "A":
            key = {"run": self.run.name, "voxel_size": float(self.voxel_size)}
            self._index.remove_row("copick/voxel_spacings", key)


# -----------------------------------------------------------------------------
# Runs
# -----------------------------------------------------------------------------


class CopickRunMLC(CopickRunOverlay):
    root: "CopickRootMLC"

    def _voxel_spacing_factory(self) -> Tuple[Type[CopickVoxelSpacingMLC], Type[CopickVoxelSpacingMeta]]:
        return CopickVoxelSpacingMLC, CopickVoxelSpacingMeta

    def _picks_factory(self) -> Type[CopickPicksMLC]:
        return CopickPicksMLC

    def _mesh_factory(self) -> Tuple[Type[CopickMeshMLC], Type[CopickMeshMeta]]:
        return CopickMeshMLC, CopickMeshMeta

    def _segmentation_factory(self) -> Tuple[Type[CopickSegmentationMLC], Type[CopickSegmentationMeta]]:
        return CopickSegmentationMLC, CopickSegmentationMeta

    @property
    def _index(self) -> CroissantIndex:
        return self.root.index

    @property
    def static_path(self) -> str:
        return f"{_join_url(self.root.index.base_url, 'ExperimentRuns')}/{self.name}"

    @property
    def overlay_path(self) -> str:
        if self.root.overlay_base_url:
            return f"{self.root.overlay_base_url}/ExperimentRuns/{self.name}"
        # Mode A: overlay == base
        return f"{self.root.index.base_url}/ExperimentRuns/{self.name}"

    @property
    def fs_static(self) -> AbstractFileSystem:
        fs, _ = _fs_for_url(self.static_path)
        return fs

    @property
    def fs_overlay(self) -> AbstractFileSystem:
        return self.root.fs_overlay

    @property
    def static_is_overlay(self) -> bool:
        return self.root.mode == "A"

    # ----- static queries: filter index rows by run name -----

    def _query_static_voxel_spacings(self) -> List[CopickVoxelSpacingMLC]:
        # Mode A: static_is_overlay — everything is in the overlay query.
        if self.root.mode == "A":
            return []
        results = []
        seen = set()
        for row in self._index.voxel_spacings:
            if row.get("run") == self.name:
                vs = float(row["voxel_size"])
                if vs in seen:
                    continue
                seen.add(vs)
                results.append(
                    CopickVoxelSpacingMLC(
                        meta=CopickVoxelSpacingMeta(voxel_size=vs),
                        run=self,
                    ),
                )
        return results

    def _query_overlay_voxel_spacings(self) -> List[CopickVoxelSpacingMLC]:
        fs = self.fs_overlay
        if fs is None:
            return []
        loc = f"{self.overlay_path}/VoxelSpacing"
        try:
            paths = set(fs.glob(loc + "*") + fs.glob(loc + "*/"))
        except FileNotFoundError:
            return []
        paths = [p.rstrip("/") for p in paths]
        spacings = []
        for p in paths:
            suffix = p[len(loc) :] if p.startswith(loc) else ""
            try:
                spacings.append(float(suffix))
            except ValueError:
                continue
        return [CopickVoxelSpacingMLC(meta=CopickVoxelSpacingMeta(voxel_size=s), run=self) for s in spacings]

    def _query_static_picks(self) -> List[CopickPicksMLC]:
        # Mode A: static_is_overlay — everything is in the overlay query.
        if self.root.mode == "A":
            return []
        results = []
        for row in self._index.picks:
            if row.get("run") == self.name:
                results.append(
                    CopickPicksMLC(
                        run=self,
                        file=CopickPicksFile(
                            pickable_object_name=row["object_name"],
                            user_id=row["user_id"],
                            session_id=row["session_id"],
                        ),
                        read_only=True,
                    ),
                )
        return results

    def _query_overlay_picks(self) -> List[CopickPicksMLC]:
        if self.root.mode == "A":
            # Mode A: the Croissant index is the authoritative list of writable picks.
            return [
                CopickPicksMLC(
                    run=self,
                    file=CopickPicksFile(
                        pickable_object_name=row["object_name"],
                        user_id=row["user_id"],
                        session_id=row["session_id"],
                    ),
                    read_only=False,
                )
                for row in self._index.picks
                if row.get("run") == self.name
            ]
        fs = self.fs_overlay
        if fs is None:
            return []
        pick_loc = f"{self.overlay_path}/Picks/"
        try:
            paths = fs.glob(pick_loc + "*.json")
        except FileNotFoundError:
            return []
        names = [p.replace(pick_loc, "").replace(".json", "") for p in paths]
        names = [n for n in names if not n.startswith(".")]
        result = []
        for n in names:
            parts = n.split("_", 2)
            if len(parts) != 3:
                continue
            u, s, o = parts
            result.append(
                CopickPicksMLC(
                    run=self,
                    file=CopickPicksFile(pickable_object_name=o, user_id=u, session_id=s),
                    read_only=False,
                ),
            )
        return result

    def _query_static_meshes(self) -> List[CopickMeshMLC]:
        # Mode A: static_is_overlay — everything is in the overlay query.
        if self.root.mode == "A":
            return []
        results = []
        for row in self._index.meshes:
            if row.get("run") == self.name:
                results.append(
                    CopickMeshMLC(
                        run=self,
                        meta=CopickMeshMeta(
                            pickable_object_name=row["object_name"],
                            user_id=row["user_id"],
                            session_id=row["session_id"],
                        ),
                        read_only=True,
                    ),
                )
        return results

    def _query_overlay_meshes(self) -> List[CopickMeshMLC]:
        if self.root.mode == "A":
            # Mode A: the Croissant index is the authoritative list of writable meshes.
            return [
                CopickMeshMLC(
                    run=self,
                    meta=CopickMeshMeta(
                        pickable_object_name=row["object_name"],
                        user_id=row["user_id"],
                        session_id=row["session_id"],
                    ),
                    read_only=False,
                )
                for row in self._index.meshes
                if row.get("run") == self.name
            ]
        fs = self.fs_overlay
        if fs is None:
            return []
        mesh_loc = f"{self.overlay_path}/Meshes/"
        try:
            paths = fs.glob(mesh_loc + "*.glb")
        except FileNotFoundError:
            return []
        names = [p.replace(mesh_loc, "").replace(".glb", "") for p in paths]
        names = [n for n in names if not n.startswith(".")]
        result = []
        for n in names:
            parts = n.split("_", 2)
            if len(parts) != 3:
                continue
            u, s, o = parts
            result.append(
                CopickMeshMLC(
                    run=self,
                    meta=CopickMeshMeta(pickable_object_name=o, user_id=u, session_id=s),
                    read_only=False,
                ),
            )
        return result

    def _query_static_segmentations(self) -> List[CopickSegmentationMLC]:
        # Mode A: static_is_overlay — everything is in the overlay query.
        if self.root.mode == "A":
            return []
        results = []
        for row in self._index.segmentations:
            if row.get("run") == self.name:
                results.append(
                    CopickSegmentationMLC(
                        run=self,
                        meta=CopickSegmentationMeta(
                            is_multilabel=bool(row["is_multilabel"]),
                            voxel_size=float(row["voxel_size"]),
                            user_id=row["user_id"],
                            session_id=row["session_id"],
                            name=row["name"],
                        ),
                        read_only=True,
                    ),
                )
        return results

    def _query_overlay_segmentations(self) -> List[CopickSegmentationMLC]:
        if self.root.mode == "A":
            # Mode A: the Croissant index is the authoritative list of writable segmentations.
            return [
                CopickSegmentationMLC(
                    run=self,
                    meta=CopickSegmentationMeta(
                        is_multilabel=bool(row["is_multilabel"]),
                        voxel_size=float(row["voxel_size"]),
                        user_id=row["user_id"],
                        session_id=row["session_id"],
                        name=row["name"],
                    ),
                    read_only=False,
                )
                for row in self._index.segmentations
                if row.get("run") == self.name
            ]
        fs = self.fs_overlay
        if fs is None:
            return []
        seg_loc = f"{self.overlay_path}/Segmentations/"
        try:
            paths = fs.glob(seg_loc + "*.zarr") + fs.glob(seg_loc + "*.zarr/")
        except FileNotFoundError:
            return []
        paths = [p.rstrip("/") for p in paths if fs.isdir(p)]
        names = [p.replace(seg_loc, "").replace(".zarr", "") for p in paths]
        names = [n for n in names if not n.startswith(".")]
        names = list(set(names))
        result = []
        for n in names:
            parts = n.split("_", 3)
            if len(parts) < 4:
                continue
            vs, u, s, rest = parts
            try:
                vs_f = float(vs)
            except ValueError:
                continue
            if rest.endswith("-multilabel"):
                nm = rest[: -len("-multilabel")]
                ml = True
            else:
                nm = rest
                ml = False
            result.append(
                CopickSegmentationMLC(
                    run=self,
                    meta=CopickSegmentationMeta(
                        is_multilabel=ml,
                        voxel_size=vs_f,
                        user_id=u,
                        session_id=s,
                        name=nm,
                    ),
                    read_only=False,
                ),
            )
        return result

    def ensure(self, create: bool = False) -> bool:
        exists = self.name in self._index.runs_by_name
        # Fall back to filesystem check: the run may have been added externally
        # (e.g. by another process) after our in-memory index was populated.
        if not exists:
            try:
                exists = self.fs_overlay.exists(self.overlay_path)
            except Exception:
                exists = False

        if not exists and create:
            fs = self.fs_overlay
            fs.makedirs(self.overlay_path, exist_ok=True)
            if self.root.mode == "A":
                self._index.add_row("copick/runs", {"name": self.name})
            return True
        return exists

    def _delete_data(self) -> None:
        if self.fs_overlay.exists(self.overlay_path):
            self.fs_overlay.rm(self.overlay_path, recursive=True)
        if self.root.mode == "A":
            self._index.remove_row("copick/runs", {"name": self.name})


# -----------------------------------------------------------------------------
# Objects
# -----------------------------------------------------------------------------


class CopickObjectMLC(CopickObjectOverlay):
    root: "CopickRootMLC"

    @property
    def _index(self) -> CroissantIndex:
        return self.root.index

    def _find_row(self) -> Optional[Dict[str, Any]]:
        for row in self._index.objects:
            if row.get("name") == self.name:
                return row
        return None

    @property
    def static_path(self) -> Optional[str]:
        row = self._find_row()
        if row is None:
            return None
        return _join_url(self._index.base_url, row["url"])

    @property
    def overlay_path(self) -> str:
        if self.root.overlay_base_url:
            return f"{self.root.overlay_base_url}/Objects/{self.name}.zarr"
        return f"{self.root.index.base_url}/Objects/{self.name}.zarr"

    @property
    def fs_static(self) -> AbstractFileSystem:
        sp = self.static_path
        if sp is None:
            return None
        fs, _ = _fs_for_url(sp)
        return fs

    @property
    def fs_overlay(self) -> AbstractFileSystem:
        return self.root.fs_overlay

    def zarr(self) -> Union[None, zarr.storage.FSStore]:
        if not self.is_particle:
            return None
        if self.read_only:
            sp = self.static_path
            if sp is None:
                return None
            fs = self.fs_static
            return zarr.storage.FSStore(
                sp,
                fs=fs,
                mode="r",
                key_separator="/",
                dimension_separator="/",
                create=False,
            )
        fs = self.fs_overlay
        path = self.overlay_path
        create = not fs.exists(path)
        store = zarr.storage.FSStore(
            path,
            fs=fs,
            mode="w",
            key_separator="/",
            dimension_separator="/",
            create=create,
        )
        if create and self.root.mode == "A":
            rel = f"Objects/{self.name}.zarr"
            self._index.add_row("copick/objects", {"name": self.name, "url": rel})
        return store

    def _delete_data(self) -> None:
        fs = self.fs_overlay
        if fs.exists(self.overlay_path):
            fs.rm(self.overlay_path, recursive=True)
        if self.root.mode == "A":
            self._index.remove_row("copick/objects", {"name": self.name})


# -----------------------------------------------------------------------------
# Root
# -----------------------------------------------------------------------------


class CopickRootMLC(CopickRoot):
    """Copick root backed by an mlcroissant manifest.

    Mode A (self-contained): ``overlay_root`` is None and ``copick:baseUrl`` is
    writable. Writes go to the project tree and auto-sync to the CSVs.

    Mode B (remote + overlay): ``overlay_root`` is set and the Croissant is
    read-only. Writes go to the overlay only; the Croissant is not updated.
    """

    def __init__(self, config: CopickConfigMLCroissant):
        # Build the Croissant index first, then apply copick:config to CopickConfig
        self.index = CroissantIndex.from_url(
            config.croissant_url,
            base_url_override=config.croissant_base_url,
            fs_args=config.croissant_fs_args or {},
        )
        # Merge copick:config content into the CopickConfig the user supplied.
        # The Croissant on disk is authoritative for pickable_objects / user_id /
        # session_id / name / description / version. We always overwrite from the
        # Croissant when a value is present there (the config we build in
        # from_croissant uses default sentinels, not real values).
        cfg_block = self.index.config_block
        for key in ("name", "description", "version", "user_id", "session_id"):
            if cfg_block.get(key) is not None:
                setattr(config, key, cfg_block[key])
        if not config.pickable_objects and "pickable_objects" in cfg_block:
            config.pickable_objects = [PickableObject(**po) for po in cfg_block["pickable_objects"]]

        super().__init__(config)

        # Overlay fs (Mode B only)
        from copick.util.reconnecting_fs import ReconnectingFileSystem

        self.fs_overlay: AbstractFileSystem
        self.overlay_base_url: Optional[str] = None
        if config.overlay_root:
            self.fs_overlay = ReconnectingFileSystem(config.overlay_root, config.overlay_fs_args or {})
            self.overlay_base_url = self.fs_overlay._strip_protocol(config.overlay_root).rstrip("/")
            self.fs_overlay._root_ref = weakref.ref(self)
        else:
            # Mode A: overlay is the Croissant's base URL location.
            # auto_mkdir=True mirrors the filesystem backend's default; without
            # it LocalFileSystem refuses to create parent chunk dirs for zarr
            # stores.
            base = self.index.base_url or ""
            if base:
                self.fs_overlay, _ = _fs_for_url(base, auto_mkdir=True)
            else:
                self.fs_overlay = fsspec.filesystem("file", auto_mkdir=True)
            self.overlay_base_url = None  # signals Mode A

    @classmethod
    def from_file(cls, path: str) -> "CopickRootMLC":
        """Initialise from a copick config JSON (not the Croissant itself)."""
        with open(path, "r") as f:
            data = json.load(f)
        return cls(CopickConfigMLCroissant(**data))

    @property
    def mode(self) -> str:
        return "B" if self.overlay_base_url else "A"

    # ----- Factories -----
    def _run_factory(self) -> Tuple[Type[CopickRunMLC], Type[CopickRunMeta]]:
        return CopickRunMLC, CopickRunMeta

    def _object_factory(self) -> Tuple[Type[CopickObjectMLC], Type[PickableObject]]:
        return CopickObjectMLC, PickableObject

    # ----- Queries -----
    def query(self) -> List[CopickRunMLC]:
        names = set(self.index.runs_by_name.keys())

        # Mode B: also discover runs that exist only in the overlay (created
        # locally after the Croissant was produced) via a glob under
        # ExperimentRuns/.
        if self.mode == "B" and self.overlay_base_url:
            run_dir = f"{self.overlay_base_url}/ExperimentRuns/"
            try:
                entries = self.fs_overlay.glob(run_dir + "*") + self.fs_overlay.glob(run_dir + "*/")
            except FileNotFoundError:
                entries = []
            for entry in entries:
                stripped = entry.rstrip("/")
                name = stripped.rsplit("/", 1)[-1]
                if name and not name.startswith("."):
                    names.add(name)

        runs = []
        for name in sorted(names):
            runs.append(CopickRunMLC(root=self, meta=CopickRunMeta(name=name)))
        return runs

    def _query_objects(self):
        clz, _ = self._object_factory()
        objects = []
        static_names = {row["name"] for row in self.index.objects}
        for obj_meta in self.config.pickable_objects:
            if self.mode == "A":
                read_only = False
            else:
                # Mode B: object is read-only if present in static only.
                overlay_exists = self.fs_overlay.exists(f"{self.overlay_base_url}/Objects/{obj_meta.name}.zarr")
                read_only = obj_meta.name in static_names and not overlay_exists
            objects.append(clz(self, obj_meta, read_only=read_only))
        self._objects = objects

    # ----- Sync controls -----
    def sync(self) -> None:
        """Flush any dirty CSVs and rewrite metadata.json."""
        self.index.commit()

    def refresh(self) -> None:
        """Reload the Croissant index from disk and reset child caches.

        Each :class:`CopickRootMLC` maintains its own in-memory Croissant
        index for performance. When another process (or another root
        instance in the same process) has modified the project — e.g. after
        an in-process ``copick sync`` CLI invocation — call ``refresh()``
        on the original root to pick up those changes.
        """
        self.index.reload()
        super().refresh()

    class _BatchCtx:
        def __init__(self, root: "CopickRootMLC"):
            self.root = root

        def __enter__(self):
            self.root.index.defer_commit()
            return self.root

        def __exit__(self, exc_type, exc, tb):
            self.root.index.resume_commit()
            self.root.index.commit()
            return False

    def batch(self):
        """Context manager that defers commits until exit.

        Usage:
            with root.batch():
                for ...:
                    run.new_picks(...).store()
        """
        return CopickRootMLC._BatchCtx(self)

    def reconnect(self) -> None:
        if hasattr(self.fs_overlay, "_reconnect"):
            self.fs_overlay._reconnect()
