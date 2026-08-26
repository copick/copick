"""Copick backend serving tomograms from an Embrella server without duplicating data.

Embrella (https://github.com/czimaginginstitute/embrella) is a cryo-ET data management
service. It exposes a public HTTP API listing per-session copick overlay projects and
serves the processing tree (AreTomo3/DenoisET output, including OME-Zarr tomograms)
through per-cluster static file servers.

This backend combines tomograms from multiple Embrella sessions into a single copick
project. The static (read-only) side are the tomogram zarrs in the processing tree,
addressed by ``(session, proc_run, recon_type, position)``. The writable overlay side
are the per-session copick projects that Embrella creates on the cluster, so
annotations made through this backend land in the same place as annotations made
through Embrella itself (run names follow the shared ``{session}_{position}``
convention).
"""

import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional, Tuple, Type

import fsspec
from fsspec import AbstractFileSystem
from fsspec.implementations.local import LocalFileSystem
from pydantic import BaseModel, Field, ValidationError, field_validator
from zarr.abc.store import Store

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
from copick.util.ome import UNITFACTOR, zarr_root_exists
from copick.util.store import copick_store

# Don't import Geometry at runtime to keep CLI snappy
if TYPE_CHECKING:
    from trimesh.parent import Geometry

logger = get_logger(__name__)

# Reconstruction type -> (workflow directory, volume subdirectory) in the processing
# tree. This mirrors Embrella's hardcoded AreTomo3 output convention. WBP volumes
# (vol002) exist as MRC only and are therefore not supported.
RECON_DIRS: Dict[str, Tuple[str, Optional[str]]] = {
    "dctf": ("aretomo3", "vol001"),
    "sart": ("aretomo3", "vol003"),
    "denoise": ("denoise", None),
}

# Known CZII cluster file servers. Overridable via the config's "clusters" field.
DEFAULT_CLUSTERS: Dict[str, Dict[str, str]] = {
    "czii": {"http_base": "https://czii-onsite.czbiohub.org/"},
    "bruno": {"http_base": "https://onsite.czbiohub.org/group.czii/"},
}

_VOL_SUFFIX = "_Vol.zarr"

_SSL_CONTEXT_CACHE: List[Any] = []


def _ssl_context():
    """Return an SSL context using certifi's CA bundle when available.

    Python environments (notably conda) frequently point OpenSSL at a missing default
    CA path; certifi (a transitive copick dependency) is the reliable fallback.
    """
    if not _SSL_CONTEXT_CACHE:
        import ssl

        try:
            import certifi

            _SSL_CONTEXT_CACHE.append(ssl.create_default_context(cafile=certifi.where()))
        except ImportError:
            _SSL_CONTEXT_CACHE.append(ssl.create_default_context())
    return _SSL_CONTEXT_CACHE[0]


async def _get_http_client(**kwargs):
    """aiohttp client factory for fsspec's HTTP filesystem using certifi's CA bundle."""
    import aiohttp

    connector = aiohttp.TCPConnector(ssl=_ssl_context())
    return aiohttp.ClientSession(connector=connector, **kwargs)


def _join_path(base: str, *parts: Optional[str]) -> str:
    """Join URL or POSIX path segments, skipping empty segments (no duplicate slashes)."""
    segments = [base.rstrip("/")]
    segments.extend(p.strip("/") for p in parts if p)
    return "/".join(segments)


def _http_get(url: str, accept: Optional[str] = None, timeout: int = 60, retries: int = 3) -> bytes:
    """GET a URL with retry/backoff on transient errors. 404s are raised immediately."""
    last_exc = None
    for attempt in range(retries):
        try:
            headers = {"Accept": accept} if accept else {}
            req = urllib.request.Request(url, headers=headers)
            context = _ssl_context() if url.startswith("https") else None
            with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:  # noqa: S310
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise
            last_exc = e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_exc = e

        if attempt < retries - 1:
            time.sleep(2**attempt + random.uniform(0, 0.5))

    raise ConnectionError(f"Failed to fetch {url} after {retries} attempts: {last_exc}")


def _entries_from_fs(fs: AbstractFileSystem, path: str) -> List[Dict[str, Any]]:
    """List a directory through fsspec, normalized to ``{"name", "is_dir"}`` entries.

    Junk entries produced by HTML link scraping (query links, parent references) are
    dropped.
    """
    entries = fs.ls(path.rstrip("/") + "/", detail=True)
    out = []
    for e in entries:
        name = e["name"].rstrip("/").rsplit("/", 1)[-1]
        if not name or name in (".", "..") or name.startswith("?"):
            continue
        out.append({"name": name, "is_dir": e.get("type") == "directory"})
    return out


def _list_dir_http(url: str) -> List[Dict[str, Any]]:
    """List a directory served by an Embrella file server.

    Prefers Caddy's JSON browse listing (``Accept: application/json``), falling back to
    fsspec's HTML link scraping.

    Returns:
        List of ``{"name": str, "is_dir": bool}`` entries.
    """
    listing_url = url.rstrip("/") + "/"
    try:
        data = json.loads(_http_get(listing_url, accept="application/json"))
        if isinstance(data, list):
            return [{"name": e["name"].rstrip("/"), "is_dir": bool(e.get("is_dir"))} for e in data]
    except (json.JSONDecodeError, KeyError, TypeError):
        pass

    # Fallback: HTML link scraping via fsspec's HTTP filesystem.
    proto = urllib.parse.urlparse(listing_url).scheme
    fs_kwargs = {"get_client": _get_http_client} if proto == "https" else {}
    fs = fsspec.filesystem(proto, **fs_kwargs)
    return _entries_from_fs(fs, listing_url)


def _positions_from_listing(entries: List[Dict[str, Any]]) -> List[str]:
    """Extract tomogram position stems (``{stem}_Vol.zarr``) from a directory listing.

    Enumeration is by suffix because position stems are not uniform (``Position_1_4``,
    but also e.g. ``L2_Series3A_Pos1.mrc``). Even/odd half-reconstructions are excluded.
    """
    stems = set()
    for e in entries:
        name = e["name"]
        if not name.endswith(_VOL_SUFFIX) or name.startswith("."):
            continue
        stem = name[: -len(_VOL_SUFFIX)]
        if stem.endswith(("_EVN", "_ODD")):
            continue
        stems.add(stem)
    return sorted(stems)


