"""Tilt series, alignments and CTF of the CryoET Data Portal, as copick metadata.

Pure functions over the portal client's ``to_dict()`` records (``TiltSeries``, ``Alignment``,
``PerSectionAlignmentParameters``, ``PerSectionParameters``, ``Frame``), so they work on live and cached data alike.

Portal conventions this module converts:

- ``PerSectionParameters``: ``raw_angle`` is the stage (nominal) tilt angle; defoci in Angstrom (the ``major`` one is
  not guaranteed to be the larger); ``astigmatic_angle`` in degrees; ``phase_shift`` in radians (``null`` means 0);
  ``max_resolution`` in Angstrom (0 means unknown). Rows exist without CTF values when no CTF was deposited.
- ``Frame``: ``acquisition_order`` starts at 0; ``accumulated_dose`` is the dose before the image.
- ``PerSectionAlignmentParameters``: ``x_offset``/``y_offset`` in tilt-series pixels; ``in_plane_rotation`` a 2x2
  rotation matrix; image and volume centres at ``N/2`` (half-pixel convention).
- ``TiltSeries.acceleration_voltage`` in volts. The portal records no amplitude contrast.

An alignment without per-section parameters is a placeholder: the portal creates one, with default values, when a
deposition holds no alignment.
"""

import json
import math
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from copick.models import (
    CopickAlignmentFile,
    CopickCTF,
    CopickExcludedSection,
    CopickReferenceVolume,
    CopickSectionAlignment,
    CopickTiltImage,
    CopickTiltSeriesMetadata,
)
from copick.util.alignment_geometry import (
    decompose_in_plane,
    default_reference_size,
    image_delta,
    native_to_cets_shift,
    rotation,
    volume_delta,
)

#: Amplitude contrast assumed for portal tilt series, which do not record it.
DEFAULT_AMPLITUDE_CONTRAST = 0.07

#: Tolerance for treating a portal matrix as the identity.
_IDENTITY_TOLERANCE = 1e-9


def _camel(value: str) -> str:
    words = re.sub(r"([_\-])+", " ", value).title().replace(" ", "")
    return words[:1].lower() + words[1:]


def parse_portal_matrix(value: Any) -> Optional[np.ndarray]:
    """Parse an ``affine_transformation_matrix``: a nested list, a JSON string (``"[[1, 0], ...]"``) or a Postgres
    array literal (``"{{1,0},...}"``). Returns ``None`` if there is none."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("{"):
            text = text.replace("{", "[").replace("}", "]")
        value = json.loads(text)
    return np.asarray(value, dtype=float)


def _is_identity(matrix: Optional[np.ndarray]) -> bool:
    if matrix is None:
        return True
    return matrix.shape[0] == matrix.shape[1] and np.allclose(matrix, np.eye(matrix.shape[0]), atol=_IDENTITY_TOLERANCE)


def _zero(value: Any) -> bool:
    return value is None or float(value) == 0.0


def tilt_series_type(tilt_series: Dict[str, Any]) -> str:
    """The copick type of a portal tilt series: ``aligned`` for a stack of aligned images, otherwise ``raw``."""
    return "aligned" if tilt_series.get("is_aligned") else "raw"


def portal_ctf(row: Dict[str, Any]) -> Optional[CopickCTF]:
    """The CTF fit of one ``PerSectionParameters`` row, or ``None`` if it has none."""
    major, minor = row.get("major_defocus"), row.get("minor_defocus")
    if major is None or minor is None:
        return None
    resolution = row.get("max_resolution")
    return CopickCTF(
        defocus_u=float(major),
        defocus_v=float(minor),
        defocus_angle=float(row.get("astigmatic_angle") or 0.0),
        phase_shift=math.degrees(float(row.get("phase_shift") or 0.0)),
        fit_resolution=float(resolution) if resolution else None,
    )


def _voltage_kv(value: Any) -> Optional[float]:
    if value is None:
        return None
    value = float(value)
    # The portal records volts; older records may hold kV
    return value / 1000.0 if value > 1000.0 else value


def portal_tilt_series_metadata(
    tilt_series: Dict[str, Any],
    per_section: Sequence[Dict[str, Any]],
    frames: Dict[int, Dict[str, Any]],
) -> CopickTiltSeriesMetadata:
    """The metadata of a portal tilt series.

    Args:
        tilt_series: The ``TiltSeries`` record.
        per_section: Its ``PerSectionParameters`` records.
        frames: ``Frame`` records by id.

    Returns:
        The metadata; images without a ``PerSectionParameters`` record have no per-image values.
    """
    by_section: Dict[int, Dict[str, Any]] = {}
    for row in per_section:
        if row.get("z_index") is not None:
            by_section.setdefault(int(row["z_index"]), row)
    n_sections = tilt_series.get("size_z")
    if n_sections is None:
        n_sections = max(by_section) + 1 if by_section else 0

    images = []
    for section in range(int(n_sections)):
        row = by_section.get(section)
        if row is None:
            images.append(CopickTiltImage(section=section))
            continue
        frame = frames.get(row.get("frame_id")) or {}
        frame_path = frame.get("s3_frame_path") or frame.get("https_frame_path")
        images.append(
            CopickTiltImage(
                section=section,
                nominal_tilt_angle=row.get("raw_angle"),
                acquisition_order=frame.get("acquisition_order"),
                accumulated_dose=frame.get("accumulated_dose"),
                exposure_dose=frame.get("exposure_dose"),
                frame_path=frame_path.rsplit("/", 1)[-1] if frame_path else None,
                ctf=portal_ctf(row),
            ),
        )

    return CopickTiltSeriesMetadata(
        pixel_size=float(tilt_series["pixel_spacing"]),
        width=int(tilt_series["size_x"]),
        height=int(tilt_series["size_y"]),
        images=images,
        tilt_axis_angle=tilt_series.get("tilt_axis"),
        voltage=_voltage_kv(tilt_series.get("acceleration_voltage")),
        spherical_aberration=tilt_series.get("spherical_aberration_constant"),
        amplitude_contrast=DEFAULT_AMPLITUDE_CONTRAST,
        amplitude_contrast_source="default",
        microscope_model=tilt_series.get("microscope_model"),
        detector_model=tilt_series.get("camera_model"),
        is_aligned=bool(tilt_series.get("is_aligned")),
        native={
            key: tilt_series.get(key)
            for key in (
                "microscope_manufacturer",
                "camera_manufacturer",
                "microscope_energy_filter",
                "microscope_phase_plate",
                "tilting_scheme",
                "total_flux",
                "binning_from_frames",
                "aligned_tiltseries_binning",
                "tilt_series_quality",
            )
            if tilt_series.get(key) is not None
        },
        provenance={
            "source": "cryoet-data-portal",
            "portal_tiltseries_id": tilt_series.get("id"),
            "portal_deposition_id": tilt_series.get("deposition_id"),
            "https_omezarr_dir": tilt_series.get("https_omezarr_dir"),
            "https_mrc_file": tilt_series.get("https_mrc_file"),
        },
    )


def resolve_alignment_tilt_series(
    alignment: Dict[str, Any],
    tilt_series: Sequence[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """The tilt series of the run an alignment aligns: the one it names, or the run's only one if it names none."""
    by_id = {ts["id"]: ts for ts in tilt_series}
    if alignment.get("tiltseries_id") is not None:
        return by_id.get(alignment["tiltseries_id"])
    return tilt_series[0] if len(tilt_series) == 1 else None


