"""MRC volume format handler."""

from typing import Optional, Tuple

import mrcfile
import numpy as np

from copick.util.handlers import FormatCapabilities


class MRCVolumeHandler:
    """Handler for MRC volume files.

    MRC is the standard format for electron microscopy data, containing
    3D density maps along with header information including voxel size.
    """

    format_name = "mrc"
    extensions = (".mrc", ".rec", ".map")
    capabilities = FormatCapabilities(
        can_read=True,
        can_write=True,
        supports_voxel_size=True,
    )

    def read(
        self,
        path: str,
        **kwargs,
    ) -> Tuple[np.ndarray, Optional[float]]:
        """Read volume data from an MRC file.

        Args:
            path: Path to the MRC file

        Returns:
            Tuple of (volume_array, voxel_size)
        """
        with mrcfile.open(path, mode="r", permissive=True) as mrc:
            volume = mrc.data.copy()
            # MRC stores voxel size in Angstrom
            voxel_size = float(mrc.voxel_size.x)
        return volume, voxel_size

    def write(
        self,
        path: str,
        volume: np.ndarray,
        voxel_size: float,
        **kwargs,
    ) -> str:
        """Write volume data to an MRC file.

        Args:
            path: Path to write the MRC file
            volume: Volume array to write
            voxel_size: Voxel size in Angstrom

        Returns:
            Path to the written file
        """
        with mrcfile.new(path, overwrite=kwargs.get("overwrite", False)) as mrc:
            mrc.set_data(volume.astype(np.float32))
            mrc.voxel_size = voxel_size
        return path


# Singleton instance
mrc_handler = MRCVolumeHandler()
