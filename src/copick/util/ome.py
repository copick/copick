import copy
import itertools
import math
import tempfile
import warnings
from collections.abc import Mapping
from typing import Any, Dict, Iterator, List, Tuple, Union

import numpy as np
import psutil
import zarr
from zarr.abc.store import Store
from zarr.codecs import Shuffle, ZstdCodec
from zarr.storage import LocalStore

from copick.util.log import get_logger
from copick.util.zarr_copy import prepare_zarr_store_for_write, zarr_store_is_empty

logger = get_logger(__name__)

DEFAULT_SPATIAL_CHUNKS = (128, 128, 128)
_SHARD_WARNING_BYTES = 5 * 1000**3
_SHARD_LIMIT_BYTES = 5 * 1000**4

# Unit conversion factors to Angstrom
UNITFACTOR = {
    "angstrom": 1.0,
    "attometer": 1e-8,
    "centimeter": 1e8,
    "decimeter": 1e9,
    "exameter": 1e28,
    "femtometer": 1e-5,
    "foot": 3.048e9,
    "gigameter": 1e19,
    "hectometer": 1e12,
    "inch": 2.54e8,
    "kilometer": 1e13,
    "megameter": 1e16,
    "meter": 1e10,
    "micrometer": 1e4,
    "mile": 1.609e13,
    "millimeter": 1e7,
    "nanometer": 1e1,
    "parsec": 3.086e26,
    "petameter": 1e25,
    "picometer": 1e-2,
    "yard": 9.144e9,
    "yoctometer": 1e-14,
    "yottameter": 1e34,
    "terameter": 1e22,
    "zeptometer": 1e-11,
    "zettameter": 1e31,
}


def zarr_root_exists(fs: Any, path: str) -> bool:
    """Return whether a path contains Zarr v2 or v3 root metadata.

    A store's directory or prefix may exist before it contains a valid Zarr
    hierarchy, so its presence alone is not sufficient to establish that a
    density map exists.

    Args:
        fs: Filesystem containing the store.
        path: Path to the root of the store.

    Returns:
        Whether the store contains a v2 ``.zgroup`` or v3 ``zarr.json`` root.
    """
    root = path.rstrip("/")
    return fs.exists(f"{root}/.zgroup") or fs.exists(f"{root}/zarr.json")


def initialize_zarr_v3(store: Union[str, Store]) -> None:
    """Materialize an empty Zarr v3 group in a new entity store."""
    zarr.group(store=store, overwrite=False, zarr_format=3)


def _writer_store(store: Union[str, Store]) -> Store:
    """Normalize the writer's local-path convenience input to a Zarr store."""
    return LocalStore(store) if isinstance(store, str) else store


def _ome_zarr_axes() -> List[Dict[str, str]]:
    return [
        {
            "name": "z",
            "type": "space",
            "unit": "angstrom",
        },
        {
            "name": "y",
            "type": "space",
            "unit": "angstrom",
        },
        {
            "name": "x",
            "type": "space",
            "unit": "angstrom",
        },
    ]


def ome_zarr_axes(ndim: int = 3) -> List[Dict[str, str]]:
    """Return copick's supported OME-Zarr axes for 3D or feature-major 4D arrays."""
    if ndim == 3:
        return _ome_zarr_axes()
    if ndim == 4:
        return [{"name": "feature"}, *_ome_zarr_axes()]
    raise ValueError(f"OME-Zarr feature arrays must be 3D or 4D, got {ndim} dimensions")


def _ome_zarr_transforms(voxel_size: float) -> Dict[str, Any]:
    return {
        "scale": [voxel_size, voxel_size, voxel_size],
        "type": "scale",
    }