def portal_alignment_name(alignment: Dict[str, Any]) -> str:
    """The copick name of a portal alignment, e.g. ``projectionMatching-local-18924``."""
    method = _camel(alignment.get("alignment_method") or "undefined")
    kind = (alignment.get("alignment_type") or "GLOBAL").lower()
    return f"{method}-{kind}-{alignment['id']}"


def classify_portal_alignment(
    alignment: Dict[str, Any],
    per_section: Sequence[Dict[str, Any]],
    tilt_series: Optional[Dict[str, Any]],
) -> Tuple[str, List[str]]:
    """Whether a portal alignment comes from its author.

    An alignment without per-section parameters is a placeholder: ``portal_default`` if all its fields hold the
    portal's defaults (no method, not portal standard, global, identity transformation, no offsets), else
    ``no_per_section``. Parameters that do not fit the tilt series (sections out of range or repeated, more sections
    than images, an already aligned stack, or no tilt series) make it ``inconsistent``; otherwise it is ``author``.
    Values that merely look trivial (zero shifts, no rotation) are never taken as a placeholder.

    Returns:
        The status and the reasons for it.
    """
    if not per_section:
        defaults = {
            "no method": alignment.get("alignment_method") is None,
            "not portal standard": not alignment.get("is_portal_standard"),
            "global": (alignment.get("alignment_type") or "GLOBAL") == "GLOBAL",
            "identity transformation": _is_identity(parse_portal_matrix(alignment.get("affine_transformation_matrix"))),
            "no offsets": all(
                _zero(alignment.get(key))
                for key in ("volume_x_offset", "volume_y_offset", "volume_z_offset", "tilt_offset", "x_rotation_offset")
            ),
        }
        if all(defaults.values()):
            return "portal_default", ["no per-section parameters; all fields hold the portal's defaults"]
        return "no_per_section", [
            "no per-section parameters, but not a portal placeholder: "
            + ", ".join(name for name, holds in defaults.items() if not holds)
            + " differ from the defaults",
        ]

    reasons = []
    if tilt_series is None:
        reasons.append("its tilt series could not be resolved")
    else:
        if tilt_series.get("is_aligned"):
            reasons.append("its tilt series holds already aligned images")
        n_sections = tilt_series.get("size_z")
        sections = [row.get("z_index") for row in per_section]
        if n_sections is not None:
            if any(z is None or not 0 <= z < n_sections for z in sections):
                reasons.append(f"sections lie outside 0..{n_sections - 1}")
            if len(sections) > n_sections:
                reasons.append(f"{len(sections)} sections for {n_sections} images")
        if len(set(sections)) != len(sections):
            reasons.append("sections are repeated")
    return ("inconsistent", reasons) if reasons else ("author", [])


