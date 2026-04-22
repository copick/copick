import contextlib
import json
import os
from typing import Any, Dict, List, Optional, Tuple

import click

from copick.cli.util import add_debug_option
from copick.util.log import get_logger


def _parse_kv(arg: Optional[str]) -> Dict[str, Any]:
    """Parse a comma-separated ``key=value`` string into a dict.

    Empty/None input yields ``{}``. Whitespace around each key and value is
    stripped. No type coercion — downstream consumers (e.g.
    ``PortalAnnotationMeta.compare``) cast through their pydantic models.
    """
    if not arg:
        return {}
    result: Dict[str, Any] = {}
    for pair in arg.split(","):
        pair = pair.strip()
        if not pair:
            continue
        if "=" not in pair:
            raise click.BadParameter(f"Expected 'key=value' in '{pair}'.")
        k, v = pair.split("=", 1)
        result[k.strip()] = v.strip()
    return result


def _parse_split_option(value: str) -> Tuple[str, List[str]]:
    """Parse a ``NAME=RUN1,RUN2`` CLI argument.

    Returns ``(split_name, [run_names])``. Whitespace around each token is
    stripped. Raises :class:`click.BadParameter` when the syntax is wrong or
    any part is empty.
    """
    if not value or "=" not in value:
        raise click.BadParameter(f"Expected 'NAME=RUN1,RUN2,...' in --split '{value}'.")
    name, rhs = value.split("=", 1)
    name = name.strip()
    if not name:
        raise click.BadParameter(f"Split name is empty in --split '{value}'.")
    if "," in name or "=" in name:
        raise click.BadParameter(f"Split name may not contain ',' or '=' (got '{name}').")
    runs = [r.strip() for r in rhs.split(",") if r.strip()]
    if not runs:
        raise click.BadParameter(f"No runs listed for split '{name}' in --split '{value}'.")
    return name, runs


def _load_splits_file(path: str) -> Dict[str, List[str]]:
    """Read a CSV with ``split,run`` columns into ``{split: [run, run, ...]}``.

    Extra columns are ignored. Missing columns raise ``ValueError``. Empty
    cells are skipped.
    """
    import csv as _csv

    mapping: Dict[str, List[str]] = {}
    with open(path, newline="") as fh:
        reader = _csv.DictReader(fh)
        if reader.fieldnames is None or "split" not in reader.fieldnames or "run" not in reader.fieldnames:
            raise ValueError(
                f"Splits file {path} must have columns 'split' and 'run' (got {reader.fieldnames!r}).",
            )
        for row in reader:
            split = (row.get("split") or "").strip()
            run = (row.get("run") or "").strip()
            if not split or not run:
                continue
            mapping.setdefault(split, []).append(run)
    return mapping


def _parse_json_opt(value: Optional[str], flag: str) -> Dict[str, Any]:
    """Parse a JSON-object CLI argument, raising BadParameter on malformed input."""
    if value is None or value == "":
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as e:
        raise click.BadParameter(f"{flag} must be a JSON object; got {value!r} ({e})") from e
    if not isinstance(parsed, dict):
        raise click.BadParameter(
            f"{flag} must be a JSON object (got {type(parsed).__name__}).",
        )
    return parsed


def _normalize_overlay_url(value: str) -> Tuple[str, bool]:
    """Return ``(normalized_url, is_local)`` for an overlay URL argument.

    A bare local path is wrapped in ``local://`` (matching the historical CLI
    shape). ``file://`` and ``local://`` URLs pass through unchanged and are
    reported as local. Anything with another protocol (``ssh://``, ``s3://``,
    …) is returned as-is and reported as remote.
    """
    if "://" not in value:
        return (f"local://{os.path.abspath(value)}", True)
    if value.startswith("file://") or value.startswith("local://"):
        return (value, True)
    return (value, False)


def _strip_local_prefix(url: str) -> str:
    """Strip ``local://`` or ``file://`` from ``url`` for filesystem operations."""
    for prefix in ("local://", "file://"):
        if url.startswith(prefix):
            return url[len(prefix) :]
    return url


def _merge_splits_inputs(
    split_args: Tuple[str, ...],
    splits_file: Optional[str],
) -> Optional[Dict[str, List[str]]]:
    """Combine ``--split`` repeats + ``--splits-file`` into a single mapping.

    CLI ``--split`` entries override any split-name already in the file.
    Returns ``None`` when neither input is provided.
    """
    if not split_args and not splits_file:
        return None
    mapping: Dict[str, List[str]] = {}
    if splits_file:
        mapping.update(_load_splits_file(splits_file))
    for raw in split_args:
        name, runs = _parse_split_option(raw)
        mapping[name] = runs
    return mapping


