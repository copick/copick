"""Time-limited, lock-protected disk cache for CryoET Data Portal query results.

A portal-backed copick project (:class:`~copick.impl.cryoet_data_portal.CopickRootCDP`)
eagerly queries the CryoET Data Portal when it is constructed. Running many concurrent
processing jobs — each building its own root — multiplies these queries until the portal
starts returning HTTP 503. This module persists the raw portal query results to disk so
subsequent process startups read the cache instead of re-querying.

Design invariants:

* **Correctness rests on atomic rename**, not on the lock. Writes go to a unique temp
  path and are atomically renamed into place, so a reader never observes a partial file.
* **The lock only reduces the cold-start stampede.** It is a best-effort dedup so that,
  when many jobs start at once with no cache yet, one fetches and the rest read the
  published result. It is a no-op on backends where an ``O_EXCL`` lock is meaningless
  (e.g. S3 overlays) or when :mod:`filelock` is unavailable.
* **Caching can only make startup faster or, worst case, exactly as slow as today.** Every
  failure path (unreadable/corrupt cache, unwritable location, lock timeout) degrades to
  querying the portal as before; it never breaks project construction.

The module operates purely on JSON-serializable ``data`` dicts (``{key: [dict, ...]}``) and
a config object; it never imports the portal implementation, so both the root and the CLI
(``copick cache ...``) can reuse the fingerprint/path/clear helpers.
"""

import json
import os
import uuid
from contextlib import nullcontext, suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Callable, Dict, List, Optional

from copick.util.log import get_logger

logger = get_logger(__name__)

# Shape types fetched for the annotation cache. Defined here (not in the portal impl) so the
# fingerprint and the portal fetch share a single source of truth without a circular import.
SHAPE_TYPES = ["Point", "OrientedPoint", "SegmentationMask"]

# Bump when the on-disk document layout changes; a mismatch invalidates old caches.
SCHEMA_VERSION = 1

# Keys of the serializable ``data`` payload (raw portal query results, one list of dicts each).
DATA_KEYS = (
    "runs",
    "annotation_files",
    "annotation_shapes",
    "annotations",
    "annotation_authors",
    "voxel_spacings",
    "tomograms",
    "tomogram_authors",
)

_CACHE_DIRNAME = ".copick_cache"


def _cdp_version() -> str:
    """Version of the installed ``cryoet_data_portal`` SDK (folded into the fingerprint)."""
    try:
        import cryoet_data_portal as cdp

        return str(getattr(cdp, "__version__", "unknown"))
    except Exception:  # noqa: BLE001 - version is best-effort
        return "unknown"


# ---------------------------------------------------------------------------
# Settings (config fields + environment overrides)
# ---------------------------------------------------------------------------


@dataclass
class CacheSettings:
    """Resolved cache knobs (environment overrides config field, which overrides default)."""

    enabled: bool = True
    ttl_seconds: int = 86400  # 24h; <= 0 means "never expire"
    lock_timeout_seconds: int = 60
    cache_dir: Optional[str] = None


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    val = raw.strip().lower()
    if val in ("1", "true", "yes", "on"):
        return True
    if val in ("0", "false", "no", "off"):
        return False
    logger.warning("Ignoring malformed boolean env %s=%r; using %s.", name, raw, default)
    return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw.strip())
    except ValueError:
        logger.warning("Ignoring malformed integer env %s=%r; using %s.", name, raw, default)
        return default


def _env_str(name: str, default: Optional[str]) -> Optional[str]:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw


def settings_from_config(config: Any) -> CacheSettings:
    """Resolve cache settings from a ``CopickConfigCDP`` plus environment overrides."""
    return CacheSettings(
        enabled=_env_bool("COPICK_PORTAL_CACHE", bool(getattr(config, "portal_cache", True))),
        ttl_seconds=_env_int(
            "COPICK_PORTAL_CACHE_TTL",
            int(getattr(config, "portal_cache_ttl_seconds", 86400)),
        ),
        lock_timeout_seconds=_env_int(
            "COPICK_PORTAL_CACHE_LOCK_TIMEOUT",
            int(getattr(config, "portal_cache_lock_timeout_seconds", 60)),
        ),
        cache_dir=_env_str("COPICK_PORTAL_CACHE_DIR", getattr(config, "portal_cache_dir", None)),
    )


# ---------------------------------------------------------------------------
# Fingerprint
# ---------------------------------------------------------------------------


