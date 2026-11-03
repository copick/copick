"""Import and export of tilt series, alignments and CTF fits in the formats of tilt-series tools.

The formats and the mapping of their rows to tilt-series sections are described in
``copick.util.acquisition_formats``.
"""

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

import numpy as np

from copick.models import (
    CopickAlignment,
    CopickAlignmentFile,
    CopickRoot,
    CopickRun,
    CopickTiltImage,
    CopickTiltSeries,
    CopickTiltSeriesMetadata,
    CopickTomogram,
)
from copick.util.acquisition_formats import (
    DEFAULT_ANGLE_TOLERANCE,
    SOURCE_FORMATS,
    AcquisitionTable,
    CtfTable,
    SectionView,
    copick_to_native,
    ctfs_to_aretomo3,
    find_mdoc,
    map_rows,
    native_reference,
    native_to_copick,
    nominal_angles,
    open_stack,
    read_angles,
    read_ctf,
    read_mdoc,
    read_native_alignment,
    resolve_map,
    tomogram_reference,
    tool_row_order,
    warp_ctf_values,
)
from copick.util.log import get_logger
from copick.util.ome import TILT_SERIES_CHUNKS, TILT_SERIES_LEVELS

logger = get_logger(__name__)

PathLike = Union[str, Path]


def _created_by() -> str:
    from copick import __version__

    return f"copick {__version__}"


def ctf_format_from_path(path: PathLike) -> str:
    """The CTF format of a file, from its name."""
    name = Path(path).name.lower()
    if name.endswith("_ctf.txt"):
        return "aretomo3"
    if name.endswith(".xml"):
        return "warp"
    if name.endswith(".star"):
        return "relion"
    if name.endswith(".txt"):
        return "ctffind4"
    raise ValueError(f"Cannot tell the CTF format of {path}; pass it (aretomo3, ctffind4, warp or relion).")


def _images(metadata: CopickTiltSeriesMetadata, n_sections: int) -> List[CopickTiltImage]:
    if len(metadata.images) == n_sections:
        return list(metadata.images)
    return [CopickTiltImage(section=i) for i in range(n_sections)]


def _add_source(metadata: CopickTiltSeriesMetadata, source: str, path: PathLike) -> Dict[str, Any]:
    provenance = dict(metadata.provenance)
    provenance["source_files"] = list(provenance.get("source_files", [])) + [str(path)]
    sources = [s for s in str(provenance.get("source") or "").split("+") if s]
    if source not in sources:
        sources.append(source)
    provenance["source"] = "+".join(sources)
    return provenance


def apply_ctf(
    metadata: CopickTiltSeriesMetadata,
    n_sections: int,
    table: CtfTable,
    section_map: str = "auto",
    angle_tolerance: float = DEFAULT_ANGLE_TOLERANCE,
    path: Optional[PathLike] = None,
) -> CopickTiltSeriesMetadata:
    """Metadata with the CTF fits of a file set on the images they map to.

    Raises:
        ValueError: If the rows cannot be mapped to the sections.
    """
    what = f"CTF file {path}" if path else "CTF fits"
    nominal = nominal_angles(metadata, n_sections)
    mode = resolve_map(section_map, table.default_map, nominal is not None, what)
    sections = map_rows(
        n_sections,
        table.angles,
        mode,
        nominal=nominal,
        tolerance=angle_tolerance,
        what=what,
        n_rows=len(table.ctfs),
    )
    images = _images(metadata, n_sections)
    for row, section in enumerate(sections):
        images[section] = images[section].model_copy(update={"ctf": table.ctfs[row]})
    native = dict(metadata.native)
    if "df_hand" in table.native:
        hands = [None] * n_sections
        for row, section in enumerate(sections):
            hands[section] = table.native["df_hand"][row]
        native["aretomo3_df_hand"] = hands
    update = {"images": images, "native": native}
    if path is not None:
        update["provenance"] = _add_source(metadata, table.source, path)
    return metadata.model_copy(update=update)


def apply_acquisition(
    metadata: CopickTiltSeriesMetadata,
    n_sections: int,
    table: AcquisitionTable,
    section_map: str = "auto",
    angle_tolerance: float = DEFAULT_ANGLE_TOLERANCE,
    path: Optional[PathLike] = None,
    overwrite_angles: bool = False,
) -> CopickTiltSeriesMetadata:
    """Metadata with a file's per-image acquisition data (angles, order, dose, movies) set on the images.

    Args:
        metadata: The metadata.
        n_sections: Number of sections of the tilt series.
        table: The file's rows.
        section_map: How the rows map to sections.
        angle_tolerance: Largest difference in degrees between a row's angle and its section's nominal angle.
        path: The file, recorded in the provenance.
        overwrite_angles: Whether the rows' angles replace known nominal tilt angles.
    """
    what = f"{table.source} file {path}" if path else table.source
    nominal = nominal_angles(metadata, n_sections)
    mode = resolve_map(section_map, table.default_map, nominal is not None, what)
    sections = map_rows(
        n_sections,
        table.angles,
        mode,
        nominal=None if overwrite_angles else nominal,
        tolerance=angle_tolerance,
        keys=table.keys,
        what=what,
        refined=table.refined,
    )
    if len(sections) != n_sections:
        logger.warning(f"{what} lists {len(sections)} images for {n_sections} sections.")
    images = _images(metadata, n_sections)

    def value(values, row):
        return None if values is None else values[row]

    for row, section in enumerate(sections):
        image = images[section]
        update = {
            "acquisition_order": value(table.acquisition_order, row),
            "exposure_dose": value(table.exposure_dose, row),
            "accumulated_dose": value(table.accumulated_dose, row),
            "exposure_time": value(table.exposure_time, row),
            "frame_path": value(table.frame_paths, row),
        }
        update = {k: v for k, v in update.items() if v is not None}
        if overwrite_angles or image.nominal_tilt_angle is None:
            update["nominal_tilt_angle"] = table.angles[row]
        images[section] = image.model_copy(update=update)

    update = {"images": images}
    if path is not None:
        update["provenance"] = _add_source(metadata, table.source, path)
    for field, table_value in (("tilt_axis_angle", table.tilt_axis_angle), ("voltage", table.voltage)):
        if getattr(metadata, field) is None and table_value is not None:
            update[field] = table_value
    return metadata.model_copy(update=update)