def portal_alignment_file(
    alignment: Dict[str, Any],
    per_section: Sequence[Dict[str, Any]],
    tilt_series: Optional[Dict[str, Any]],
    run_name: Optional[str] = None,
) -> CopickAlignmentFile:
    """A portal alignment as a copick alignment.

    Per-section parameters are converted from the portal's half-pixel convention and pixel shifts to the CETS frame
    in Angstrom (see ``copick.util.alignment_geometry``). The reference volume is the portal's alignment volume. Of a
    local alignment only the rigid part is kept. Sections of the tilt series without parameters are excluded as
    ``not_aligned``.
    """
    status, reasons = classify_portal_alignment(alignment, per_section, tilt_series)
    warnings = list(reasons)
    alignment_type = alignment.get("alignment_type") or "GLOBAL"
    if alignment_type == "LOCAL":
        warnings.append("Only the rigid (global) part of this local alignment is available.")

    reference = None
    sections: List[CopickSectionAlignment] = []
    excluded: List[CopickExcludedSection] = []
    tilt_series_type_ = None if tilt_series is None else tilt_series_type(tilt_series)
    registration = parse_portal_matrix(alignment.get("affine_transformation_matrix"))

    if tilt_series is not None:
        pixel_size = round(float(tilt_series["pixel_spacing"]), 3)
        width, height = int(tilt_series["size_x"]), int(tilt_series["size_y"])
        n_sections = tilt_series.get("size_z")
        extent = [alignment.get(f"volume_{axis}_dimension") for axis in "xyz"]
        if all(e for e in extent):
            extent = tuple(float(e) for e in extent)
            reference = CopickReferenceVolume(
                size=default_reference_size(extent, pixel_size),
                voxel_size=pixel_size,
                native_extent=extent,
                offset=tuple(float(alignment.get(f"volume_{axis}_offset") or 0.0) for axis in "xyz"),
                registration=None if _is_identity(registration) else registration.tolist(),
            )
        else:
            warnings.append("The alignment records no volume size; its parameters cannot be converted.")

        if reference is not None:
            d_img = image_delta(width, height, pixel_size, "half")
            d_vol = volume_delta(reference.size, pixel_size, "half", reference.native_extent)
            seen = set()
            for row in sorted(per_section, key=lambda r: (r.get("z_index") is None, r.get("z_index") or 0)):
                z = row.get("z_index")
                if z is None or z in seen or (n_sections is not None and not 0 <= z < n_sections):
                    continue
                seen.add(z)
                try:
                    in_plane = decompose_in_plane(row.get("in_plane_rotation") or [[1.0, 0.0], [0.0, 1.0]])
                except ValueError as e:
                    warnings.append(f"Section {z}: {e}; left out.")
                    continue
                tilt_angle = float(row.get("tilt_angle") or 0.0)
                x_tilt = float(row.get("volume_x_rotation") or 0.0)
                shift = native_to_cets_shift(
                    (float(row.get("x_offset") or 0.0) * pixel_size, float(row.get("y_offset") or 0.0) * pixel_size),
                    rotation(tilt_angle, x_tilt, in_plane),
                    d_img,
                    d_vol,
                )
                sections.append(
                    CopickSectionAlignment(
                        section=int(z),
                        tilt_angle=tilt_angle,
                        x_tilt=x_tilt,
                        in_plane_rotation=in_plane,
                        shift_x=float(shift[0]),
                        shift_y=float(shift[1]),
                    ),
                )
            if sections and n_sections is not None:
                excluded = [
                    CopickExcludedSection(section=z, reason="not_aligned") for z in range(n_sections) if z not in seen
                ]

    return CopickAlignmentFile(
        name=portal_alignment_name(alignment),
        run_name=run_name,
        tilt_series=tilt_series_type_,
        tilt_series_portal_id=None if tilt_series is None else tilt_series.get("id"),
        alignment_type=alignment_type,
        method=alignment.get("alignment_method"),
        source_format="PORTAL",
        native_frame={"image_center": "half", "volume_center": "half"},
        status=status,
        is_portal_standard=alignment.get("is_portal_standard"),
        rigid_part_of_local=alignment_type == "LOCAL",
        reference_volume=reference,
        sections=sections,
        excluded_sections=excluded,
        tilt_offset=alignment.get("tilt_offset"),
        x_rotation_offset=alignment.get("x_rotation_offset"),
        warnings=warnings,
        provenance={
            "source": "cryoet-data-portal",
            "portal_alignment_id": alignment.get("id"),
            "portal_deposition_id": alignment.get("deposition_id"),
            "https_alignment_metadata": alignment.get("https_alignment_metadata"),
        },
    )