def object_identifiers(config: Any) -> List[str]:
    """Sorted list of pickable-object identifiers (the portal ``object_id`` filter keys).

    Matches ``CopickRootCDP.go_map`` keys: identifiers that are not ``None``. The annotation
    queries filter by these, so the cache is only valid for the same identifier set.
    """
    ids = [
        po.identifier for po in getattr(config, "pickable_objects", []) if getattr(po, "identifier", None) is not None
    ]
    return sorted(ids)


def compute_fingerprint(dataset_ids: List[int], identifiers: List[str]) -> str:
    """Stable hash of everything that changes the portal query result set."""
    payload = {
        "dataset_ids": sorted(int(d) for d in dataset_ids),
        "identifiers": sorted(identifiers),
        "shape_types": SHAPE_TYPES,
        "cdp_version": _cdp_version(),
        "schema_version": SCHEMA_VERSION,
    }
    return sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def fingerprint_for_config(config: Any) -> str:
    """Compute the cache fingerprint for a ``CopickConfigCDP`` (root and CLI share this)."""
    return compute_fingerprint(list(getattr(config, "dataset_ids", [])), object_identifiers(config))


# ---------------------------------------------------------------------------
# Cache locations (overlay primary, local fallback)
# ---------------------------------------------------------------------------


@dataclass
class CacheLocation:
    """One candidate cache location: an fsspec filesystem plus the cache/lock paths."""

    fs: Any
    directory: str
    path: str
    # OS path when this location is on a local filesystem (enables atomic os.replace and a
    # filelock ``SoftFileLock``); ``None`` for remote backends (atomic-rename-only, no lock).
    local_path: Optional[str] = None

    @property
    def lockable(self) -> bool:
        return self.local_path is not None


def _fs_is_local(fs: Any) -> bool:
    inner = getattr(fs, "_fs", fs)  # unwrap ReconnectingFileSystem
    proto = getattr(inner, "protocol", None)
    protos = proto if isinstance(proto, (list, tuple)) else (proto,)
    return any(p in ("file", "local") for p in protos)


def _local_location(file_path: str) -> CacheLocation:
    import fsspec

    fs = fsspec.filesystem("file", auto_mkdir=True)
    directory = os.path.dirname(file_path)
    return CacheLocation(fs=fs, directory=directory, path=file_path, local_path=file_path)


def _xdg_cache_file(fingerprint: str) -> str:
    base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return os.path.join(base, "copick", "portal", f"portal_{fingerprint}.json")


def build_overlay_fs(config: Any):
    """Build an overlay filesystem + stripped root from a config (used by the CLI)."""
    from copick.util.reconnecting_fs import ReconnectingFileSystem

    fs = ReconnectingFileSystem(config.overlay_root, getattr(config, "overlay_fs_args", None) or {})
    root_overlay = fs._strip_protocol(config.overlay_root)  # noqa: SLF001
    return fs, root_overlay


def resolve_locations(
    fingerprint: str,
    settings: CacheSettings,
    fs_overlay: Any = None,
    root_overlay: Optional[str] = None,
) -> List[CacheLocation]:
    """Ordered candidate cache locations. Reads try each in order; writes use the first that succeeds.

    * A pinned ``cache_dir`` short-circuits to a single local location.
    * Otherwise: the overlay (``{root_overlay}/.copick_cache/portal_{fp}.json``) first, then a
      local ``~/.cache/copick/portal/`` fallback for read-only overlays.
    """
    filename = f"portal_{fingerprint}.json"

    if settings.cache_dir:
        return [_local_location(os.path.join(settings.cache_dir, filename))]

    locations: List[CacheLocation] = []
    if fs_overlay is not None and root_overlay:
        directory = f"{root_overlay.rstrip('/')}/{_CACHE_DIRNAME}"
        path = f"{directory}/{filename}"
        local_path = path if _fs_is_local(fs_overlay) else None
        locations.append(CacheLocation(fs=fs_overlay, directory=directory, path=path, local_path=local_path))

    locations.append(_local_location(_xdg_cache_file(fingerprint)))
    return locations


