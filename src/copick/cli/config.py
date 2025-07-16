import json
import os
from typing import List

import click

from copick.cli.util import add_debug_option
from copick.util.log import get_logger


@click.group(short_help="Manage copick configuration files.")
@click.pass_context
def config(ctx):
    """Manage copick configuration files."""
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
    type=str,
    required=True,
    help="Path to the local overlay directory where intermediate files will be stored or read.",
)
@click.option(
    "--output",
    default="config.json",
    type=str,
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


@config.command(context_settings={"show_default": True}, short_help="Set up a configuration file for a local project.")
@click.pass_context
@click.option("--overlay-root", type=str, required=True, help="Overlay root path.")
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
    type=str,
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

        pickable_objects.append(obj_dict)
        label_counter += 1

    config_data = {
        "config_type": "filesystem",
        "name": proj_name,
        "description": proj_description,
        "version": "0.1.6",  # TODO: Update this to the actual version - how to do this automatically?
        "pickable_objects": pickable_objects,
        "overlay_root": "local://" + overlay_root,
        "overlay_fs_args": {"auto_mkdir": True},
    }

    # Only create the directory if it is non-empty (i.e., the file is not in the current directory)
    directory = os.path.dirname(config)
    if directory:
        os.makedirs(directory, exist_ok=True)
    # Write the JSON data to the file
    with open(config, "w") as f:
        json.dump(config_data, f, indent=4)

    logger.info(f"Generated configuration file at {config}.")
