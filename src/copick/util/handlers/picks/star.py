"""STAR (RELION) picks format handler."""

from typing import TYPE_CHECKING, Dict, Optional, Tuple, Union

import numpy as np

from copick.util.handlers import FormatCapabilities

if TYPE_CHECKING:
    import pandas as pd

    from copick.util.formats import RelionTomogram


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
        voxel_spacing: Optional[float],
        tomogram_centers: Optional[Dict[str, Tuple[float, float, float]]] = None,
        tomo_name: Optional[str] = None,
        relion_version: Optional[str] = None,
        *,
        optics: Optional["pd.DataFrame"] = None,
        tilt_series_pixel_size: Optional[float] = None,
        tomogram_center: Optional[Tuple[float, float, float]] = None,
        tomograms: Optional[Dict[str, "RelionTomogram"]] = None,
    ) -> Tuple[np.ndarray, np.ndarray, Optional[np.ndarray], Optional[np.ndarray]]:
        """Convert a RELION DataFrame to positions and transforms.

        Coordinates are resolved by ``copick.util.formats.relion_coordinates_to_angstrom``: centred Angstrom
        coordinates when the tomogram centres are known, else rlnCoordinateX/Y/Z in tilt-series pixels, else in
        pixels of ``voxel_spacing``. Orientations and shifts follow RELION (``copick.util.relion.relion_rows_to_poses``):
        the rotation is ``A_subtomogram @ A_particle`` and the location is the coordinate minus
        ``A_subtomogram @ rlnOrigin{X,Y,Z}Angst``. Filament tables (``rlnHelicalTubeID`` with
        ``rlnHelicalTrackLengthAngst``) are ordered along each filament, and the tube IDs become instance IDs.

        Args:
            df: DataFrame with RELION columns
            voxel_spacing: Voxel spacing in Angstrom for legacy tomogram-pixel coordinates
            tomogram_centers: Dict mapping tomo_name to (center_x, center_y, center_z) in Angstrom.
            tomo_name: Tomogram name for single-tomo reads (used with tomogram_centers)
            relion_version: Force centred ("relion5") or pixel ("relion4") coordinates
            optics: The STAR file's optics table
            tilt_series_pixel_size: Tilt-series pixel size in Angstrom
            tomogram_center: Tomogram centre in Angstrom for every row
            tomograms: tomograms.star entries by tomogram name

        Returns:
            Tuple of (positions_angstrom, transforms_4x4, None, instance_ids or None)
        """
        from copick.util.formats import relion_coordinates_to_angstrom
        from copick.util.relion import order_filament_rows, relion_instance_ids, relion_rows_to_poses

        df = order_filament_rows(df)
        coordinates = relion_coordinates_to_angstrom(
            df,
            voxel_spacing=voxel_spacing,
            tomogram_centers=tomogram_centers,
            tomogram_center=tomogram_center,
            tomo_name=tomo_name,
            tilt_series_pixel_size=tilt_series_pixel_size,
            optics=optics,
            tomograms=tomograms,
            relion_version=relion_version,
        )
        rotations, offsets = relion_rows_to_poses(df)

        transforms = np.zeros((len(df), 4, 4), dtype=float)
        transforms[:, :3, :3] = rotations
        transforms[:, 3, 3] = 1.0

        return coordinates - offsets, transforms, None, relion_instance_ids(df)

    def read(
        self,
        path: str,
        voxel_spacing: Optional[float],
        tomogram_centers: Optional[Dict[str, Tuple[float, float, float]]] = None,
        tomo_name: Optional[str] = None,
        relion_version: Optional[str] = None,
        *,
        tilt_series_pixel_size: Optional[float] = None,
        tomogram_center: Optional[Tuple[float, float, float]] = None,
        tomograms: Optional[Dict[str, "RelionTomogram"]] = None,
        **kwargs,
    ) -> Tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]:
        """Read picks from a STAR file.

        Args:
            path: Path to the STAR file
            voxel_spacing: Voxel spacing in Angstrom for legacy tomogram-pixel coordinates (may be None)
            tomogram_centers: Dict mapping tomo_name to (center_x, center_y, center_z) in Angstrom.
            tomo_name: Tomogram name for coordinate conversion (if not in STAR file)
            relion_version: Force centred ("relion5") or pixel ("relion4") coordinates
            tilt_series_pixel_size: Tilt-series pixel size in Angstrom (overrides the optics table)
            tomogram_center: Tomogram centre in Angstrom for every particle
            tomograms: tomograms.star entries by tomogram name

        Returns:
            Tuple of (positions_angstrom, transforms_4x4, None, instance_ids or None)
        """
        from copick.util.formats import read_star_particles_with_optics

        df, optics = read_star_particles_with_optics(path)
        return self._df_to_picks(
            df,
            voxel_spacing,
            tomogram_centers=tomogram_centers,
            tomo_name=tomo_name,
            relion_version=relion_version,
            optics=optics,
            tilt_series_pixel_size=tilt_series_pixel_size,
            tomogram_center=tomogram_center,
            tomograms=tomograms,
        )

    def write(
        self,
        path: str,
        positions: np.ndarray,
        transforms: np.ndarray,
        voxel_spacing: Optional[float],
        include_optics: bool = True,
        *,
        tomo_name: Optional[str] = None,
        tomogram_center: Optional[Tuple[float, float, float]] = None,
        tilt_series_pixel_size: Optional[float] = None,
        tomogram: Optional["RelionTomogram"] = None,
        instance_ids: Optional[np.ndarray] = None,
        filament: bool = False,
        polarity_known: Union[bool, np.ndarray] = False,
        coordinates: str = "auto",
        **kwargs,
    ) -> str:
        """Write picks to a STAR file.

        Coordinates and optics follow ``copick.util.formats.build_relion_star_tables``: centred coordinates when the
        tomogram centre is known, rlnCoordinateX/Y/Z in tilt-series pixels and an optics table when the tilt-series
        pixel size is known.

        Args:
            path: Path to write the STAR file
            positions: Nx3 array of positions in Angstrom
            transforms: Nx4x4 array of transformation matrices; their translations are added to the positions
            voxel_spacing: Voxel spacing in Angstrom, for legacy tomogram-pixel coordinates when neither the centre
                nor the tilt-series pixel size is known
            include_optics: Whether to include the optics table
            tomo_name: Written as rlnTomoName
            tomogram_center: Tomogram centre in Angstrom
            tilt_series_pixel_size: Tilt-series pixel size in Angstrom
            tomogram: tomograms.star entry for this tomogram (centre, pixel size and CTF parameters)
            instance_ids: Instance IDs (filament IDs with ``filament``)
            filament: Write RELION's filament columns (``copick.util.formats.build_relion_particles_df``)
            polarity_known: For filament columns: whether the point order follows the filament's polarity, for all
                picks (a bool) or per pick (an (N,) array); ``rlnAnglePsiFlipRatio`` is 0 where it does, else 0.5
            coordinates: ``"auto"``, or ``"centered"`` for centered coordinates only (the center is then required)

        Returns:
            Path to the written file
        """
        from copick.util.formats import build_relion_star_tables, write_star_particles

        particles, optics = build_relion_star_tables(
            {tomo_name: (positions, transforms)},
            voxel_spacing=voxel_spacing,
            tomogram_centers={tomo_name: tomogram_center} if tomogram_center is not None else None,
            tilt_series_pixel_size=tilt_series_pixel_size,
            tomograms={tomo_name: tomogram} if tomogram is not None and tomo_name is not None else None,
            include_optics=include_optics,
            instance_ids={tomo_name: instance_ids} if instance_ids is not None else None,
            filament=filament,
            polarity_known=polarity_known,
            coordinates=coordinates,
        )
        write_star_particles(path, particles, optics)
        return path

    def read_grouped(
        self,
        path: str,
        voxel_spacing: Optional[float],
        index_to_run: Dict[int, str],
        tomogram_centers: Optional[Dict[str, Tuple[float, float, float]]] = None,
        relion_version: Optional[str] = None,
        *,
        tilt_series_pixel_size: Optional[float] = None,
        tomograms: Optional[Dict[str, "RelionTomogram"]] = None,
        **kwargs,
    ) -> Dict[str, Tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]]:
        """Read picks grouped by tomogram name from a STAR file.

        STAR files with _rlnTomoName column can contain particles from multiple
        tomograms. This method groups them by tomogram name.

        Note: index_to_run is ignored for STAR files because they use string
        tomogram names directly from the _rlnTomoName column.

        Args:
            path: Path to the STAR file
            voxel_spacing: Voxel spacing in Angstrom for legacy tomogram-pixel coordinates (may be None)
            index_to_run: Ignored for STAR files (uses _rlnTomoName directly)
            tomogram_centers: Dict mapping tomo_name to (center_x, center_y, center_z) in Angstrom.
            relion_version: Force centred ("relion5") or pixel ("relion4") coordinates
            tilt_series_pixel_size: Tilt-series pixel size in Angstrom (overrides the optics table)
            tomograms: tomograms.star entries by tomogram name

        Returns:
            Dict mapping run_name to (positions, transforms, scores, instance_ids or None)
        """
        from copick.util.formats import group_star_particles_by_tomogram, read_star_particles_with_optics

        df, optics = read_star_particles_with_optics(path)
        results = {}

        for run_name, run_df in group_star_particles_by_tomogram(df).items():
            results[run_name] = self._df_to_picks(
                run_df,
                voxel_spacing,
                tomogram_centers=tomogram_centers,
                tomo_name=run_name,
                relion_version=relion_version,
                optics=optics,
                tilt_series_pixel_size=tilt_series_pixel_size,
                tomograms=tomograms,
            )

        return results

    def write_grouped(
        self,
        path: str,
        grouped_data: Dict[str, Tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]],
        voxel_spacing: Optional[float],
        run_to_index: Optional[Dict[str, int]] = None,
        include_optics: bool = True,
        *,
        tomogram_centers: Optional[Dict[str, Tuple[float, float, float]]] = None,
        tilt_series_pixel_size: Union[None, float, Dict[str, float]] = None,
        tomograms: Optional[Dict[str, "RelionTomogram"]] = None,
        grouped_instance_ids: Optional[Dict[str, np.ndarray]] = None,
        filament: bool = False,
        polarity_known: Union[bool, Dict[str, Union[bool, np.ndarray]]] = False,
        coordinates: str = "auto",
        **kwargs,
    ) -> str:
        """Write picks from multiple runs to a single STAR file.

        Uses run_name directly as _rlnTomoName column value. Coordinates and optics follow
        ``copick.util.formats.build_relion_star_tables``.

        Args:
            path: Path to write the STAR file
            grouped_data: Dict mapping run_name to (positions, transforms, scores)
            voxel_spacing: Voxel spacing in Angstrom, for legacy tomogram-pixel coordinates
            run_to_index: Ignored for STAR files (uses run_name directly)
            include_optics: Whether to include the optics table
            tomogram_centers: Tomogram centre in Angstrom per run
            tilt_series_pixel_size: Tilt-series pixel size in Angstrom, for every run or per run (a dict)
            tomograms: tomograms.star entries by run name
            grouped_instance_ids: Instance IDs per run (filament IDs with ``filament``)
            filament: Write RELION's filament columns (``copick.util.formats.build_relion_particles_df``)
            polarity_known: For filament columns: whether the point order follows the filaments' polarity, for all
                picks (a bool) or per run (a dict of run name to a bool or an (N,) array)
            coordinates: ``"auto"``, or ``"centered"`` for centered coordinates only (every run's center is then
                required)

        Returns:
            Path to the written file
        """
        from copick.util.formats import write_star_particles_grouped

        write_star_particles_grouped(
            path,
            grouped_data,
            voxel_spacing,
            tomogram_centers=tomogram_centers,
            tilt_series_pixel_size=tilt_series_pixel_size,
            tomograms=tomograms,
            include_optics=include_optics,
            instance_ids=grouped_instance_ids,
            filament=filament,
            polarity_known=polarity_known,
            coordinates=coordinates,
        )
        return path


# Singleton instance
star_handler = STARPicksHandler()