def volume_pyramid(
    volume: np.ndarray,
    voxel_size: float,
    levels: int,
    dtype: np.dtype = np.float32,
) -> Dict[float, np.ndarray]:
    """Create a volume pyramid by downscaling with interpolation, maintaining the local mean.

    Args:
        volume: The volume to downsample.
        voxel_size: The voxel size of the input volume.
        levels: The number of levels in the pyramid.
        dtype: The data type of the output arrays.

    Returns:
        A dictionary containing the pyramid with the voxel size as the key.
    """
    # This is a super heavy import, so we do it here to avoid loading it before it's needed.
    from skimage.transform import downscale_local_mean

    pyramid = {voxel_size: volume.astype(dtype)}
    vs = voxel_size

    for _ in range(1, levels):
        array = pyramid[vs]
        vs *= 2
        pyramid[vs] = downscale_local_mean(array, (2, 2, 2)).astype(dtype)

    return pyramid


def segmentation_pyramid(
    segmentation: np.ndarray,
    voxel_size: float,
    levels: int,
    dtype: np.dtype = np.int8,
) -> Dict[float, np.ndarray]:
    """Create an image pyramid by downsampling without interpolation.

    Args:
        segmentation: The segmentation to downsample.
        voxel_size: The voxel size of the input segmentation.
        levels: The number of levels in the pyramid.
        dtype: The data type of the output arrays.

    Returns:
        A dictionary containing the pyramid with the voxel size as the key.
    """
    # This is a super heavy import, so we do it here to avoid loading it before it's needed.
    from skimage.transform import rescale

    pyramid = {voxel_size: segmentation.astype(dtype)}
    vs = voxel_size

    for _ in range(1, levels):
        array = pyramid[vs]
        vs *= 2
        pyramid[vs] = rescale(
            array,
            (1.0 / 2.0, 1.0 / 2.0, 1.0 / 2.0),
            anti_aliasing=False,
            preserve_range=True,
            order=0,
        ).astype(dtype)

    return pyramid


def ome_metadata(pyramid: Dict[float, np.ndarray]) -> Dict[str, Any]:
    return {
        "axes": _ome_zarr_axes(),
        "coordinate_transformations": [[_ome_zarr_transforms(voxel_size)] for voxel_size in pyramid],
    }


def _shape_tuple(value: Tuple[int, ...], ndim: int, name: str) -> Tuple[int, ...]:
    """Validate and normalize a chunk or shard shape."""
    if len(value) != ndim:
        raise ValueError(f"{name} must contain exactly {ndim} dimensions, got {len(value)}")
    if any(isinstance(item, bool) or not isinstance(item, (int, np.integer)) or item <= 0 for item in value):
        raise ValueError(f"{name} dimensions must be positive integers, got {value!r}")
    return tuple(int(item) for item in value)


def padded_shard_shape(shape: Tuple[int, ...], chunks: Tuple[int, ...]) -> Tuple[int, ...]:
    """Return the smallest chunk-aligned shard containing an entire array."""
    normalized_shape = _shape_tuple(shape, len(shape), "shape")
    normalized_chunks = _shape_tuple(chunks, len(shape), "chunks")
    return tuple(
        chunk * math.ceil(size / chunk) for size, chunk in zip(normalized_shape, normalized_chunks, strict=True)
    )


def _validate_shards(shards: Tuple[int, ...], chunks: Tuple[int, ...]) -> Tuple[int, ...]:
    normalized = _shape_tuple(shards, len(chunks), "shards")
    if any(shard % chunk for shard, chunk in zip(normalized, chunks, strict=True)):
        raise ValueError(f"shards must be evenly divisible by chunks, got shards={normalized!r}, chunks={chunks!r}")
    return normalized


def _preflight_shard_size(shards: Tuple[int, ...], dtype: np.dtype) -> None:
    shard_bytes = math.prod(shards) * dtype.itemsize
    if shard_bytes >= _SHARD_LIMIT_BYTES:
        raise ValueError(
            f"Padded uncompressed shard size is {shard_bytes} bytes; shards must remain below 5 TB",
        )
    if shard_bytes > _SHARD_WARNING_BYTES:
        warnings.warn(
            f"Padded uncompressed shard size is {shard_bytes} bytes, above the recommended 5 GB ceiling",
            UserWarning,
            stacklevel=3,
        )


