"""Files of tilt-series tools: stacks, tilt angles, acquisition metadata, CTF fits and alignments.

Reads and writes what AreTomo3, Warp, RELION 5, IMOD, CTFFIND4 and SerialEM exchange, and converts it to and from
copick's models. Parsing is done by ``cryoet-alignment``. This module maps the files' rows to the sections of a copick
tilt series and converts alignments between each tool's frame and copick's CETS frame (see
``copick.util.alignment_geometry``).

Each file lists images in its own order:

==================  ============================================  ==================
File                Rows                                          Default mapping
==================  ============================================  ==================
SerialEM ``.mdoc``  ``ZValue``: the stack as SerialEM wrote it    ``index``
``.rawtlt``/``.tlt``  the stack                                   ``index``
AreTomo3 ``_TLT``   the stack it accompanies                      ``index``
AreTomo3 ``.aln``,  ascending tilt angle, dark images included    ``sorted``
``_CTF.txt``
CTFFIND4            the stack                                     ``index``
Warp XML            the ``.tomostar``                             ``angle``
RELION 5            the kept tilts                                ``angle``
IMOD ``.xf``        the stack                                     ``index``
==================  ============================================  ==================

``index`` maps row ``i`` (or the row's ``ZValue``) to section ``i``. ``sorted`` pairs the rows in ascending angle with
the sections in ascending nominal tilt angle. ``angle`` matches each row to the section with the nearest nominal tilt
angle. When the nominal tilt angles are known, every mapping is checked against them; a mapping that fits only with
the signs of the angles flipped is refused, never flipped.
"""

import math
import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

import numpy as np

from copick.models import (
    CopickAlignmentFile,
    CopickCTF,
    CopickExcludedSection,
    CopickReferenceVolume,
    CopickSectionAlignment,
    CopickTiltSeriesMetadata,
)
from copick.util.alignment_geometry import (
    FRAME_CONVENTIONS,
    CenterKind,
    FrameConvention,
    center,
    cets_to_native_shift,
    decompose_in_plane,
    default_reference_size,
    image_delta,
    native_to_cets_shift,
    rotation,
)
from copick.util.log import get_logger

logger = get_logger(__name__)

#: Ways to map the rows of a file to the sections of a tilt series.
SECTION_MAPS = ("auto", "index", "sorted", "angle")
#: Largest difference in degrees between a row's angle and the nominal tilt angle of its section.
DEFAULT_ANGLE_TOLERANCE = 1.0

#: Stack formats by file extension.
STACK_FORMATS = {
    ".mrc": "mrc",
    ".st": "mrc",
    ".mrcs": "mrc",
    ".ali": "mrc",
    ".tif": "tiff",
    ".tiff": "tiff",
    ".zarr": "zarr",
}
#: Tilt-angle file formats.
ANGLE_FORMATS = ("rawtlt", "tlt", "aretomo3-tlt")
#: CTF file formats.
CTF_FORMATS = ("aretomo3", "ctffind4", "warp", "relion")
#: Alignment formats, as named on the command line.
ALIGNMENT_FORMATS = ("aretomo3", "warp", "relion", "imod")
#: Source formats of alignments, as stored in ``CopickAlignmentFile.source_format``.
SOURCE_FORMATS = {"aretomo3": "ARETOMO3", "warp": "WARP", "relion": "RELION", "imod": "IMOD", "cdp": "PORTAL"}

# AreTomo3 and cryoet-alignment write this resolution when the fit resolution is unknown.
_UNKNOWN_RESOLUTION = 999.0


# ---------------------------------------------------------------------------------------------------------------------
# Stacks


def stack_format(path: str, file_type: Optional[str] = None) -> str:
    """The format (``mrc``, ``tiff`` or ``zarr``) of a stack, from ``file_type`` or the file extension."""
    if file_type:
        file_type = file_type.lower()
        if file_type not in ("mrc", "tiff", "zarr"):
            raise ValueError(f"Unsupported stack format {file_type!r}; use mrc, tiff or zarr.")
        return file_type
    suffix = Path(str(path).rstrip("/")).suffix.lower()
    if suffix not in STACK_FORMATS:
        raise ValueError(f"Cannot tell the format of {path}; pass the file type (mrc, tiff or zarr).")
    return STACK_FORMATS[suffix]


@dataclass
class Stack:
    """Images ``(section, y, x)`` of a stack file and the pixel size its header records."""

    data: Any
    pixel_size: Optional[float]

    @property
    def shape(self) -> Tuple[int, int, int]:
        return tuple(int(n) for n in self.data.shape)


class SectionView:
    """The sections of a stack in another order, read one at a time."""

    def __init__(self, data: Any, order: Sequence[int]):
        self.data = data
        self.order = [int(i) for i in order]
        self.shape = (len(self.order),) + tuple(int(n) for n in data.shape[1:])
        self.dtype = data.dtype

    def __getitem__(self, index: int) -> np.ndarray:
        return np.asarray(self.data[self.order[index]])


@contextmanager
def open_stack(path: str, file_type: Optional[str] = None) -> Iterator[Stack]:
    """Open a stack of tilt images for reading.

    MRC files (``.mrc``, ``.st``, ``.mrcs``, ``.ali``) are memory-mapped, so sections are read as they are used. TIFF
    files are read whole. A Zarr store is read at its first OME-Zarr level, or as a plain array.

    Yields:
        Stack: The images ``(section, y, x)`` and the header pixel size in Angstrom (``None`` if unknown).
    """
    fmt = stack_format(path, file_type)
    if fmt == "mrc":
        import mrcfile

        with mrcfile.mmap(path, mode="r", permissive=True) as mrc:
            data = mrc.data
            if data is None:
                raise ValueError(f"{path} holds no image data.")
            if data.ndim == 2:
                data = data[np.newaxis]
            pixel_size = float(mrc.voxel_size.x)
            yield _checked(Stack(data, pixel_size if pixel_size > 0 else None), path)
    elif fmt == "tiff":
        import tifffile

        data = tifffile.imread(path)
        if data.ndim == 2:
            data = data[np.newaxis]
        yield _checked(Stack(data, None), path)
    else:
        import zarr

        node = zarr.open(path, mode="r")
        if isinstance(node, zarr.Group):
            from copick.util.ome import get_level_path, get_pixel_size_from_zarr

            try:
                level_path = get_level_path(node, 0)
            except KeyError:
                raise ValueError(f"{path} is a Zarr group without OME-Zarr multiscales metadata.") from None
            yield _checked(Stack(node[level_path], get_pixel_size_from_zarr(node)), path)
        else:
            yield _checked(Stack(node, None), path)


