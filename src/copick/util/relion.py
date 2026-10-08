from typing import TYPE_CHECKING, Dict, Optional, Sequence, Tuple, Union

import numpy as np
import zarr

from copick.util.ome import get_level_path

if TYPE_CHECKING:
    import pandas as pd

    from copick.models import CopickFilaments, CopickPicks


def normalize_transforms(picks: "CopickPicks", eps: float = 1e-8) -> np.ndarray:
    """
    Returns a normalized copy of transforms with bottom rows [0,0,0,1].
    Raises:
    - NotImplementedError if any bottom row has nonzero xyz (perspective terms)
    - ValueError if the homogeneous coordinate w is (approximately) 0
    """
    _, transforms = picks.numpy()
    if transforms.ndim != 3 or transforms.shape[-2:] != (4, 4):
        raise ValueError("Expected (N, 4, 4) array.")

    bottom = transforms[:, 3, :]
    xyz = bottom[:, :3]
    w = bottom[:, 3]

    perspective_mask = np.any(np.abs(xyz) > eps, axis=1)
    if np.any(perspective_mask):
        idx = np.where(perspective_mask)[0]
        raise NotImplementedError(f"Perspective terms present in bottom row for indices {idx.tolist()}.")

    w_bad_mask = np.abs(w) <= eps
    if np.any(w_bad_mask):
        idx = np.where(w_bad_mask)[0]
        raise ValueError(f"Invalid bottom row (w≈0) for indices {idx.tolist()}.")

    norm = transforms / w[:, None, None]
    return norm


def get_tomogram_spacing_and_dimensions(
    picks: "CopickPicks",
    only_voxel_size: bool = False,
) -> Tuple[float, Union[int, None], Union[int, None], Union[int, None]]:
    """
    Get tomogram voxel size and dimensions for the run these picks belong to.
    Returns a tuple of (voxel_size, tomogram_x, tomogram_y, tomogram_z).
    If only_voxel_size is True, only the voxel size will be returned (voxel_size, None, None, None).
    """
    from warnings import warn

    if only_voxel_size:
        if len(picks.run.voxel_spacings) == 0:
            raise ValueError("At least one voxel spacing must defined to import these particles from RELION.")
        elif len(picks.run.voxel_spacings) > 1:
            warn(
                "Multiple voxel spacings found, using the smallest one for converting the coordinates.",
                UserWarning,
                stacklevel=2,
            )
        return min(picks.run.voxel_spacings, key=lambda x: x.voxel_size).voxel_size, None, None, None

    vs_with_tomogram = [v for v in picks.run.voxel_spacings if v.tomograms]
    if len(vs_with_tomogram) == 0:
        raise ValueError(
            "At least one voxel spacing with a tomogram must be defined to import these particles from RELION.",
        )
    voxel_spacing = min(vs_with_tomogram, key=lambda x: x.voxel_size)
    if len(vs_with_tomogram) > 1:
        warn(
            f"Multiple voxel spacings with tomograms found, using the smallest ({voxel_spacing.voxel_size}) for converting the coordinates.",
            UserWarning,
            stacklevel=2,
        )
    tomogram = voxel_spacing.tomograms[0]
    if len(voxel_spacing.tomograms) > 1:
        warn(
            f"Multiple tomograms for voxel spacing {voxel_spacing.voxel_size} found, using ({tomogram.tomo_type}) for converting the coordinates.",
            UserWarning,
            stacklevel=2,
        )
    zarr_group = zarr.open(tomogram.zarr(), mode="r")
    tomogram_z, tomogram_y, tomogram_x = zarr_group[get_level_path(zarr_group, 0)].shape

    return voxel_spacing.voxel_size, tomogram_x, tomogram_y, tomogram_z


#: Rotation by +90 degrees about Y. RELION's filament poses are the filament frame times this
#: (tomography_python_programs/get_particle_poses/filaments.py).
RY90 = np.array([[0.0, 0.0, 1.0], [0.0, 1.0, 0.0], [-1.0, 0.0, 0.0]])