def _voxel_size_from_zattrs(zattrs: Dict[str, Any]) -> float:
    """Extract the level-0 voxel size (Angstrom) from OME-NGFF multiscales attributes.

    Handles both NGFF 0.4 (root-level ``multiscales``) and 0.5 (nested under ``ome``).
    """
    multiscales = zattrs.get("multiscales") or zattrs.get("ome", {}).get("multiscales")
    if not multiscales:
        raise ValueError("No multiscales metadata found in .zattrs")

    unit = "angstrom"
    for axis in multiscales[0].get("axes", []):
        if axis.get("type") == "space" and "unit" in axis:
            unit = axis["unit"]
            break

    for transform in multiscales[0]["datasets"][0].get("coordinateTransformations", []):
        if transform.get("type") == "scale":
            return float(transform["scale"][0]) * UNITFACTOR.get(unit, 1.0)

    raise ValueError("No scale transformation found in multiscales metadata")


class EmbrellaClusterSpec(BaseModel):
    """Location of one cluster's processing tree.

    Attributes:
        http_base: Base URL of the cluster's static file server.
        posix_base: POSIX base path of the processing tree (for local/ssh access).
    """

    http_base: str
    posix_base: str = "/hpc/projects/group.czii/"


class EmbrellaTomoSelection(BaseModel):
    """One selected tomogram version: a processing run and reconstruction type.

    Attributes:
        proc_run: Embrella processing run name, e.g. "run003" (an AreTomo3 run for
            dctf/sart, a DenoisET run for denoise).
        recon_type: Reconstruction type, one of "dctf", "sart", "denoise".
        cluster: Cluster (key into the config's clusters map) holding the tomogram
            zarrs. Defaults to the config's default_data_cluster.
        voxel_size: Voxel size override (Angstrom). If unset, the voxel size is read
            from the first tomogram's OME-Zarr metadata.
        positions: Pinned position stems. If unset, positions are enumerated by
            listing the volume directory.
    """

    proc_run: str
    recon_type: str
    cluster: Optional[str] = None
    voxel_size: Optional[float] = None
    positions: Optional[List[str]] = None

    @field_validator("recon_type")
    @classmethod
    def _validate_recon_type(cls, v: str) -> str:
        v = v.lower()
        if v == "wbp":
            raise ValueError(
                "WBP reconstructions are stored as MRC only (no zarr is produced) and cannot be "
                "served by the embrella backend. Choose one of 'dctf', 'sart' or 'denoise'.",
            )
        if v not in RECON_DIRS:
            raise ValueError(f"Unknown recon_type '{v}'. Supported types are {sorted(RECON_DIRS)}.")
        return v

    @field_validator("proc_run")
    @classmethod
    def _validate_proc_run(cls, v: str) -> str:
        if "_" in v:
            raise ValueError(
                "proc_run must not contain underscores (the derived tomo_type is used in "
                "'{tomo_type}_{feature_type}_features.zarr' file names).",
            )
        return v

    @property
    def tomo_type(self) -> str:
        """The copick tomo_type for this selection, e.g. "run003-dctf"."""
        return f"{self.proc_run}-{self.recon_type}"


class EmbrellaSessionSpec(BaseModel):
    """One Embrella session contributing tomograms to the project.

    Attributes:
        name: The Embrella session name (MsiSession.name), e.g. "25aug25a".
        tomograms: Tomogram versions to expose from this session.
        overlay_run: Name of the Embrella copick project (processing run under the
            copick plan) used as the annotation overlay for this session. If unset,
            the newest completed project reported by the Embrella API is used.
    """

    name: str
    tomograms: List[EmbrellaTomoSelection]
    overlay_run: Optional[str] = None


class CopickConfigEmbrella(CopickConfig):
    """Copick configuration for Embrella-backed projects.

    Attributes:
        embrella_base_url: Base URL of the Embrella server, e.g.
            "https://umbrella.czbiohub.org".
        sessions: Embrella sessions (and per-session tomogram versions) to combine.
        clusters: Cluster name -> file server locations. Defaults to the known CZII
            clusters.
        default_data_cluster: Cluster holding the tomogram zarrs unless overridden
            per selection.
        scope: The "{scope}.processing" path segment (falls back to this value when a
            session has no Embrella copick project reporting its scope).
        overlay_mode: How the per-session overlay projects are accessed: "local"
            (POSIX paths, on-cluster), "ssh" (fsspec sshfs, off-cluster) or "http"
            (read-only, via the file server).
        overlay_fs_args: Filesystem arguments for the overlay access (e.g. sshfs
            host/username for "ssh" mode).
        static_mode: How tomogram zarrs are read: "http" (default) or "local".
        static_fs_args: Filesystem arguments for static access.
        overlay_root: Optional project-level overlay URL used to store pickable
            object templates (Objects/). Without it, objects are config-only.
        overlay_root_fs_args: Filesystem arguments for the project-level overlay.
        exclude_overlay_tomo_types: Tomo types hidden from overlay projects (e.g.
            legacy duplicated "dctf" imports).
    """

    config_type: str = "embrella"
    embrella_base_url: str
    sessions: List[EmbrellaSessionSpec]

    clusters: Dict[str, EmbrellaClusterSpec] = Field(
        default_factory=lambda: {k: EmbrellaClusterSpec(**v) for k, v in DEFAULT_CLUSTERS.items()},
    )
    default_data_cluster: str = "czii"
    scope: str = "krios1"

    overlay_mode: Literal["local", "ssh", "http"] = "local"
    overlay_fs_args: Optional[Dict[str, Any]] = {}
    static_mode: Literal["http", "local"] = "http"
    static_fs_args: Optional[Dict[str, Any]] = {}

    overlay_root: Optional[str] = None
    overlay_root_fs_args: Optional[Dict[str, Any]] = {}

    exclude_overlay_tomo_types: List[str] = []


@dataclass
class EmbrellaSessionEntry:
    """Resolved per-session state: the overlay project location and scope."""

    session: str
    scope: str
    overlay_run: Optional[str] = None
    cluster_id: Optional[str] = None
    overlay_url: Optional[str] = None
    overlay_posix: Optional[str] = None
    read_only: bool = True
    pickable_objects: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class EmbrellaTomoRecord:
    """One static tomogram: a position of a (session, proc_run, recon_type) selection."""

    session: str
    proc_run: str
    recon_type: str
    position: str
    tomo_type: str
    voxel_size: float
    static_url: str
    static_posix: str


@dataclass
class EmbrellaIndex:
    """In-memory index of all static entities served by this project."""

    sessions: Dict[str, EmbrellaSessionEntry] = field(default_factory=dict)
    runs: Dict[str, Tuple[str, str]] = field(default_factory=dict)
    tomos_by_run: Dict[str, List[EmbrellaTomoRecord]] = field(default_factory=dict)