def _uniform_dose(metadata: CopickTiltSeriesMetadata, dose_per_tilt: float) -> CopickTiltSeriesMetadata:
    images = []
    for image in metadata.images:
        update = {"exposure_dose": float(dose_per_tilt)}
        if image.acquisition_order is not None:
            update["accumulated_dose"] = image.acquisition_order * float(dose_per_tilt)
        images.append(image.model_copy(update=update))
    if images and any(i.acquisition_order is None for i in metadata.images):
        logger.warning("The acquisition order is unknown; the accumulated dose is left unset.")
    return metadata.model_copy(update={"images": images})


def _get_run(root: CopickRoot, run_name: str, create: bool = False) -> CopickRun:
    from copick.ops.add import get_or_create_run

    return get_or_create_run(root, run_name, create=create)


def _get_tilt_series(run: CopickRun, ts_type: str) -> CopickTiltSeries:
    found = run.get_tilt_series_list(ts_type)
    if not found:
        raise ValueError(f"Run {run.name} has no tilt series {ts_type}.")
    return found[0]


def add_tilt_series_from_file(
    root: CopickRoot,
    run_name: str,
    ts_type: str,
    path: PathLike,
    file_type: Optional[str] = None,
    pixel_size: Optional[float] = None,
    angles: Optional[PathLike] = None,
    angles_format: Optional[str] = None,
    mdoc: Union[PathLike, str, None] = "auto",
    ctf: Optional[PathLike] = None,
    ctf_format: Optional[str] = None,
    dose_per_tilt: Optional[float] = None,
    voltage: Optional[float] = None,
    spherical_aberration: Optional[float] = None,
    amplitude_contrast: Optional[float] = None,
    tilt_axis_angle: Optional[float] = None,
    handedness: Optional[str] = None,
    section_map: str = "auto",
    angle_tolerance: float = DEFAULT_ANGLE_TOLERANCE,
    sort_by_angle: bool = False,
    is_aligned: bool = False,
    levels: int = TILT_SERIES_LEVELS,
    chunks: Tuple[int, int, int] = TILT_SERIES_CHUNKS,
    dtype: Optional[str] = "float32",
    create: bool = True,
    overwrite: bool = False,
) -> CopickTiltSeries:
    """Add a tilt series from a stack file and its acquisition metadata.

    Args:
        root: The copick project.
        run_name: The run.
        ts_type: Type of the tilt series (e.g. ``raw``).
        path: The stack (MRC ``.mrc``/``.st``/``.mrcs``/``.ali``, TIFF, or Zarr).
        file_type: Format of the stack (``mrc``, ``tiff``, ``zarr``). Default: from the extension.
        pixel_size: Pixel size in Angstrom. Default: from the stack's header or the mdoc.
        angles: Tilt-angle file in stack order (``.rawtlt``, ``.tlt``, AreTomo3 ``_TLT.txt``).
        angles_format: Its format. Default: from its name.
        mdoc: SerialEM mdoc; ``"auto"`` uses one next to the stack, ``None`` none.
        ctf: CTF fits (AreTomo3 ``_CTF.txt``, CTFFIND4, Warp XML, RELION ``tomograms.star``).
        ctf_format: Their format. Default: from the file name.
        dose_per_tilt: Dose of every image in e/Å², overriding the files.
        voltage: Acceleration voltage in kV.
        spherical_aberration: Spherical aberration in mm.
        amplitude_contrast: Amplitude contrast.
        tilt_axis_angle: Tilt-axis angle in degrees, overriding the mdoc.
        handedness: ``right_handed`` or ``left_handed``, if known.
        section_map: How the mdoc's and CTF file's rows map to sections (see ``copick.util.acquisition_formats``).
        angle_tolerance: Largest difference in degrees between a row's angle and its section's nominal angle.
        sort_by_angle: Store the sections in ascending nominal tilt angle.
        is_aligned: Whether the images are already aligned.
        levels: Number of pyramid levels.
        chunks: Chunk shape.
        dtype: Data type of the stored images (``None``: that of the stack).
        create: Create the run if it does not exist.
        overwrite: Replace the images of an existing tilt series.

    Returns:
        CopickTiltSeries: The tilt series.
    """
    run = _get_run(root, run_name, create=create)
    existing = run.get_tilt_series(ts_type)
    if existing is not None and existing.shape is not None and not overwrite:
        raise ValueError(f"Tilt series {ts_type} of run {run.name} exists; pass overwrite to replace it.")

    with open_stack(str(path), file_type) as stack:
        n_sections, height, width = stack.shape
        mdoc_path = find_mdoc(str(path)) if mdoc == "auto" else mdoc
        mdoc_table = read_mdoc(str(mdoc_path), dose_per_tilt) if mdoc_path else None
        pixel_size = pixel_size or stack.pixel_size or (mdoc_table.pixel_size if mdoc_table else None)
        if pixel_size is None:
            raise ValueError(f"The pixel size of {path} is unknown; pass pixel_size (--pixel-size).")

        metadata = CopickTiltSeriesMetadata(
            pixel_size=pixel_size,
            width=width,
            height=height,
            images=[CopickTiltImage(section=i) for i in range(n_sections)],
            provenance={"source": "", "source_files": [str(path)], "created_by": _created_by()},
        )
        if angles is not None:
            table = read_angles(str(angles), angles_format)
            if len(table) != n_sections:
                raise ValueError(f"{angles} lists {len(table)} angles for {n_sections} sections of {path}.")
            metadata = apply_acquisition(metadata, n_sections, table, "index", angle_tolerance, angles)
        if mdoc_table is not None:
            nominal_known = nominal_angles(metadata, n_sections) is not None
            mode = section_map if section_map != "auto" else ("angle" if nominal_known else "index")
            metadata = apply_acquisition(metadata, n_sections, mdoc_table, mode, angle_tolerance, mdoc_path)
        if dose_per_tilt is not None and mdoc_table is None:
            metadata = _uniform_dose(metadata, dose_per_tilt)
        if ctf is not None:
            table = read_ctf(str(ctf), ctf_format or ctf_format_from_path(ctf), pixel_size=pixel_size)
            metadata = apply_ctf(metadata, n_sections, table, section_map, angle_tolerance, ctf)

        update = {
            "voltage": voltage if voltage is not None else metadata.voltage,
            "spherical_aberration": spherical_aberration,
            "amplitude_contrast": amplitude_contrast,
            "amplitude_contrast_source": None if amplitude_contrast is None else "user",
            "tilt_axis_angle": tilt_axis_angle if tilt_axis_angle is not None else metadata.tilt_axis_angle,
            "handedness": handedness,
            "is_aligned": is_aligned,
        }
        if not any(
            any(v is not None for k, v in image.model_dump().items() if k != "section") for image in metadata.images
        ):
            update["images"] = []
        metadata = metadata.model_copy(update=update)

        data = stack.data
        if sort_by_angle:
            nominal = nominal_angles(metadata, n_sections)
            if nominal is None:
                raise ValueError("Sorting by angle needs the nominal tilt angle of every section.")
            order = sorted(range(n_sections), key=lambda s: (nominal[s], s))
            data = SectionView(data, order)
            images = [metadata.images[old].model_copy(update={"section": new}) for new, old in enumerate(order)]
            metadata = metadata.model_copy(update={"images": images})
        metadata = CopickTiltSeriesMetadata.model_validate(metadata.model_dump())

        tilt_series = existing if existing is not None else run.new_tilt_series(ts_type)
        tilt_series.from_numpy(
            data,
            metadata=metadata,
            levels=levels,
            dtype=None if dtype is None else np.dtype(dtype),
            chunks=chunks,
        )
    logger.info(f"Added tilt series {ts_type} ({n_sections} sections) to run {run.name}.")
    return tilt_series