def canonical_v3_compressors(dtype: np.dtype) -> Tuple[Any, ...]:
    """Return the canonical dtype-specific Zarr v3 compressor pipeline."""
    dtype = np.dtype(dtype)
    if np.issubdtype(dtype, np.bool_) or np.issubdtype(dtype, np.integer):
        return (ZstdCodec(level=3),)
    if np.issubdtype(dtype, np.floating):
        return (Shuffle(elementsize=dtype.itemsize), ZstdCodec(level=3))
    raise TypeError(f"Canonical OME-Zarr output does not support dtype {dtype}")


def write_ome_zarr(
    store: Union[str, Store],
    pyramid: Dict[float, np.ndarray],
    axes: List[Dict[str, str]],
    chunk_size: Tuple[int, ...],
    overwrite: bool = True,
    metadata: Union[Mapping[str, Any], None] = None,
    shard_size: Union[Tuple[int, ...], None] = None,
    coordinate_transformations: Union[List[List[Dict[str, Any]]], None] = None,
) -> None:
    """Write an OME-Zarr 0.5 / Zarr v3 pyramid with the canonical layout."""
    # These imports are intentionally lazy because importing ome-zarr is
    # expensive and writes are already non-trivial operations.
    from ome_zarr.format import FormatV05
    from ome_zarr.writer import write_multiscales_metadata

    if not pyramid:
        raise ValueError("pyramid must contain at least one level")
    ndim = next(iter(pyramid.values())).ndim
    chunks = _shape_tuple(chunk_size, ndim, "chunk_size")
    if len(axes) != ndim:
        raise ValueError(f"axes must contain exactly {ndim} entries, got {len(axes)}")
    if coordinate_transformations is not None and len(coordinate_transformations) != len(pyramid):
        raise ValueError("coordinate_transformations must contain one entry per pyramid level")
    if metadata is not None and not isinstance(metadata, Mapping):
        raise TypeError("metadata must be a mapping or None")
    writer_metadata = {} if metadata is None else copy.deepcopy(dict(metadata))

    layouts = []
    for array in pyramid.values():
        if array.ndim != ndim:
            raise ValueError("all pyramid levels must have the same dimensionality")
        shards = padded_shard_shape(array.shape, chunks) if shard_size is None else _validate_shards(shard_size, chunks)
        _preflight_shard_size(shards, array.dtype)
        layouts.append((shards, canonical_v3_compressors(array.dtype)))

    target_store = _writer_store(store)
    prepare_zarr_store_for_write(target_store, overwrite)
    root_group = zarr.group(store=target_store, overwrite=overwrite, zarr_format=3)

    datasets = []
    dimension_names = tuple(axis["name"] for axis in axes)
    for level, ((voxel_size, array), (shards, compressors)) in enumerate(zip(pyramid.items(), layouts, strict=True)):
        path = str(level)
        root_group.create_array(
            path,
            data=array,
            chunks=chunks,
            shards=shards,
            compressors=compressors,
            chunk_key_encoding={"name": "v2", "separator": "/"},
            dimension_names=dimension_names,
            overwrite=overwrite,
        )
        transformations = (
            coordinate_transformations[level]
            if coordinate_transformations is not None
            else [
                {
                    "scale": [1.0] * (ndim - 3) + [voxel_size, voxel_size, voxel_size],
                    "type": "scale",
                },
            ]
        )
        datasets.append({"path": path, "coordinateTransformations": copy.deepcopy(transformations)})

    write_multiscales_metadata(
        root_group,
        datasets,
        fmt=FormatV05(),
        axes=axes,
        metadata=writer_metadata,
    )
    if metadata is not None:
        ome = copy.deepcopy(root_group.attrs["ome"])
        ome["multiscales"][0]["metadata"] = copy.deepcopy(writer_metadata)
        root_group.attrs["ome"] = ome