def _checked(stack: Stack, path: str) -> Stack:
    if len(stack.shape) != 3:
        raise ValueError(f"{path} is not a stack of images: shape {stack.shape}.")
    return stack


# ---------------------------------------------------------------------------------------------------------------------
# Acquisition tables (tilt angles, SerialEM mdoc)


@dataclass
class AcquisitionTable:
    """Per-image acquisition data of a file, in the file's row order.

    Attributes:
        source: The kind of file.
        angles: Tilt angle of each row in degrees.
        keys: Stack section each row names, if the file names one (the mdoc ``ZValue``).
        acquisition_order: 0-based acquisition order of each row.
        exposure_dose: Dose of each image in e/Å².
        accumulated_dose: Dose each image received before it was acquired in e/Å².
        exposure_time: Exposure time of each image in seconds.
        frame_paths: File name of each image's movie.
        pixel_size: Pixel size in Angstrom.
        voltage: Acceleration voltage in kV.
        tilt_axis_angle: Tilt-axis angle in degrees.
        image_size: Image size ``(width, height)`` in pixels.
        default_map: How the rows map to sections by default.
        refined: Whether the angles may be refined rather than nominal.
    """

    source: str
    angles: List[float]
    keys: Optional[List[int]] = None
    acquisition_order: Optional[List[int]] = None
    exposure_dose: Optional[List[float]] = None
    accumulated_dose: Optional[List[float]] = None
    exposure_time: Optional[List[Optional[float]]] = None
    frame_paths: Optional[List[Optional[str]]] = None
    pixel_size: Optional[float] = None
    voltage: Optional[float] = None
    tilt_axis_angle: Optional[float] = None
    image_size: Optional[Tuple[int, int]] = None
    default_map: str = "index"
    refined: bool = False

    def __len__(self) -> int:
        return len(self.angles)


def accumulate_dose(exposure_dose: Sequence[float], acquisition_order: Sequence[int]) -> List[float]:
    """The dose each image received before it was acquired: the sum of the doses of the images acquired earlier."""
    ranked = sorted(range(len(acquisition_order)), key=lambda i: acquisition_order[i])
    accumulated = [0.0] * len(ranked)
    total = 0.0
    for i in ranked:
        accumulated[i] = total
        total += float(exposure_dose[i])
    return accumulated


def angles_format(path: str, fmt: Optional[str] = None) -> str:
    """The format of a tilt-angle file, from ``fmt`` or its name."""
    if fmt:
        if fmt not in ANGLE_FORMATS:
            raise ValueError(f"Unknown tilt-angle format {fmt!r}; use one of {', '.join(ANGLE_FORMATS)}.")
        return fmt
    name = Path(path).name.lower()
    if name.endswith("_tlt.txt"):
        return "aretomo3-tlt"
    if name.endswith(".rawtlt"):
        return "rawtlt"
    if name.endswith(".tlt"):
        return "tlt"
    raise ValueError(f"Cannot tell the format of {path}; pass the angle format ({', '.join(ANGLE_FORMATS)}).")


def read_angles(path: str, fmt: Optional[str] = None) -> AcquisitionTable:
    """Read a tilt-angle file: IMOD ``.rawtlt``/``.tlt`` or AreTomo3 ``_TLT.txt`` (with acquisition order and dose)."""
    fmt = angles_format(path, fmt)
    if fmt == "aretomo3-tlt":
        from cryoet_alignment.io.aretomo3 import AreTomo3TLT

        tlt = AreTomo3TLT.from_file(path)
        order = None if tlt.acq_indices is None else [a - 1 for a in tlt.acq_indices]
        dose = tlt.doses
        return AcquisitionTable(
            source=fmt,
            angles=[float(a) for a in tlt.tilts],
            acquisition_order=order,
            exposure_dose=dose,
            accumulated_dose=None if order is None or dose is None else accumulate_dose(dose, order),
        )

    angles = [float(line.split()[0]) for line in Path(path).read_text().splitlines() if line.strip()]
    if not angles:
        raise ValueError(f"{path} lists no tilt angles.")
    if fmt == "tlt":
        logger.warning(f"{path}: IMOD .tlt files may hold refined angles; they are used as nominal tilt angles.")
    return AcquisitionTable(source=fmt, angles=angles, refined=fmt == "tlt")


def find_mdoc(stack_path: str) -> Optional[Path]:
    """The SerialEM mdoc next to a stack (``TS_01.mrc.mdoc`` or ``TS_01.mdoc``), if there is one."""
    path = Path(str(stack_path).rstrip("/"))
    for candidate in (path.with_name(path.name + ".mdoc"), path.with_suffix(".mdoc")):
        if candidate.exists():
            return candidate
    return None


def read_mdoc(path: str, dose_per_tilt: Optional[float] = None) -> AcquisitionTable:
    """Read a SerialEM tilt-series mdoc.

    Args:
        path: The mdoc.
        dose_per_tilt: Dose of every image in e/Å², overriding the file's.

    Returns:
        AcquisitionTable: One row per ``[ZValue]`` section, keyed by ``ZValue``.
    """
    from cryoet_alignment.io.serialem import SerialEMMdoc

    mdoc = SerialEMMdoc.from_file(path)
    sections = mdoc.sections
    if dose_per_tilt is not None:
        exposure = [float(dose_per_tilt)] * len(sections)
    else:
        exposure = [s.exposure_dose for s in sections]
        if any(d is None for d in exposure) or not any(d > 0 for d in exposure):
            exposure = None
    return AcquisitionTable(
        source="mdoc",
        angles=[float(a) for a in mdoc.tilt_angles],
        keys=[s.z_value for s in sections],
        acquisition_order=mdoc.acquisition_order(),
        exposure_dose=exposure,
        accumulated_dose=mdoc.pre_exposure(dose_per_tilt),
        exposure_time=[s.exposure_time for s in sections],
        frame_paths=[s.sub_frame_name for s in sections],
        pixel_size=mdoc.pixel_spacing,
        voltage=mdoc.voltage,
        tilt_axis_angle=mdoc.tilt_axis_angle,
        image_size=mdoc.image_size,
    )


# ---------------------------------------------------------------------------------------------------------------------
# Section mapping


def _sign_flip_message(what: str) -> str:
    return (
        f"{what}: the angles fit the tilt series only with their signs flipped. copick does not flip them; check the "
        "tool's angle convention (e.g. Warp's ts_import negates stage angles unless --dont_invert is given)."
    )


