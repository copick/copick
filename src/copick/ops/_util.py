from typing import Any, Dict, List

import numpy as np
from skimage.transform import downscale_local_mean


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
    return {"scale": [voxel_size, voxel_size, voxel_size], "type": "scale"}


def volume_pyramid(
    volume: np.ndarray,
    voxel_size: float,
    levels: int,
) -> Dict[float, np.ndarray]:
    pyramid = {voxel_size: volume}

    vs = voxel_size

    for _ in range(1, levels):
        array = pyramid[vs]
        vs *= 2
        pyramid[vs] = downscale_local_mean(array, (2, 2, 2))

    return pyramid


def ome_metadata(pyramid: Dict[float, np.ndarray]) -> Dict[str, Any]:
    return {
        "axes": _ome_zarr_axes(),
        "transforms": [_ome_zarr_transforms(voxel_size) for voxel_size in pyramid],
    }
