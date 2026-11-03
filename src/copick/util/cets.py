"""CETS-shaped metadata stored with copick entities.

copick stores the metadata of tilt series (and, later, alignments and tomogram links) in the shape of the CETS data
models (`TomoBabel/cets-data-models <https://github.com/TomoBabel/cets-data-models>`_), without depending on them.
Each stored block holds:

- ``schema``: the copick schema of the block, e.g. ``copick-tiltseries/1``;
- ``cets_target``: the CETS data-model version the CETS parts were written for;
- CETS objects, as their JSON dump (``TiltSeries``, ``AcquisitionSession``, ``Instrument``, ...);
- ``extensions``: copick data that CETS has no field for. CETS models forbid unknown fields, so these sit next to the
  CETS objects rather than inside them.

Identifiers are unique within a run; ``copick export cets`` prefixes them with the run name.
"""

from math import floor
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from copick.models import CopickTiltSeriesMetadata

#: The CETS data-model version the stored CETS objects are written for.
CETS_TARGET = {
    "repository": "TomoBabel/cets-data-models",
    "commit": "6784161",
    "base": "e8a6102",
}

#: Key of copick's block in the attributes of a Zarr group.
COPICK_ATTRS_KEY = "copick"
#: Schema of the block stored with a tilt series.
TILT_SERIES_SCHEMA = "copick-tiltseries/1"

#: Tolerance for comparing stored frame values, in pixels or Angstrom.
_FRAME_TOLERANCE = 1e-6


def tilt_image_id(ts_id: str, section: int) -> str:
    """CETS identifier of the image at ``section`` of tilt series ``ts_id``."""
    return f"{ts_id}_{section}"


def acquisition_session_id(ts_id: str) -> str:
    """CETS identifier of the acquisition session of tilt series ``ts_id``."""
    return f"{ts_id}_session"


def instrument_id(ts_id: str) -> str:
    """CETS identifier of the instrument of tilt series ``ts_id``."""
    return f"{ts_id}_instrument"


def _coordinate_system(name: str, axis_type: str, unit: str, axes: Tuple[str, ...]) -> Dict[str, Any]:
    return {"name": name, "axes": [{"name": a, "axis_type": axis_type, "axis_unit": unit} for a in axes]}


def image_frame(width: int, height: int, pixel_size: float) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """The CETS frame of a 2D image: its ``array`` and ``physical`` coordinate systems and the ``array_to_physical``
    transformation, centered at ``floor(N/2)`` on each axis.

    Args:
        width: Image width in pixels.
        height: Image height in pixels.
        pixel_size: Pixel size in Angstrom.

    Returns:
        The coordinate systems and the coordinate transformations.
    """
    systems = [
        _coordinate_system("array", "array", "pixel", ("x", "y")),
        _coordinate_system("physical", "space", "angstrom", ("x", "y")),
    ]
    transforms = [
        {
            "transformation_type": "sequence",
            "name": "array_to_physical",
            "input": "array",
            "output": "physical",
            "sequence": [
                {
                    "transformation_type": "translation",
                    "name": "center_array_origin",
                    "translation": [-float(floor(width / 2)), -float(floor(height / 2))],
                },
                {"transformation_type": "scale", "name": "scale_to_physical", "scale": [pixel_size, pixel_size]},
            ],
        },
    ]
    return systems, transforms


def _check_image_frame(image: Dict[str, Any], width: int, height: int, pixel_size: float) -> None:
    """Raise ``ValueError`` unless ``image`` has exactly the frame ``image_frame`` writes."""
    where = f"tilt image {image.get('id')!r}"
    frames = [t for t in image.get("coordinate_transformations") or [] if t.get("name") == "array_to_physical"]
    if len(frames) != 1:
        raise ValueError(f"{where}: expected one array_to_physical transformation, found {len(frames)}.")
    frame = frames[0]
    if frame.get("transformation_type") != "sequence" or (frame.get("input"), frame.get("output")) != (
        "array",
        "physical",
    ):
        raise ValueError(f"{where}: array_to_physical must be a sequence from 'array' to 'physical'.")
    steps = frame.get("sequence") or []
    kinds = [step.get("transformation_type") for step in steps]
    if kinds != ["translation", "scale"]:
        raise ValueError(f"{where}: array_to_physical must be [translation, scale], got {kinds}.")
    expected = [-floor(width / 2), -floor(height / 2)]
    translation = steps[0].get("translation") or []
    if len(translation) != 2 or any(abs(t - e) > _FRAME_TOLERANCE for t, e in zip(translation, expected, strict=True)):
        raise ValueError(f"{where}: translation {translation} does not center the image at {expected}.")
    scale = steps[1].get("scale") or []
    if len(scale) != 2 or any(abs(s - pixel_size) > 1e-3 for s in scale):
        raise ValueError(f"{where}: scale {scale} differs from the pixel size {pixel_size}.")


def _drop_none(values: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in values.items() if v is not None}