def _match_by_angle(angles: Sequence[float], nominal: Sequence[float], tolerance: float, what: str) -> List[int]:
    targets = np.asarray(nominal, dtype=float)
    sections = []
    for row, angle in enumerate(angles):
        distance = np.abs(targets - angle)
        section = int(np.argmin(distance))
        if distance[section] > tolerance:
            if all(np.min(np.abs(targets + a)) <= tolerance for a in angles):
                raise ValueError(_sign_flip_message(what))
            raise ValueError(
                f"{what}: row {row} at {angle:.2f} deg matches no section within {tolerance} deg (nearest: section "
                f"{section} at {targets[section]:.2f} deg).",
            )
        sections.append(section)
    return sections


def _check_angles(
    angles: Sequence[float],
    nominal: Sequence[float],
    tolerance: float,
    what: str,
    warn_only: bool,
) -> None:
    angles, nominal = np.asarray(angles, dtype=float), np.asarray(nominal, dtype=float)
    deviation = float(np.max(np.abs(angles - nominal))) if len(angles) else 0.0
    if deviation <= tolerance:
        return
    if float(np.max(np.abs(angles + nominal))) <= tolerance:
        message = _sign_flip_message(what)
    else:
        message = (
            f"{what}: the angles differ from the nominal tilt angles of their sections by up to {deviation:.2f} deg "
            f"(more than {tolerance} deg); choose another section mapping or a larger angle tolerance."
        )
    if warn_only:
        logger.warning(message)
    else:
        raise ValueError(message)


def map_rows(
    n_sections: int,
    angles: Optional[Sequence[float]],
    mode: str,
    nominal: Optional[Sequence[Optional[float]]] = None,
    tolerance: float = DEFAULT_ANGLE_TOLERANCE,
    keys: Optional[Sequence[int]] = None,
    what: str = "rows",
    refined: bool = False,
    n_rows: Optional[int] = None,
) -> List[int]:
    """The tilt-series section of each row of a file.

    Args:
        n_sections: Number of sections of the tilt series.
        angles: Tilt angle of each row, if the file has them; rows without are taken to be in ascending angle.
        mode: ``index``, ``sorted`` or ``angle`` (see the module documentation).
        nominal: Nominal tilt angle of each section, if known.
        tolerance: Largest difference in degrees between a row's angle and the nominal tilt angle of its section.
        keys: Section each row names (``index`` mode).
        what: Name of the rows in messages.
        refined: Whether the rows' angles may be refined; a mismatch is then only reported.
        n_rows: Number of rows, for files with neither angles nor keys.

    Returns:
        The section of each row.

    Raises:
        ValueError: If the rows cannot be mapped, or the mapping contradicts the nominal tilt angles.
    """
    if angles is not None:
        n_rows = len(angles)
    elif keys is not None:
        n_rows = len(keys)
    elif n_rows is None:
        raise ValueError(f"{what}: the number of rows is unknown.")
    known = nominal is not None and len(nominal) == n_sections and all(a is not None for a in nominal)
    if mode == "angle" and angles is None:
        raise ValueError(f"{what}: mapping by angle needs the rows' tilt angles.")
    if mode == "index":
        sections = [int(k) for k in keys] if keys is not None else list(range(n_rows))
    elif mode == "sorted":
        if n_rows != n_sections:
            raise ValueError(f"{what}: {n_rows} rows for {n_sections} sections; 'sorted' pairs them one to one.")
        # Rows without angles are in ascending angle already (AreTomo3's _CTF.txt)
        rows = sorted(range(n_rows), key=lambda i: (angles[i], i)) if angles is not None else list(range(n_rows))
        targets = sorted(range(n_sections), key=lambda s: (nominal[s], s)) if known else list(range(n_sections))
        sections = [0] * n_rows
        for row, section in zip(rows, targets, strict=True):
            sections[row] = section
    elif mode == "angle":
        if not known:
            raise ValueError(f"{what}: mapping by angle needs the nominal tilt angles of the tilt series.")
        sections = _match_by_angle(angles, nominal, tolerance, what)
    else:
        raise ValueError(f"Unknown section mapping {mode!r}; use one of {', '.join(SECTION_MAPS)}.")

    outside = sorted({s for s in sections if not 0 <= s < n_sections})
    if outside:
        raise ValueError(f"{what}: sections {outside} are outside the tilt series (0..{n_sections - 1}).")
    if len(set(sections)) != len(sections):
        duplicates = sorted({s for s in sections if sections.count(s) > 1})
        raise ValueError(f"{what}: several rows map to sections {duplicates}.")
    if known and angles is not None:
        _check_angles(angles, [nominal[s] for s in sections], tolerance, what, warn_only=refined or mode == "index")
    return sections


def resolve_map(mode: str, default: str, nominal_known: bool, what: str) -> str:
    """The mapping to use for ``mode``: the file's default for ``auto``, or ``index`` if that needs unknown angles."""
    if mode != "auto":
        return mode
    if default in ("sorted", "angle") and not nominal_known:
        logger.warning(f"{what}: the nominal tilt angles are unknown; rows are mapped to sections by index.")
        return "index"
    return default


def nominal_angles(metadata: CopickTiltSeriesMetadata, n_sections: Optional[int] = None) -> Optional[List[float]]:
    """The nominal tilt angle of every section, or ``None`` unless all ``n_sections`` are known."""
    angles = metadata.nominal_tilt_angles
    n_sections = metadata.n_sections if n_sections is None else n_sections
    if not angles or len(angles) != n_sections or any(a is None for a in angles):
        return None
    return [float(a) for a in angles]


# ---------------------------------------------------------------------------------------------------------------------
# CTF


@dataclass
class CtfTable:
    """Per-image CTF fits of a file, in the file's row order."""

    source: str
    ctfs: List[CopickCTF]
    angles: Optional[List[float]] = None
    default_map: str = "index"
    native: Dict[str, Any] = field(default_factory=dict)


def _resolution(value: Optional[float]) -> Optional[float]:
    return None if value is None or value <= 0 or value >= _UNKNOWN_RESOLUTION else float(value)


