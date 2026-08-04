"""Zarr volume format handler."""

from typing import Optional, Tuple

import numpy as np
import zarr

from copick.util.handlers import FormatCapabilities
from copick.util.ome import get_level_path, get_multiscales, get_voxel_size_from_zarr, write_ome_zarr_3d


class ZarrVolumeHandler:
    """Handler for Zarr volume files/directories.

    Zarr is a chunked, compressed array format well-suited for large
    volumetric data. It supports multi-resolution pyramids via OME-NGFF.
    """

    format_name = "zarr"
    extensions = (".zarr",)
    capabilities = FormatCapabilities(
        can_read=True,
        can_write=True,
        supports_voxel_size=True,  # Via OME-NGFF metadata
    )

    def read(
        self,
        path: str,
        level: int = 0,
        **kwargs,
    ) -> Tuple[np.ndarray, Optional[float]]:
        """Read volume data from a Zarr store.

        Args:
            path: Path to the Zarr store (directory or .zarr file)
            level: Pyramid level to read (0 = full resolution)

        Returns:
            Tuple of (volume_array, voxel_size_or_none)
        """
        store = zarr.open(path, mode="r")

        # Try to read from OME-NGFF structure (multiscales)
        if isinstance(store, zarr.Group):
            # Check for OME-NGFF multiscales
            try:
                get_multiscales(store)
            except KeyError:
                has_multiscales = False
            else:
                has_multiscales = True

            if not has_multiscales:
                # Simple group, try to find array
                if level != 0:
                    raise ValueError(f"Level {level} not found in Zarr store (max: 0)")
                for key in store:
                    if isinstance(store[key], zarr.Array):
                        return np.array(store[key]), None
                raise ValueError("No arrays found in Zarr group")

            dataset_path = get_level_path(store, level)
            volume = np.array(store[dataset_path])

            # Get voxel size with proper unit conversion using ome.py utility
            try:
                voxel_size = get_voxel_size_from_zarr(store)
                # Scale voxel size for pyramid levels
                if level > 0:
                    voxel_size = voxel_size * (2**level)
            except (KeyError, ValueError):
                voxel_size = None

            return volume, voxel_size
        elif isinstance(store, zarr.Array):
            if level != 0:
                raise ValueError(f"Level {level} not found in Zarr store (max: 0)")
            return np.array(store), None
        else:
            raise ValueError(f"Unexpected Zarr store type: {type(store)}")

    def write(
        self,
        path: str,
        volume: np.ndarray,
        voxel_size: float,
        chunks: Tuple[int, int, int] = (256, 256, 256),
        **kwargs,
    ) -> str:
        """Write volume data to a Zarr store.

        Args:
            path: Path to write the Zarr store
            volume: Volume array to write
            voxel_size: Voxel size in Angstrom
            chunks: Chunk size for the Zarr array

        Returns:
            Path to the written store
        """
        write_ome_zarr_3d(path, {voxel_size: volume}, chunk_size=chunks)
        return path


# Singleton instance
zarr_handler = ZarrVolumeHandler()