def _load_source_root(
    source_config: Optional[str],
    source_dataset_ids: Optional[str],
) -> Tuple[Any, Optional[str]]:
    """Load a copick root from either a config file or CDP dataset IDs.

    Returns ``(root, temp_config_path)``. ``temp_config_path`` is non-None
    only when the CDP shortcut was used; callers should delete it in a
    ``finally`` clause.

    Raises :class:`click.BadParameter` when neither or both inputs are
    provided.
    """
    import copick
    from copick.util.sync import create_dataportal_config, parse_dataset_ids

    if bool(source_config) == bool(source_dataset_ids):
        raise click.BadParameter(
            "Provide exactly one of --config / --source-config or --source-dataset-ids.",
        )
    if source_dataset_ids:
        dataset_ids = parse_dataset_ids(source_dataset_ids)
        temp_path = create_dataportal_config(dataset_ids)
        try:
            root = copick.from_file(temp_path)
        except Exception:
            # On failure clean up the temp file immediately so we don't leak.
            with contextlib.suppress(OSError):
                os.unlink(temp_path)
            raise
        return root, temp_path
    root = copick.from_file(source_config)
    return root, None


@click.group(short_help="Create and manage copick configuration files.")
@click.pass_context
def config(ctx):
    """Create and manage copick configuration files."""
    pass


def parse_object(ctx, param, value):
    """Parse the --objects input manually"""
    parsed_objects = []
    for obj in value:
        parts = obj.split(",")
        if len(parts) < 2:
            raise click.BadParameter(f"Invalid format for --objects: {obj}")

        name = parts[0].strip()
        is_particle = parts[1].strip().lower() == "true"

        radius = None
        pdb_id = None
        if is_particle:
            if len(parts) >= 3:
                try:
                    radius = int(parts[2])
                except ValueError as err:
                    raise click.BadParameter(f"Invalid radius value in --objects: {parts[2]}") from err
            if len(parts) >= 4:
                pdb_id = parts[3].strip()

        parsed_objects.append((name, is_particle, radius, pdb_id))

    return parsed_objects


@config.command(
    context_settings={"show_default": True},
    short_help="Set up a configuration file from CZDP dataset IDs.",
    no_args_is_help=True,
)
@click.option(
    "-ds",
    "--dataset-id",
    type=int,
    required=True,
    multiple=True,
    help="Dataset IDs from the CryoET Data Portal to include in the configuration",
)
@click.option(
    "--overlay",
    type=click.Path(file_okay=False, dir_okay=True),
    required=True,
    help="Path to the local overlay directory where intermediate files will be stored or read.",
)
@click.option(
    "--output",
    default="config.json",
    type=click.Path(dir_okay=False),
    required=True,
    help="Path to save the generated configuration file.",
)
@add_debug_option
@click.pass_context
def dataportal(
    ctx,
    dataset_id: List[int],
    overlay: str,
    output: str,
    debug: bool = False,
):
    """
    Generate a configuration file from a CZDP dataset ID and local overlay directory
    """
    # Deferred import for performance
    import copick

    logger = get_logger(__name__, debug=debug)
    logger.info("Generating configuration file from CZDP dataset IDs...")

    # Generate Config for the Given Directory
    try:
        copick.from_czcdp_datasets(
            dataset_id,
            overlay_root=overlay,
            output_path=output,
            overlay_fs_args={"auto_mkdir": True},
        )
    except Exception as e:
        logger.critical(f"Failed to generate configuration file: {e}")
        ctx.fail(f"Error generating configuration file: {e}")
        return

    logger.info(f"Generated configuration file at {output}.")


@config.command(
    context_settings={"show_default": True},
    short_help="Set up a configuration file for a local project.",
    no_args_is_help=True,
)
@click.pass_context
@click.option(
    "--overlay-root",
    type=click.Path(file_okay=False, dir_okay=True),
    required=True,
    help="Overlay root path.",
)
@click.option(
    "--objects",
    type=str,
    multiple=True,
    callback=parse_object,
    required=False,
    help="List of desired objects in the format: name,is_particle,[radius],[pdb_id]. Repeat this option for multiple objects.",
)
@click.option(
    "--config",
    type=click.Path(dir_okay=False),
    required=False,
    default="config.json",
    help="Path to the output JSON configuration file.",
)
@click.option("--proj-name", type=str, required=False, default="project", help="Name of the project configuration.")
@click.option(
    "--proj-description",
    type=str,
    required=False,
    default="Config Project for SessionXXa",
    help="Description of the project configuration.",
)
@add_debug_option
def filesystem(
    ctx,
    config: str,
    proj_name: str,
    proj_description: str,
    overlay_root: str,
    objects: List[str],
    debug: bool = False,
):
    """
    Generate a configuration file for a local project directory.

    Example Useage:
    copick config filesystem \
        --config config.json \
        --overlay-root /mnt/24sep24a/run002 \
        --objects membrane,False --objects apoferritin,True,60,4V1W \
        --proj-name 24sep24a --proj-description "Synaptic Vesicles collected on 24sep24"
    """
    import copick
    from copick.models import PickableObject

    logger = get_logger(__name__, debug=debug)
    logger.info("Generating configuration file for a local project directory...")

    label_counter = 1
    pickable_objects = []
    for obj in objects:
        name, is_particle, radius, pdb_id = obj

        # Check if the name contains an underscore
        if "_" in name:
            raise ValueError(f"The protein name ({name}) should not contain the '_' character!")

        obj_dict = {"name": name, "is_particle": is_particle, "label": label_counter}

        if is_particle and radius is not None:
            obj_dict["radius"] = radius
            if pdb_id:
                obj_dict["pdb_id"] = pdb_id

        pickable_objects.append(PickableObject(**obj_dict))
        label_counter += 1

    copick.new_config(
        config=config,
        proj_name=proj_name,
        proj_description=proj_description,
        overlay_root=overlay_root,
        pickable_objects=pickable_objects,
    )

    logger.info(f"Generated configuration file at {config}.")