def read_ctf(path: str, fmt: str, pixel_size: Optional[float] = None, tomo_name: Optional[str] = None) -> CtfTable:
    """Read per-image CTF fits.

    Args:
        path: The file: an AreTomo3 ``_CTF.txt``, a CTFFIND4 output ``.txt``, a Warp tilt-series XML or a RELION
            ``tomograms.star``.
        fmt: ``aretomo3``, ``ctffind4``, ``warp`` or ``relion``.
        pixel_size: Pixel size of a Warp tilt series, if its XML does not record one.
        tomo_name: The tomogram of a RELION file listing several.

    Returns:
        CtfTable: The fits in canonical form (``u >= v`` in Angstrom, angle in [0, 180) degrees, phase in degrees).
    """
    if fmt in ("aretomo3", "ctffind4"):
        from cryoet_alignment.io.aretomo3 import AreTomo3CTF

        table = AreTomo3CTF.from_file(path)
        ctfs = [
            CopickCTF(
                defocus_u=r.df_max_a,
                defocus_v=r.df_min_a,
                defocus_angle=r.azimuth_deg,
                phase_shift=math.degrees(r.phase_rad),
                fit_resolution=_resolution(r.res_a),
                fit_score=r.score,
            )
            for r in table.rows
        ]
        native = {"df_hand": [r.df_hand for r in table.rows]} if table.has_df_hand else {}
        return CtfTable(source=fmt, ctfs=ctfs, default_map="sorted" if fmt == "aretomo3" else "index", native=native)

    if fmt == "warp":
        from cryoet_alignment.io.warp import WarpAlignment

        warp = WarpAlignment.from_file(path, pixel_size_a=pixel_size or 1.0)
        if not warp.has_ctf:
            raise ValueError(f"{path} holds no per-tilt CTF fit.")
        ctfs = [
            CopickCTF(
                defocus_u=(e.defocus_um + e.defocus_delta_um / 2.0) * 1e4,
                defocus_v=(e.defocus_um - e.defocus_delta_um / 2.0) * 1e4,
                defocus_angle=e.defocus_angle_deg,
                phase_shift=(e.phase_shift_pi or 0.0) * 180.0,
            )
            for e in warp.entries
        ]
        return CtfTable(source=fmt, ctfs=ctfs, angles=[-e.tilt_angle for e in warp.entries], default_map="angle")

    if fmt == "relion":
        from cryoet_alignment.io.relion import RelionAlignment

        relion = RelionAlignment.from_file(path, tomo_name=tomo_name)
        if not relion.has_ctf:
            raise ValueError(f"{path} holds no per-tilt CTF fit for every tilt of {relion.tomo_name}.")
        ctfs = [
            CopickCTF(
                defocus_u=e.defocus_u,
                defocus_v=e.defocus_v,
                defocus_angle=e.defocus_angle,
                phase_shift=e.phase_shift or 0.0,
                fit_resolution=_resolution(e.ctf_max_resolution),
                fit_score=e.ctf_figure_of_merit,
            )
            for e in relion.entries
        ]
        angles = [e.nominal_stage_tilt_angle for e in relion.entries]
        return CtfTable(source=fmt, ctfs=ctfs, angles=angles, default_map="angle")

    raise ValueError(f"Unknown CTF format {fmt!r}; use one of {', '.join(CTF_FORMATS)}.")


def ctfs_to_aretomo3(ctfs: Sequence[Optional[CopickCTF]], df_hand: Optional[Sequence[int]] = None):
    """CTF fits as an AreTomo3 ``_CTF.txt`` (CTFFIND4 columns), one row per fit in the given order.

    Raises:
        ValueError: If a fit is missing; the file needs one per image.
    """
    from cryoet_alignment.io.aretomo3 import AreTomo3CTF, CtfInfo

    missing = [i for i, ctf in enumerate(ctfs) if ctf is None]
    if missing:
        raise ValueError(f"Rows {missing} have no CTF fit; the file needs one for every image.")
    return AreTomo3CTF(
        rows=[
            CtfInfo(
                micrograph=i + 1,
                df_max_a=ctf.defocus_u,
                df_min_a=ctf.defocus_v,
                azimuth_deg=ctf.defocus_angle,
                phase_rad=math.radians(ctf.phase_shift),
                score=0.0 if ctf.fit_score is None else ctf.fit_score,
                res_a=999.99 if ctf.fit_resolution is None else ctf.fit_resolution,
                df_hand=None if df_hand is None else int(df_hand[i]),
            )
            for i, ctf in enumerate(ctfs)
        ],
    )


def warp_ctf_values(ctf: CopickCTF) -> Dict[str, float]:
    """A CTF fit as the values of Warp's per-tilt CTF grids (µm, degrees, multiples of π)."""
    return {
        "defocus_um": (ctf.defocus_u + ctf.defocus_v) / 2.0 * 1e-4,
        "defocus_delta_um": (ctf.defocus_u - ctf.defocus_v) * 1e-4,
        "defocus_angle_deg": ctf.defocus_angle,
        "phase_shift_pi": ctf.phase_shift / 180.0,
    }


# ---------------------------------------------------------------------------------------------------------------------
# Alignments


@dataclass
class NativeAlignment:
    """An alignment read from a tool's files, before it is mapped to the sections of a tilt series.

    ``hub`` holds the per-row parameters in the tool's own frame (cryoet-alignment's canonical model relabels fields
    and applies no centre corrections), with offsets in pixels of ``shift_pixel_size``.

    Attributes:
        source_format: ``ARETOMO3``, ``WARP``, ``RELION`` or ``IMOD``.
        hub: The ``cryoet_alignment`` ``Alignment``.
        row_angles: Stage tilt angle of each row of the tool's stack, for mapping rows to sections.
        row_reasons: Why rows without parameters have none (``dark`` or ``excluded``).
        row_doses: Accumulated dose of each row in e/Å², if the files record it, to check the mapping.
        row_movies: Movie of each row, if the files record it, to check the mapping.
        n_rows: Number of rows of the tool's stack, if the files record it.
        default_map: How rows map to sections by default.
        refined_angles: Whether ``row_angles`` may be refined angles.
        shift_pixel_size: Pixel size of the hub's offsets, if the files record it (else that of the tilt series).
        image_size: Size of the images the tool aligned in pixels, if recorded.
        image_extent: Extent of those images in Angstrom, if recorded.
        volume_size: Size of the tool's volume in voxels of ``volume_voxel_size``, if recorded.
        volume_voxel_size: Voxel size of ``volume_size`` (``None``: the pixel size of the offsets).
        volume_extent: Extent of the tool's volume in Angstrom, if recorded.
        alignment_type: ``GLOBAL`` or ``LOCAL`` (of which only the rigid part is kept).
        native: Format-specific values, kept for reference.
        warnings: Losses or assumptions of the import.
    """

    source_format: str
    hub: Any
    row_angles: Dict[int, float]
    row_reasons: Dict[int, str] = field(default_factory=dict)
    row_doses: Dict[int, float] = field(default_factory=dict)
    row_movies: Dict[int, str] = field(default_factory=dict)
    n_rows: Optional[int] = None
    default_map: str = "index"
    refined_angles: bool = False
    shift_pixel_size: Optional[float] = None
    image_size: Optional[Tuple[int, int]] = None
    image_extent: Optional[Tuple[float, float]] = None
    volume_size: Optional[Tuple[int, int, int]] = None
    volume_voxel_size: Optional[float] = None
    volume_extent: Optional[Tuple[float, float, float]] = None
    alignment_type: str = "GLOBAL"
    native: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


