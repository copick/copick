"""Dynamo table picks format handler."""

from typing import Dict, Optional, Tuple

import numpy as np

from copick.util.handlers import FormatCapabilities


class DynamoPicksHandler:
    """Handler for Dynamo table files.

    Dynamo tables are MATLAB-style tables containing particle coordinates,
    Euler angles, and tomogram indices.
    """

    format_name = "dynamo"
    extensions = (".tbl",)
    capabilities = FormatCapabilities(
        can_read=True,
        can_write=True,
        supports_voxel_size=True,
        supports_transforms=True,
        supports_scores=True,  # CC scores
        supports_grouped_import=True,  # Has tomogram index column (20)
        supports_grouped_export=True,  # Supports combined export with tomo column
    )

    def read(
        self,
        path: str,
        voxel_spacing: float,
        **kwargs,
    ) -> Tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]:
        """Read picks from a Dynamo table file.

        Args:
            path: Path to the .tbl file
            voxel_spacing: Voxel spacing in Angstrom

        Returns:
            Tuple of (positions_angstrom, transforms_4x4, scores)
        """
        from copick.util.formats import dynamo_to_copick_transform, read_dynamo_table

        # Read raw Dynamo data (positions in pixels, Euler angles)
        positions_px, eulers_deg, shifts_px, scores = read_dynamo_table(path)

        # Convert to copick format (positions in Angstrom, 4x4 transforms)
        positions_angstrom, transforms = dynamo_to_copick_transform(
            positions_px,
            eulers_deg,
            shifts_px,
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
        """Write picks to a Dynamo table file.

        Args:
            path: Path to write the .tbl file
            positions: Nx3 array of positions in Angstrom
            transforms: Nx4x4 array of transformation matrices
            voxel_spacing: Voxel spacing in Angstrom
            scores: Optional Nx1 array of CC scores

        Returns:
            Path to the written file
        """
        from copick.util.formats import write_dynamo_table

        write_dynamo_table(path, positions, transforms, voxel_spacing, scores=scores)
        return path

    def read_grouped(
        self,
        path: str,
        voxel_spacing: float,
        index_to_run: Dict[int, str],
        **kwargs,
    ) -> Dict[str, Tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]]:
        """Read picks grouped by tomogram index from a Dynamo table.

        Args:
            path: Path to the .tbl file
            voxel_spacing: Voxel spacing in Angstrom
            index_to_run: Mapping from tomogram index to run name

        Returns:
            Dict mapping run_name to (positions, transforms, scores)
        """
        from copick.util.formats import read_dynamo_table_grouped

        return read_dynamo_table_grouped(path, voxel_spacing, index_to_run)

    def write_grouped(
        self,
        path: str,
        grouped_data: Dict[str, Tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]],
        voxel_spacing: float,
        run_to_index: Optional[Dict[str, int]] = None,
        **kwargs,
    ) -> str:
        """Write picks from multiple runs to a single Dynamo table file.

        Args:
            path: Path to write the .tbl file
            grouped_data: Dict mapping run_name to (positions, transforms, scores)
            voxel_spacing: Voxel spacing in Angstrom
            run_to_index: Mapping from run name to tomogram index (required)

        Returns:
            Path to the written file

        Raises:
            ValueError: If run_to_index is not provided
        """
        from copick.util.formats import write_dynamo_table_grouped

        if run_to_index is None:
            raise ValueError("run_to_index mapping is required for Dynamo combined export")

        write_dynamo_table_grouped(
            path,
            grouped_data,
            voxel_spacing,
            run_to_index,
        )
        return path


# Singleton instance
dynamo_handler = DynamoPicksHandler()