# ---------------------------------------------------------------------------
# Load / store
# ---------------------------------------------------------------------------


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _load_location(loc: CacheLocation, fingerprint: str, ttl_seconds: int) -> Optional[Dict[str, Any]]:
    """Return the ``data`` payload from ``loc`` if present, valid, and fresh; else ``None``."""
    try:
        if not loc.fs.exists(loc.path):
            return None
        with loc.fs.open(loc.path, "r") as f:
            doc = json.load(f)
        if doc.get("schema_version") != SCHEMA_VERSION:
            logger.debug("Portal cache %s: schema mismatch, ignoring.", loc.path)
            return None
        if doc.get("fingerprint") != fingerprint:
            logger.debug("Portal cache %s: fingerprint mismatch, ignoring.", loc.path)
            return None
        if ttl_seconds and ttl_seconds > 0:
            created = doc.get("created")
            try:
                age = (_now_utc() - datetime.fromisoformat(created)).total_seconds()
            except (TypeError, ValueError):
                return None
            if age > ttl_seconds:
                logger.debug("Portal cache %s: stale (age %.0fs > ttl %ds).", loc.path, age, ttl_seconds)
                return None
        data = doc.get("data")
        if not isinstance(data, dict):
            return None
        logger.debug("Portal cache hit: %s", loc.path)
        return data
    except Exception as e:  # noqa: BLE001 - any read failure is a cache miss
        logger.debug("Portal cache %s: unreadable (%s), ignoring.", loc.path, e)
        return None


def _atomic_write_text(loc: CacheLocation, text: str) -> None:
    """Write ``text`` to ``loc.path`` atomically (unique temp + rename)."""
    with suppress(Exception):
        loc.fs.makedirs(loc.directory, exist_ok=True)

    token = f"{os.getpid()}.{uuid.uuid4().hex}"
    if loc.local_path is not None:
        tmp = f"{loc.local_path}.{token}.tmp"
        with open(tmp, "w") as f:
            f.write(text)
            f.flush()
            with suppress(OSError):
                os.fsync(f.fileno())
        os.replace(tmp, loc.local_path)
        return

    # Remote backend: unique temp key + rename (atomic on POSIX-backed remotes; on stores
    # without atomic rename the object is still written whole, never byte-partial).
    tmp = f"{loc.path}.{token}.tmp"
    with loc.fs.open(tmp, "w") as f:
        f.write(text)
    try:
        loc.fs.mv(tmp, loc.path)
    except Exception:  # noqa: BLE001 - fall back to a direct overwrite
        with loc.fs.open(loc.path, "w") as f:
            f.write(text)
        with suppress(Exception):
            loc.fs.rm(tmp)


def _store_location(
    loc: CacheLocation,
    fingerprint: str,
    dataset_ids: List[int],
    data: Dict[str, Any],
) -> bool:
    """Serialize and atomically write the cache document to ``loc``. Returns success."""
    try:
        doc = {
            "schema_version": SCHEMA_VERSION,
            "created": _now_utc().isoformat(),
            "cdp_version": _cdp_version(),
            "dataset_ids": sorted(int(d) for d in dataset_ids),
            "fingerprint": fingerprint,
            "data": data,
        }
        # default=str coerces cdp date fields (deposition/release/last_modified) that the
        # consumers never read; _Portal* models ignore the extra keys on load.
        text = json.dumps(doc, default=str)
        _atomic_write_text(loc, text)
        logger.debug("Portal cache written: %s", loc.path)
        return True
    except Exception as e:  # noqa: BLE001 - a failed store just means the next process refetches
        logger.info("Could not write portal cache to %s (%s); continuing without it.", loc.path, e)
        return False


def _make_lock(loc: CacheLocation, timeout: int):
    """A ``SoftFileLock`` for lockable local locations, else a no-op context manager."""
    if not loc.lockable:
        return nullcontext()
    try:
        from filelock import SoftFileLock
    except Exception:  # noqa: BLE001 - filelock optional; degrade to atomic-rename-only
        return nullcontext()
    with suppress(Exception):
        os.makedirs(os.path.dirname(loc.local_path), exist_ok=True)
    return SoftFileLock(f"{loc.local_path}.lock", timeout=max(1, timeout))