def imod_basename(path: str) -> str:
    """The basename of IMOD alignment files, from the basename itself or any of ``.xf``, ``.tlt``, ``.xtilt``."""
    for suffix in (".xf", ".tlt", ".xtilt"):
        if str(path).endswith(suffix):
            return str(path)[: -len(suffix)]
    return str(path)


def read_native_alignment(
    path: str,
    fmt: str,
    pixel_size: Optional[float] = None,
    tomo_name: Optional[str] = None,
    image_size: Optional[Tuple[int, int]] = None,
    rigid_only: bool = False,
    allow_varying_grids: bool = False,
) -> NativeAlignment:
    """Read an alignment in a tool's format.

    Args:
        path: The ``.aln`` (AreTomo3), tilt-series XML (Warp), ``tomograms.star`` (RELION) or basename / ``.xf``
            (IMOD, with ``.tlt``, optional ``.xtilt`` and ``tilt.com`` next to it).
        fmt: ``aretomo3``, ``warp``, ``relion`` or ``imod``.
        pixel_size: Pixel size of the stack the tool aligned, if not that of the tilt series (Warp: overrides its
            XML).
        tomo_name: The tomogram of a RELION file listing several.
        image_size: Image size ``(width, height)``, needed for RELION files with projection matrices.
        rigid_only: Keep the rigid part of a local (patch) AreTomo3 alignment.
        allow_varying_grids: Drop the spatially varying deformation of a Warp alignment.

    Raises:
        ValueError: If the alignment is local and its loss is not allowed, or the files are inconsistent.
    """
    from cryoet_alignment.io.cryoet_data_portal import Alignment

    if fmt == "aretomo3":
        from cryoet_alignment.io.aretomo3 import AreTomo3ALN

        aln = AreTomo3ALN.from_file(path)
        warnings = []
        if not aln.is_rigid:
            if not rigid_only:
                raise ValueError(
                    f"{path} is a local alignment ({aln.NumPatches} patches); copick stores only its rigid part. "
                    "Pass rigid_only (--rigid-only) to import that.",
                )
            warnings.append(f"Only the rigid part of this local alignment ({aln.NumPatches} patches) is stored.")
        hub = Alignment.from_aretomo3(aln)
        offset = float(aln.AlphaOffset or 0.0)
        row_angles = {z: float(g.tilt) - offset for z, g in zip(aln.z_indices(), aln.GlobalAlignments, strict=True)}
        row_angles.update({d.section_idx: float(d.angle) for d in aln.DarkFrames})
        thickness = int(aln.Thickness or 0)
        return NativeAlignment(
            source_format="ARETOMO3",
            hub=hub,
            row_angles=row_angles,
            row_reasons={d.section_idx: "dark" for d in aln.DarkFrames},
            n_rows=aln.n_raw,
            default_map="sorted",
            shift_pixel_size=pixel_size,
            image_size=(int(aln.RawSize[0]), int(aln.RawSize[1])),
            volume_size=(int(aln.RawSize[0]), int(aln.RawSize[1]), thickness) if thickness > 0 else None,
            alignment_type="GLOBAL" if aln.is_rigid else "LOCAL",
            native={"num_patches": aln.NumPatches, "alpha_offset": aln.AlphaOffset, "beta_offset": aln.BetaOffset},
            warnings=warnings,
        )

    if fmt == "warp":
        from cryoet_alignment.io.warp import WarpAlignment

        warp = WarpAlignment.from_file(path, pixel_size_a=pixel_size)
        if warp.grid_audit.has_varying_grids and not allow_varying_grids:
            raise ValueError(
                f"{path} carries spatially varying deformation grids "
                f"({', '.join(warp.grid_audit.varying_grid_names)}); copick stores only the rigid part. Pass "
                "allow_varying_grids (--allow-varying-grids) to drop them.",
            )
        warnings = []
        if warp.grid_audit.has_varying_grids:
            warnings.append(
                f"Spatially varying deformation grids ({', '.join(warp.grid_audit.varying_grid_names)}) were dropped.",
            )
        hub = Alignment.from_warp(warp, allow_varying_grids=allow_varying_grids)
        extent = tuple(float(v) for v in warp.volume_dimensions_physical)
        return NativeAlignment(
            source_format="WARP",
            hub=hub,
            # Warp's ts_import stores the negated stage angles (unless --dont_invert)
            row_angles={e.z_index: -float(e.tilt_angle) for e in warp.entries},
            row_reasons={e.z_index: "excluded" for e in warp.entries if not e.use_tilt},
            row_doses={e.z_index: float(e.dose) for e in warp.entries} if any(e.dose > 0 for e in warp.entries) else {},
            row_movies={e.z_index: e.movie_path for e in warp.entries if e.movie_path},
            n_rows=warp.n_tilts,
            default_map="angle",
            shift_pixel_size=warp.pixel_size_a,
            image_extent=tuple(float(v) for v in warp.image_dimensions_physical),
            volume_extent=extent if all(v > 0 for v in extent) else None,
            alignment_type="GLOBAL" if warp.is_rigid else "LOCAL",
            native={
                "level_angle_x": warp.level_angle_x,
                "level_angle_y": warp.level_angle_y,
                "are_angles_inverted": warp.are_angles_inverted,
            },
            warnings=warnings,
        )

    if fmt == "relion":
        from cryoet_alignment.io.relion import RelionAlignment

        relion = RelionAlignment.from_file(path, tomo_name=tomo_name, image_size_px=image_size)
        hub = Alignment.from_relion(relion)
        return NativeAlignment(
            source_format="RELION",
            hub=hub,
            row_angles={i: float(e.nominal_stage_tilt_angle) for i, e in enumerate(relion.entries)},
            default_map="angle",
            shift_pixel_size=relion.pixel_size_a,
            volume_size=tuple(int(n) for n in relion.volume_size_px),
            volume_voxel_size=relion.pixel_size_a,
            native={"tomo_name": relion.tomo_name, "hand": relion.hand},
        )

    if fmt == "imod":
        from cryoet_alignment.io.imod import ImodAlignment

        imod = ImodAlignment.read(base_name=imod_basename(path))
        hub = Alignment.from_imod(imod)
        n_rows = len(imod.tlt.angles)
        aligned = {p.z_index for p in hub.per_section_alignment_parameters}
        volume_size = None
        tiltcom = imod.tiltcom
        if tiltcom is not None:
            binning = int(tiltcom.IMAGEBINNED or 1)
            volume_size = (int(tiltcom.FULLIMAGE[0]), int(tiltcom.FULLIMAGE[1]), int(tiltcom.THICKNESS) * binning)
        return NativeAlignment(
            source_format="IMOD",
            hub=hub,
            row_angles={i: float(a) for i, a in enumerate(imod.tlt.angles)},
            row_reasons={z: "excluded" for z in range(n_rows) if z not in aligned},
            n_rows=n_rows,
            default_map="index",
            refined_angles=True,
            shift_pixel_size=pixel_size,
            volume_size=volume_size,
        )

    raise ValueError(f"Unknown alignment format {fmt!r}; use one of {', '.join(ALIGNMENT_FORMATS)}.")