def filament_relion_angles(rotations: np.ndarray) -> Dict[str, np.ndarray]:
    """RELION's filament convention for object-to-tomogram rotations whose +Z axis is the filament axis.

    RELION (``get_particle_poses/filaments.py``, ``relion_tomo_import_coordinates``) stores a filament particle's frame
    in ``rlnTomoSubtomogram{Rot,Tilt,Psi}``, pre-rotated by Ry(90), and sets ``rlnAngle{Rot,Tilt,Psi}`` to (0, 90, 0)
    with priors ``rlnAngleTiltPrior`` = 90 and ``rlnAnglePsiPrior`` = 0, so that ``A_subtomogram @ A_particle`` is the
    frame and helical refinement searches around in-plane particles.

    Args:
        rotations: (N, 3, 3) object-to-tomogram rotations.

    Returns:
        Dict of RELION column name to (N,) array.
    """
    from copick.util.formats import _relion_eulers

    rotations = np.asarray(rotations, dtype=float).reshape(-1, 3, 3)
    n = rotations.shape[0]
    sub = _relion_eulers(rotations @ RY90)
    return {
        "rlnTomoSubtomogramRot": sub[:, 0],
        "rlnTomoSubtomogramTilt": sub[:, 1],
        "rlnTomoSubtomogramPsi": sub[:, 2],
        "rlnAngleRot": np.zeros(n),
        "rlnAngleTilt": np.full(n, 90.0),
        "rlnAnglePsi": np.zeros(n),
        "rlnAngleTiltPrior": np.full(n, 90.0),
        "rlnAnglePsiPrior": np.zeros(n),
    }


def filament_track_lengths(positions: np.ndarray, instance_ids: np.ndarray) -> np.ndarray:
    """Distance in Angstrom along each filament, in point order: 0 at each filament's first point.

    This is ``rlnHelicalTrackLengthAngst`` in Angstrom, as its name says. (RELION's own filament picker writes evenly
    spaced values in tilt-series pixels.)

    Args:
        positions: (N, 3) particle centres in Angstrom.
        instance_ids: (N,) filament IDs.
    """
    positions = np.asarray(positions, dtype=float).reshape(-1, 3)
    instance_ids = np.asarray(instance_ids)
    lengths = np.zeros(positions.shape[0])
    for filament_id in np.unique(instance_ids):
        index = np.flatnonzero(instance_ids == filament_id)
        steps = np.linalg.norm(np.diff(positions[index], axis=0), axis=1)
        lengths[index[1:]] = np.cumsum(steps)
    return lengths


def order_filament_rows(df: "pd.DataFrame") -> "pd.DataFrame":
    """Rows of a RELION particle table in filament order when it has filament columns.

    With ``rlnHelicalTubeID`` and ``rlnHelicalTrackLengthAngst``, rows are stably sorted by (rlnTomoName, tube, track
    length), so that each filament's points are contiguous and ordered along it; otherwise the table is unchanged.
    """
    keys = [key for key in ("rlnHelicalTubeID", "rlnHelicalTrackLengthAngst") if key in df.columns]
    if len(keys) < 2:
        return df
    if "rlnTomoName" in df.columns:
        keys = ["rlnTomoName", *keys]
    return df.sort_values(keys, kind="stable").reset_index(drop=True)


def relion_instance_ids(df: "pd.DataFrame") -> Optional[np.ndarray]:
    """Filament IDs (``rlnHelicalTubeID``) of a RELION particle table, or None if it has none."""
    if "rlnHelicalTubeID" not in df.columns:
        return None
    return df["rlnHelicalTubeID"].to_numpy().astype(np.int64)


