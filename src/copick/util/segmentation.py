"""Helpers for segmentation volumes: label dtypes that never lose a value."""

from typing import Optional, Union

import numpy as np

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