def add_ctf_from_file(
    root: CopickRoot,
    run_name: str,
    ts_type: str,
    path: PathLike,
    ctf_format: Optional[str] = None,
    section_map: str = "auto",
    angle_tolerance: float = DEFAULT_ANGLE_TOLERANCE,
    tomo_name: Optional[str] = None,
) -> CopickTiltSeries:
    """Set the CTF fits of a tilt series from a file.

    Raises:
        PermissionError: If the tilt series is read-only (changing static metadata is not supported yet).
    """
    tilt_series = _get_tilt_series(_get_run(root, run_name), ts_type)
    metadata = tilt_series.metadata
    if metadata is None:
        raise ValueError(f"Tilt series {ts_type} of run {run_name} holds no images.")
    table = read_ctf(
        str(path),
        ctf_format or ctf_format_from_path(path),
        pixel_size=metadata.pixel_size,
        tomo_name=tomo_name or run_name,
    )
    tilt_series.store_metadata(
        apply_ctf(metadata, tilt_series.n_sections, table, section_map, angle_tolerance, path),
    )
    return tilt_series


def _resolve_tomograms(root: CopickRoot, run_name: str, uris: Iterable[str]) -> List[CopickTomogram]:
    from copick.util.uri import resolve_copick_objects

    tomograms = []
    for uri in uris:
        found = resolve_copick_objects(uri, root, "tomogram", run_name)
        if not found:
            raise ValueError(f"Run {run_name} has no tomogram {uri}.")
        tomograms.extend(found)
    return tomograms