@config.command(
    context_settings={"show_default": True},
    short_help="Set up a configuration file from an mlcroissant manifest.",
    no_args_is_help=True,
)
@click.option(
    "--croissant-url",
    type=str,
    required=True,
    help="URL or path to the Croissant metadata.json.",
)
@click.option(
    "--overlay",
    type=str,
    required=False,
    help=(
        "Optional writable overlay (Mode B). Accepts any fsspec URL "
        "(e.g. 'ssh:///remote/overlay', 's3://bucket/overlay') or a bare "
        "local path. If omitted, the Croissant's copick:baseUrl is used "
        "as the write location (Mode A)."
    ),
)
@click.option(
    "--overlay-fs-args",
    "overlay_fs_args_arg",
    type=str,
    required=False,
    default=None,
    help=(
        "JSON object of fsspec kwargs for --overlay (e.g. "
        '\'{"host":"localhost","port":2222}\'). Local overlays add '
        "'auto_mkdir=true' automatically unless overridden."
    ),
)
@click.option(
    "--static-fs-args",
    "static_fs_args_arg",
    type=str,
    required=False,
    default=None,
    help=(
        "JSON object of fsspec kwargs for resolving data URLs against the "
        "Croissant's base URL (e.g. SSH credentials for overlay data)."
    ),
)
@click.option(
    "--croissant-fs-args",
    "croissant_fs_args_arg",
    type=str,
    required=False,
    default=None,
    help=(
        "JSON object of fsspec kwargs for fetching the Croissant manifest "
        "itself (typically empty when --croissant-url is local)."
    ),
)
@click.option(
    "--base-url",
    type=str,
    required=False,
    help="Optional override for the Croissant's copick:baseUrl (for moved datasets).",
)
@click.option(
    "--output",
    default="config.json",
    type=click.Path(dir_okay=False),
    required=True,
    help="Path to save the generated copick configuration file.",
)
@add_debug_option
@click.pass_context
def mlcroissant(
    ctx,
    croissant_url: str,
    overlay: str,
    overlay_fs_args_arg: Optional[str],
    static_fs_args_arg: Optional[str],
    croissant_fs_args_arg: Optional[str],
    base_url: str,
    output: str,
    debug: bool = False,
):
    """
    Generate a copick configuration file from an mlcroissant manifest.
    """
    import copick

    logger = get_logger(__name__, debug=debug)
    logger.info("Generating configuration file from Croissant manifest...")

    if overlay:
        overlay_url, overlay_is_local = _normalize_overlay_url(overlay)
        overlay_fs_args = _parse_json_opt(overlay_fs_args_arg, "--overlay-fs-args")
        if overlay_is_local:
            overlay_fs_args.setdefault("auto_mkdir", True)
            os.makedirs(_strip_local_prefix(overlay_url), exist_ok=True)
    else:
        overlay_url = None
        overlay_fs_args = None

    static_fs_args = _parse_json_opt(static_fs_args_arg, "--static-fs-args")
    croissant_fs_args = _parse_json_opt(croissant_fs_args_arg, "--croissant-fs-args")

    try:
        copick.from_croissant(
            croissant_url=croissant_url,
            overlay_root=overlay_url,
            croissant_base_url=base_url,
            overlay_fs_args=overlay_fs_args,
            static_fs_args=static_fs_args or None,
            croissant_fs_args=croissant_fs_args or None,
            output_path=output,
        )
    except Exception as e:
        logger.critical(f"Failed to generate configuration file: {e}")
        ctx.fail(f"Error generating configuration file: {e}")
        return

    logger.info(f"Generated configuration file at {output}.")


