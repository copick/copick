from typing import List

import click

from copick.cli.util import add_debug_option
from copick.util.log import get_logger


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
    type=click.Path(file_okay=False, dir_okay=True),
    required=False,
    help="Optional writable overlay (Mode B). If omitted, the Croissant's copick:baseUrl is used as the write location (Mode A).",
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

    try:
        copick.from_croissant(
            croissant_url=croissant_url,
            overlay_root=overlay,
            croissant_base_url=base_url,
            overlay_fs_args={"auto_mkdir": True} if overlay else None,
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
    required=True,
    help="Path to the input copick configuration file.",
)
@click.option(
    "--project-root",
    type=click.Path(file_okay=False, dir_okay=True),
    required=True,
    help="Copick project root directory; Croissant/ is written under this.",
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
@add_debug_option
@click.pass_context
def export_croissant_cmd(
    ctx,
    config_path: str,
    project_root: str,
    base_url: str,
    dataset_name: str,
    description: str,
    license_: str,
    cite_as: str,
    date_published: str,
    no_file_sha256: bool,
    debug: bool = False,
):
    """
    Export a copick project to a Croissant manifest + CSV sidecars under
    <project-root>/Croissant/.
    """
    import copick
    from copick.ops.croissant import export_croissant

    logger = get_logger(__name__, debug=debug)
    logger.info("Loading copick project...")

    try:
        root = copick.from_file(config_path)
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
        )
    except Exception as e:
        logger.critical(f"Failed to export Croissant: {e}")
        ctx.fail(f"Error exporting Croissant: {e}")
        return

    logger.info(f"Wrote Croissant at {metadata_path}.")