def add_alignment_from_file(
    root: CopickRoot,
    run_name: str,
    path: PathLike,
    fmt: str,
    ts_type: str,
    name: Optional[str] = None,
    tomo_name: Optional[str] = None,
    native_pixel_size: Optional[float] = None,
    volume_size: Optional[Sequence[int]] = None,
    thickness: Optional[int] = None,
    reference_tomogram: Optional[str] = None,
    link_tomograms: Sequence[str] = (),
    preferred: bool = False,
    ctf: Optional[PathLike] = None,
    ctf_format: Optional[str] = None,
    tlt: Optional[PathLike] = None,
    update_tilt_series: bool = True,
    section_map: str = "auto",
    angle_tolerance: float = DEFAULT_ANGLE_TOLERANCE,
    assume_frame: Optional[str] = None,
    rigid_only: bool = False,
    allow_varying_grids: bool = False,
    overwrite: bool = False,
) -> CopickAlignment:
    """Add an alignment of a tilt series from a tool's files.

    Args:
        root: The copick project.
        run_name: The run.
        path: The alignment: AreTomo3 ``.aln``, Warp tilt-series XML, RELION ``tomograms.star`` or IMOD basename.
        fmt: ``aretomo3``, ``warp``, ``relion`` or ``imod``.
        ts_type: The tilt series it aligns.
        name: Name of the alignment. Default: the format.
        tomo_name: The tomogram of a RELION file listing several. Default: the run name, if the file lists several.
        native_pixel_size: Pixel size of the stack the tool aligned, if not that of the tilt series.
        volume_size: Size ``(x, y, z)`` of the tool's reconstruction in pixels, overriding the files.
        thickness: Thickness of the tool's reconstruction in pixels, overriding the files.
        reference_tomogram: URI (``tomo_type@voxel_size``) of the tomogram the tool reconstructed with this alignment;
            it becomes the reference volume and is linked.
        link_tomograms: URIs of further tomograms reconstructed with this alignment.
        preferred: Prefer this alignment over the tilt series' others.
        ctf: CTF fits to store on the tilt series (AreTomo3 ``_CTF.txt``, ...).
        ctf_format: Their format. Default: from the file name.
        tlt: AreTomo3 ``_TLT.txt`` whose acquisition order and dose to store on the tilt series.
        update_tilt_series: Whether ``ctf`` and ``tlt`` are stored on the tilt series.
        section_map: How the tool's rows map to sections.
        angle_tolerance: Largest difference in degrees between a row's angle and its section's nominal angle.
        assume_frame: Centre convention (``half`` or ``floor``) of an IMOD alignment of odd-sized images.
        rigid_only: Import the rigid part of a local AreTomo3 alignment.
        allow_varying_grids: Drop the spatially varying deformation of a Warp alignment.
        overwrite: Replace an existing alignment of this name (its tomogram links are kept).

    Returns:
        CopickAlignment: The alignment.
    """
    run = _get_run(root, run_name)
    tilt_series = _get_tilt_series(run, ts_type)
    metadata = tilt_series.metadata
    n_sections = tilt_series.n_sections
    if metadata is None or not n_sections:
        raise ValueError(f"Tilt series {ts_type} of run {run_name} holds no images.")

    name = name or fmt
    existing = run.get_alignment(name)
    if existing is not None and not overwrite:
        raise ValueError(f"Alignment {name} exists in run {run_name}; pass overwrite to replace it.")

    if (ctf is not None or tlt is not None) and update_tilt_series:
        if tlt is not None:
            table = read_angles(str(tlt), "aretomo3-tlt")
            metadata = apply_acquisition(metadata, n_sections, table, section_map, angle_tolerance, tlt)
        if ctf is not None:
            table = read_ctf(str(ctf), ctf_format or ctf_format_from_path(ctf), metadata.pixel_size, tomo_name)
            metadata = apply_ctf(metadata, n_sections, table, section_map, angle_tolerance, ctf)
        tilt_series.store_metadata(metadata)
    elif ctf is not None or tlt is not None:
        logger.warning("The CTF and _TLT.txt files are not stored: update_tilt_series is off.")

    if fmt == "relion" and tomo_name is None:
        from cryoet_alignment.io.relion import RelionAlignment

        try:
            RelionAlignment.from_file(str(path), image_size_px=(metadata.width, metadata.height))
        except ValueError as e:
            if "pass tomo_name" not in str(e):
                raise
            tomo_name = run_name
    native = read_native_alignment(
        str(path),
        fmt,
        pixel_size=native_pixel_size,
        tomo_name=tomo_name,
        image_size=(metadata.width, metadata.height),
        rigid_only=rigid_only,
        allow_varying_grids=allow_varying_grids,
    )

    links = _resolve_tomograms(root, run_name, link_tomograms)
    shift_pixel_size = native.shift_pixel_size or native_pixel_size or metadata.pixel_size
    if reference_tomogram is not None:
        tomogram = _resolve_tomograms(root, run_name, [reference_tomogram])[0]
        reference = tomogram_reference(tomogram)
        links.insert(0, tomogram)
    else:
        reference = native_reference(
            native,
            shift_pixel_size,
            volume_size=volume_size,
            thickness=thickness,
            image_size=(metadata.width, metadata.height),
        )
    imported = native_to_copick(
        native,
        metadata,
        reference,
        section_map=section_map,
        tolerance=angle_tolerance,
        assume_frame=assume_frame,
        n_sections=n_sections,
    )
    for warning in imported.warnings:
        logger.warning(f"Alignment {name} of run {run_name}: {warning}")

    fields = dict(
        excluded_sections=imported.excluded_sections,
        alignment_type=native.alignment_type,
        source_format=native.source_format,
        native_frame=imported.native_frame,
        status="author",
        preferred=preferred,
        rigid_part_of_local=native.alignment_type == "LOCAL",
        tilt_offset=float(native.hub.tilt_offset or 0.0),
        x_rotation_offset=float(native.hub.x_rotation_offset or 0.0),
        warnings=imported.warnings,
        provenance={
            "source": fmt,
            "source_files": [str(path)] + [str(p) for p in (ctf, tlt) if p is not None],
            "native": native.native,
            "created_by": _created_by(),
        },
    )
    if existing is not None:
        file = existing.file
        existing.meta = CopickAlignmentFile(
            name=file.name,
            run_name=run.name,
            tilt_series=tilt_series.ts_type,
            tilt_series_portal_id=file.tilt_series_portal_id,
            linked_tomograms=file.linked_tomograms,
            sections=imported.sections,
            reference_volume=imported.reference_volume,
            **fields,
        )
        existing.store()
        alignment = existing
    else:
        alignment = run.new_alignment(
            name,
            tilt_series,
            sections=imported.sections,
            reference_volume=imported.reference_volume,
            **fields,
        )
    for tomogram in links:
        tomogram.set_alignment(alignment)
    logger.info(f"Added alignment {alignment.name} ({len(imported.sections)} sections) to run {run_name}.")
    return alignment