def relion_rows_to_poses(df: "pd.DataFrame") -> Tuple[np.ndarray, np.ndarray]:
    """Rotations and shifts of RELION tomography particles, in copick's convention.

    RELION composes a particle's orientation as ``A = A_subtomogram @ A_particle`` from ``rlnTomoSubtomogram{Rot,Tilt,
    Psi}`` and ``rlnAngle{Rot,Tilt,Psi}``, and places it at its coordinate minus ``A_subtomogram @ rlnOrigin{X,Y,Z}Angst``
    (RELION's ``ParticleSet::getMatrix3x3`` and ``getPosition``). Each Euler triple is converted with
    ``Rotation.from_euler("ZYZ", angles).inv()``, which equals RELION's Euler-angle matrix. Missing columns count as
    zero angles and zero shifts.

    Args:
        df: RELION particle table.

    Returns:
        Tuple of (rotations, offsets): (N, 3, 3) object-to-tomogram rotations, and (N, 3) shifts in Angstrom in the
        tomogram frame, to be subtracted from the particle coordinates.
    """
    from scipy.spatial.transform import Rotation

    n = len(df)

    sub_orientations = np.tile(np.eye(3), (n, 1, 1))
    if {"rlnTomoSubtomogramRot", "rlnTomoSubtomogramTilt", "rlnTomoSubtomogramPsi"}.issubset(df.columns):
        angles = df[["rlnTomoSubtomogramRot", "rlnTomoSubtomogramTilt", "rlnTomoSubtomogramPsi"]].to_numpy(dtype=float)
        sub_orientations = Rotation.from_euler("ZYZ", angles, degrees=True).inv().as_matrix().reshape(n, 3, 3)

    particle_orientations = np.tile(np.eye(3), (n, 1, 1))
    if {"rlnAngleRot", "rlnAngleTilt", "rlnAnglePsi"}.issubset(df.columns):
        angles = df[["rlnAngleRot", "rlnAngleTilt", "rlnAnglePsi"]].to_numpy(dtype=float)
        particle_orientations = Rotation.from_euler("ZYZ", angles, degrees=True).inv().as_matrix().reshape(n, 3, 3)

    origins = np.zeros((n, 3), dtype=float)
    if {"rlnOriginXAngst", "rlnOriginYAngst", "rlnOriginZAngst"}.issubset(df.columns):
        origins = df[["rlnOriginXAngst", "rlnOriginYAngst", "rlnOriginZAngst"]].to_numpy(dtype=float)

    rotations = np.einsum("nij,njk->nik", sub_orientations, particle_orientations)
    offsets = np.einsum("nij,nj->ni", sub_orientations, origins)
    return rotations, offsets


def copick_tomogram_center(
    picks: "CopickPicks",
    voxel_spacing: Optional[float] = None,
) -> Optional[Tuple[float, float, float]]:
    """Centre in Angstrom of the tomogram of the run these picks belong to (tomogram shape / 2 * voxel size).

    Uses a tomogram at ``voxel_spacing`` if the run has one there, else the tomogram at the smallest voxel spacing
    with a tomogram (as earlier copick versions did). Returns None if the run has no tomogram.
    """
    from copick.util.formats import get_tomogram_centers_from_copick

    run = picks.run
    if voxel_spacing is not None:
        centers = get_tomogram_centers_from_copick(run.root, [run.name], voxel_spacing)
        if run.name in centers:
            return centers[run.name]
    try:
        voxel_size, tomogram_x, tomogram_y, tomogram_z = get_tomogram_spacing_and_dimensions(picks)
    except ValueError:
        return None
    return (tomogram_x / 2 * voxel_size, tomogram_y / 2 * voxel_size, tomogram_z / 2 * voxel_size)


def _smallest_voxel_spacing(picks: "CopickPicks") -> Optional[float]:
    """The run's smallest voxel spacing, or None if it has none."""
    if not picks.run.voxel_spacings:
        return None
    return get_tomogram_spacing_and_dimensions(picks, only_voxel_size=True)[0]


def picks_to_df_relion(
    picks: "CopickPicks",
    *,
    voxel_spacing: Optional[float] = None,
    tilt_series_pixel_size: Optional[float] = None,
    tomogram_center: Optional[Tuple[float, float, float]] = None,
    filament: Union[bool, str] = "auto",
    polarity_known: Union[bool, Sequence[bool], np.ndarray] = False,
) -> "pd.DataFrame":
    """Returns the points as a pandas DataFrame with RELION columns.

    Columns are rlnTomoName, rlnAngleRot/Tilt/Psi and, following ``copick.util.formats.build_relion_particles_df``,
    rlnCenteredCoordinateX/Y/ZAngst whenever the tomogram centre is known and rlnCoordinateX/Y/Z in tilt-series pixels
    whenever ``tilt_series_pixel_size`` is given. Positions include the transforms' translations.

    Args:
        picks: The picks to convert.
        voxel_spacing: Voxel spacing whose tomogram defines the centre (see ``copick_tomogram_center``).
        tilt_series_pixel_size: Tilt-series pixel size in Angstrom; enables rlnCoordinateX/Y/Z.
        tomogram_center: Tomogram centre in Angstrom; overrides the copick tomogram.
        filament: Write RELION's filament columns (see ``filament_relion_angles``): True, False, or "auto" for picks
            of an object declared a filament.
        polarity_known: For filament columns: whether the point order follows the filament's polarity, for all picks
            (a bool) or per pick (an (N,) array, e.g. from ``filament_polarity_known``). rlnAnglePsiFlipRatio is 0
            where it does and 0.5 elsewhere.
    """
    from copick.util.formats import build_relion_particles_df

    points, _ = picks.numpy()
    transforms = normalize_transforms(picks)
    if tomogram_center is None:
        tomogram_center = copick_tomogram_center(picks, voxel_spacing)
    legacy_voxel_spacing = None
    if tomogram_center is None and tilt_series_pixel_size is None:
        legacy_voxel_spacing = voxel_spacing if voxel_spacing is not None else _smallest_voxel_spacing(picks)

    return build_relion_particles_df(
        points,
        transforms,
        tomo_name=picks.run.name,
        tomogram_center=tomogram_center,
        tilt_series_pixel_size=tilt_series_pixel_size,
        legacy_voxel_spacing=legacy_voxel_spacing,
        instance_ids=picks.instance_ids(),
        filament=is_filament_export(picks, filament),
        polarity_known=polarity_known,
    )