def _build_index(data: Dict[str, Any]) -> EmbrellaIndex:
    """Build the in-memory index from the (JSON-serializable) fetch payload."""
    index = EmbrellaIndex()

    for sess in data["sessions"]:
        entry = EmbrellaSessionEntry(
            session=sess["session"],
            scope=sess["scope"],
            overlay_run=sess.get("overlay_run"),
            cluster_id=sess.get("cluster_id"),
            overlay_url=sess.get("overlay_url"),
            overlay_posix=sess.get("overlay_posix"),
            read_only=sess.get("read_only", True),
            pickable_objects=sess.get("pickable_objects", []),
        )
        index.sessions[entry.session] = entry

        for sel in sess["selections"]:
            tomo_type = f"{sel['proc_run']}-{sel['recon_type']}"
            for position in sel["positions"]:
                run_name = f"{entry.session}_{position}"
                record = EmbrellaTomoRecord(
                    session=entry.session,
                    proc_run=sel["proc_run"],
                    recon_type=sel["recon_type"],
                    position=position,
                    tomo_type=tomo_type,
                    voxel_size=sel["voxel_size"],
                    static_url=_join_path(sel["data_url"], f"{position}{_VOL_SUFFIX}"),
                    static_posix=_join_path(sel["data_posix"], f"{position}{_VOL_SUFFIX}"),
                )
                index.runs[run_name] = (entry.session, position)
                index.tomos_by_run.setdefault(run_name, []).append(record)

    return index


class CopickPicksEmbrella(CopickPicksOverlay):
    """CopickPicks stored in the owning session's Embrella copick overlay project."""

    run: "CopickRunEmbrella"

    @property
    def path(self) -> str:
        return f"{self.run.overlay_path}/Picks/{self.user_id}_{self.session_id}_{self.pickable_object_name}.json"

    @property
    def directory(self) -> str:
        return f"{self.run.overlay_path}/Picks/"

    @property
    def fs(self) -> Optional[AbstractFileSystem]:
        return self.run.fs_overlay

    def _load(self) -> CopickPicksFile:
        if self.fs is None or not self.fs.exists(self.path):
            logger.critical(f"File not found: {self.path}")
            raise FileNotFoundError(f"File not found: {self.path}")

        with self.fs.open(self.path, "r") as f:
            data = json.load(f)

        return CopickPicksFile(**data)

    def _store(self) -> None:
        if self.fs is None:
            raise PermissionError(f"Run {self.run.name} has no writable Embrella overlay project.")

        if not self.fs.exists(self.directory):
            self.fs.makedirs(self.directory, exist_ok=True)

        with self.fs.open(self.path, "w") as f:
            json.dump(self.meta.model_dump(), f, indent=4)

    def _delete_data(self) -> None:
        if self.fs is not None and self.fs.exists(self.path):
            self.fs.rm(self.path)
        else:
            raise FileNotFoundError(f"File not found: {self.path}")


class CopickMeshEmbrella(CopickMeshOverlay):
    """CopickMesh stored in the owning session's Embrella copick overlay project."""

    run: "CopickRunEmbrella"

    @property
    def path(self) -> str:
        return f"{self.run.overlay_path}/Meshes/{self.user_id}_{self.session_id}_{self.pickable_object_name}.glb"

    @property
    def directory(self) -> str:
        return f"{self.run.overlay_path}/Meshes/"

    @property
    def fs(self) -> Optional[AbstractFileSystem]:
        return self.run.fs_overlay

    def _load(self) -> "Geometry":
        if self.fs is None or not self.fs.exists(self.path):
            logger.critical(f"File not found: {self.path}")
            raise FileNotFoundError(f"File not found: {self.path}")

        with self.fs.open(self.path, "rb") as f:
            # Defer trimesh import to keep CLI snappy (trimesh imports scipy)
            import trimesh

            scene = trimesh.load(f, file_type="glb")

        return scene

    def _store(self) -> None:
        if self.fs is None:
            raise PermissionError(f"Run {self.run.name} has no writable Embrella overlay project.")

        if not self.fs.exists(self.directory):
            self.fs.makedirs(self.directory, exist_ok=True)

        with self.fs.open(self.path, "wb") as f:
            _ = self._mesh.export(f, file_type="glb")

    def _delete_data(self) -> None:
        if self.fs is not None and self.fs.exists(self.path):
            self.fs.rm(self.path)
        else:
            raise FileNotFoundError(f"File not found: {self.path}")


class CopickSegmentationEmbrella(CopickSegmentationOverlay):
    """CopickSegmentation stored in the owning session's Embrella copick overlay project."""

    run: "CopickRunEmbrella"

    @property
    def filename(self) -> str:
        if self.is_multilabel:
            return f"{self.voxel_size:.3f}_{self.user_id}_{self.session_id}_{self.name}-multilabel.zarr"
        else:
            return f"{self.voxel_size:.3f}_{self.user_id}_{self.session_id}_{self.name}.zarr"

    @property
    def path(self) -> str:
        return f"{self.run.overlay_path}/Segmentations/{self.filename}"

    @property
    def fs(self) -> Optional[AbstractFileSystem]:
        return self.run.fs_overlay

    def zarr(self) -> Store:
        """Get the zarr store for the segmentation object.

        Returns:
            Store: The zarr store for the segmentation object.
        """
        if self.fs is None:
            raise PermissionError(f"Run {self.run.name} has no writable Embrella overlay project.")

        if self.read_only:
            mode = "r"
            create = False
        else:
            mode = "w"
            create = not self.fs.exists(self.path)

        return copick_store(self.fs, self.path, read_only=mode == "r", create=create)

    def _delete_data(self) -> None:
        if self.fs is not None and self.fs.exists(self.path):
            self.fs.rm(self.path, recursive=True)
        else:
            raise FileNotFoundError(f"File not found: {self.path}")


class CopickFeaturesEmbrella(CopickFeaturesOverlay):
    """CopickFeatures stored in the owning session's Embrella copick overlay project."""

    tomogram: "CopickTomogramEmbrella"

    @property
    def path(self) -> str:
        return f"{self.tomogram.overlay_stem}_{self.feature_type}_features.zarr"

    @property
    def fs(self) -> Optional[AbstractFileSystem]:
        return self.tomogram.fs_overlay

    def zarr(self) -> Store:
        """Get the zarr store for the features object.

        Returns:
            Store: The zarr store for the features object.
        """
        if self.fs is None:
            raise PermissionError(
                f"Run {self.tomogram.voxel_spacing.run.name} has no writable Embrella overlay project.",
            )

        if self.read_only:
            mode = "r"
            create = False
        else:
            mode = "w"
            create = not self.fs.exists(self.path)

        return copick_store(self.fs, self.path, read_only=mode == "r", create=create)

    def _delete_data(self) -> None:
        if self.fs is not None and self.fs.exists(self.path):
            self.fs.rm(self.path, recursive=True)
        else:
            raise FileNotFoundError(f"File not found: {self.path}")