# ---------------------------------------------------------------------------------------------------------------------
# Export


def _level(tilt_series: CopickTiltSeries, level: int) -> Tuple[Any, float]:
    import zarr

    from copick.util.ome import get_pixel_size_from_zarr

    group = zarr.open(tilt_series.zarr(), mode="r")
    path = group.attrs["multiscales"][0]["datasets"][level]["path"]
    return group[path], get_pixel_size_from_zarr(group, level)


def _mrc_mode(dtype: np.dtype) -> Tuple[int, np.dtype]:
    """The MRC mode for images of ``dtype``, and the type to write them as (``float32`` if MRC has no mode for it)."""
    import mrcfile.utils

    try:
        return int(mrcfile.utils.mode_from_dtype(np.dtype(dtype))), np.dtype(dtype)
    except ValueError:
        return 2, np.dtype(np.float32)


def write_angle_file(
    metadata: CopickTiltSeriesMetadata,
    n_sections: int,
    path: PathLike,
    fmt: str = "rawtlt",
) -> Path:
    """Write the nominal tilt angles in stack order: IMOD ``.rawtlt``/``.tlt`` or AreTomo3 ``_TLT.txt``.

    An AreTomo3 ``_TLT.txt`` also holds the acquisition order and the dose of each image, when known.
    """
    nominal = nominal_angles(metadata, n_sections)
    if nominal is None:
        raise ValueError("The nominal tilt angles of the tilt series are unknown.")
    path = Path(path)
    if fmt == "aretomo3-tlt":
        from cryoet_alignment.io.aretomo3 import AreTomo3TLT, TltInfo

        images = metadata.images
        order = [i.acquisition_order for i in images]
        dose = [i.exposure_dose for i in images]
        has_order = all(o is not None for o in order)
        has_dose = has_order and all(d is not None for d in dose)
        rows = [
            TltInfo(
                tilt=nominal[s],
                acq_index=order[s] + 1 if has_order else None,
                dose=dose[s] if has_dose else None,
            )
            for s in range(n_sections)
        ]
        path.write_text(str(AreTomo3TLT(rows=rows)))
    elif fmt in ("rawtlt", "tlt"):
        path.write_text("".join(f"{a:.2f}\n" for a in nominal))
    else:
        raise ValueError(f"Unknown angle format {fmt!r}.")
    return path


def _section_ctfs(metadata: CopickTiltSeriesMetadata, n_sections: int, sections: Sequence[int]) -> List[Any]:
    images = metadata.images if len(metadata.images) == n_sections else []
    if not images:
        raise ValueError("The tilt series has no CTF fits.")
    ctfs = [images[s].ctf for s in sections]
    missing = [s for s, ctf in zip(sections, ctfs, strict=True) if ctf is None]
    if missing:
        raise ValueError(f"Sections {missing} have no CTF fit; partial CTF fits are not exported.")
    return ctfs


def write_ctf_file(
    metadata: CopickTiltSeriesMetadata,
    n_sections: int,
    path: PathLike,
    fmt: str = "aretomo3",
) -> Path:
    """Write the CTF fits as an AreTomo3 ``_CTF.txt`` (ascending tilt angle) or a CTFFIND4 file (stack order)."""
    if fmt not in ("aretomo3", "ctffind4"):
        raise ValueError(f"CTF fits can be written as aretomo3 or ctffind4, not {fmt!r}.")
    order = tool_row_order(metadata, fmt == "aretomo3", n_sections)
    hands = metadata.native.get("aretomo3_df_hand")
    df_hand = [hands[s] for s in order] if hands and all(hands[s] is not None for s in order) else None
    path = Path(path)
    path.write_text(str(ctfs_to_aretomo3(_section_ctfs(metadata, n_sections, order), df_hand)))
    return path