def frame_convention(
    source_format: str,
    image_size: Sequence[int],
    volume_size: Optional[Sequence[int]] = None,
    assume_frame: Optional[CenterKind] = None,
) -> FrameConvention:
    """The image and volume centre conventions of a tool.

    IMOD's centres are pinned here only for even sizes, where ``N/2`` and ``floor(N/2)`` agree; odd sizes need
    ``assume_frame``.

    Raises:
        ValueError: For IMOD with odd sizes and no ``assume_frame``, or ``assume_frame`` with another tool.
    """
    if source_format == "IMOD":
        if assume_frame is not None:
            return FrameConvention(assume_frame, assume_frame)
        sizes = [int(n) for n in image_size] + [int(n) for n in (volume_size or ())]
        if any(n % 2 for n in sizes):
            raise ValueError(
                f"IMOD's centre convention is known here only for even sizes, got {sizes}; pass assume_frame "
                "(--assume-frame half or floor).",
            )
        return FrameConvention("half", "half")
    if assume_frame is not None:
        raise ValueError(f"assume_frame applies to IMOD only; {source_format} has a known centre convention.")
    return FRAME_CONVENTIONS[source_format]


def native_volume_center(reference: CopickReferenceVolume, kind: CenterKind, voxel_size: float) -> np.ndarray:
    """Position in Angstrom, from the corner of the reference volume, of the centre a tool puts on it.

    A tool with ``half`` centres puts it at half the volume's extent. A tool with ``floor`` centres reconstructs the
    extent in ``round(extent / voxel_size)`` voxels of ``voxel_size`` and puts it at the floor of half of those.
    """
    extent = np.asarray(reference.extent, dtype=float)
    if kind == "half":
        return extent / 2.0
    size = np.round(extent / voxel_size)
    return center(size, voxel_size, "floor")


def _volume_offset(reference: CopickReferenceVolume, kind: CenterKind, voxel_size: float) -> np.ndarray:
    return native_volume_center(reference, kind, voxel_size) - center(reference.size, reference.voxel_size, "floor")


def native_reference(
    native: NativeAlignment,
    pixel_size: float,
    volume_size: Optional[Sequence[int]] = None,
    thickness: Optional[int] = None,
    image_size: Optional[Tuple[int, int]] = None,
) -> CopickReferenceVolume:
    """The reference volume of an imported alignment: the volume the tool reconstructs with it.

    Args:
        native: The alignment.
        pixel_size: Pixel size of the tool's offsets in Angstrom.
        volume_size: Size ``(x, y, z)`` of the tool's volume in pixels of ``pixel_size``, overriding the files.
        thickness: Thickness of the tool's volume in pixels; x and y are those of the images.
        image_size: Size of the images, for ``thickness``.

    Raises:
        ValueError: If the files do not record the volume and none is given.
    """
    if volume_size is not None:
        return CopickReferenceVolume(size=tuple(int(n) for n in volume_size), voxel_size=pixel_size)
    if thickness is not None:
        width, height = native.image_size or image_size
        return CopickReferenceVolume(size=(int(width), int(height), int(thickness)), voxel_size=pixel_size)
    if native.volume_extent is not None:
        return CopickReferenceVolume(
            size=default_reference_size(native.volume_extent, pixel_size),
            voxel_size=pixel_size,
            native_extent=native.volume_extent,
        )
    if native.volume_size is not None:
        return CopickReferenceVolume(size=native.volume_size, voxel_size=native.volume_voxel_size or pixel_size)
    raise ValueError(
        "The alignment files do not record the size of the reconstructed volume; pass its thickness (--thickness), "
        "size (--volume-size) or the reconstructed tomogram (--reference-tomogram).",
    )


@dataclass
class ImportedAlignment:
    """An alignment mapped to a tilt series, in copick's CETS frame."""

    sections: List[CopickSectionAlignment]
    excluded_sections: List[CopickExcludedSection]
    reference_volume: CopickReferenceVolume
    native_frame: Dict[str, str]
    warnings: List[str]