class CopickTomogramMetaEmbrella(CopickTomogramMeta):
    """Tomogram metadata with Embrella provenance."""

    embrella_session: Optional[str] = None
    embrella_proc_run: Optional[str] = None
    embrella_recon_type: Optional[str] = None
    embrella_position: Optional[str] = None
    embrella_static_url: Optional[str] = None
    embrella_static_path: Optional[str] = None

    @classmethod
    def from_record(cls, record: EmbrellaTomoRecord) -> "CopickTomogramMetaEmbrella":
        return cls(
            tomo_type=record.tomo_type,
            embrella_session=record.session,
            embrella_proc_run=record.proc_run,
            embrella_recon_type=record.recon_type,
            embrella_position=record.position,
            embrella_static_url=record.static_url,
            embrella_static_path=record.static_posix,
        )


class CopickTomogramEmbrella(CopickTomogramOverlay):
    """CopickTomogram served in place from the Embrella processing tree (static) or the
    session's overlay project (writable)."""

    voxel_spacing: "CopickVoxelSpacingEmbrella"
    meta: CopickTomogramMetaEmbrella

    def _feature_factory(self) -> Tuple[Type[CopickFeaturesEmbrella], Type[CopickFeaturesMeta]]:
        return CopickFeaturesEmbrella, CopickFeaturesMeta

    @property
    def embrella_tomo(self) -> bool:
        """Whether this tomogram is served from the Embrella processing tree."""
        return self.meta.embrella_static_url is not None

    @property
    def static_path(self) -> Optional[str]:
        if not self.embrella_tomo:
            return None
        root = self.voxel_spacing.run.root
        if root.config.static_mode == "local":
            return self.meta.embrella_static_path
        return self.meta.embrella_static_url

    @property
    def fs_static(self) -> Optional[AbstractFileSystem]:
        if not self.embrella_tomo:
            return None
        return self.voxel_spacing.run.root._static_fs_for(self.static_path)

    @property
    def overlay_path(self) -> Optional[str]:
        base = self.voxel_spacing.overlay_path
        return None if base is None else f"{base}/{self.tomo_type}.zarr"

    @property
    def overlay_stem(self) -> Optional[str]:
        base = self.voxel_spacing.overlay_path
        return None if base is None else f"{base}/{self.tomo_type}"

    @property
    def fs_overlay(self) -> Optional[AbstractFileSystem]:
        return self.voxel_spacing.fs_overlay

    def _query_static_features(self) -> List[CopickFeaturesEmbrella]:
        # Embrella does not serve features.
        return []

    def _query_overlay_features(self) -> List[CopickFeaturesEmbrella]:
        if self.fs_overlay is None or self.overlay_stem is None:
            return []

        root = self.voxel_spacing.run.root
        entries = root.overlay_listdir(self.fs_overlay, self.voxel_spacing.overlay_path)
        prefix = f"{self.tomo_type}_"
        suffix = "_features.zarr"
        feature_types = [
            e["name"].removeprefix(prefix).removesuffix(suffix)
            for e in entries
            if e["is_dir"] and e["name"].startswith(prefix) and e["name"].endswith(suffix)
        ]
        feature_types = [ft for ft in feature_types if ft and not ft.startswith(".")]

        feature_types = list(set(feature_types))
        clz, meta_clz = self._feature_factory()

        return [
            clz(
                tomogram=self,
                meta=meta_clz(
                    tomo_type=self.tomo_type,
                    feature_type=ft,
                ),
                read_only=self.voxel_spacing.run.overlay_read_only,
            )
            for ft in feature_types
        ]

    def zarr(self) -> Store:
        """Get the zarr store for the tomogram object.

        Returns:
            Store: The zarr store for the tomogram object.
        """
        if self.read_only:
            fs = self.fs_static
            path = self.static_path
            mode = "r"
            create = False
        else:
            fs = self.fs_overlay
            path = self.overlay_path
            if fs is None or path is None:
                raise PermissionError(
                    f"Run {self.voxel_spacing.run.name} has no writable Embrella overlay project.",
                )
            mode = "w"
            create = not fs.exists(path)

        return copick_store(fs, path, read_only=mode == "r", create=create)

    def _delete_data(self) -> None:
        if self.fs_overlay is not None and self.fs_overlay.exists(self.overlay_path):
            self.fs_overlay.rm(self.overlay_path, recursive=True)
        else:
            raise FileNotFoundError(f"File not found: {self.overlay_path}")


class CopickVoxelSpacingEmbrella(CopickVoxelSpacingOverlay):
    """CopickVoxelSpacing combining static Embrella tomograms and overlay tomograms."""

    run: "CopickRunEmbrella"

    def _tomogram_factory(self) -> Tuple[Type[CopickTomogramEmbrella], Type[CopickTomogramMetaEmbrella]]:
        return CopickTomogramEmbrella, CopickTomogramMetaEmbrella

    @property
    def overlay_path(self) -> Optional[str]:
        base = self.run.overlay_path
        return None if base is None else f"{base}/VoxelSpacing{self.voxel_size:.3f}"

    @property
    def fs_overlay(self) -> Optional[AbstractFileSystem]:
        return self.run.fs_overlay

    def _static_records(self) -> List[EmbrellaTomoRecord]:
        records = self.run.root.index.tomos_by_run.get(self.run.name, [])
        size = round(self.voxel_size, 3)
        return [r for r in records if r.voxel_size == size]

    def _query_static_tomograms(self) -> List[CopickTomogramEmbrella]:
        clz, meta_clz = self._tomogram_factory()
        return [
            clz(
                voxel_spacing=self,
                meta=meta_clz.from_record(r),
                read_only=True,
            )
            for r in self._static_records()
        ]

    def _query_overlay_tomograms(self) -> List[CopickTomogramEmbrella]:
        if self.fs_overlay is None or self.overlay_path is None:
            return []

        entries = self.run.root.overlay_listdir(self.fs_overlay, self.overlay_path)
        tomo_types = [
            e["name"].removesuffix(".zarr") for e in entries if e["is_dir"] and e["name"].endswith(".zarr")
        ]
        tomo_types = [t for t in tomo_types if "features" not in t]
        tomo_types = [tt for tt in tomo_types if tt and not tt.startswith(".")]
        tomo_types = [tt for tt in tomo_types if tt not in self.run.root.config.exclude_overlay_tomo_types]

        tomo_types = list(set(tomo_types))
        clz, meta_clz = self._tomogram_factory()

        return [
            clz(
                voxel_spacing=self,
                meta=meta_clz(tomo_type=tt),
                read_only=self.run.overlay_read_only,
            )
            for tt in tomo_types
        ]

    def ensure(self, create: bool = False) -> bool:
        """Checks if the voxel spacing record exists in the static index or overlay directory,
        optionally creating it in the overlay filesystem if it does not.

        Args:
            create: Whether to create the voxel spacing record if it does not exist.

        Returns:
            bool: True if the voxel spacing record exists, False otherwise.
        """
        exists = bool(self._static_records())

        if not exists and self.fs_overlay is not None and self.overlay_path is not None:
            exists = self.fs_overlay.exists(self.overlay_path)

        if not exists and create:
            if self.fs_overlay is None or self.overlay_path is None or self.run.overlay_read_only:
                raise PermissionError(
                    f"Run {self.run.name} has no writable Embrella overlay project.",
                )
            self.fs_overlay.makedirs(self.overlay_path, exist_ok=True)
            with self.fs_overlay.open(self.overlay_path + "/.meta", "w") as f:
                f.write("meta")  # Touch the file
            return True
        else:
            return exists

    def _delete_data(self) -> None:
        if self.fs_overlay is not None and self.fs_overlay.exists(self.overlay_path):
            self.fs_overlay.rm(self.overlay_path, recursive=True)
        else:
            raise FileNotFoundError(f"File not found: {self.overlay_path}")


