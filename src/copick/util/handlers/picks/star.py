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
        tomogram_centers: Optional[Dict[str, Tuple[float, float, float]]] = None,
        tomo_name: Optional[str] = None,
        relion_version: Optional[str] = None,
    ) -> Tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]:
        """Convert a RELION DataFrame to positions and transforms.

        Supports both RELION 4.x pixel coordinates and RELION 5.0 centered
        Angstrom coordinates. The version is auto-detected from column names
        unless explicitly specified.

        Args:
            df: DataFrame with RELION columns
            voxel_spacing: Voxel spacing in Angstrom for coordinate conversion
            tomogram_centers: Dict mapping tomo_name to (center_x, center_y, center_z) in Angstrom.
                Required for RELION 5.0 centered coordinate conversion.
            tomo_name: Tomogram name for single-tomo reads (used with tomogram_centers)
            relion_version: Override auto-detection ("relion4" or "relion5")

        Returns:
            Tuple of (positions_angstrom, transforms_4x4, None)
        """
        from scipy.spatial.transform import Rotation

        from copick.util.formats import detect_relion_version

        # Auto-detect or use provided version
        version = relion_version or detect_relion_version(df)

        if version == "relion5":
            # RELION 5.0: Centered Angstrom coordinates
            positions_angstrom = df[
                ["rlnCenteredCoordinateXAngst", "rlnCenteredCoordinateYAngst", "rlnCenteredCoordinateZAngst"]
            ].to_numpy()

            # Convert centered -> absolute using tomogram centers
            if tomogram_centers is None:
                raise ValueError(
                    "RELION 5.0 coordinates require tomogram dimensions. Provide --tomograms-star "
                    "or ensure tomograms are already imported into the copick project.",
                )

            # Get tomo_name from df if not provided (for grouped reads)
            if "rlnTomoName" in df.columns:
                for i, (_, row) in enumerate(df.iterrows()):
                    tomo = str(row["rlnTomoName"])
                    if tomo not in tomogram_centers:
                        raise ValueError(f"Tomogram '{tomo}' not found in tomogram centers")
                    center = tomogram_centers[tomo]
                    positions_angstrom[i] += np.array(center)
            elif tomo_name:
                if tomo_name not in tomogram_centers:
                    raise ValueError(f"Tomogram '{tomo_name}' not found in tomogram centers")
                center = np.array(tomogram_centers[tomo_name])
                positions_angstrom += center
            else:
                raise ValueError("Cannot determine tomogram name for RELION 5.0 coordinate conversion")

        else:
            # RELION 4.x: Pixel coordinates
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
        tomogram_centers: Optional[Dict[str, Tuple[float, float, float]]] = None,
        tomo_name: Optional[str] = None,
        relion_version: Optional[str] = None,
        **kwargs,
    ) -> Tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]:
        """Read picks from a STAR file.

        Args:
            path: Path to the STAR file
            voxel_spacing: Voxel spacing in Angstrom for coordinate conversion
            tomogram_centers: Dict mapping tomo_name to (center_x, center_y, center_z) in Angstrom.
                Required for RELION 5.0 centered coordinate conversion.
            tomo_name: Tomogram name for coordinate conversion (if not in STAR file)
            relion_version: Override auto-detection ("relion4" or "relion5")

        Returns:
            Tuple of (positions_angstrom, transforms_4x4, None)
        """
        from copick.util.formats import read_star_particles

        df = read_star_particles(path)
        return self._df_to_picks(
            df,
            voxel_spacing,
            tomogram_centers=tomogram_centers,
            tomo_name=tomo_name,
            relion_version=relion_version,
        )

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
        tomogram_centers: Optional[Dict[str, Tuple[float, float, float]]] = None,
        relion_version: Optional[str] = None,
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
            tomogram_centers: Dict mapping tomo_name to (center_x, center_y, center_z) in Angstrom.
                Required for RELION 5.0 centered coordinate conversion.
            relion_version: Override auto-detection ("relion4" or "relion5")

        Returns:
            Dict mapping run_name to (positions, transforms, scores)
        """
        from copick.util.formats import read_star_particles_grouped

        grouped_dfs = read_star_particles_grouped(path)
        results = {}

        for run_name, df in grouped_dfs.items():
            positions, transforms, scores = self._df_to_picks(
                df,
                voxel_spacing,
                tomogram_centers=tomogram_centers,
                tomo_name=run_name,
                relion_version=relion_version,
            )
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
