"""EM (TOM toolbox motivelist) picks format handler."""

from typing import Dict, Optional, Tuple

import numpy as np

from copick.util.handlers import FormatCapabilities


class EMPicksHandler:
    """Handler for TOM toolbox motivelist (EM) files.

    EM motivelists are matrix files containing particle coordinates
    and Euler angles, with optional tomogram indices.
    """

    format_name = "em"
    extensions = (".em",)
    capabilities = FormatCapabilities(
        can_read=True,
        can_write=True,
        supports_voxel_size=True,
        supports_transforms=True,
        supports_scores=True,  # CCC scores in row 1
        supports_grouped_import=True,  # Has tomogram index column
        supports_grouped_export=True,  # Supports combined export with tomogram index
    )

    def read(
        self,
        path: str,
        voxel_spacing: float,
        tomo_index_row: int = 4,
        **kwargs,
    ) -> Tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]:
        """Read picks from an EM motivelist file.

        Args:
            path: Path to the EM file
            voxel_spacing: Voxel spacing in Angstrom
            tomo_index_row: Row index for tomogram number (default: 4)

        Returns:
            Tuple of (positions_angstrom, transforms_4x4, scores)
        """
        from copick.util.formats import em_to_copick_transform, read_em_motivelist

        # Read raw EM data (positions in pixels, Euler angles)
        positions_px, eulers_deg, scores = read_em_motivelist(path)

        # Convert to copick format (positions in Angstrom, 4x4 transforms)
        positions_angstrom, transforms = em_to_copick_transform(
            positions_px,
            eulers_deg,
            voxel_spacing,
        )

        return positions_angstrom, transforms, scores

    def write(
        self,
        path: str,
        positions: np.ndarray,
        transforms: np.ndarray,
        voxel_spacing: float,
        scores: Optional[np.ndarray] = None,
        **kwargs,
    ) -> str:
        """Write picks to an EM motivelist file.

        Args:
            path: Path to write the EM file
            positions: Nx3 array of positions in Angstrom
            transforms: Nx4x4 array of transformation matrices
            voxel_spacing: Voxel spacing in Angstrom
            scores: Optional Nx1 array of CCC scores

        Returns:
            Path to the written file
        """
        from copick.util.formats import write_em_motivelist

        write_em_motivelist(path, positions, transforms, voxel_spacing, scores=scores)
        return path

    def read_grouped(
        self,
        path: str,
        voxel_spacing: float,
        index_to_run: Dict[int, str],
        tomo_index_row: int = 4,
        **kwargs,
    ) -> Dict[str, Tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]]:
        """Read picks grouped by tomogram index from an EM motivelist.

        Args:
            path: Path to the EM file
            voxel_spacing: Voxel spacing in Angstrom
            index_to_run: Mapping from tomogram index to run name
            tomo_index_row: Row index for tomogram number (default: 4)

        Returns:
            Dict mapping run_name to (positions, transforms, scores)
        """
        from copick.util.formats import read_em_motivelist_grouped

        return read_em_motivelist_grouped(
            path,
            voxel_spacing,
            index_to_run,
            tomo_index_row=tomo_index_row,
        )

    def write_grouped(
        self,
        path: str,
        grouped_data: Dict[str, Tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]],
        voxel_spacing: float,
        run_to_index: Optional[Dict[str, int]] = None,
        tomogram_dimensions: Optional[Tuple[int, int, int]] = None,
        **kwargs,
    ) -> str:
        """Write picks from multiple runs to a single EM motivelist file.

        Args:
            path: Path to write the EM file
            grouped_data: Dict mapping run_name to (positions, transforms, scores)
            voxel_spacing: Voxel spacing in Angstrom
            run_to_index: Mapping from run name to tomogram index (required)
            tomogram_dimensions: Optional (z, y, x) dimensions for coordinate conversion

        Returns:
            Path to the written file

        Raises:
            ValueError: If run_to_index is not provided
        """
        from copick.util.formats import write_em_motivelist_grouped

        if run_to_index is None:
            raise ValueError("run_to_index mapping is required for EM combined export")

        write_em_motivelist_grouped(
            path,
            grouped_data,
            voxel_spacing,
            run_to_index,
            tomogram_dimensions=tomogram_dimensions,
        )
        return path


# Singleton instance
em_picks_handler = EMPicksHandler()
