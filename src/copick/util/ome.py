import copy
import itertools
from typing import Any, Dict, Iterator, List, Tuple, Union

import numpy as np
import psutil
import zarr
from numcodecs import Blosc
from zarr.abc.store import Store

from copick.util.log import get_logger

logger = get_logger(__name__)

_DEFAULT_WRITER_METADATA = object()

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


def initialize_zarr_v2(store: Union[str, Store]) -> None:
    """Materialize an empty Zarr v2 group in a new entity store."""
    zarr.group(store=store, overwrite=False, zarr_format=2)


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


def write_ome_zarr_3d(
    store: Union[str, Store],
    pyramid: Dict[float, np.ndarray],
    chunk_size: Tuple[int, ...] = (256, 256, 256),
    overwrite: bool = True,
    metadata: Any = _DEFAULT_WRITER_METADATA,
) -> None:
    """Write a 3D pyramid as OME-Zarr 0.4 / Zarr v2.

    Args:
        store: A path string or mutable Zarr store to write to.
        pyramid: The pyramid to write.
        chunk_size: The chunk size to use for the Zarr store. Default is (256, 256, 256).
        overwrite: Whether to overwrite an existing group and arrays.
        metadata: Additional OME multiscale metadata. When omitted, preserve the existing empty metadata mapping.
    """
    # This is a super heavy import, so we do it here to avoid loading it before it's needed.
    # Writing is slow anyway.
    from ome_zarr.format import FormatV04
    from ome_zarr.writer import write_multiscale

    ome_meta = ome_metadata(pyramid)
    root_group = zarr.group(store=store, overwrite=overwrite, zarr_format=2)
    compressor = Blosc(cname="lz4", clevel=5, shuffle=Blosc.SHUFFLE)
    writer_metadata = {} if metadata is _DEFAULT_WRITER_METADATA else metadata
    ome_zarr_metadata = writer_metadata if isinstance(writer_metadata, dict) else {}

    write_multiscale(
        list(pyramid.values()),
        group=root_group,
        fmt=FormatV04(),
        axes=ome_meta["axes"],
        coordinate_transformations=ome_meta["coordinate_transformations"],
        storage_options={
            "chunks": chunk_size,
            "compressor": compressor,
            "overwrite": overwrite,
        },
        compute=True,
        metadata=ome_zarr_metadata,
    )
    multiscales = root_group.attrs["multiscales"]
    multiscales[0]["metadata"] = copy.deepcopy(writer_metadata)
    root_group.attrs["multiscales"] = multiscales


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


def write_single_level_ome_zarr_v2(source_group: zarr.Group, target_store: Store, level: int = 0) -> None:
    """Semantically export one OME level as OME-Zarr 0.4 / Zarr v2.

    The destination is rebuilt instead of copying group attributes across a
    format boundary.  Source values are decoded one inner chunk at a time, so
    a sharded v3 source intentionally becomes an unsharded v2 array.
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
    target_path = "0"
    target_group = zarr.group(store=target_store, overwrite=True, zarr_format=2)
    target_array = target_group.create_array(
        target_path,
        shape=source_array.shape,
        dtype=source_array.dtype,
        chunks=source_array.chunks,
        fill_value=source_array.fill_value,
        compressor=Blosc(cname="lz4", clevel=5, shuffle=Blosc.SHUFFLE),
        chunk_key_encoding={"name": "v2", "separator": "/"},
        attributes=dict(source_array.attrs),
    )
    copy_array_chunkwise(source_array, target_array)

    dataset = copy.deepcopy(datasets[level])
    dataset["path"] = target_path
    rebuilt = {
        key: copy.deepcopy(value)
        for key, value in source_multiscale.items()
        if key in {"axes", "metadata", "name", "type"}
    }
    rebuilt["version"] = "0.4"
    rebuilt["datasets"] = [dataset]
    target_group.attrs["multiscales"] = [rebuilt]


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