@config.command(
    name="export-croissant",
    context_settings={"show_default": True},
    short_help="Export a copick project to an mlcroissant manifest.",
    no_args_is_help=True,
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(dir_okay=False, exists=True),
    required=False,
    default=None,
    help="Path to the input copick configuration file. Mutually exclusive with --source-dataset-ids.",
)
@click.option(
    "--source-dataset-ids",
    "source_dataset_ids",
    type=str,
    required=False,
    default=None,
    help="Comma-separated CryoET Data Portal dataset IDs (e.g. '10000,10001'). Creates a temporary CDP config; mutually exclusive with --config.",
)
@click.option(
    "--project-root",
    type=click.Path(file_okay=False, dir_okay=True),
    required=True,
    help="Copick project root directory; Croissant/ is written under this.",
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Overwrite an existing Croissant/metadata.json under --project-root.",
)
@click.option(
    "--base-url",
    type=str,
    required=False,
    help="Absolute URL that resolves to --project-root at consumer read time. Required for filesystem sources; ignored for CDP (common portal-URL prefix is used).",
)
@click.option("--dataset-name", type=str, required=False, help="Dataset title for the Croissant.")
@click.option("--description", type=str, required=False, help="Dataset description.")
@click.option("--license", "license_", type=str, required=False, default="CC-BY-4.0", help="Dataset license.")
@click.option("--cite-as", type=str, required=False, default="", help="Citation string.")
@click.option("--date-published", type=str, required=False, help="ISO date string (defaults to today).")
@click.option(
    "--no-file-sha256",
    is_flag=True,
    default=False,
    help="Skip computing sha256 for picks/meshes (faster but marks output non-strict).",
)
@click.option(
    "--emit-config",
    "emit_config",
    type=click.Path(dir_okay=False),
    required=False,
    default=None,
    help="Also write an mlcroissant copick config JSON at this path, pointing at the exported Croissant. Off by default.",
)
@click.option(
    "--config-overlay",
    "config_overlay",
    type=str,
    required=False,
    default=None,
    help=(
        "Overlay URL to embed in the emitted copick config (Mode B). Accepts "
        "any fsspec URL (e.g. 'ssh:///remote/overlay', 's3://bucket/overlay') "
        "or a bare local path. Only used when --emit-config is set. If "
        "omitted, the emitted config is Mode A (self-contained)."
    ),
)
@click.option(
    "--config-overlay-fs-args",
    "config_overlay_fs_args_arg",
    type=str,
    required=False,
    default=None,
    help=(
        "JSON object of fsspec kwargs for --config-overlay (e.g. "
        '\'{"host":"localhost","port":2222}\'). Local overlays add '
        "'auto_mkdir=true' automatically unless overridden."
    ),
)
@click.option(
    "--config-static-fs-args",
    "config_static_fs_args_arg",
    type=str,
    required=False,
    default=None,
    help=(
        "JSON object of fsspec kwargs for reaching the Croissant's base URL "
        "(data location) from the emitted copick config. Defaults to the "
        "source config's overlay_fs_args. Never written to the Croissant "
        "manifest itself (kept credential-free for sharing)."
    ),
)
@click.option(
    "--config-croissant-fs-args",
    "config_croissant_fs_args_arg",
    type=str,
    required=False,
    default=None,
    help=(
        "JSON object of fsspec kwargs for reading the Croissant manifest "
        "itself from the emitted copick config. Defaults to empty (typical "
        "when --project-root is local)."
    ),
)
@click.option(
    "--runs",
    "runs_arg",
    type=str,
    required=False,
    default=None,
    help="Comma-separated run names to include. Omit to include all runs.",
)
@click.option(
    "--tomograms",
    "tomograms_arg",
    type=str,
    multiple=True,
    help="Copick URI to filter tomograms (e.g. 'wbp@10.0'). Repeatable. Omit to include all tomograms.",
)
@click.option(
    "--features",
    "features_arg",
    type=str,
    multiple=True,
    help="Copick URI to filter features (e.g. 'wbp@10.0:sobel'). Repeatable. Omit to include all features.",
)
@click.option(
    "--picks",
    "picks_arg",
    type=str,
    multiple=True,
    help="Copick URI to filter picks (e.g. 'ribosome:*/*'). Repeatable. Omit to include all picks.",
)
@click.option(
    "--meshes",
    "meshes_arg",
    type=str,
    multiple=True,
    help="Copick URI to filter meshes (e.g. 'ribosome:*/*'). Repeatable. Omit to include all meshes.",
)
@click.option(
    "--segmentations",
    "segmentations_arg",
    type=str,
    multiple=True,
    help="Copick URI to filter segmentations (e.g. 'membrane:*/*@10.0'). Repeatable. Omit to include all segmentations.",
)
@click.option(
    "--objects",
    "objects_arg",
    type=str,
    required=False,
    default=None,
    help="Comma-separated pickable object names to emit density maps for. Omit to include all objects.",
)
@click.option(
    "--tomo-type-map",
    "tomo_type_map_arg",
    type=str,
    required=False,
    default=None,
    help="Rename tomo_type values at CSV emission time, e.g. 'wbp-raw:wbp,denoised-cryocare:denoised'.",
)
@click.option(
    "--object-name-map",
    "object_name_map_arg",
    type=str,
    required=False,
    default=None,
    help="Rename object names at CSV emission time (applies to picks/meshes/segmentations/objects and copick:config.pickable_objects), e.g. 'cytosolic-ribosome:ribosome'.",
)
@click.option(
    "--session-id-template",
    "session_id_template_arg",
    type=str,
    required=False,
    default=None,
    help="Python str.format template for synthesizing picks/segmentations session_id values from CDP annotation metadata (CDP-only). Placeholders: any scalar _PortalAnnotation field, plus {author}, {authors}, {annotation_file_id}.",
)
@click.option(
    "--picks-portal-meta",
    "picks_portal_meta_arg",
    type=str,
    required=False,
    default=None,
    help="Comma-separated k=v pairs filtering CDP picks by portal annotation metadata (e.g. 'ground_truth_status=true,method_type=manual'). CDP-only.",
)
@click.option(
    "--picks-author",
    "picks_author_arg",
    type=str,
    required=False,
    default=None,
    help="Comma-separated author names filtering CDP picks (e.g. 'Alice,Bob'). CDP-only.",
)
@click.option(
    "--segmentations-portal-meta",
    "segmentations_portal_meta_arg",
    type=str,
    required=False,
    default=None,
    help="Comma-separated k=v pairs filtering CDP segmentations by portal annotation metadata. CDP-only.",
)
@click.option(
    "--segmentations-author",
    "segmentations_author_arg",
    type=str,
    required=False,
    default=None,
    help="Comma-separated author names filtering CDP segmentations. CDP-only.",
)
@click.option(
    "--tomograms-portal-meta",
    "tomograms_portal_meta_arg",
    type=str,
    required=False,
    default=None,
    help="Comma-separated k=v pairs filtering CDP tomograms by portal tomogram metadata (e.g. 'reconstruction_method=wbp,ctf_corrected=true'). CDP-only.",
)
@click.option(
    "--tomograms-author",
    "tomograms_author_arg",
    type=str,
    required=False,
    default=None,
    help="Comma-separated author names filtering CDP tomograms. CDP-only.",
)
@click.option(
    "--split",
    "split_args",
    type=str,
    multiple=True,
    help="Assign runs to an ML split, e.g. 'train=TS_001,TS_002'. Repeatable. Standard names (train/val/validation/test/eval) map to the canonical cr:*Split URIs; custom names emit without a URI.",
)
@click.option(
    "--splits-file",
    "splits_file",
    type=click.Path(dir_okay=False, exists=True),
    required=False,
    default=None,
    help="CSV with columns 'split' and 'run' providing split assignments. Combined with any --split flags (the CLI flags override duplicate split names).",
)
@add_debug_option
@click.pass_context
def export_croissant_cmd(
    ctx,
    config_path: str,
    source_dataset_ids: str,
    project_root: str,
    force: bool,
    base_url: str,
    dataset_name: str,
    description: str,
    license_: str,
    cite_as: str,
    date_published: str,
    no_file_sha256: bool,
    emit_config: str,
    config_overlay: str,
    config_overlay_fs_args_arg: Optional[str],
    config_static_fs_args_arg: Optional[str],
    config_croissant_fs_args_arg: Optional[str],
    runs_arg: str,
    tomograms_arg: tuple,
    features_arg: tuple,
    picks_arg: tuple,
    meshes_arg: tuple,
    segmentations_arg: tuple,
    objects_arg: str,
    tomo_type_map_arg: str,
    object_name_map_arg: str,
    session_id_template_arg: str,
    picks_portal_meta_arg: str,
    picks_author_arg: str,
    segmentations_portal_meta_arg: str,
    segmentations_author_arg: str,
    tomograms_portal_meta_arg: str,
    tomograms_author_arg: str,
    split_args: tuple,
    splits_file: Optional[str],
    debug: bool = False,
):
    """
    Export a copick project to a Croissant manifest + CSV sidecars under
    <project-root>/Croissant/.

    With --emit-config PATH, also writes a ready-to-use mlcroissant copick
    configuration JSON at PATH. Pair with --config-overlay DIR to embed a
    writable overlay (Mode B) so viz tools can annotate without touching the
    source data.

    Subset selection: any of --runs / --tomograms / --features / --picks /
    --meshes / --segmentations / --objects may be provided to restrict the
    export. URI-based flags follow copick's standard URI grammar and can be
    repeated to union multiple selectors. Any flag that's omitted means "no
    filter, include everything of that type".
    """
    import json as _json

    from copick.ops.croissant import export_croissant
    from copick.util.sync import parse_list, parse_mapping

    logger = get_logger(__name__, debug=debug)
    logger.info("Loading copick project...")

    try:
        root, temp_config_path = _load_source_root(config_path, source_dataset_ids)
    except click.BadParameter:
        raise
    except Exception as e:
        logger.critical(f"Failed to load copick project: {e}")
        ctx.fail(f"Error loading copick project: {e}")
        return

    logger.info(f"Exporting Croissant to {project_root}/Croissant/...")
    try:
        metadata_path = export_croissant(
            root,
            project_root=project_root,
            base_url=base_url,
            dataset_name=dataset_name,
            description=description,
            license=license_,
            cite_as=cite_as,
            date_published=date_published,
            compute_file_sha256=not no_file_sha256,
            force=force,
            runs=parse_list(runs_arg) if runs_arg else None,
            tomograms=list(tomograms_arg) if tomograms_arg else None,
            features=list(features_arg) if features_arg else None,
            picks=list(picks_arg) if picks_arg else None,
            meshes=list(meshes_arg) if meshes_arg else None,
            segmentations=list(segmentations_arg) if segmentations_arg else None,
            objects=parse_list(objects_arg) if objects_arg else None,
            tomo_type_map=parse_mapping(tomo_type_map_arg) if tomo_type_map_arg else None,
            object_name_map=parse_mapping(object_name_map_arg) if object_name_map_arg else None,
            session_id_template=session_id_template_arg or None,
            picks_portal_meta=_parse_kv(picks_portal_meta_arg) or None,
            picks_author=parse_list(picks_author_arg) if picks_author_arg else None,
            segmentations_portal_meta=_parse_kv(segmentations_portal_meta_arg) or None,
            segmentations_author=parse_list(segmentations_author_arg) if segmentations_author_arg else None,
            tomograms_portal_meta=_parse_kv(tomograms_portal_meta_arg) or None,
            tomograms_author=parse_list(tomograms_author_arg) if tomograms_author_arg else None,
            splits=_merge_splits_inputs(split_args, splits_file),
        )
    except Exception as e:
        logger.critical(f"Failed to export Croissant: {e}")
        ctx.fail(f"Error exporting Croissant: {e}")
        return
    finally:
        if temp_config_path:
            with contextlib.suppress(OSError):
                os.unlink(temp_config_path)

    logger.info(f"Wrote Croissant at {metadata_path}.")

    if emit_config:
        source_cfg = root.config
        default_static_fs_args = dict(getattr(source_cfg, "overlay_fs_args", {}) or {})
        static_fs_args = (
            _parse_json_opt(config_static_fs_args_arg, "--config-static-fs-args")
            if config_static_fs_args_arg is not None
            else default_static_fs_args
        )
        croissant_fs_args = _parse_json_opt(
            config_croissant_fs_args_arg,
            "--config-croissant-fs-args",
        )

        mlc_cfg = {
            "config_type": "mlcroissant",
            "pickable_objects": [],
            "croissant_url": str(metadata_path),
            "static_fs_args": static_fs_args,
            "croissant_fs_args": croissant_fs_args,
        }
        if config_overlay:
            overlay_url, overlay_is_local = _normalize_overlay_url(config_overlay)
            overlay_args = _parse_json_opt(
                config_overlay_fs_args_arg,
                "--config-overlay-fs-args",
            )
            if overlay_is_local:
                overlay_args.setdefault("auto_mkdir", True)
                os.makedirs(_strip_local_prefix(overlay_url), exist_ok=True)
            mlc_cfg["overlay_root"] = overlay_url
            mlc_cfg["overlay_fs_args"] = overlay_args
        with open(emit_config, "w") as f:
            _json.dump(mlc_cfg, f, indent=4)
        logger.info(f"Wrote mlcroissant copick config at {emit_config}.")


