from typing import Any, Dict, List, MutableMapping, Optional, Tuple

import numpy as np
import psutil
import zarr

from copick.util.log import get_logger

logger = get_logger(__name__)

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


def _ome_zarr_transforms(voxel_size: float, channel_axis: bool = False) -> Dict[str, Any]:
    return {
        "scale": [1.0, voxel_size, voxel_size, voxel_size] if channel_axis else [voxel_size, voxel_size, voxel_size],
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
    dtype: Optional[np.dtype] = None,
) -> Dict[float, np.ndarray]:
    """Create an image pyramid by downsampling without interpolation.

    Args:
        segmentation: The segmentation to downsample, ``(Z, Y, X)`` or channel-first ``(C, Z, Y, X)``. Each channel
            is downsampled on the same grid, so values that belong together at a voxel stay together.
        voxel_size: The voxel size of the input segmentation.
        levels: The number of levels in the pyramid.
        dtype: The data type of the output arrays. ``None`` keeps the input dtype. A value the cast would change
            raises ``ValueError`` instead of wrapping.

    Returns:
        A dictionary containing the pyramid with the voxel size as the key.
    """
    # This is a super heavy import, so we do it here to avoid loading it before it's needed.
    from skimage.transform import rescale

    from copick.util.segmentation import checked_label_cast

    base = checked_label_cast(segmentation, dtype)
    if base.ndim == 4:
        channels = [segmentation_pyramid(channel, voxel_size, levels) for channel in base]
        return {vs: np.stack([channel[vs] for channel in channels]) for vs in channels[0]}
    dtype = base.dtype
    pyramid = {voxel_size: base}
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


def ome_metadata(pyramid: Dict[float, np.ndarray], channel_axis: bool = False) -> Dict[str, Any]:
    axes = _ome_zarr_axes()
    if channel_axis:
        axes = [{"name": "c", "type": "channel"}, *axes]
    return {
        "axes": axes,
        "coordinate_transformations": [[_ome_zarr_transforms(voxel_size, channel_axis)] for voxel_size in pyramid],
    }


