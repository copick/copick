"""EM (Electron Microscopy) volume format handler.

This handler supports the EM file format used by TOM toolbox and EMAN.
"""

from typing import Optional, Tuple

import numpy as np

from copick.util.handlers import FormatCapabilities


class EMVolumeHandler:
    """Handler for EM volume files.

    EM is a format used by TOM toolbox and EMAN for storing 3D volumes
    and 2D images. It has a simple header followed by raw data.
    """

    format_name = "em"
    extensions = (".em",)
    capabilities = FormatCapabilities(
        can_read=True,
        can_write=True,
        supports_voxel_size=False,  # EM format has limited metadata
    )

    def read(
        self,
        path: str,
        **kwargs,
    ) -> Tuple[np.ndarray, Optional[float]]:
        """Read volume data from an EM file.

        Args:
            path: Path to the EM file

        Returns:
            Tuple of (volume_array, None) - voxel size not available in EM
        """
        from copick.util.formats import read_em_file

        volume = read_em_file(path)
        return volume, None

    def write(
        self,
        path: str,
        volume: np.ndarray,
        voxel_size: float,
        **kwargs,
    ) -> str:
        """Write volume data to an EM file.

        Args:
            path: Path to write the EM file
            volume: Volume array to write
            voxel_size: Voxel size (not stored in EM format)

        Returns:
            Path to the written file
        """
        from copick.util.formats import write_em_file

        write_em_file(path, volume)
        return path


# Singleton instance
em_handler = EMVolumeHandler()