class CopickRunMetaEmbrella(CopickRunMeta):
    """Run metadata with Embrella provenance."""

    embrella_session: Optional[str] = None
    embrella_position: Optional[str] = None


class CopickRunEmbrella(CopickRunOverlay):
    """CopickRun combining static Embrella tomograms and one session's overlay project.

    Run names follow Embrella's copick convention ``{session}_{position}``, so overlay
    annotations line up with the per-session copick projects created by Embrella.
    """

    root: "CopickRootEmbrella"
    meta: CopickRunMetaEmbrella

    def _voxel_spacing_factory(self) -> Tuple[Type[CopickVoxelSpacingEmbrella], Type[CopickVoxelSpacingMeta]]:
        return CopickVoxelSpacingEmbrella, CopickVoxelSpacingMeta

    def _picks_factory(self) -> Type[CopickPicksEmbrella]:
        return CopickPicksEmbrella

    def _mesh_factory(self) -> Tuple[Type[CopickMeshEmbrella], Type[CopickMeshMeta]]:
        return CopickMeshEmbrella, CopickMeshMeta

    def _segmentation_factory(self) -> Tuple[Type[CopickSegmentationEmbrella], Type[CopickSegmentationMeta]]:
        return CopickSegmentationEmbrella, CopickSegmentationMeta

    @property
    def embrella_session(self) -> Optional[str]:
        """The Embrella session this run belongs to."""
        return self.meta.embrella_session or self.root.session_for_run(self.name)

    @property
    def embrella_position(self) -> Optional[str]:
        """The position stem of this run within its Embrella session."""
        if self.meta.embrella_position is not None:
            return self.meta.embrella_position
        hit = self.root.index.runs.get(self.name)
        return hit[1] if hit else None

    @property
    def fs_overlay(self) -> Optional[AbstractFileSystem]:
        return self.root.overlay_for_run(self.name)[0]

    @property
    def overlay_path(self) -> Optional[str]:
        return self.root.overlay_for_run(self.name)[1]

    @property
    def overlay_read_only(self) -> bool:
        return self.root.overlay_for_run(self.name)[2]

    def _query_static_voxel_spacings(self) -> List[CopickVoxelSpacingEmbrella]:
        records = self.root.index.tomos_by_run.get(self.name, [])
        sizes = sorted({r.voxel_size for r in records})
        clz, meta_clz = self._voxel_spacing_factory()

        return [clz(meta=meta_clz(voxel_size=s), run=self) for s in sizes]

    def _query_overlay_voxel_spacings(self) -> List[CopickVoxelSpacingEmbrella]:
        if self.fs_overlay is None or self.overlay_path is None:
            return []

        entries = self.root.overlay_listdir(self.fs_overlay, self.overlay_path)
        spacings = [
            float(e["name"].removeprefix("VoxelSpacing"))
            for e in entries
            if e["is_dir"] and e["name"].startswith("VoxelSpacing")
        ]

        clz, meta_clz = self._voxel_spacing_factory()

        return [
            clz(
                meta=meta_clz(voxel_size=s),
                run=self,
            )
            for s in spacings
        ]

    def _query_static_picks(self) -> List[CopickPicksEmbrella]:
        # Embrella does not serve annotations; they live in the overlay projects.
        return []

    def _query_overlay_picks(self) -> List[CopickPicksEmbrella]:
        if self.fs_overlay is None or self.overlay_path is None:
            return []

        entries = self.root.overlay_listdir(self.fs_overlay, f"{self.overlay_path}/Picks")
        names = [
            e["name"].removesuffix(".json")
            for e in entries
            if not e["is_dir"] and e["name"].endswith(".json") and not e["name"].startswith(".")
        ]

        users = [n.split("_")[0] for n in names]
        sessions = [n.split("_")[1] for n in names]
        objects = [n.split("_")[2] for n in names]

        assert len(users) == len(sessions) == len(objects)

        return [
            CopickPicksEmbrella(
                run=self,
                file=CopickPicksFile(
                    pickable_object_name=o,
                    user_id=u,
                    session_id=s,
                ),
                read_only=self.overlay_read_only,
            )
            for u, s, o in zip(users, sessions, objects, strict=True)
        ]

    def _query_static_meshes(self) -> List[CopickMeshEmbrella]:
        # Embrella does not serve annotations; they live in the overlay projects.
        return []

    def _query_overlay_meshes(self) -> List[CopickMeshEmbrella]:
        if self.fs_overlay is None or self.overlay_path is None:
            return []

        entries = self.root.overlay_listdir(self.fs_overlay, f"{self.overlay_path}/Meshes")
        names = [
            e["name"].removesuffix(".glb")
            for e in entries
            if not e["is_dir"] and e["name"].endswith(".glb") and not e["name"].startswith(".")
        ]

        users = [n.split("_")[0] for n in names]
        sessions = [n.split("_")[1] for n in names]
        objects = [n.split("_")[2] for n in names]

        clz, meta_clz = self._mesh_factory()

        return [
            clz(
                run=self,
                meta=meta_clz(
                    pickable_object_name=o,
                    user_id=u,
                    session_id=s,
                ),
                read_only=self.overlay_read_only,
            )
            for u, s, o in zip(users, sessions, objects, strict=True)
        ]

    def _query_static_segmentations(self) -> List[CopickSegmentationEmbrella]:
        # Embrella does not serve annotations; they live in the overlay projects.
        return []

    def _query_overlay_segmentations(self) -> List[CopickSegmentationEmbrella]:
        if self.fs_overlay is None or self.overlay_path is None:
            return []

        entries = self.root.overlay_listdir(self.fs_overlay, f"{self.overlay_path}/Segmentations")
        names = [
            e["name"].removesuffix(".zarr")
            for e in entries
            if e["is_dir"] and e["name"].endswith(".zarr") and not e["name"].startswith(".")
        ]

        # Deduplicate
        names = list(set(names))

        # multilabel vs single label
        metas = []
        clz, meta_clz = self._segmentation_factory()
        for n in names:
            parts = n.split("_")
            if "multilabel" in n:
                metas.append(
                    meta_clz(
                        is_multilabel=True,
                        voxel_size=float(parts[0]),
                        user_id=parts[1],
                        session_id=parts[2],
                        name=parts[3].replace("-multilabel", ""),
                    ),
                )
            else:
                metas.append(
                    meta_clz(
                        is_multilabel=False,
                        voxel_size=float(parts[0]),
                        user_id=parts[1],
                        session_id=parts[2],
                        name=parts[3],
                    ),
                )

        return [
            clz(
                run=self,
                meta=m,
                read_only=self.overlay_read_only,
            )
            for m in metas
        ]

    def ensure(self, create: bool = False) -> bool:
        """Checks if the run exists in the static index or overlay project, optionally creating
        it in the overlay filesystem if it does not.

        Args:
            create: Whether to create the run record if it does not exist.

        Returns:
            bool: True if the run record exists, False otherwise.
        """
        exists = self.name in self.root.index.runs

        if not exists:
            fs, path, _ = self.root.overlay_for_run(self.name)
            if fs is not None and path is not None:
                exists = fs.exists(path)

        if not exists and create:
            fs, path, read_only = self.root.overlay_for_run(self.name)
            if fs is None or path is None:
                raise ValueError(
                    f"Cannot create run '{self.name}': it does not belong to any configured "
                    f"Embrella session with a writable overlay project. Configured sessions: "
                    f"{sorted(self.root.index.sessions)}.",
                )
            if read_only:
                raise PermissionError(
                    f"Cannot create run '{self.name}': the overlay project of session "
                    f"'{self.root.session_for_run(self.name)}' is read-only.",
                )
            fs.makedirs(path, exist_ok=True)
            with fs.open(path + "/.meta", "w") as f:
                f.write("meta")  # Touch the file
            return True
        else:
            return exists

    def _delete_data(self) -> None:
        fs, path, _ = self.root.overlay_for_run(self.name)
        if fs is not None and path is not None and fs.exists(path):
            fs.rm(path, recursive=True)
        else:
            raise FileNotFoundError(f"File not found: {path}")