def write_ome_zarr_3d(
    store: MutableMapping,
    pyramid: Dict[float, np.ndarray],
    chunk_size: Tuple[int, ...] = (256, 256, 256),
    channel_axis: bool = False,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Write a 3D pyramid to an OME-Zarr store.

    Args:
        store: The store to write to.
        pyramid: The pyramid to write.
        chunk_size: The spatial chunk size to use for the Zarr store. Default is (256, 256, 256).
        channel_axis: The arrays are channel-first ``(C, Z, Y, X)``; written with a leading ``c`` axis of type
            ``channel``, one channel per chunk.
        metadata: Extra entries for the multiscales metadata.
    """
    # This is a super heavy import, so we do it here to avoid loading it before it's needed.
    # Writing is slow anyway.
    from ome_zarr.writer import write_multiscale

    ome_meta = ome_metadata(pyramid, channel_axis)
    root_group = zarr.group(store=store, overwrite=True)
    if channel_axis and len(chunk_size) == 3:
        chunk_size = (1, *chunk_size)

    write_multiscale(
        list(pyramid.values()),
        group=root_group,
        axes=ome_meta["axes"],
        coordinate_transformations=ome_meta["coordinate_transformations"],
        storage_options=dict(chunks=chunk_size, overwrite=True),
        compute=True,
        metadata={} if metadata is None else metadata,
    )


#: Chunks of every level of a tilt series ``(section, y, x)``: one image per chunk along the stack, as the CryoET Data
#: Portal stores tilt series.
TILT_SERIES_CHUNKS = (1, 1024, 1024)
#: Number of levels of a tilt-series pyramid (full size and two binned levels), as on the CryoET Data Portal.
TILT_SERIES_LEVELS = 3


def tilt_series_transforms(pixel_size: float, levels: int) -> List[List[Dict[str, Any]]]:
    """The OME-NGFF scale of each level of a tilt-series pyramid.

    Images are binned by 2 along y and x per level; sections never are. The section axis keeps the pixel size as its
    scale, as on the CryoET Data Portal, so readers that take the scale of the first spatial axis read the pixel size.

    Args:
        pixel_size: Pixel size of the full-size images in Angstrom.
        levels: Number of levels.

    Returns:
        One list of coordinate transformations per level.
    """
    return [[{"type": "scale", "scale": [pixel_size, pixel_size * 2**i, pixel_size * 2**i]}] for i in range(levels)]


def tilt_series_level_shapes(shape: Tuple[int, int, int], levels: int) -> List[Tuple[int, int, int]]:
    """The shape of each level of a tilt-series pyramid, binning y and x by 2 per level (partial blocks kept)."""
    shapes = [tuple(int(s) for s in shape)]
    for _ in range(1, levels):
        n, h, w = shapes[-1]
        shapes.append((n, -(-h // 2), -(-w // 2)))
    return shapes


def write_ome_zarr_tilt_series(
    store: MutableMapping,
    stack: Any,
    pixel_size: float,
    levels: int = TILT_SERIES_LEVELS,
    chunks: Tuple[int, int, int] = TILT_SERIES_CHUNKS,
    dtype: Optional[np.dtype] = np.float32,
    attrs: Optional[Dict[str, Any]] = None,
) -> None:
    """Write a tilt series ``(section, y, x)`` as a multiscale OME-Zarr image.

    The stack is written one section at a time, so any object indexable as ``stack[i]`` (a NumPy array, a memory-mapped
    MRC file, a Zarr array) can be written with memory for one image. Each level is the local mean of 2x2 pixel blocks
    of the level before it; sections are never binned.

    Args:
        store: The store to write to. Existing content is replaced.
        stack: The images, shape ``(section, y, x)``.
        pixel_size: Pixel size of the images in Angstrom.
        levels: Number of levels in the pyramid.
        chunks: Chunk shape of every level.
        dtype: Data type of every level; ``None`` keeps the type of the stack.
        attrs: Extra group attributes to write next to the multiscales metadata.
    """
    # Heavy imports, only needed when writing
    from ome_zarr.writer import write_multiscales_metadata
    from skimage.transform import downscale_local_mean

    shape = tuple(int(s) for s in stack.shape)
    if len(shape) != 3:
        raise ValueError(f"A tilt series must have shape (section, y, x), got {shape}.")
    if levels < 1:
        raise ValueError("A tilt series needs at least one level.")
    dtype = np.dtype(stack.dtype if dtype is None else dtype)

    root_group = zarr.group(store=store, overwrite=True)
    arrays = [
        root_group.create_dataset(str(level), shape=level_shape, chunks=chunks, dtype=dtype, overwrite=True)
        for level, level_shape in enumerate(tilt_series_level_shapes(shape, levels))
    ]

    for section in range(shape[0]):
        image = np.asarray(stack[section]).astype(dtype)
        arrays[0][section] = image
        for array in arrays[1:]:
            image = downscale_local_mean(image, (2, 2)).astype(dtype)
            array[section] = image

    datasets = [
        {"path": str(level), "coordinateTransformations": transforms}
        for level, transforms in enumerate(tilt_series_transforms(pixel_size, levels))
    ]
    write_multiscales_metadata(root_group, datasets=datasets, axes=_ome_zarr_axes(), name="/")
    if attrs:
        root_group.attrs.update(attrs)


def get_pixel_size_from_zarr(zarr_group: zarr.Group, level: int = 0) -> float:
    """The pixel size of a level of an OME-Zarr image in Angstrom: the scale of its last (x) axis.

    Unlike ``get_voxel_size_from_zarr``, this reads the in-plane pixel size of any level of a tilt series, whose
    section axis is not binned.

    Args:
        zarr_group: The zarr group containing OME-Zarr metadata.
        level: Index of the multiscale level.

    Returns:
        The pixel size in Angstrom.
    """
    multiscales = zarr_group.attrs["multiscales"]
    axes = multiscales[0]["axes"]
    unit = axes[-1].get("unit", "angstrom") if isinstance(axes[-1], dict) else "angstrom"
    for transform in multiscales[0]["datasets"][level]["coordinateTransformations"]:
        if transform["type"] == "scale":
            return float(transform["scale"][-1]) * UNITFACTOR.get(unit, 1.0)
    raise ValueError("No scale transformation found in coordinate transformations")


def get_voxel_size_from_zarr(zarr_group: zarr.Group) -> float:
    """Extract voxel size from OME-Zarr coordinate transformations.

    Args:
        zarr_group: The zarr group containing OME-Zarr metadata.

    Returns:
        The voxel size in Angstrom from the coordinate transformations.
    """
    multiscales = zarr_group.attrs["multiscales"]

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

    # Find the scale transformation. Spatial axes come last in OME-NGFF, so a leading channel axis (scale 1) is
    # skipped by reading the first of the trailing three.
    for transform in coord_transforms:
        if transform["type"] == "scale":
            scale = transform["scale"]
            scale_value = float(scale[len(scale) - 3] if len(scale) >= 3 else scale[0])

            # Handle unit conversion
            conversion_factor = UNITFACTOR.get(unit, 1.0)  # Default to 1.0 if unknown unit

            # Convert to Angstrom
            return scale_value * conversion_factor

    # If no scale transformation found, raise an error
    raise ValueError("No scale transformation found in coordinate transformations")


def fits_in_memory(array: zarr.Group, slices: Tuple[slice, ...]) -> Tuple[bool, int, int]:
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

    requested = np.prod(np.array(num_elem)) * array.itemsize
    available = psutil.virtual_memory().available
    fits = requested < available

    return fits, requested, available