def native_to_copick(
    native: NativeAlignment,
    metadata: CopickTiltSeriesMetadata,
    reference: CopickReferenceVolume,
    section_map: str = "auto",
    tolerance: float = DEFAULT_ANGLE_TOLERANCE,
    assume_frame: Optional[CenterKind] = None,
    n_sections: Optional[int] = None,
) -> ImportedAlignment:
    """Map an alignment to the sections of a tilt series and convert it to copick's CETS frame.

    Args:
        native: The alignment.
        metadata: Metadata of the tilt series.
        reference: Its reference volume (see ``native_reference``).
        section_map: How the tool's rows map to sections (see the module documentation).
        tolerance: Largest difference in degrees between a row's angle and the nominal angle of its section.
        assume_frame: Centre convention of an IMOD alignment of odd-sized images or volumes.
        n_sections: Number of sections of the tilt series (default: that of the metadata).
    """
    width, height, pixel_size = metadata.width, metadata.height, metadata.pixel_size
    n_sections = metadata.n_sections if n_sections is None else n_sections
    warnings = list(native.warnings)
    nominal = nominal_angles(metadata, n_sections)

    shift_pixel_size = native.shift_pixel_size or pixel_size
    frame = frame_convention(
        native.source_format,
        native.image_size or (width, height),
        np.round(np.asarray(reference.extent) / shift_pixel_size).astype(int).tolist(),
        assume_frame,
    )

    what = f"{native.source_format} alignment"
    rows = sorted(native.row_angles)
    mode = resolve_map(section_map, native.default_map, nominal is not None, what)
    if mode in ("index", "sorted") and native.n_rows is not None and native.n_rows != n_sections:
        raise ValueError(f"{what}: {native.n_rows} rows for a tilt series of {n_sections} sections.")
    mapped = map_rows(
        n_sections,
        [native.row_angles[r] for r in rows],
        mode,
        nominal=nominal,
        tolerance=tolerance,
        keys=rows,
        what=what,
        refined=native.refined_angles,
    )
    section_of = dict(zip(rows, mapped, strict=True))
    _check_row_values(native, section_of, metadata, n_sections, nominal, tolerance, what, warnings)

    # Offset of the tool's image centre from the CETS centre of the stored images
    if native.image_extent is not None and frame.image_center == "half":
        native_image_center = np.asarray(native.image_extent, dtype=float) / 2.0
    else:
        native_size = native.image_size or (
            int(round(width * pixel_size / shift_pixel_size)),
            int(round(height * pixel_size / shift_pixel_size)),
        )
        native_image_center = center(native_size, shift_pixel_size, frame.image_center)
    stored_extent = np.asarray([width, height], dtype=float) * pixel_size
    native_extent = (
        np.asarray(native.image_extent, dtype=float)
        if native.image_extent is not None
        else np.asarray(native.image_size or (width, height), dtype=float) * shift_pixel_size
    )
    if np.max(np.abs(native_extent - stored_extent)) > pixel_size:
        warnings.append(
            f"The tool aligned images of {native_extent.tolist()} Å, the tilt series holds {stored_extent.tolist()} Å; "
            "they are assumed to share their corner.",
        )
    d_img = native_image_center - center((width, height), pixel_size, "floor")
    d_vol = _volume_offset(reference, frame.volume_center, shift_pixel_size)

    sections = []
    for p in native.hub.per_section_alignment_parameters:
        in_plane = decompose_in_plane(p.in_plane_rotation)
        matrix = rotation(p.tilt_angle, p.volume_x_rotation, in_plane)
        shift = native_to_cets_shift(
            (p.x_offset * shift_pixel_size, p.y_offset * shift_pixel_size),
            matrix,
            d_img,
            d_vol,
        )
        sections.append(
            CopickSectionAlignment(
                section=section_of[p.z_index],
                tilt_angle=float(p.tilt_angle),
                x_tilt=float(p.volume_x_rotation),
                in_plane_rotation=in_plane,
                shift_x=float(shift[0]),
                shift_y=float(shift[1]),
            ),
        )

    aligned = {s.section for s in sections}
    reasons = {section_of[r]: reason for r, reason in native.row_reasons.items() if r in section_of}
    excluded = [
        CopickExcludedSection(section=s, reason=reasons.get(s, "not_aligned"))
        for s in range(n_sections)
        if s not in aligned
    ]
    return ImportedAlignment(
        sections=sections,
        excluded_sections=excluded,
        reference_volume=reference,
        native_frame={"image_center": frame.image_center, "volume_center": frame.volume_center},
        warnings=warnings,
    )


def _stem(path: str) -> str:
    name = re.split(r"[\\/]", path)[-1]
    return name.rsplit(".", 1)[0] if "." in name else name


def _row_agreement(
    native: NativeAlignment,
    section_of: Dict[int, int],
    images: Sequence[Any],
) -> Tuple[int, int]:
    """How many of the rows' doses and movies the sections they map to have, and how many of those agree."""
    checked = agreeing = 0
    for row, section in section_of.items():
        image = images[section]
        movie = native.row_movies.get(row)
        if movie and image.frame_path:
            checked += 1
            agreeing += _stem(movie) == _stem(image.frame_path)
        dose = native.row_doses.get(row)
        if dose is not None and image.accumulated_dose is not None:
            checked += 1
            agreeing += abs(dose - image.accumulated_dose) <= max(0.5, 0.05 * abs(image.accumulated_dose))
    return checked, agreeing


def _check_row_values(
    native: NativeAlignment,
    section_of: Dict[int, int],
    metadata: CopickTiltSeriesMetadata,
    n_sections: int,
    nominal: Optional[List[float]],
    tolerance: float,
    what: str,
    warnings: List[str],
) -> None:
    """Check a mapping of rows to sections against the rows' doses and movies.

    Tilt series are often symmetric in angle, so angles whose signs are flipped still match sections, the mirrored
    ones. The doses and movies of the rows tell them apart.

    Raises:
        ValueError: If the rows' values fit only the mapping with the angles' signs flipped.
    """
    if len(metadata.images) != n_sections or not (native.row_doses or native.row_movies):
        return
    checked, agreeing = _row_agreement(native, section_of, metadata.images)
    if not checked or agreeing == checked:
        return
    if nominal is not None:
        rows = list(section_of)
        try:
            flipped = map_rows(
                n_sections,
                [-native.row_angles[r] for r in rows],
                "angle",
                nominal,
                tolerance,
                what=what,
            )
        except ValueError:
            flipped = None
        if flipped is not None:
            flipped_checked, flipped_agreeing = _row_agreement(
                native,
                dict(zip(rows, flipped, strict=True)),
                metadata.images,
            )
            if flipped_checked and flipped_agreeing == flipped_checked:
                raise ValueError(_sign_flip_message(what))
    warnings.append(
        f"{checked - agreeing} of {checked} doses and movies of the rows differ from those of the sections they map to.",
    )


def tomogram_reference(tomogram) -> CopickReferenceVolume:
    """A tomogram as the reference volume of an alignment."""
    shape = tomogram.shape
    if shape is None:
        raise ValueError(f"Tomogram {tomogram.tomo_type} holds no data.")
    return CopickReferenceVolume(
        size=tuple(int(n) for n in reversed(shape)),
        voxel_size=tomogram.voxel_spacing.voxel_size,
    )


