from typing import Any, Dict, List, MutableMapping, Tuple

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
        pyramid[vs] = (
            rescale(
                array,
                (1.0 / 2.0, 1.0 / 2.0, 1.0 / 2.0),
                anti_aliasing=False,
                preserve_range=True,
                order=0,
            ).astype(dtype),
        )

    return pyramid


def ome_metadata(pyramid: Dict[float, np.ndarray]) -> Dict[str, Any]:
    return {
        "axes": _ome_zarr_axes(),
        "coordinate_transformations": [[_ome_zarr_transforms(voxel_size)] for voxel_size in pyramid],
    }


def write_ome_zarr_3d(
    store: MutableMapping,
    pyramid: Dict[float, np.ndarray],
    chunk_size: Tuple[int, ...] = (256, 256, 256),
) -> None:
    """Write a 3D pyramid to an OME-Zarr store.

    Args:
        store: The store to write to.
        pyramid: The pyramid to write.
        chunk_size: The chunk size to use for the Zarr store. Default is (256, 256, 256).
    """
    # This is a super heavy import, so we do it here to avoid loading it before it's needed.
    # Writing is slow anyway.
    from ome_zarr.writer import write_multiscale

    ome_meta = ome_metadata(pyramid)
    root_group = zarr.group(store=store, overwrite=True)

    write_multiscale(
        list(pyramid.values()),
        group=root_group,
        axes=ome_meta["axes"],
        coordinate_transformations=ome_meta["coordinate_transformations"],
        storage_options=dict(chunks=chunk_size, overwrite=True),
        compute=True,
        metadata={},
    )


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
    for dim, sl in zip(array.shape, slices):
        num_elem.append(len(range(*sl.indices(dim))))

    requested = np.prod(np.array(num_elem)) * array.itemsize
    available = psutil.virtual_memory().available
    fits = requested < available

    return fits, requested, available