def export_tilt_series(
    tilt_series: CopickTiltSeries,
    output_dir: PathLike,
    output_format: str = "mrc",
    level: int = 0,
    angles: Optional[str] = "rawtlt",
    ctf_format: Optional[str] = None,
    basename: Optional[str] = None,
) -> List[Path]:
    """Export a tilt series as a stack, with its tilt angles and CTF fits.

    Args:
        tilt_series: The tilt series.
        output_dir: Directory to write to.
        output_format: ``mrc``, ``tiff`` or ``zarr``.
        level: Pyramid level of the stack (``mrc``, ``tiff``).
        angles: Angle file to write: ``rawtlt``, ``tlt``, ``aretomo3-tlt`` or ``None``.
        ctf_format: CTF file to write: ``aretomo3``, ``ctffind4`` or ``None``.
        basename: Base name of the files. Default: the run name.

    Returns:
        The written paths.
    """
    from copick.util.cets import tilt_series_to_attrs

    metadata = tilt_series.metadata
    if metadata is None:
        raise ValueError(f"Tilt series {tilt_series.ts_type} of run {tilt_series.run.name} holds no images.")
    n_sections = tilt_series.n_sections
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    base = basename or tilt_series.run.name
    written = []

    if output_format == "zarr":
        import zarr

        from copick.util.ome import write_ome_zarr_tilt_series

        group = zarr.open(tilt_series.zarr(), mode="r")
        datasets = group.attrs["multiscales"][0]["datasets"]
        target = output_dir / f"{base}.zarr"
        source = group[datasets[0]["path"]]
        write_ome_zarr_tilt_series(
            zarr.DirectoryStore(str(target)),
            source,
            metadata.pixel_size,
            levels=len(datasets),
            chunks=tuple(source.chunks),
            dtype=None,
            attrs=tilt_series_to_attrs(tilt_series.cets_id, metadata),
        )
        written.append(target)
    else:
        array, pixel_size = _level(tilt_series, level)
        if output_format == "mrc":
            import mrcfile

            target = output_dir / f"{base}.mrc"
            mode, dtype = _mrc_mode(array.dtype)
            with mrcfile.new_mmap(str(target), shape=tuple(array.shape), mrc_mode=mode, overwrite=True) as m:
                for i in range(array.shape[0]):
                    m.data[i] = np.asarray(array[i]).astype(dtype)
                m.voxel_size = pixel_size
        elif output_format == "tiff":
            import tifffile

            target = output_dir / f"{base}.tif"
            with tifffile.TiffWriter(str(target), bigtiff=True) as writer:
                for i in range(array.shape[0]):
                    writer.write(np.asarray(array[i]), contiguous=True)
        else:
            raise ValueError(f"Unknown stack format {output_format!r}; use mrc, tiff or zarr.")
        written.append(target)

    if angles:
        suffix = {"rawtlt": ".rawtlt", "tlt": ".tlt", "aretomo3-tlt": "_TLT.txt"}[angles]
        written.append(write_angle_file(metadata, n_sections, output_dir / f"{base}{suffix}", angles))
    if ctf_format:
        suffix = "_CTF.txt" if ctf_format == "aretomo3" else "_ctffind4.txt"
        written.append(write_ctf_file(metadata, n_sections, output_dir / f"{base}{suffix}", ctf_format))
    return written


def _reference_for_export(
    alignment: CopickAlignment,
    reference_tomogram: Optional[CopickTomogram],
) -> Tuple[Optional[Any], Optional[Sequence[float]]]:
    if reference_tomogram is None:
        return None, None
    link = reference_tomogram.alignment_link
    offset = None
    if link is not None and link.alignment == alignment.name and link.reference_offset is not None:
        offset = link.reference_offset
    return tomogram_reference(reference_tomogram), offset