def tilt_series_to_attrs(ts_id: str, metadata: "CopickTiltSeriesMetadata") -> Dict[str, Any]:
    """The Zarr group attributes holding the metadata of a tilt series.

    Args:
        ts_id: CETS identifier of the tilt series.
        metadata: The metadata.

    Returns:
        ``{"copick": block}``, with the block as described in the module documentation.
    """
    md = metadata
    session_id = acquisition_session_id(ts_id)
    systems, transforms = image_frame(md.width, md.height, md.pixel_size)

    images = []
    image_extensions = []
    for image in md.images:
        block = _drop_none(
            {
                "id": tilt_image_id(ts_id, image.section),
                "section": image.section,
                "nominal_tilt_angle": image.nominal_tilt_angle,
                "acquisition_order": image.acquisition_order,
                "accumulated_dose": image.accumulated_dose,
                "exposure_time": image.exposure_time,
                "width": md.width,
                "height": md.height,
            },
        )
        if image.ctf is not None:
            block["ctf_metadata"] = {
                "defocus_u": image.ctf.defocus_u,
                "defocus_v": image.ctf.defocus_v,
                "defocus_angle": image.ctf.defocus_angle,
                "phase_shift": image.ctf.phase_shift,
            }
        block["coordinate_systems"] = systems
        block["coordinate_transformations"] = transforms
        images.append(block)

        extension = _drop_none(
            {
                "exposure_dose": image.exposure_dose,
                "frame_path": image.frame_path,
                "ctf_fit_resolution": image.ctf.fit_resolution if image.ctf is not None else None,
                "ctf_fit_score": image.ctf.fit_score if image.ctf is not None else None,
            },
        )
        if extension:
            image_extensions.append({"section": image.section, **extension})

    block = {
        "schema": TILT_SERIES_SCHEMA,
        "cets_target": dict(CETS_TARGET),
        "tilt_series": {
            "id": ts_id,
            "ctf_corrected": md.ctf_corrected,
            "acquisition_session_id": session_id,
            "images": images,
        },
        "acquisition_session": _drop_none(
            {
                "id": session_id,
                "instrument_id": instrument_id(ts_id),
                "amplitude_contrast": md.amplitude_contrast,
                "spherical_aberration": md.spherical_aberration,
                "tilt_axis_angle": md.tilt_axis_angle,
                "handedness": md.handedness,
            },
        ),
        "instrument": _drop_none(
            {
                "id": instrument_id(ts_id),
                "voltage": md.voltage,
                "microscope_model": md.microscope_model,
                "detector_model": md.detector_model,
            },
        ),
        "extensions": {
            "pixel_size": md.pixel_size,
            "width": md.width,
            "height": md.height,
            "is_aligned": md.is_aligned,
            "amplitude_contrast_source": md.amplitude_contrast_source,
            "ctf_status": md.ctf_status,
            "ctf_flags": md.ctf_flags,
            "images": image_extensions,
            "native": md.native,
            "provenance": md.provenance,
        },
    }
    return {COPICK_ATTRS_KEY: block}


def tilt_series_from_attrs(attrs: Dict[str, Any]) -> Optional["CopickTiltSeriesMetadata"]:
    """Read the metadata of a tilt series from its Zarr group attributes.

    Args:
        attrs: The group attributes.

    Returns:
        The metadata, or ``None`` if the attributes hold no copick block.

    Raises:
        ValueError: If the block has another schema or does not have the stored form, naming the offending element.
    """
    from copick.models import CopickCTF, CopickTiltImage, CopickTiltSeriesMetadata

    block = attrs.get(COPICK_ATTRS_KEY)
    if not block:
        return None
    if block.get("schema") != TILT_SERIES_SCHEMA:
        raise ValueError(f"Unsupported tilt series metadata schema {block.get('schema')!r}.")

    tilt_series = block.get("tilt_series") or {}
    session = block.get("acquisition_session") or {}
    instrument = block.get("instrument") or {}
    extensions = block.get("extensions") or {}
    pixel_size = extensions["pixel_size"]
    width = extensions["width"]
    height = extensions["height"]
    fit_by_section = {e["section"]: e for e in extensions.get("images") or []}

    images = []
    for image in tilt_series.get("images") or []:
        _check_image_frame(image, width, height, pixel_size)
        if (image.get("width"), image.get("height")) != (width, height):
            raise ValueError(f"tilt image {image.get('id')!r}: size differs from the tilt series' {width}x{height}.")
        extension = fit_by_section.get(image["section"], {})
        ctf = None
        if image.get("ctf_metadata"):
            ctf = CopickCTF(
                **image["ctf_metadata"],
                fit_resolution=extension.get("ctf_fit_resolution"),
                fit_score=extension.get("ctf_fit_score"),
            )
        images.append(
            CopickTiltImage(
                section=image["section"],
                nominal_tilt_angle=image.get("nominal_tilt_angle"),
                acquisition_order=image.get("acquisition_order"),
                accumulated_dose=image.get("accumulated_dose"),
                exposure_dose=extension.get("exposure_dose"),
                exposure_time=image.get("exposure_time"),
                frame_path=extension.get("frame_path"),
                ctf=ctf,
            ),
        )

    return CopickTiltSeriesMetadata(
        pixel_size=pixel_size,
        width=width,
        height=height,
        images=images,
        tilt_axis_angle=session.get("tilt_axis_angle"),
        voltage=instrument.get("voltage"),
        spherical_aberration=session.get("spherical_aberration"),
        amplitude_contrast=session.get("amplitude_contrast"),
        amplitude_contrast_source=extensions.get("amplitude_contrast_source"),
        handedness=session.get("handedness"),
        microscope_model=instrument.get("microscope_model"),
        detector_model=instrument.get("detector_model"),
        is_aligned=bool(extensions.get("is_aligned", False)),
        ctf_corrected=bool(tilt_series.get("ctf_corrected", False)),
        native=extensions.get("native") or {},
        provenance=extensions.get("provenance") or {},
    )


def minimal_tilt_series_metadata(shape: Tuple[int, int, int], pixel_size: float) -> "CopickTiltSeriesMetadata":
    """Metadata holding only the image geometry of a tilt series of ``shape`` ``(section, y, x)``."""
    from copick.models import CopickTiltSeriesMetadata

    return CopickTiltSeriesMetadata(pixel_size=pixel_size, width=int(shape[2]), height=int(shape[1]))
