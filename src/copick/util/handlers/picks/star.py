"""STAR (RELION) picks format handler."""

from typing import TYPE_CHECKING, Dict, Optional, Tuple

import numpy as np

from copick.util.handlers import FormatCapabilities

if TYPE_CHECKING:
    import pandas as pd


class STARPicksHandler:
    """Handler for RELION STAR particle files.

    STAR files are the standard format for RELION particle data,
    containing coordinates, Euler angles, and metadata.
    """

    format_name = "star"
    extensions = (".star",)
    capabilities = FormatCapabilities(
        can_read=True,
        can_write=True,
        supports_voxel_size=True,
        supports_transforms=True,
        supports_scores=False,
        supports_grouped_import=True,  # Supports _rlnTomoName column for grouping
        supports_grouped_export=True,  # Supports combined export with _rlnTomoName
    )

    def _df_to_picks(
        self,
        df: "pd.DataFrame",
        voxel_spacing: float,
    ) -> Tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]:
        """Convert a RELION DataFrame to positions and transforms.

        Args:
            df: DataFrame with RELION columns
            voxel_spacing: Voxel spacing in Angstrom for coordinate conversion

        Returns:
            Tuple of (positions_angstrom, transforms_4x4, None)
        """
        from scipy.spatial.transform import Rotation

        # Extract pixel coordinates and convert to Angstrom
        if {"rlnCoordinateX", "rlnCoordinateY", "rlnCoordinateZ"}.issubset(df.columns):
            positions_px = df[["rlnCoordinateX", "rlnCoordinateY", "rlnCoordinateZ"]].to_numpy()
        else:
            raise ValueError("STAR file must contain rlnCoordinateX, rlnCoordinateY, rlnCoordinateZ columns")

        positions_angstrom = positions_px * voxel_spacing

        # Extract Euler angles and convert to 4x4 transformation matrices
        N = len(positions_angstrom)
        transforms = np.zeros((N, 4, 4), dtype=float)
        transforms[:, 3, 3] = 1.0

        if {"rlnAngleRot", "rlnAngleTilt", "rlnAnglePsi"}.issubset(df.columns):
            angles = df[["rlnAngleRot", "rlnAngleTilt", "rlnAnglePsi"]].to_numpy()
            transforms[:, :3, :3] = Rotation.from_euler("ZYZ", angles, degrees=True).inv().as_matrix()
        else:
            transforms[:, :3, :3] = np.eye(3)

        return positions_angstrom, transforms, None

    def read(
        self,
        path: str,
        voxel_spacing: float,
        **kwargs,
    ) -> Tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]:
        """Read picks from a STAR file.

        Args:
            path: Path to the STAR file
            voxel_spacing: Voxel spacing in Angstrom for coordinate conversion

        Returns:
            Tuple of (positions_angstrom, transforms_4x4, None)
        """
        from copick.util.formats import read_star_particles

        df = read_star_particles(path)
        return self._df_to_picks(df, voxel_spacing)

    def write(
        self,
        path: str,
        positions: np.ndarray,
        transforms: np.ndarray,
        voxel_spacing: float,
        include_optics: bool = True,
        **kwargs,
    ) -> str:
        """Write picks to a STAR file.

        Args:
            path: Path to write the STAR file
            positions: Nx3 array of positions in Angstrom
            transforms: Nx4x4 array of transformation matrices
            voxel_spacing: Voxel spacing in Angstrom
            include_optics: Whether to include optics group

        Returns:
            Path to the written file
        """
        from copick.util.formats import write_star_particles

        write_star_particles(
            path,
            positions,
            transforms,
            voxel_spacing,
            include_optics=include_optics,
        )
        return path

    def read_grouped(
        self,
        path: str,
        voxel_spacing: float,
        index_to_run: Dict[int, str],
        **kwargs,
    ) -> Dict[str, Tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]]:
        """Read picks grouped by tomogram name from a STAR file.

        STAR files with _rlnTomoName column can contain particles from multiple
        tomograms. This method groups them by tomogram name.

        Note: index_to_run is ignored for STAR files because they use string
        tomogram names directly from the _rlnTomoName column.

        Args:
            path: Path to the STAR file
            voxel_spacing: Voxel spacing in Angstrom for coordinate conversion
            index_to_run: Ignored for STAR files (uses _rlnTomoName directly)

        Returns:
            Dict mapping run_name to (positions, transforms, scores)
        """
        from copick.util.formats import read_star_particles_grouped

        grouped_dfs = read_star_particles_grouped(path)
        results = {}

        for run_name, df in grouped_dfs.items():
            positions, transforms, scores = self._df_to_picks(df, voxel_spacing)
            results[run_name] = (positions, transforms, scores)

        return results

    def write_grouped(
        self,
        path: str,
        grouped_data: Dict[str, Tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]],
        voxel_spacing: float,
        run_to_index: Optional[Dict[str, int]] = None,
        include_optics: bool = True,
        **kwargs,
    ) -> str:
        """Write picks from multiple runs to a single STAR file.

        Uses run_name directly as _rlnTomoName column value.

        Args:
            path: Path to write the STAR file
            grouped_data: Dict mapping run_name to (positions, transforms, scores)
            voxel_spacing: Voxel spacing in Angstrom
            run_to_index: Ignored for STAR files (uses run_name directly)
            include_optics: Whether to include optics group

        Returns:
            Path to the written file
        """
        from copick.util.formats import write_star_particles_grouped

        optics_group = None
        if include_optics:
            optics_group = {
                "rlnOpticsGroupName": "opticsGroup1",
                "rlnOpticsGroup": 1,
                "rlnImagePixelSize": voxel_spacing,
                "rlnVoltage": 300.0,
                "rlnSphericalAberration": 2.7,
                "rlnAmplitudeContrast": 0.1,
            }

        write_star_particles_grouped(
            path,
            grouped_data,
            voxel_spacing,
            optics_group=optics_group,
        )
        return path


# Singleton instance
star_handler = STARPicksHandler()