class CopickObjectEmbrella(CopickObjectOverlay):
    """CopickObject with templates stored in the optional project-level overlay.

    The per-session overlay projects are shared Embrella artifacts, so project-global
    object templates are not written into them. Without a project-level
    ``overlay_root`` in the config, objects are config-only (no density maps).
    """

    root: "CopickRootEmbrella"

    @property
    def path(self) -> Optional[str]:
        if self.root.root_objects is None:
            return None
        return f"{self.root.root_objects}/Objects/{self.name}.zarr"

    @property
    def fs(self) -> Optional[AbstractFileSystem]:
        return self.root.fs_objects

    def zarr(self) -> Optional[Store]:
        if not self.is_particle:
            return None

        if self.fs is None:
            self.root._warn_no_object_root()
            return None

        # Read-only objects have no destination when their map is absent.
        if self.read_only and not self.has_density_map():
            return None

        if self.read_only:
            mode = "r"
            create = False
        else:
            mode = "w"
            create = not self.fs.exists(self.path)

        return copick_store(self.fs, self.path, read_only=mode == "r", create=create)

    def has_density_map(self) -> bool:
        """Return whether the project-level overlay contains Zarr root metadata for this object."""
        if not self.is_particle or self.fs is None:
            return False
        return zarr_root_exists(self.fs, self.path)

    def _delete_data(self) -> None:
        if self.fs is not None and self.fs.exists(self.path):
            self.fs.rm(self.path, recursive=True)


