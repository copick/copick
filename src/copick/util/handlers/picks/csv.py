"""CSV picks format handler."""

from typing import Dict, Optional, Tuple

import numpy as np

from copick.util.handlers import FormatCapabilities


class CSVPicksHandler:
    """Handler for copick CSV particle files.

    CSV files contain particle picks with run_name, coordinates,
    and optionally transformation matrices.
    """

    format_name = "csv"
    extensions = (".csv",)
    capabilities = FormatCapabilities(
        can_read=True,
        can_write=True,
        supports_voxel_size=False,  # Coordinates already in Angstrom
        supports_transforms=True,
        supports_scores=True,
        supports_grouped_import=True,  # Has run_name column
        supports_grouped_export=True,  # Supports combined export with run_name column
    )

    def read(
        self,
        path: str,
        voxel_spacing: float = 1.0,
        **kwargs,
    ) -> Tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]:
        """Read picks from a CSV file.

        Note: CSV files store coordinates in Angstrom, so voxel_spacing
        is typically not needed (pass 1.0).

        Args:
            path: Path to the CSV file
            voxel_spacing: Ignored (coordinates already in Angstrom)

        Returns:
            Tuple of (positions_angstrom, transforms_4x4, scores_or_none)
        """
        from copick.util.formats import read_copick_csv

        positions, transforms, scores, _ = read_copick_csv(path)
        return positions, transforms, scores

    def write(
        self,
        path: str,
        positions: np.ndarray,
        transforms: np.ndarray,
        voxel_spacing: float,
        run_name: str = "",
        scores: Optional[np.ndarray] = None,
        **kwargs,
    ) -> str:
        """Write picks to a CSV file.

        Args:
            path: Path to write the CSV file
            positions: Nx3 array of positions in Angstrom
            transforms: Nx4x4 array of transformation matrices
            voxel_spacing: Ignored (coordinates already in Angstrom)
            run_name: Run name to include in the file
            scores: Optional Nx1 array of scores

        Returns:
            Path to the written file
        """
        from copick.util.formats import write_copick_csv

        write_copick_csv(path, positions, transforms, run_name=run_name, scores=scores)
        return path

    def read_grouped(
        self,
        path: str,
        voxel_spacing: float,
        index_to_run: Dict[int, str],
        **kwargs,
    ) -> Dict[str, Tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]]:
        """Read picks grouped by run_name from a CSV file.

        Note: CSV files use run_name strings, not indices, so index_to_run
        is ignored. Run names are read directly from the file.

        Args:
            path: Path to the CSV file
            voxel_spacing: Ignored (coordinates already in Angstrom)
            index_to_run: Ignored (CSV uses run_name column directly)

        Returns:
            Dict mapping run_name to (positions, transforms, scores)
        """
        from copick.util.formats import read_copick_csv_grouped

        return read_copick_csv_grouped(path)

    def write_grouped(
        self,
        path: str,
        grouped_data: Dict[str, Tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]],
        voxel_spacing: float,
        run_to_index: Optional[Dict[str, int]] = None,
        **kwargs,
    ) -> str:
        """Write picks from multiple runs to a single CSV file.

        Simply concatenates all runs with run_name column identifying each.

        Args:
            path: Path to write the CSV file
            grouped_data: Dict mapping run_name to (positions, transforms, scores)
            voxel_spacing: Ignored (coordinates already in Angstrom)
            run_to_index: Ignored for CSV (uses run_name directly)

        Returns:
            Path to the written file
        """
        from copick.util.formats import write_picks_csv_grouped

        write_picks_csv_grouped(path, grouped_data)
        return path


# Singleton instance
csv_handler = CSVPicksHandler()