@config.command(
    name="append-croissant",
    context_settings={"show_default": True},
    short_help="Append filtered rows from a copick project into an existing Croissant.",
    no_args_is_help=True,
)
@click.option(
    "--croissant",
    "croissant_path",
    type=click.Path(dir_okay=False, exists=True),
    required=True,
    help="Path / URL to the destination Croissant metadata.json. Must be writable (Mode A).",
)
@click.option(
    "--source-config",
    "source_config",
    type=click.Path(dir_okay=False, exists=True),
    required=False,
    default=None,
    help="Path to a copick config JSON (filesystem, CDP, or mlcroissant). Mutually exclusive with --source-dataset-ids.",
)
@click.option(
    "--source-dataset-ids",
    "source_dataset_ids",
    type=str,
    required=False,
    default=None,
    help="Comma-separated CryoET Data Portal dataset IDs (e.g. '10000,10001'). Mutually exclusive with --source-config.",
)
@click.option(
    "--no-file-sha256",
    is_flag=True,
    default=False,
    help="Skip computing sha256 for picks/meshes (faster but marks output non-strict).",
)
@click.option(
    "--runs",
    "runs_arg",
    type=str,
    required=False,
    default=None,
    help="Comma-separated run names to include. Omit to include all runs.",
)
@click.option(
    "--tomograms",
    "tomograms_arg",
    type=str,
    multiple=True,
    help="Copick URI to filter tomograms (e.g. 'wbp@10.0'). Repeatable.",
)
@click.option(
    "--features",
    "features_arg",
    type=str,
    multiple=True,
    help="Copick URI to filter features (e.g. 'wbp@10.0:sobel'). Repeatable.",
)
@click.option(
    "--picks",
    "picks_arg",
    type=str,
    multiple=True,
    help="Copick URI to filter picks (e.g. 'ribosome:*/*'). Repeatable.",
)
@click.option(
    "--meshes",
    "meshes_arg",
    type=str,
    multiple=True,
    help="Copick URI to filter meshes (e.g. 'ribosome:*/*'). Repeatable.",
)
@click.option(
    "--segmentations",
    "segmentations_arg",
    type=str,
    multiple=True,
    help="Copick URI to filter segmentations (e.g. 'membrane:*/*@10.0'). Repeatable.",
)
@click.option(
    "--objects",
    "objects_arg",
    type=str,
    required=False,
    default=None,
    help="Comma-separated pickable object names to emit density maps for.",
)
@click.option(
    "--tomo-type-map",
    "tomo_type_map_arg",
    type=str,
    required=False,
    default=None,
    help="Rename tomo_type values at emission time, e.g. 'wbp-raw:wbp'.",
)
@click.option(
    "--object-name-map",
    "object_name_map_arg",
    type=str,
    required=False,
    default=None,
    help="Rename object names at emission time (also updates copick:config.pickable_objects and records portal_original_name in metadata).",
)
@click.option(
    "--session-id-template",
    "session_id_template_arg",
    type=str,
    required=False,
    default=None,
    help="Python str.format template for synthesizing picks/segmentations session_id from CDP annotation metadata. CDP-only.",
)
@click.option(
    "--picks-portal-meta",
    "picks_portal_meta_arg",
    type=str,
    required=False,
    default=None,
    help="Comma-separated k=v pairs filtering CDP picks by portal metadata. CDP-only.",
)
@click.option(
    "--picks-author",
    "picks_author_arg",
    type=str,
    required=False,
    default=None,
    help="Comma-separated author names filtering CDP picks. CDP-only.",
)
@click.option(
    "--segmentations-portal-meta",
    "segmentations_portal_meta_arg",
    type=str,
    required=False,
    default=None,
    help="Comma-separated k=v pairs filtering CDP segmentations. CDP-only.",
)
@click.option(
    "--segmentations-author",
    "segmentations_author_arg",
    type=str,
    required=False,
    default=None,
    help="Comma-separated author names filtering CDP segmentations. CDP-only.",
)
@click.option(
    "--tomograms-portal-meta",
    "tomograms_portal_meta_arg",
    type=str,
    required=False,
    default=None,
    help="Comma-separated k=v pairs filtering CDP tomograms. CDP-only.",
)
@click.option(
    "--tomograms-author",
    "tomograms_author_arg",
    type=str,
    required=False,
    default=None,
    help="Comma-separated author names filtering CDP tomograms. CDP-only.",
)
@click.option(
    "--split",
    "split_args",
    type=str,
    multiple=True,
    help="Assign appended runs to an ML split, e.g. 'train=TS_001,TS_002'. Repeatable. Preserves existing destination splits for runs you don't mention.",
)
@click.option(
    "--splits-file",
    "splits_file",
    type=click.Path(dir_okay=False, exists=True),
    required=False,
    default=None,
    help="CSV with columns 'split' and 'run' providing split assignments for appended runs.",
)
@add_debug_option
@click.pass_context
def append_croissant_cmd(
    ctx,
    croissant_path: str,
    source_config: str,
    source_dataset_ids: str,
    no_file_sha256: bool,
    runs_arg: str,
    tomograms_arg: tuple,
    features_arg: tuple,
    picks_arg: tuple,
    meshes_arg: tuple,
    segmentations_arg: tuple,
    objects_arg: str,
    tomo_type_map_arg: str,
    object_name_map_arg: str,
    session_id_template_arg: str,
    picks_portal_meta_arg: str,
    picks_author_arg: str,
    segmentations_portal_meta_arg: str,
    segmentations_author_arg: str,
    tomograms_portal_meta_arg: str,
    tomograms_author_arg: str,
    split_args: tuple,
    splits_file: Optional[str],
    debug: bool = False,
):
    """
    Append filtered rows from a source copick project into an existing
    Croissant at --croissant.

    The destination's top-level metadata (name, description, license, etc.) is
    preserved; only rows and copick:config.pickable_objects are unioned.
    Rows with the same primary key as an existing destination row are replaced
    (last append wins). Appended URLs are absolutized so the destination CSVs
    remain self-sufficient even when source and destination use different
    base URLs.

    Multiple appends with different filters / transforms let you build up a
    Croissant incrementally — e.g. export curated tomograms first, then append
    ribosome picks from one author with a session template, then append
    proteasome picks from a different author with a different template.
    """
    from copick.ops.croissant import append_croissant
    from copick.util.sync import parse_list, parse_mapping

    logger = get_logger(__name__, debug=debug)
    logger.info("Loading source copick project...")

    try:
        source_root, temp_config_path = _load_source_root(source_config, source_dataset_ids)
    except click.BadParameter:
        raise
    except Exception as e:
        logger.critical(f"Failed to load source copick project: {e}")
        ctx.fail(f"Error loading source copick project: {e}")
        return

    logger.info(f"Appending into Croissant at {croissant_path}...")
    try:
        metadata_path = append_croissant(
            croissant_path,
            source_root,
            compute_file_sha256=not no_file_sha256,
            runs=parse_list(runs_arg) if runs_arg else None,
            tomograms=list(tomograms_arg) if tomograms_arg else None,
            features=list(features_arg) if features_arg else None,
            picks=list(picks_arg) if picks_arg else None,
            meshes=list(meshes_arg) if meshes_arg else None,
            segmentations=list(segmentations_arg) if segmentations_arg else None,
            objects=parse_list(objects_arg) if objects_arg else None,
            tomo_type_map=parse_mapping(tomo_type_map_arg) if tomo_type_map_arg else None,
            object_name_map=parse_mapping(object_name_map_arg) if object_name_map_arg else None,
            session_id_template=session_id_template_arg or None,
            picks_portal_meta=_parse_kv(picks_portal_meta_arg) or None,
            picks_author=parse_list(picks_author_arg) if picks_author_arg else None,
            segmentations_portal_meta=_parse_kv(segmentations_portal_meta_arg) or None,
            segmentations_author=parse_list(segmentations_author_arg) if segmentations_author_arg else None,
            tomograms_portal_meta=_parse_kv(tomograms_portal_meta_arg) or None,
            tomograms_author=parse_list(tomograms_author_arg) if tomograms_author_arg else None,
            splits=_merge_splits_inputs(split_args, splits_file),
        )
    except Exception as e:
        logger.critical(f"Failed to append to Croissant: {e}")
        ctx.fail(f"Error appending to Croissant: {e}")
        return
    finally:
        if temp_config_path:
            with contextlib.suppress(OSError):
                os.unlink(temp_config_path)

    logger.info(f"Appended rows into {metadata_path}.")


