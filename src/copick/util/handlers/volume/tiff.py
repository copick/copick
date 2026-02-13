"""TIFF volume format handler."""

from typing import Optional, Tuple

import numpy as np
import tifffile

from copick.util.handlers import FormatCapabilities


class TIFFVolumeHandler:
    """Handler for TIFF volume files.

    TIFF is a widely-used image format that can store 3D volumes as
    multi-page images. Note that TIFF does not natively store voxel size.
    """

    format_name = "tiff"
    extensions = (".tiff", ".tif")
    capabilities = FormatCapabilities(
        can_read=True,
        can_write=True,
        supports_voxel_size=False,  # TIFF doesn't store voxel size reliably
    )

    def read(
        self,
        path: str,
        **kwargs,
    ) -> Tuple[np.ndarray, Optional[float]]:
        """Read volume data from a TIFF file.

        Args:
            path: Path to the TIFF file

        Returns:
            Tuple of (volume_array, None) - voxel size not available in TIFF
        """
        volume = tifffile.imread(path)
        return volume, None

    def write(
        self,
        path: str,
        volume: np.ndarray,
        voxel_size: float,
        compression: Optional[str] = None,
        **kwargs,
    ) -> str:
        """Write volume data to a TIFF file.

        Args:
            path: Path to write the TIFF file
            volume: Volume array to write
            voxel_size: Voxel size in Angstrom (stored in metadata if possible)
            compression: Compression method (lzw, zlib, jpeg, or None)

        Returns:
            Path to the written file
        """
        # Map compression names to tifffile options
        compression_map = {
            "lzw": "lzw",
            "zlib": "zlib",
            "jpeg": "jpeg",
            None: None,
            "none": None,
        }
        comp = compression_map.get(compression.lower() if compression else None)

        # Store resolution in ImageJ-compatible format (pixels per unit)
        # Note: This is limited and may not be read by all software
        tifffile.imwrite(
            path,
            volume,
            compression=comp,
            imagej=True,
            resolution=(1.0 / voxel_size, 1.0 / voxel_size) if voxel_size else None,
            metadata={"spacing": voxel_size, "unit": "Angstrom"} if voxel_size else None,
        )
        return path


# Singleton instance
tiff_handler = TIFFVolumeHandler()
