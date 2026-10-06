"""Helpers for segmentation volumes: label dtypes that never lose a value, and the store name that records a
segmentation's type."""

from typing import Any, Dict, List, Optional, Union

import numpy as np

from copick.util.log import get_logger

logger = get_logger(__name__)

_UNSIGNED = (np.uint8, np.uint16, np.uint32, np.uint64)

DTypeLike = Union[np.dtype, type, str]


def _value_range(data: np.ndarray) -> tuple:
    """Return (min, max) of ``data``, refusing non-finite and non-integral values."""
    if data.size == 0:
        return 0, 0
    if data.dtype.kind == "b":
        return int(data.min()), int(data.max())
    if data.dtype.kind == "f":
        if not np.all(np.isfinite(data)):
            raise ValueError("Segmentation values must be finite; found NaN or infinity.")
        if np.any(data != np.floor(data)):
            raise ValueError("Segmentation values must be integers; found non-integral floating-point values.")
        return int(data.min()), int(data.max())
    if data.dtype.kind in "iu":
        return int(data.min()), int(data.max())
    raise ValueError(f"Segmentation data must be integer, boolean or integral floating point, not {data.dtype}.")


def label_dtype(data: np.ndarray, floor: DTypeLike = np.uint8) -> np.dtype:
    """The smallest unsigned integer dtype, no narrower than ``floor``, that holds every value of ``data``.

    Args:
        data: Label volume. Integer, boolean, or floating point with integral values.
        floor: The narrowest dtype to return.

    Returns:
        The chosen dtype.

    Raises:
        ValueError: If ``data`` has negative, non-integral or non-finite values, or values above ``uint64``.
    """
    data = np.asarray(data)
    lo, hi = _value_range(data)
    if lo < 0:
        raise ValueError(
            f"Segmentation values must be non-negative, found {lo}. Pass an explicit signed dtype to store "
            "negative labels.",
        )
    floor_size = np.dtype(floor).itemsize
    for dt in _UNSIGNED:
        if np.dtype(dt).itemsize >= floor_size and hi <= np.iinfo(dt).max:
            return np.dtype(dt)
    raise ValueError(f"Segmentation value {hi} does not fit any unsigned integer dtype.")


def checked_label_cast(data: np.ndarray, dtype: Optional[DTypeLike]) -> np.ndarray:
    """Cast a label volume to ``dtype``, refusing any value the cast would change.

    Args:
        data: Label volume.
        dtype: Target dtype. ``None`` keeps the input dtype.

    Returns:
        ``data`` as ``dtype`` (no copy when it already is).

    Raises:
        ValueError: If a value is negative for an unsigned target, outside the target's range, non-integral for an
            integer target, or not exactly representable by a floating-point target.
    """
    data = np.asarray(data)
    if dtype is None:
        return data
    dtype = np.dtype(dtype)
    if data.dtype == dtype:
        return data

    if dtype.kind == "f":
        if data.dtype.kind in "iub":
            lo, hi = _value_range(data)
            exact = 2 ** (np.finfo(dtype).nmant + 1)
            if lo < -exact or hi > exact:
                raise ValueError(
                    f"Segmentation values in [{lo}, {hi}] are not exactly representable as {dtype} "
                    f"(exact up to {exact}).",
                )
        return data.astype(dtype, copy=False)

    lo, hi = _value_range(data)
    if dtype.kind == "b":
        if lo < 0 or hi > 1:
            raise ValueError(f"Segmentation values in [{lo}, {hi}] do not fit {dtype}.")
    elif dtype.kind in "iu":
        info = np.iinfo(dtype)
        if lo < info.min or hi > info.max:
            raise ValueError(
                f"Segmentation values in [{lo}, {hi}] do not fit {dtype} ([{info.min}, {info.max}]). Pass a wider "
                "dtype, or dtype=None to choose one.",
            )
    else:
        raise ValueError(f"Unsupported segmentation dtype {dtype}.")
    return data.astype(dtype, copy=False)


# ---------------------------------------------------------------------------
# Segmentation types, the directory and the store name that record them
# ---------------------------------------------------------------------------

#: The segmentation types. ``binary``: one object, voxel = 1. ``multilabel``: several objects, voxel = the object's
#: ``label``. ``instance``: one object, voxel = the instance ID (0 = background).
SEGMENTATION_TYPES = ("binary", "multilabel", "instance")

#: Run-level directory of each type. Binary and multilabel share the original directory, where clients have always
#: looked; newer types get their own, which clients that predate them never list.
SEGMENTATION_DIRECTORIES = {
    "binary": "Segmentations",
    "multilabel": "Segmentations",
    "instance": "InstanceSegmentations",
}

# Directories that hold a single type, which therefore needs no mark in the store name.
_DIRECTORY_TYPES = {d: t for t, d in SEGMENTATION_DIRECTORIES.items() if d != "Segmentations"}

_TYPE_SUFFIXES = {"multilabel": "-multilabel"}