def polarity_filaments(picks: "CopickPicks", filaments_uri: Optional[str] = None) -> Optional["CopickFilaments"]:
    """The Filaments that state the polarity of these picks' filaments, or None if there are none.

    Args:
        picks: Picks of a filament object; their instance IDs are filament IDs.
        filaments_uri: Filaments URI (``object:user/session``), resolved in the picks' run. Of several matches, those of
            the picks' object are used. Default: the Filaments under the picks' own URI (object, user and session),
            as a tool that writes both (e.g. copick-helix) leaves them.

    Raises:
        ValueError: If ``filaments_uri`` matches more than one Filaments of the picks' object in the run, since filament
            IDs are unique only within one Filaments file.
    """
    run = picks.run
    if filaments_uri is None:
        matches = run.get_filaments(
            object_name=picks.pickable_object_name,
            user_id=picks.user_id,
            session_id=picks.session_id,
        )
    else:
        from copick.util.uri import resolve_copick_objects

        matches = resolve_copick_objects(filaments_uri, run.root, "filaments", run.name)
        if len(matches) > 1:
            matches = [f for f in matches if f.pickable_object_name == picks.pickable_object_name]
    if len(matches) > 1:
        found = ", ".join(f"{f.pickable_object_name}:{f.user_id}/{f.session_id}" for f in matches)
        raise ValueError(
            f"{filaments_uri} matches several Filaments in {run.name} ({found}); filament IDs are unique only within "
            "one of them. Name one Filaments session.",
        )
    return matches[0] if matches else None


def _uri(entity) -> str:
    return f"{entity.pickable_object_name}:{entity.user_id}/{entity.session_id}"


def _polarity_lookup(
    picks: "CopickPicks",
    filaments_uri: Optional[str],
) -> Tuple[np.ndarray, Optional[str], Dict[int, bool]]:
    """The picks' filament IDs, the URI of the Filaments that state their polarity (None if there are none), and the
    polarity of each filament in those Filaments.

    Raises:
        ValueError: If ``filaments_uri`` matches no Filaments in the picks' run (or several), or a pick's filament is
            not in the Filaments.
    """
    instance_ids = np.asarray(picks.instance_ids(), dtype=np.int64)
    filaments = polarity_filaments(picks, filaments_uri)
    if filaments is None:
        if filaments_uri is not None and len(instance_ids):
            raise ValueError(
                f"No Filaments match {filaments_uri} in {picks.run.name}, so the polarity of {_uri(picks)} is "
                "unknown. Name the Filaments these picks were sampled from.",
            )
        return instance_ids, None, {}
    polarity = {f.instance_id: bool(f.polarity_known) for f in filaments.filaments}
    missing = sorted({int(i) for i in instance_ids} - set(polarity))
    if missing:
        raise ValueError(
            f"{len(missing)} filament IDs of {_uri(picks)} in {picks.run.name} have no filament in "
            f"{_uri(filaments)}: {missing[:20]}{' ...' if len(missing) > 20 else ''}. Each pick must come from a "
            "filament of the Filaments that state the polarity.",
        )
    return instance_ids, _uri(filaments), polarity