def export_alignment(
    alignment: CopickAlignment,
    output_dir: PathLike,
    output_format: str,
    reference_tomogram: Optional[CopickTomogram] = None,
    include_ctf: bool = False,
    drop_x_tilt: bool = False,
    hand: float = -1.0,
    relion_tomo_name: Optional[str] = None,
    assume_frame: Optional[str] = None,
    basename: Optional[str] = None,
    amplitude_contrast: Optional[float] = None,
) -> Union[List[Path], Any]:
    """Export an alignment in a tool's format.

    Args:
        alignment: The alignment.
        output_dir: Directory to write to.
        output_format: ``aretomo3`` (``.aln`` + ``_TLT.txt``), ``warp`` (tilt-series XML), ``relion``, ``imod``
            (``.xf``, ``.tlt``, ``.xtilt``, ``tilt.com``, ``newst.com`` in ``<output_dir>/<basename>/``) or ``cdp``
            (CryoET Data Portal alignment JSON).
        reference_tomogram: Tomogram the tool should reconstruct; default: the alignment's reference volume.
        include_ctf: Also write the CTF fits (AreTomo3 ``_CTF.txt``, Warp grids, RELION columns).
        drop_x_tilt: Drop the tilt about x, which AreTomo3 cannot represent.
        hand: RELION ``rlnTomoHand``.
        relion_tomo_name: RELION ``rlnTomoName``. Default: the run name.
        assume_frame: Centre convention for IMOD with odd sizes.
        basename: Base name of the files. Default: the run name.
        amplitude_contrast: RELION amplitude contrast if the tilt series has none (default 0.07).

    Returns:
        The written paths, or for ``relion`` the ``RelionAlignment`` to write (see ``write_relion_alignments``).
    """
    file = alignment.file
    tilt_series = alignment.tilt_series
    if tilt_series is None:
        raise ValueError(f"Alignment {alignment.name} aligns no tilt series of run {alignment.run.name}.")
    metadata = tilt_series.metadata
    n_sections = tilt_series.n_sections
    if output_format == "aretomo3" and not drop_x_tilt and any(abs(s.x_tilt) > 0 for s in file.sections):
        worst = max(abs(s.x_tilt) for s in file.sections)
        raise ValueError(
            f"AreTomo3 cannot represent the tilt about x (up to {worst:.4f} deg) of alignment {alignment.name}; pass "
            "drop_x_tilt (--drop-x-tilt) to drop it.",
        )
    reference, offset = _reference_for_export(alignment, reference_tomogram)
    exported = copick_to_native(
        file,
        metadata,
        SOURCE_FORMATS[output_format],
        n_sections=n_sections,
        reference=reference,
        reference_offset=offset,
        sort_by_angle=output_format in ("aretomo3", "warp", "relion"),
        drop_x_tilt=drop_x_tilt,
        assume_frame=assume_frame,
    )
    for warning in exported.warnings:
        logger.warning(f"Alignment {alignment.name} of run {alignment.run.name}: {warning}")
    hub = exported.hub
    images = metadata.images if len(metadata.images) == n_sections else [None] * n_sections
    pixel_size = metadata.pixel_size
    width, height = metadata.width, metadata.height
    extent = exported.reference_volume.extent
    base = basename or alignment.run.name
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [exported.section_of_row[r] for r in range(exported.n_rows)]

    if output_format == "aretomo3":
        aln = hub.to_aretomo(
            ts_size=(width, height, n_sections),
            dark_angles=exported.dark_angles,
            thickness_px=int(round(extent[2] / pixel_size)),
        )
        written = [output_dir / f"{base}.aln"]
        written[0].write_text(str(aln))
        if nominal_angles(metadata, n_sections) is not None:
            # AreTomo3 reads the _TLT.txt in the order of its input stack and sorts both by angle
            written.append(write_angle_file(metadata, n_sections, output_dir / f"{base}_TLT.txt", "aretomo3-tlt"))
        if include_ctf:
            written.append(write_ctf_file(metadata, n_sections, output_dir / f"{base}_CTF.txt", "aretomo3"))
        return written

    if output_format == "warp":
        warp = hub.to_warp(
            pixel_size_a=pixel_size,
            image_size_px=(width, height),
            n_rows=exported.n_rows,
            dark_angles=exported.dark_angles,
            doses={r: images[s].accumulated_dose or 0.0 for r, s in enumerate(rows) if images[s] is not None},
            movie_paths={r: images[s].frame_path or "" for r, s in enumerate(rows) if images[s] is not None},
        )
        params = dict(warp.ctf_params)
        for key, value in (
            ("Voltage", metadata.voltage),
            ("Cs", metadata.spherical_aberration),
            ("Amplitude", metadata.amplitude_contrast),
        ):
            if value is not None:
                params[key] = f"{value:.9g}"
        update = {"ctf_params": params}
        if include_ctf:
            ctfs = _section_ctfs(metadata, n_sections, rows)
            update["entries"] = [
                e.model_copy(update=warp_ctf_values(ctf)) for e, ctf in zip(warp.entries, ctfs, strict=True)
            ]
        warp = warp.model_copy(update=update)
        target = output_dir / f"{base}.xml"
        target.write_text(str(warp))
        return [target]

    if output_format == "relion":
        missing = [n for n in ("voltage", "spherical_aberration") if getattr(metadata, n) is None]
        if missing:
            raise ValueError(
                f"RELION needs the {' and '.join(missing)} of tilt series {tilt_series.ts_type}; set them on its "
                "metadata.",
            )
        ac = metadata.amplitude_contrast if metadata.amplitude_contrast is not None else amplitude_contrast
        if ac is None:
            logger.warning(f"Tilt series {tilt_series.ts_type} records no amplitude contrast; 0.07 is written.")
            ac = 0.07
        params = sorted(hub.per_section_alignment_parameters, key=lambda p: p.z_index)
        sections = [exported.section_of_row[p.z_index] for p in params]
        pre = [0.0 if images[s] is None else images[s].accumulated_dose or 0.0 for s in sections]
        relion = hub.to_relion(
            tomo_name=relion_tomo_name or base,
            pixel_size_a=pixel_size,
            hand=hand,
            voltage=metadata.voltage,
            spherical_aberration=metadata.spherical_aberration,
            amplitude_contrast=ac,
            pre_exposures=pre,
        )
        ctfs = _section_ctfs(metadata, n_sections, sections) if include_ctf else [None] * len(sections)
        entries = []
        for entry, section, ctf in zip(relion.entries, sections, ctfs, strict=True):
            update = {}
            # RELION's nominal stage angle is the tilt series' nominal angle, not the refined one
            if images[section] is not None and images[section].nominal_tilt_angle is not None:
                update["nominal_stage_tilt_angle"] = images[section].nominal_tilt_angle
            if ctf is not None:
                update.update(
                    defocus_u=ctf.defocus_u,
                    defocus_v=ctf.defocus_v,
                    defocus_angle=ctf.defocus_angle,
                    phase_shift=ctf.phase_shift,
                    ctf_max_resolution=ctf.fit_resolution,
                    ctf_figure_of_merit=ctf.fit_score,
                )
            entries.append(entry.model_copy(update=update))
        if include_ctf:
            for field in ("ctf_max_resolution", "ctf_figure_of_merit"):
                if any(getattr(e, field) is None for e in entries):
                    entries = [e.model_copy(update={field: None}) for e in entries]
        return relion.model_copy(update={"entries": entries})

    if output_format == "imod":
        imod = hub.to_imod(ts_size=(width, height, n_sections), ts_spacing=pixel_size, basename=base)
        angles = list(imod.tlt.angles)
        for row, angle in exported.dark_angles.items():
            angles[row] = angle
        imod.tlt.angles = angles
        directory = output_dir / base
        directory.mkdir(parents=True, exist_ok=True)
        imod.write(base_name=str(directory / base))
        return sorted(directory.iterdir())

    if output_format == "cdp":
        target = output_dir / f"{base}_alignment.json"
        target.write_text(json.dumps(hub.model_dump(), indent=1) + "\n")
        return [target]

    raise ValueError(f"Unknown alignment format {output_format!r}.")


