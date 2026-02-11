"""Base protocols for format handlers.

This module defines the interfaces (Protocols) that format handlers must implement.
These enable a pluggable architecture for reading/writing different file formats.
"""

from dataclasses import dataclass
from typing import Dict, Optional, Protocol, Tuple, runtime_checkable

import numpy as np


@dataclass
class FormatCapabilities:
    """Describes what operations a format handler supports."""

    can_read: bool = True
    can_write: bool = False
    supports_voxel_size: bool = False
    supports_transforms: bool = False
    supports_scores: bool = False
    supports_grouped_import: bool = False
    supports_grouped_export: bool = False


@runtime_checkable
class VolumeFormatHandler(Protocol):
    """Protocol for volume file format handlers (tomograms, segmentations).

    Implementations must provide:
    - format_name: Short identifier for the format (e.g., "mrc", "zarr")
    - extensions: File extensions this handler supports
    - capabilities: FormatCapabilities describing what the handler can do
    - read(): Read volume data from a file
    - write(): (Optional) Write volume data to a file
    """

    format_name: str
    extensions: Tuple[str, ...]
    capabilities: FormatCapabilities

    def read(
        self,
        path: str,
        **kwargs,
    ) -> Tuple[np.ndarray, Optional[float]]:
        """Read volume data from a file.

        Args:
            path: Path to the file to read
            **kwargs: Format-specific options

        Returns:
            Tuple of (volume_array, voxel_size_or_none)
            voxel_size is None if the format doesn't store voxel size
        """
        ...

    def write(
        self,
        path: str,
        volume: np.ndarray,
        voxel_size: float,
        **kwargs,
    ) -> str:
        """Write volume data to a file.

        Args:
            path: Path to write the file
            volume: Volume array to write
            voxel_size: Voxel size in Angstrom
            **kwargs: Format-specific options

        Returns:
            Path to the written file
        """
        ...


@runtime_checkable
class PicksFormatHandler(Protocol):
    """Protocol for particle picks file format handlers.

    Implementations must provide:
    - format_name: Short identifier for the format (e.g., "star", "em")
    - extensions: File extensions this handler supports
    - capabilities: FormatCapabilities describing what the handler can do
    - read(): Read picks data from a file
    - write(): (Optional) Write picks data to a file
    - read_grouped(): (Optional) Read picks grouped by tomogram index
    """

    format_name: str
    extensions: Tuple[str, ...]
    capabilities: FormatCapabilities

    def read(
        self,
        path: str,
        voxel_spacing: float,
        **kwargs,
    ) -> Tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]:
        """Read picks data from a file.

        Args:
            path: Path to the file to read
            voxel_spacing: Voxel spacing in Angstrom for coordinate conversion
            **kwargs: Format-specific options

        Returns:
            Tuple of (positions_angstrom, transforms_4x4, scores_or_none)
            - positions_angstrom: Nx3 array of positions in Angstrom
            - transforms_4x4: Nx4x4 array of transformation matrices
            - scores: Optional Nx1 array of scores (None if not supported)
        """
        ...

    def write(
        self,
        path: str,
        positions: np.ndarray,
        transforms: np.ndarray,
        voxel_spacing: float,
        **kwargs,
    ) -> str:
        """Write picks data to a file.

        Args:
            path: Path to write the file
            positions: Nx3 array of positions in Angstrom
            transforms: Nx4x4 array of transformation matrices
            voxel_spacing: Voxel spacing in Angstrom
            **kwargs: Format-specific options

        Returns:
            Path to the written file
        """
        ...

    def read_grouped(
        self,
        path: str,
        voxel_spacing: float,
        index_to_run: Dict[int, str],
        **kwargs,
    ) -> Dict[str, Tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]]:
        """Read picks grouped by tomogram index.

        For formats that store picks from multiple tomograms in a single file.

        Args:
            path: Path to the file to read
            voxel_spacing: Voxel spacing in Angstrom
            index_to_run: Mapping from tomogram index to run name
            **kwargs: Format-specific options

        Returns:
            Dict mapping run_name to (positions, transforms, scores)
        """
        ...

    def write_grouped(
        self,
        path: str,
        grouped_data: Dict[str, Tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]],
        voxel_spacing: float,
        run_to_index: Optional[Dict[str, int]] = None,
        **kwargs,
    ) -> str:
        """Write picks from multiple runs to a single file.

        For formats that can store picks from multiple tomograms in a single file.

        Args:
            path: Path to write the file
            grouped_data: Dict mapping run_name to (positions, transforms, scores)
                - positions: Nx3 array of positions in Angstrom
                - transforms: Nx4x4 array of transformation matrices
                - scores: Optional Nx1 array of scores (None if not supported)
            voxel_spacing: Voxel spacing in Angstrom
            run_to_index: Optional mapping from run name to tomogram index
                (required for EM/Dynamo formats, ignored for STAR/CSV)
            **kwargs: Format-specific options

        Returns:
            Path to the written file
        """
        ...