def write_ome_zarr_3d(
    store: Union[str, Store],
    pyramid: Dict[float, np.ndarray],
    chunk_size: Tuple[int, ...] = DEFAULT_SPATIAL_CHUNKS,
    overwrite: bool = True,
    metadata: Union[Mapping[str, Any], None] = None,
    shard_size: Union[Tuple[int, ...], None] = None,
) -> None:
    """Write a 3D pyramid as OME-Zarr 0.5 / Zarr v3.

    Args:
        store: A path string or Zarr store to write to.
        pyramid: The pyramid to write.
        chunk_size: Inner chunk shape. Default is ``(128, 128, 128)``.
        overwrite: Whether to overwrite an existing group and arrays.
        metadata: Additional OME multiscale metadata. ``None`` omits the optional metadata field.
        shard_size: Optional explicit shard shape. By default, one padded logical shard is used per level.
    """
    for array in pyramid.values():
        if array.ndim != 3:
            raise ValueError(f"write_ome_zarr_3d expects 3D arrays, got shape {array.shape!r}")
    write_ome_zarr(
        store,
        pyramid,
        ome_zarr_axes(),
        chunk_size,
        overwrite=overwrite,
        metadata=metadata,
        shard_size=shard_size,
    )


def iter_chunk_slices(shape: Tuple[int, ...], chunks: Tuple[int, ...]) -> Iterator[Tuple[slice, ...]]:
    """Yield bounded selections covering an array one inner chunk at a time."""
    starts = (range(0, size, chunk) for size, chunk in zip(shape, chunks, strict=True))
    for origin in itertools.product(*starts):
        yield tuple(
            slice(start, min(start + chunk, size)) for start, chunk, size in zip(origin, chunks, shape, strict=True)
        )


def copy_array_chunkwise(source: zarr.Array, target: zarr.Array) -> None:
    """Copy decoded array values without materializing the complete volume."""
    for selection in iter_chunk_slices(source.shape, source.chunks):
        target[selection] = source[selection]


def write_single_level_ome_zarr(source_group: zarr.Group, target_store: Store, level: int = 0) -> None:
    """Semantically export one OME level as canonical OME-Zarr 0.5 / Zarr v3.

    Source values are decoded one inner chunk at a time into a local memory map.
    The completed level is then handed to the canonical writer once, avoiding
    repeated remote rewrites of its volume-sized shard.
    """
    multiscales = get_multiscales(source_group)
    if not multiscales:
        raise ValueError("OME-Zarr metadata contains no multiscale entries")
    source_multiscale = multiscales[0]
    datasets = source_multiscale.get("datasets", [])
    if level < 0 or level >= len(datasets):
        raise ValueError(f"Level {level} not found in Zarr store (max: {len(datasets) - 1})")

    source_path = get_level_path(source_group, level)
    source_array = source_group[source_path]
    if source_array.ndim not in (3, 4):
        raise ValueError(f"Single-level OME-Zarr export supports 3D or 4D arrays, got {source_array.ndim} dimensions")
    if not zarr_store_is_empty(target_store):
        raise FileExistsError("Single-level Zarr export target is not empty")

    axes = copy.deepcopy(source_multiscale.get("axes"))
    if not isinstance(axes, list) or len(axes) != source_array.ndim:
        raise ValueError("Source OME-Zarr axes do not match the exported array")
    transformations = copy.deepcopy(datasets[level].get("coordinateTransformations"))
    if not isinstance(transformations, list):
        raise ValueError("Source OME-Zarr dataset has no coordinate transformations")

    with tempfile.TemporaryDirectory(prefix="copick-zarr-export-") as directory:
        staging = np.memmap(
            f"{directory}/level.dat",
            dtype=source_array.dtype,
            mode="w+",
            shape=source_array.shape,
        )
        copy_array_chunkwise(source_array, staging)
        staging.flush()

        writer_kwargs = {}
        if "metadata" in source_multiscale:
            writer_kwargs["metadata"] = copy.deepcopy(source_multiscale["metadata"])
        chunk_size = DEFAULT_SPATIAL_CHUNKS if source_array.ndim == 3 else (1, *DEFAULT_SPATIAL_CHUNKS)
        write_ome_zarr(
            target_store,
            {1.0: staging},
            axes,
            chunk_size,
            coordinate_transformations=[transformations],
            **writer_kwargs,
        )
        del staging

    target_group = zarr.open_group(target_store, mode="r+")
    target_array = target_group[get_level_path(target_group, 0)]
    target_array.attrs.update(dict(source_array.attrs))
    preserved_fields = {
        key: copy.deepcopy(source_multiscale[key]) for key in ("name", "type") if key in source_multiscale
    }
    if preserved_fields:
        ome = copy.deepcopy(target_group.attrs["ome"])
        ome["multiscales"][0].update(preserved_fields)
        target_group.attrs["ome"] = ome