def write_relion_alignments(alignments: Sequence[Any], tomograms_star: PathLike) -> List[Path]:
    """Write RELION alignments of several tomograms as one ``tomograms.star`` and ``tilt_series/<name>.star`` each."""
    import pandas as pd
    import starfile
    from cryoet_alignment.io.relion.alignment import VERSION_COMMENT

    tomograms_star = Path(tomograms_star)
    names = [a.tomo_name for a in alignments]
    if len(set(names)) != len(names):
        raise ValueError(f"RELION tomogram names must be unique, got {names}.")
    rows = []
    written = []
    for relion in alignments:
        relion.to_file(tomograms_star)
        rows.append(starfile.read(tomograms_star, always_dict=True)["global"])
        written.append(tomograms_star.parent / "tilt_series" / f"{relion.tomo_name}.star")
    starfile.write({"global": pd.concat(rows, ignore_index=True)}, tomograms_star)
    tomograms_star.write_text(f"{VERSION_COMMENT}\n" + tomograms_star.read_text())
    return [tomograms_star] + written


def export_alignments(
    root: CopickRoot,
    alignment_uri: str,
    output_dir: PathLike,
    output_format: str,
    run_names: Optional[Sequence[str]] = None,
    reference_tomogram: Optional[str] = None,
    **kwargs,
) -> List[Path]:
    """Export the alignments a URI selects, from all or some runs.

    RELION alignments are written to one ``tomograms.star`` in ``output_dir``, each run's under its own name.

    Args:
        root: The copick project.
        alignment_uri: Alignments to export (e.g. ``aretomo3`` or ``*@raw?default=true``).
        output_dir: Directory to write to.
        output_format: ``aretomo3``, ``warp``, ``relion``, ``imod`` or ``cdp``.
        run_names: Runs to export. Default: all.
        reference_tomogram: URI of each run's tomogram the tool should reconstruct.
        **kwargs: Passed to ``export_alignment``.

    Returns:
        The written paths.
    """
    from copick.util.uri import resolve_copick_objects

    written: List[Path] = []
    relion = []
    runs = run_names if run_names is not None else [run.name for run in root.runs]
    for run_name in runs:
        alignments = resolve_copick_objects(alignment_uri, root, "alignment", run_name)
        if len(alignments) > 1 and "basename" not in kwargs:
            raise ValueError(
                f"{alignment_uri} selects {len(alignments)} alignments of run {run_name}; select one per run.",
            )
        tomogram = None
        if reference_tomogram is not None and alignments:
            tomogram = _resolve_tomograms(root, run_name, [reference_tomogram])[0]
        for alignment in alignments:
            result = export_alignment(alignment, output_dir, output_format, reference_tomogram=tomogram, **kwargs)
            if output_format == "relion":
                relion.append(result)
            else:
                written.extend(result)
    if relion:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        written.extend(write_relion_alignments(relion, Path(output_dir) / "tomograms.star"))
    return written


def export_ctf(
    tilt_series: CopickTiltSeries,
    output_dir: PathLike,
    fmt: str = "aretomo3",
    basename: Optional[str] = None,
) -> Path:
    """Export the CTF fits of a tilt series as an AreTomo3 ``_CTF.txt`` or a CTFFIND4 file."""
    metadata = tilt_series.metadata
    if metadata is None:
        raise ValueError(f"Tilt series {tilt_series.ts_type} of run {tilt_series.run.name} holds no images.")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    base = basename or tilt_series.run.name
    suffix = "_CTF.txt" if fmt == "aretomo3" else "_ctffind4.txt"
    return write_ctf_file(metadata, tilt_series.n_sections, output_dir / f"{base}{suffix}", fmt)