def filament_polarity_known(picks: "CopickPicks", filaments_uri: Optional[str] = None) -> np.ndarray:
    """Per pick, whether the point order of its filament follows the structure's polarity.

    Each pick is matched to the filament whose ``instance_id`` equals its own, in the Filaments chosen by
    ``polarity_filaments``, and takes that filament's ``polarity_known``. Every pick's filament must be in those
    Filaments. Without any (none under the picks' own URI, and no ``filaments_uri``), every pick counts as of unknown
    polarity.

    With ``polarity_known``, a filament's points run from the minus to the plus end (microtubules) or from the pointed to
    the barbed end (actin), so the +Z axis of a pick sampled in point order points toward the plus (barbed) end.

    Args:
        picks: Picks of a filament object.
        filaments_uri: Filaments URI; default: the picks' own URI (see ``polarity_filaments``).

    Returns:
        (N,) bool array.

    Raises:
        ValueError: If a pick's filament is not in the Filaments, or ``filaments_uri`` matches no Filaments in the
            picks' run, or several (see ``polarity_filaments``).
    """
    instance_ids, _, polarity = _polarity_lookup(picks, filaments_uri)
    return np.array([polarity.get(int(i), False) for i in instance_ids], dtype=bool)


def is_filament_export(picks: "CopickPicks", filament: Union[bool, str]) -> bool:
    """Whether to write filament columns for these picks: ``filament`` if it is a bool, else (``"auto"``) whether
    their object is declared a filament."""
    if isinstance(filament, bool):
        return filament
    if filament != "auto":
        raise ValueError(f"filament must be True, False or 'auto', not {filament!r}")
    obj = picks.run.root.get_object(picks.pickable_object_name)
    return bool(obj is not None and obj.is_filament)


def relion_df_to_picks(
    picks: "CopickPicks",
    df: "pd.DataFrame",
    *,
    optics: Optional["pd.DataFrame"] = None,
    tilt_series_pixel_size: Optional[float] = None,
    tomogram_center: Optional[Tuple[float, float, float]] = None,
    relion_version: Optional[str] = None,
) -> None:
    """Set the points from a pandas DataFrame with RELION columns.

    Coordinates are resolved by ``copick.util.formats.relion_coordinates_to_angstrom`` (centred coordinates with the
    copick tomogram's centre first, then rlnCoordinateX/Y/Z in tilt-series pixels, then in pixels of the run's smallest
    voxel spacing), and orientations and shifts by ``relion_rows_to_poses``: each pick's location is its coordinate
    minus its shift, and its transform holds the rotation with zero translation. ``rlnHelicalTubeID`` becomes the
    pick's instance ID, and filament rows are ordered along each filament (``order_filament_rows``).

    Args:
        picks: The picks to set.
        df: RELION particle table; every row belongs to this run.
        optics: The STAR file's optics table, for its tilt-series pixel size.
        tilt_series_pixel_size: Tilt-series pixel size in Angstrom, overriding the optics table.
        tomogram_center: Tomogram centre in Angstrom; overrides the copick tomogram.
        relion_version: Force centred ("relion5") or pixel ("relion4") coordinates.
    """
    from copick.util.formats import relion_coordinates_to_angstrom

    if not {"rlnCenteredCoordinateXAngst", "rlnCenteredCoordinateYAngst", "rlnCenteredCoordinateZAngst"}.issubset(
        df.columns,
    ) and not {"rlnCoordinateX", "rlnCoordinateY", "rlnCoordinateZ"}.issubset(df.columns):
        raise ValueError("DataFrame does not contain required RELION columns.")

    df = order_filament_rows(df)
    has_centered = {
        "rlnCenteredCoordinateXAngst",
        "rlnCenteredCoordinateYAngst",
        "rlnCenteredCoordinateZAngst",
    }.issubset(
        df.columns,
    )
    if tomogram_center is None and has_centered:
        tomogram_center = copick_tomogram_center(picks)

    coordinates = relion_coordinates_to_angstrom(
        df.drop(columns=["rlnTomoName"], errors="ignore"),
        voxel_spacing=_smallest_voxel_spacing(picks),
        tomogram_center=tomogram_center,
        tilt_series_pixel_size=tilt_series_pixel_size,
        optics=optics,
        relion_version=relion_version,
    )
    rotations, offsets = relion_rows_to_poses(df)

    transforms = np.zeros((len(df), 4, 4), dtype=float)
    transforms[:, :3, :3] = rotations
    transforms[:, 3, 3] = 1.0

    picks.from_numpy(coordinates - offsets, transforms, instance_ids=relion_instance_ids(df))