def rebase_sections(
    file: CopickAlignmentFile,
    reference: CopickReferenceVolume,
    reference_offset: Optional[Sequence[float]] = None,
) -> List[CopickSectionAlignment]:
    """The sections of an alignment with another reference volume.

    Positions ``p`` of the new reference relate to those of the old one as ``p_old = p + o``, so the shifts become
    ``t + (R @ o)[:2]``. Without ``reference_offset``, the two volumes share their centre in the alignment's native
    convention, as copick assumes for tomograms reconstructed with an alignment (see ``CopickAlignment.project``).

    Args:
        file: The alignment.
        reference: The new reference volume.
        reference_offset: ``o`` in Angstrom, from the new reference's CETS centre to the old one's.
    """
    old = file.reference_volume
    if old is None:
        raise ValueError(f"Alignment {file.name} has no reference volume.")
    if reference_offset is not None:
        offset = np.asarray(reference_offset, dtype=float)
    else:
        kind = file.native_frame.get("volume_center", "floor")
        offset = _volume_offset(old, kind, old.voxel_size) - _volume_offset(reference, kind, reference.voxel_size)
    sections = []
    for s in file.sections:
        shift = np.asarray([s.shift_x, s.shift_y]) + (s.matrix() @ offset)[:2]
        sections.append(s.model_copy(update={"shift_x": float(shift[0]), "shift_y": float(shift[1])}))
    return sections


@dataclass
class ExportedAlignment:
    """An alignment in a tool's frame and row order, as cryoet-alignment's canonical model."""

    hub: Any
    row_of_section: Dict[int, int]
    section_of_row: Dict[int, int]
    n_rows: int
    pixel_size: float
    dark_angles: Dict[int, float]
    reference_volume: CopickReferenceVolume
    warnings: List[str]


def tool_row_order(metadata: CopickTiltSeriesMetadata, sort_by_angle: bool, n_sections: int) -> List[int]:
    """The sections in the tool's row order: ascending nominal tilt angle if ``sort_by_angle`` and known."""
    nominal = nominal_angles(metadata, n_sections)
    if sort_by_angle and nominal is not None:
        return sorted(range(n_sections), key=lambda s: (nominal[s], s))
    return list(range(n_sections))


def copick_to_native(
    file: CopickAlignmentFile,
    metadata: CopickTiltSeriesMetadata,
    source_format: str,
    n_sections: int,
    reference: Optional[CopickReferenceVolume] = None,
    reference_offset: Optional[Sequence[float]] = None,
    sort_by_angle: bool = True,
    drop_x_tilt: bool = False,
    assume_frame: Optional[CenterKind] = None,
) -> ExportedAlignment:
    """Convert a copick alignment to a tool's frame and row order.

    Args:
        file: The alignment.
        metadata: Metadata of its tilt series.
        source_format: The tool: ``ARETOMO3``, ``WARP``, ``RELION``, ``IMOD`` or ``PORTAL``.
        n_sections: Number of sections of the tilt series.
        reference: The volume the tool should reconstruct (default: the alignment's reference volume).
        reference_offset: Offset of ``reference`` from the alignment's reference volume (see ``rebase_sections``).
        sort_by_angle: Order the rows by ascending nominal tilt angle (else by section).
        drop_x_tilt: Set the tilt about x to zero, for tools that cannot represent it.
        assume_frame: Centre convention for IMOD with odd sizes.

    Raises:
        ValueError: If the alignment has no reference volume or its tilt series no images.
    """
    from cryoet_alignment.io.cryoet_data_portal.alignment import Alignment, PerSectionAlignmentParameters, ang2mat

    if file.reference_volume is None:
        raise ValueError(f"Alignment {file.name} has no reference volume; its shifts cannot be converted.")
    width, height, pixel_size = metadata.width, metadata.height, metadata.pixel_size
    warnings = []
    sections = file.sections
    if reference is not None:
        sections = rebase_sections(file, reference, reference_offset)
    reference = reference or file.reference_volume

    if drop_x_tilt and any(abs(s.x_tilt) > 0 for s in sections):
        worst = max(abs(s.x_tilt) for s in sections)
        warnings.append(f"The tilt about x (up to {worst:.4f} deg) was dropped.")
        sections = [s.model_copy(update={"x_tilt": 0.0}) for s in sections]

    native_volume = np.round(np.asarray(reference.extent) / pixel_size).astype(int).tolist()
    frame = frame_convention(source_format, (width, height), native_volume, assume_frame)
    d_img = image_delta(width, height, pixel_size, frame.image_center)
    d_vol = _volume_offset(reference, frame.volume_center, pixel_size)

    order = tool_row_order(metadata, sort_by_angle, n_sections)
    row_of_section = {s: row for row, s in enumerate(order)}
    params = []
    for s in sections:
        shift = cets_to_native_shift((s.shift_x, s.shift_y), s.matrix(), d_img, d_vol)
        params.append(
            PerSectionAlignmentParameters(
                z_index=row_of_section[s.section],
                tilt_angle=s.tilt_angle,
                volume_x_rotation=s.x_tilt,
                in_plane_rotation=ang2mat(s.in_plane_rotation).tolist(),
                x_offset=float(shift[0]) / pixel_size,
                y_offset=float(shift[1]) / pixel_size,
            ),
        )

    # Rows without parameters keep the nominal angle, with the sign the aligned rows have
    nominal = nominal_angles(metadata, n_sections)
    dark_angles = {}
    if nominal is not None:
        correlation = sum(s.tilt_angle * nominal[s.section] for s in sections)
        sign = -1.0 if correlation < 0 else 1.0
        aligned = {s.section for s in sections}
        dark_angles = {row_of_section[s]: sign * nominal[s] for s in range(n_sections) if s not in aligned}

    extent = reference.extent
    hub = Alignment(
        affine_transformation_matrix=np.eye(4).tolist(),
        alignment_type="GLOBAL",
        format=source_format,
        is_portal_standard=bool(file.is_portal_standard),
        tilt_offset=float(file.tilt_offset or 0.0),
        volume_offset=dict(zip("xyz", (float(v) for v in reference.offset), strict=True)),
        x_rotation_offset=float(file.x_rotation_offset or 0.0),
        per_section_alignment_parameters=sorted(params, key=lambda p: p.z_index),
        volume_dimension=dict(zip("xyz", (float(v) for v in extent), strict=True)),
    )
    if file.rigid_part_of_local or file.alignment_type == "LOCAL":
        warnings.append("Only the rigid part of this local alignment is exported.")
    return ExportedAlignment(
        hub=hub,
        row_of_section=row_of_section,
        section_of_row={row: s for s, row in row_of_section.items()},
        n_rows=n_sections,
        pixel_size=pixel_size,
        dark_angles=dark_angles,
        reference_volume=reference,
        warnings=warnings,
    )