def get_multiscales(zarr_group: zarr.Group) -> List[Dict[str, Any]]:
    """Return OME multiscale metadata from either the 0.4 or 0.5 layout.

    OME-Zarr 0.4 stores ``multiscales`` at the root of the group's
    attributes. OME-Zarr 0.5 nests it below the ``ome`` attribute.

    Args:
        zarr_group: The Zarr group containing OME-Zarr metadata.

    Returns:
        The OME multiscale metadata entries.

    Raises:
        KeyError: If neither supported metadata layout is present.
    """
    if "multiscales" in zarr_group.attrs:
        return zarr_group.attrs["multiscales"]

    ome = zarr_group.attrs.get("ome")
    if isinstance(ome, dict) and "multiscales" in ome:
        return ome["multiscales"]

    raise KeyError("OME-Zarr multiscales metadata not found")


def get_level_path(zarr_group: zarr.Group, level: int) -> str:
    """Resolve a bounded pyramid level to its metadata-defined dataset path.

    Args:
        zarr_group: The Zarr group containing OME-Zarr metadata.
        level: Zero-based pyramid level.

    Returns:
        The dataset path declared for ``level``.

    Raises:
        ValueError: If ``level`` is negative or outside the declared pyramid.
        KeyError: If required OME-Zarr metadata is absent.
    """
    multiscales = get_multiscales(zarr_group)
    datasets = multiscales[0]["datasets"]
    if level < 0 or level >= len(datasets):
        raise ValueError(f"Level {level} not found in Zarr store (max: {len(datasets) - 1})")

    return datasets[level]["path"]


def get_voxel_size_from_zarr(zarr_group: zarr.Group) -> float:
    """Extract voxel size from OME-Zarr coordinate transformations.

    Args:
        zarr_group: The zarr group containing OME-Zarr metadata.

    Returns:
        The voxel size in Angstrom from the coordinate transformations.
    """
    multiscales = get_multiscales(zarr_group)

    # Get unit from axes (should be consistent across spatial axes)
    axes = multiscales[0]["axes"]
    unit = "angstrom"  # Default
    for axis in axes:
        if axis.get("type") == "space" and "unit" in axis:
            unit = axis["unit"]
            break

    datasets = multiscales[0]["datasets"]
    first_dataset = datasets[0]
    coord_transforms = first_dataset["coordinateTransformations"]

    # Find the scale transformation
    for transform in coord_transforms:
        if transform["type"] == "scale":
            scale_value = float(transform["scale"][0])

            # Handle unit conversion
            conversion_factor = UNITFACTOR.get(unit, 1.0)  # Default to 1.0 if unknown unit

            # Convert to Angstrom
            return scale_value * conversion_factor

    # If no scale transformation found, raise an error
    raise ValueError("No scale transformation found in coordinate transformations")


def fits_in_memory(array: zarr.Array, slices: Tuple[slice, ...]) -> Tuple[bool, int, int]:
    """Check if the array fits in memory after slicing.

    Args:
        array: The Zarr array to check.
        slices: The slices to apply to the array.

    Returns:
        A tuple containing:
            - A boolean indicating if the array fits in memory.
            - The number of bytes requested.
            - The number of bytes available.
    """

    num_elem = []
    for dim, sl in zip(array.shape, slices, strict=True):
        num_elem.append(len(range(*sl.indices(dim))))

    requested = np.prod(np.array(num_elem)) * array.dtype.itemsize
    available = psutil.virtual_memory().available
    fits = requested < available

    return fits, requested, available