#: Name endings that mark a segmentation's type in its store name. An object whose name ends in one of these is
#: ambiguous in a store name.
RESERVED_NAME_SUFFIXES = tuple(_TYPE_SUFFIXES.values())


def segmentation_type(is_multilabel: bool, is_instance: bool) -> str:
    """Return ``"binary"``, ``"multilabel"`` or ``"instance"``.

    Raises:
        ValueError: If both flags are set.
    """
    if is_multilabel and is_instance:
        raise ValueError("A segmentation is either multilabel or instance, not both.")
    if is_multilabel:
        return "multilabel"
    return "instance" if is_instance else "binary"


def segmentation_directory(is_multilabel: bool = False, is_instance: bool = False) -> str:
    """The run-level directory that holds a segmentation of this type."""
    return SEGMENTATION_DIRECTORIES[segmentation_type(is_multilabel, is_instance)]


#: Values of the ``--segmentation-type`` filter of the CLI: one type, or ``all``. Without it, commands select binary
#: and multilabel segmentations, as ``CopickRun.get_segmentations`` and an untyped URI do.
SEGMENTATION_TYPE_FILTERS = ("binary", "multilabel", "instance", "all")


def segmentation_type_query(segmentation_type: Optional[str] = None) -> Dict[str, Optional[bool]]:
    """The ``get_segmentations`` type arguments that select ``segmentation_type`` (one of ``SEGMENTATION_TYPE_FILTERS``).

    ``None`` selects binary and multilabel segmentations, ``"all"`` every type.
    """
    if segmentation_type is None:
        return {"is_multilabel": None, "is_instance": False}
    kind = segmentation_type.lower()
    if kind == "all":
        return {"is_multilabel": None, "is_instance": None}
    if kind not in SEGMENTATION_TYPES:
        raise ValueError(f"Unknown segmentation type {segmentation_type!r}; use one of {SEGMENTATION_TYPE_FILTERS}.")
    return {"is_multilabel": kind == "multilabel", "is_instance": kind == "instance"}


def segmentation_store_name(
    voxel_size: float,
    user_id: str,
    session_id: str,
    name: str,
    *,
    is_multilabel: bool = False,
    is_instance: bool = False,
) -> str:
    """The store name of a segmentation: ``{voxel_size:.3f}_{user}_{session}_{name}[-multilabel].zarr``.

    Only multilabel segmentations carry a suffix; other types are told apart by their directory.
    """
    suffix = _TYPE_SUFFIXES.get(segmentation_type(is_multilabel, is_instance), "")
    return f"{voxel_size:.3f}_{user_id}_{session_id}_{name}{suffix}.zarr"


def parse_segmentation_store_name(store_name: str, directory: str = "Segmentations") -> Optional[Dict[str, Any]]:
    """Parse a segmentation store name (with or without ``.zarr``) into metadata fields.

    Args:
        store_name: The store's basename.
        directory: The run-level directory the store is in, which decides its type except in ``Segmentations``,
            where the ``-multilabel`` suffix does.

    Returns:
        ``voxel_size``, ``user_id``, ``session_id``, ``name``, ``is_multilabel`` and ``is_instance``, or ``None`` if
        the name is not a segmentation store name.
    """
    if directory != "Segmentations" and directory not in _DIRECTORY_TYPES:
        raise ValueError(f"{directory} is not a segmentation directory.")
    stem = store_name[: -len(".zarr")] if store_name.endswith(".zarr") else store_name
    parts = stem.split("_", 3)
    if len(parts) != 4:
        return None
    voxel_size, user_id, session_id, name = parts
    try:
        voxel_size = float(voxel_size)
    except ValueError:
        return None
    kind = _DIRECTORY_TYPES.get(directory, "binary")
    if directory == "Segmentations":
        for candidate, suffix in _TYPE_SUFFIXES.items():
            if name.endswith(suffix):
                kind = candidate
                name = name[: -len(suffix)]
                break
    if not (user_id and session_id and name):
        return None
    return {
        "voxel_size": voxel_size,
        "user_id": user_id,
        "session_id": session_id,
        "name": name,
        "is_multilabel": kind == "multilabel",
        "is_instance": kind == "instance",
    }


def list_segmentation_stores(fs: Any, run_path: str) -> List[Dict[str, Any]]:
    """Parse every segmentation store under a run (``Segmentations/`` and each newer type's directory).

    Hidden entries and names that do not parse are skipped.
    """
    found = []
    for directory in ("Segmentations", *_DIRECTORY_TYPES):
        location = f"{run_path}/{directory}/"
        try:
            paths = fs.glob(location + "*.zarr") + fs.glob(location + "*.zarr/")
        except FileNotFoundError:
            continue
        for path in sorted({p.rstrip("/") for p in paths}):
            if not fs.isdir(path):
                continue
            store_name = path.rsplit("/", 1)[-1]
            if store_name.startswith("."):
                continue
            fields = parse_segmentation_store_name(store_name, directory)
            if fields is None:
                logger.debug(f"Skipping {path}: not a segmentation store name.")
                continue
            found.append(fields)
    return found