def get_or_fetch(
    fingerprint: str,
    dataset_ids: List[int],
    settings: CacheSettings,
    fetch_fn: Callable[[], Dict[str, Any]],
    fs_overlay: Any = None,
    root_overlay: Optional[str] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Return the portal ``data`` payload from cache, or fetch it once and persist it.

    ``fetch_fn`` performs the portal queries and returns a JSON-serializable ``data`` dict; it
    is invoked **at most once**. When caching is disabled, ``fetch_fn`` is called directly.
    """
    if not settings.enabled:
        return fetch_fn()

    locations = resolve_locations(fingerprint, settings, fs_overlay, root_overlay)
    if not locations:
        return fetch_fn()

    # Fast read pass (lock-free): any fresh hit wins.
    if not force:
        for loc in locations:
            data = _load_location(loc, fingerprint, settings.ttl_seconds)
            if data is not None:
                return data

    # Miss: fetch once, gated by a per-location lock to collapse the cold-start herd.
    fetched: Dict[str, Dict[str, Any]] = {}

    def fetch_once() -> Dict[str, Any]:
        if "data" not in fetched:
            fetched["data"] = fetch_fn()
        return fetched["data"]

    for loc in locations:
        try:
            with _make_lock(loc, settings.lock_timeout_seconds):
                if not force:
                    # Double-check: a sibling may have published while we waited on the lock.
                    data = _load_location(loc, fingerprint, settings.ttl_seconds)
                    if data is not None:
                        return data
                data = fetch_once()
                if _store_location(loc, fingerprint, dataset_ids, data):
                    return data
                # Store failed at this location; try the next candidate.
        except Exception as e:  # noqa: BLE001 - includes filelock Timeout
            logger.info("Portal cache lock/store at %s failed (%s); trying next location.", loc.path, e)
            if not force:
                data = _load_location(loc, fingerprint, settings.ttl_seconds)
                if data is not None:
                    return data

    # No location could persist the cache — return the (already) fetched data uncached.
    return fetch_once()


# ---------------------------------------------------------------------------
# Inspection / invalidation (used by the CLI)
# ---------------------------------------------------------------------------


@dataclass
class CacheStatus:
    """Read-only status of a single cache location (for ``copick cache info``)."""

    path: str
    exists: bool
    fresh: Optional[bool] = None
    created: Optional[str] = None
    age_seconds: Optional[float] = None
    lockable: bool = False


def status_for_config(
    config: Any,
    fs_overlay: Any = None,
    root_overlay: Optional[str] = None,
) -> List[CacheStatus]:
    """Report each candidate cache location's presence and freshness. Never queries the portal."""
    settings = settings_from_config(config)
    if fs_overlay is None:
        fs_overlay, root_overlay = build_overlay_fs(config)
    fingerprint = fingerprint_for_config(config)
    locations = resolve_locations(fingerprint, settings, fs_overlay, root_overlay)

    out: List[CacheStatus] = []
    for loc in locations:
        status = CacheStatus(path=loc.path, exists=False, lockable=loc.lockable)
        try:
            if loc.fs.exists(loc.path):
                status.exists = True
                with loc.fs.open(loc.path, "r") as f:
                    doc = json.load(f)
                status.created = doc.get("created")
                valid = doc.get("schema_version") == SCHEMA_VERSION and doc.get("fingerprint") == fingerprint
                if status.created:
                    with suppress(TypeError, ValueError):
                        age = (_now_utc() - datetime.fromisoformat(status.created)).total_seconds()
                        status.age_seconds = age
                        ttl = settings.ttl_seconds
                        status.fresh = valid and (ttl <= 0 or age <= ttl)
                else:
                    status.fresh = valid
        except Exception as e:  # noqa: BLE001 - status is best-effort
            logger.debug("Could not read cache status at %s (%s).", loc.path, e)
        out.append(status)
    return out


def clear(
    config: Any,
    remove_all: bool = False,
    fs_overlay: Any = None,
    root_overlay: Optional[str] = None,
) -> List[str]:
    """Remove the portal disk cache for ``config``. Returns the removed paths. No portal query.

    With ``remove_all`` every ``portal_*.json`` in each candidate directory is removed (use when
    the pickable objects changed and the fingerprint no longer matches); otherwise only the file
    matching the current fingerprint is removed.
    """
    settings = settings_from_config(config)
    if fs_overlay is None:
        fs_overlay, root_overlay = build_overlay_fs(config)
    fingerprint = fingerprint_for_config(config)
    locations = resolve_locations(fingerprint, settings, fs_overlay, root_overlay)

    removed: List[str] = []
    for loc in locations:
        try:
            if remove_all:
                for path in loc.fs.glob(f"{loc.directory}/portal_*.json"):
                    with suppress(Exception):
                        loc.fs.rm(path)
                        removed.append(path)
            elif loc.fs.exists(loc.path):
                loc.fs.rm(loc.path)
                removed.append(loc.path)
        except Exception as e:  # noqa: BLE001 - clearing is best-effort per location
            logger.debug("Could not clear cache at %s (%s).", loc.path, e)
    return removed