@config.command(
    name="set-splits",
    context_settings={"show_default": True},
    short_help="Edit train/val/test split assignments on an existing Croissant.",
    no_args_is_help=True,
)
@click.option(
    "--croissant",
    "croissant_path",
    type=click.Path(dir_okay=False, exists=True),
    required=True,
    help="Path / URL to the destination Croissant metadata.json. Must be writable (Mode A).",
)
@click.option(
    "--split",
    "split_args",
    type=str,
    multiple=True,
    help="Assign runs to an ML split, e.g. 'train=TS_001,TS_002'. Repeatable.",
)
@click.option(
    "--splits-file",
    "splits_file",
    type=click.Path(dir_okay=False, exists=True),
    required=False,
    default=None,
    help="CSV with columns 'split' and 'run' providing assignments. Combined with --split flags (CLI flags override duplicate split names).",
)
@click.option(
    "--clear-all",
    "clear_all",
    is_flag=True,
    default=False,
    help="Clear every run's split before applying the new mapping.",
)
@click.option(
    "--unassign",
    "unassign_arg",
    type=str,
    required=False,
    default=None,
    help="Comma-separated run names to clear split for, applied AFTER the mapping.",
)
@add_debug_option
@click.pass_context
def set_croissant_splits_cmd(
    ctx,
    croissant_path: str,
    split_args: tuple,
    splits_file: Optional[str],
    clear_all: bool,
    unassign_arg: Optional[str],
    debug: bool = False,
):
    """
    Assign or edit train/val/test (or custom) splits on an existing Croissant.

    Splits live in the Croissant's runs.csv `split` column. This command opens
    the destination in Mode A, applies the mapping + unassign + clear-all
    options under a single batch commit, and rewrites metadata.json so the
    spec-conforming splits RecordSet reflects the new set of distinct split
    names.

    Examples:

    \b
        copick config set-splits \\
            --croissant Croissant/metadata.json \\
            --split train=TS_001,TS_002 \\
            --split val=TS_003 \\
            --split test=TS_004

    \b
        # Start fresh:
        copick config set-splits --croissant ... --clear-all --split train=TS_001
    """
    from copick.ops.croissant import set_splits
    from copick.util.sync import parse_list

    logger = get_logger(__name__, debug=debug)

    if not split_args and not splits_file and not clear_all and not unassign_arg:
        ctx.fail("Nothing to do — pass at least one of --split / --splits-file / --clear-all / --unassign.")
        return

    try:
        mapping = _merge_splits_inputs(split_args, splits_file)
    except Exception as e:
        ctx.fail(f"Error parsing split inputs: {e}")
        return

    try:
        metadata_path = set_splits(
            croissant_path,
            mapping,
            clear_existing=clear_all,
            unassign=parse_list(unassign_arg) if unassign_arg else None,
        )
    except Exception as e:
        logger.critical(f"Failed to set splits: {e}")
        ctx.fail(f"Error setting splits: {e}")
        return

    logger.info(f"Updated splits in {metadata_path}.")