class CopickRootEmbrella(CopickRoot):
    """CopickRoot combining tomograms from multiple Embrella sessions.

    At construction the root builds an in-memory index by querying the Embrella
    projects API (one call per session), fetching each session's overlay project
    ``config.json``, enumerating tomogram zarrs via the cluster file servers and
    reading one ``.zattrs`` per selection for the voxel size. All static queries are
    served from this index; no further network round trips per run.
    """

    config: CopickConfigEmbrella

    def __init__(self, config: CopickConfigEmbrella):
        import weakref

        from copick.util.reconnecting_fs import ReconnectingFileSystem

        super().__init__(config)

        self._index: Optional[EmbrellaIndex] = None
        self._index_data: Optional[Dict[str, Any]] = None
        self._fs_cache: Dict[str, AbstractFileSystem] = {}
        self._warned_no_object_root = False

        # Optional project-level overlay for pickable object templates.
        self.fs_objects: Optional[AbstractFileSystem] = None
        self.root_objects: Optional[str] = None
        if config.overlay_root:
            self.fs_objects = ReconnectingFileSystem(config.overlay_root, config.overlay_root_fs_args)
            self.root_objects = self.fs_objects._strip_protocol(config.overlay_root).rstrip("/")
            self.fs_objects._root_ref = weakref.ref(self)

        # Eagerly build the index and per-session overlay filesystems.
        self._ensure_index()
        self._session_fs: Dict[str, Tuple[Optional[AbstractFileSystem], Optional[str], bool]] = (
            self._build_session_filesystems()
        )

    @classmethod
    def from_file(cls, path: str) -> "CopickRootEmbrella":
        with open(path, "r") as f:
            data = json.load(f)

        return cls(CopickConfigEmbrella(**data))

    @property
    def index(self) -> EmbrellaIndex:
        return self._ensure_index()

    def _ensure_index(self) -> EmbrellaIndex:
        if self._index is None:
            self._index_data = self._fetch_index_data()
            self._index = _build_index(self._index_data)
        return self._index

    def _fetch_index_data(self) -> Dict[str, Any]:
        """Fetch all remote state into a JSON-serializable payload (see _build_index)."""
        config = self.config
        base = config.embrella_base_url.rstrip("/")
        payload_sessions = []

        for spec in config.sessions:
            url = f"{base}/copick/v1/projects/?session_id={urllib.parse.quote(spec.name)}&status=all"
            try:
                data = json.loads(_http_get(url, accept="application/json"))
                projects = data.get("projects", [])
            except (ConnectionError, urllib.error.HTTPError) as e:
                raise ConnectionError(f"Could not reach the Embrella projects API at {url}: {e}") from e

            sess = self._resolve_session(spec, projects)
            sess["selections"] = [self._resolve_selection(spec, sel, sess["scope"]) for sel in spec.tomograms]
            payload_sessions.append(sess)

        return {"sessions": payload_sessions}

    def _resolve_session(self, spec: EmbrellaSessionSpec, projects: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Pick this session's overlay project and resolve its locations."""
        project = None
        if spec.overlay_run is not None:
            matches = [p for p in projects if p.get("run_name") == spec.overlay_run]
            if not matches:
                logger.warning(
                    f"Embrella session '{spec.name}': pinned overlay project '{spec.overlay_run}' was not "
                    f"found; the session will be read-only.",
                )
            else:
                project = matches[0]
        elif projects:
            candidates = sorted(projects, key=lambda p: p.get("created_at") or "", reverse=True)
            completed = [p for p in candidates if p.get("status") == "completed"]
            project = completed[0] if completed else candidates[0]
        else:
            logger.warning(
                f"Embrella session '{spec.name}' has no copick overlay project; annotations will be "
                f"unavailable (static tomograms are still served).",
            )

        sess: Dict[str, Any] = {
            "session": spec.name,
            "scope": self.config.scope,
            "overlay_run": None,
            "cluster_id": None,
            "overlay_url": None,
            "overlay_posix": None,
            "read_only": True,
            "pickable_objects": [],
        }

        if project is None:
            return sess

        sess["overlay_run"] = project.get("run_name")
        sess["cluster_id"] = project.get("cluster_id")
        sess["scope"] = project.get("scope") or self.config.scope
        sess["overlay_url"] = (project.get("root_url") or "").rstrip("/") or None

        config_url = project.get("config_url")
        try:
            overlay_config = json.loads(_http_get(config_url))
            overlay_root = overlay_config.get("overlay_root") or ""
            overlay_posix = overlay_root.removeprefix("local://").rstrip("/")
            sess["overlay_posix"] = overlay_posix or None
            sess["read_only"] = not overlay_posix
            sess["pickable_objects"] = overlay_config.get("pickable_objects", [])
        except (ConnectionError, urllib.error.HTTPError, json.JSONDecodeError) as e:
            logger.warning(
                f"Embrella session '{spec.name}': could not read the overlay project config at "
                f"{config_url} ({e}); the session will be read-only.",
            )

        return sess

    def _resolve_selection(
        self,
        spec: EmbrellaSessionSpec,
        sel: EmbrellaTomoSelection,
        scope: str,
    ) -> Dict[str, Any]:
        """Resolve one tomogram selection: data locations, positions and voxel size."""
        cluster_key = sel.cluster or self.config.default_data_cluster
        if cluster_key not in self.config.clusters:
            raise ValueError(
                f"Unknown cluster '{cluster_key}' for session '{spec.name}' selection "
                f"'{sel.proc_run}:{sel.recon_type}'. Configured clusters: {sorted(self.config.clusters)}.",
            )
        cluster = self.config.clusters[cluster_key]

        workflow, vol = RECON_DIRS[sel.recon_type]
        data_url = _join_path(cluster.http_base, f"{scope}.processing", workflow, spec.name, sel.proc_run, vol)
        data_posix = _join_path(cluster.posix_base, f"{scope}.processing", workflow, spec.name, sel.proc_run, vol)

        context = f"session '{spec.name}', selection '{sel.proc_run}:{sel.recon_type}'"

        positions = sel.positions
        if positions is None:
            positions = self._list_positions(data_url, data_posix, context)

        if not positions:
            logger.warning(
                f"No tomogram zarrs found for {context} at "
                f"{data_url if self.config.static_mode == 'http' else data_posix}. Check the cluster "
                f"('{cluster_key}') and proc_run, or pin 'positions' in the config.",
            )

        voxel_size = sel.voxel_size
        if voxel_size is None and positions:
            voxel_size = self._sniff_voxel_size(data_url, data_posix, positions[0], context)

        return {
            "proc_run": sel.proc_run,
            "recon_type": sel.recon_type,
            "positions": positions,
            "voxel_size": round(voxel_size, 3) if voxel_size is not None else None,
            "data_url": data_url,
            "data_posix": data_posix,
        }

    def _list_positions(self, data_url: str, data_posix: str, context: str) -> List[str]:
        """Enumerate position stems by listing the volume directory."""
        if self.config.static_mode == "local":
            fs = self._static_fs_for(data_posix)
            if not fs.exists(data_posix):
                return []
            return _positions_from_listing(_entries_from_fs(fs, data_posix))

        try:
            return _positions_from_listing(_list_dir_http(data_url))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return []
            raise
        except ConnectionError as e:
            raise ConnectionError(
                f"Could not list tomograms for {context} at {data_url}: {e}. If the file server does "
                f"not allow directory listings, pin 'positions' in the config.",
            ) from e

    def _sniff_voxel_size(self, data_url: str, data_posix: str, position: str, context: str) -> float:
        """Read the voxel size from the first tomogram's OME-Zarr attributes."""
        try:
            if self.config.static_mode == "local":
                zattrs_path = _join_path(data_posix, f"{position}{_VOL_SUFFIX}", ".zattrs")
                fs = self._static_fs_for(zattrs_path)
                with fs.open(zattrs_path, "r") as f:
                    zattrs = json.load(f)
            else:
                zattrs_url = _join_path(data_url, f"{position}{_VOL_SUFFIX}", ".zattrs")
                zattrs = json.loads(_http_get(zattrs_url))

            return _voxel_size_from_zattrs(zattrs)
        except (ConnectionError, urllib.error.HTTPError, OSError, json.JSONDecodeError, ValueError, KeyError) as e:
            raise ValueError(
                f"Could not determine the voxel size for {context} from the tomogram's OME-Zarr "
                f"metadata ({e}). Set 'voxel_size' for this selection in the config.",
            ) from e

    def _build_session_filesystems(
        self,
    ) -> Dict[str, Tuple[Optional[AbstractFileSystem], Optional[str], bool]]:
        """Build one (filesystem, root, read_only) triple per session for overlay access."""
        import weakref

        from copick.util.reconnecting_fs import ReconnectingFileSystem

        mode = self.config.overlay_mode
        out: Dict[str, Tuple[Optional[AbstractFileSystem], Optional[str], bool]] = {}
        local_fs: Optional[AbstractFileSystem] = None
        ssh_fs: Optional[AbstractFileSystem] = None

        for name, entry in self.index.sessions.items():
            fs: Optional[AbstractFileSystem] = None
            root: Optional[str] = None
            read_only = True

            if mode == "http":
                if entry.overlay_url is not None:
                    fs = self._static_fs_for(entry.overlay_url)
                    root = entry.overlay_url
            elif entry.overlay_posix is not None and not entry.read_only:
                if mode == "local":
                    if local_fs is None:
                        local_fs = LocalFileSystem(auto_mkdir=True)
                    fs, root = local_fs, entry.overlay_posix
                else:  # ssh
                    if ssh_fs is None:
                        ssh_fs = ReconnectingFileSystem(
                            f"ssh://{entry.overlay_posix}",
                            self.config.overlay_fs_args,
                        )
                        ssh_fs._root_ref = weakref.ref(self)
                    fs, root = ssh_fs, entry.overlay_posix
                read_only = False

            out[name] = (fs, root, read_only if fs is not None else True)

        return out

    def _static_fs_for(self, path: str) -> AbstractFileSystem:
        """Return a (cached) filesystem for a static URL or POSIX path."""
        proto = urllib.parse.urlparse(path).scheme if "://" in path else "file"
        if proto not in self._fs_cache:
            fs_args = dict(self.config.static_fs_args or {})
            if proto == "https" and "get_client" not in fs_args:
                fs_args["get_client"] = _get_http_client
            self._fs_cache[proto] = fsspec.filesystem(proto, **fs_args)
        return self._fs_cache[proto]

    def overlay_listdir(self, fs: AbstractFileSystem, path: str) -> List[Dict[str, Any]]:
        """List an overlay directory, normalized to ``{"name", "is_dir"}`` entries.

        Over HTTP, the file server's JSON listing is used (fsspec's HTML scraping and
        glob are unreliable against directory index pages). A missing directory yields
        an empty list.
        """
        proto = fs.protocol if isinstance(fs.protocol, str) else fs.protocol[0]
        try:
            if proto in ("http", "https"):
                return _list_dir_http(path)
            return _entries_from_fs(fs, path)
        except FileNotFoundError:
            return []
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return []
            raise

    def _warn_no_object_root(self) -> None:
        if not self._warned_no_object_root:
            logger.warning(
                "This project has no project-level 'overlay_root'; pickable object templates cannot "
                "be stored. Set 'overlay_root' in the config to enable object density maps.",
            )
            self._warned_no_object_root = True

    def session_for_run(self, name: str) -> Optional[str]:
        """Resolve the Embrella session owning a copick run name."""
        hit = self.index.runs.get(name)
        if hit is not None:
            return hit[0]

        candidates = [s for s in self.index.sessions if name.startswith(f"{s}_")]
        return max(candidates, key=len) if candidates else None

    def overlay_for_run(self, name: str) -> Tuple[Optional[AbstractFileSystem], Optional[str], bool]:
        """Resolve the overlay (filesystem, run path, read_only) for a copick run name."""
        session = self.session_for_run(name)
        if session is None:
            return None, None, True

        fs, root, read_only = self._session_fs[session]
        if fs is None or root is None:
            return None, None, True

        return fs, f"{root}/ExperimentRuns/{name}", read_only

    def _run_factory(self) -> Tuple[Type[CopickRunEmbrella], Type[CopickRunMetaEmbrella]]:
        return CopickRunEmbrella, CopickRunMetaEmbrella

    def _object_factory(self) -> Tuple[Type[CopickObjectEmbrella], Type[PickableObject]]:
        return CopickObjectEmbrella, PickableObject

    def query(self) -> List[CopickRunEmbrella]:
        names: Dict[str, Tuple[str, Optional[str]]] = {
            run_name: (session, position) for run_name, (session, position) in self.index.runs.items()
        }

        # Union with runs that only exist in the overlay projects.
        for session, (fs, root, _) in self._session_fs.items():
            if fs is None or root is None:
                continue
            run_dir = f"{root}/ExperimentRuns"
            try:
                entries = self.overlay_listdir(fs, run_dir)
            except (OSError, ConnectionError) as e:
                logger.warning(f"Could not list overlay runs for session '{session}' at {run_dir}: {e}")
                continue
            for e in entries:
                if not e["is_dir"] or e["name"].startswith("."):
                    continue
                names.setdefault(e["name"], (session, None))

        clz, meta_clz = self._run_factory()
        runs = []
        for n in sorted(names):
            session, position = names[n]
            rm = meta_clz(name=n, embrella_session=session, embrella_position=position)
            runs.append(clz(root=self, meta=rm))

        return runs

    def _query_objects(self) -> None:
        """Objects are writable only when a project-level overlay_root is configured."""
        clz, meta_clz = self._object_factory()
        writable = self.fs_objects is not None
        self._objects = [clz(self, obj_meta, read_only=not writable) for obj_meta in self.config.pickable_objects]

    def overlay_pickable_objects(self) -> List[PickableObject]:
        """Collect the pickable objects declared by the sessions' overlay projects.

        Objects are deduplicated by name (first session wins); conflicting duplicate
        definitions are reported.

        Returns:
            List[PickableObject]: The deduplicated objects.
        """
        out: Dict[str, PickableObject] = {}
        for entry in self.index.sessions.values():
            for obj_dict in entry.pickable_objects:
                try:
                    po = PickableObject(**obj_dict)
                except ValidationError as e:
                    logger.warning(
                        f"Skipping invalid pickable object {obj_dict.get('name')!r} from session "
                        f"'{entry.session}': {e}",
                    )
                    continue
                if po.name in out:
                    prev = out[po.name]
                    if prev.label != po.label or prev.identifier != po.identifier:
                        logger.warning(
                            f"Conflicting definitions for pickable object '{po.name}' across overlay "
                            f"projects; keeping the first one (label={prev.label}, "
                            f"identifier={prev.identifier}).",
                        )
                    continue
                out[po.name] = po

        return list(out.values())

    def refresh_index(self) -> None:
        """Re-fetch the Embrella index and invalidate all cached entities."""
        self._index = None
        self._index_data = None
        self._ensure_index()
        self._session_fs = self._build_session_filesystems()
        self._invalidate_all_caches()

    def reconnect(self) -> None:
        """Force reconnection of all reconnecting filesystems."""
        seen = set()
        for fs, _, _ in self._session_fs.values():
            if fs is not None and hasattr(fs, "_reconnect") and id(fs) not in seen:
                fs._reconnect()
                seen.add(id(fs))
        if self.fs_objects is not None and id(self.fs_objects) not in seen:
            self.fs_objects._reconnect()
