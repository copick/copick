"""Utilities for synchronization operations between Copick projects."""

import os
import tempfile
from typing import Dict, List

from copick.models import CopickRoot
from copick.util.log import get_logger


def parse_mapping(mapping_str: str) -> Dict[str, str]:
    """Parse a mapping string like 'run1:target1,run2:target2' into a dictionary.

    Args:
        mapping_str: String containing comma-separated mappings with optional colons.

    Returns:
        Dictionary mapping source names to target names.
    """
    if not mapping_str:
        return {}

    mapping = {}
    for pair in mapping_str.split(","):
        if ":" in pair:
            source, target = pair.split(":", 1)
            mapping[source.strip()] = target.strip()
        else:
            # If no colon, map to itself
            mapping[pair.strip()] = pair.strip()
    return mapping


def parse_list(list_str: str) -> List[str]:
    """Parse a comma-separated string into a list.

    Args:
        list_str: String containing comma-separated values.

    Returns:
        List of trimmed string values.
    """
    if not list_str:
        return []
    return [item.strip() for item in list_str.split(",")]


def parse_dataset_ids(dataset_ids_str: str) -> List[int]:
    """Parse a comma-separated string into a list of dataset IDs.

    Args:
        dataset_ids_str: String containing comma-separated dataset IDs.

    Returns:
        List of integer dataset IDs.
    """
    if not dataset_ids_str:
        return []
    return [int(item.strip()) for item in dataset_ids_str.split(",")]


def create_dataportal_config(dataset_ids: List[int]) -> str:
    """Create a temporary dataportal configuration file.

    Args:
        dataset_ids: List of dataset IDs to include in the configuration.

    Returns:
        str: Path to the temporary configuration file.
    """
    import copick

    # Create a temporary directory for the overlay
    temp_dir = tempfile.mkdtemp(prefix="copick_sync_")
    overlay_root = os.path.join(temp_dir, "overlay")

    # Create a temporary config file
    config_fd, config_path = tempfile.mkstemp(suffix=".json", prefix="copick_sync_config_")
    os.close(config_fd)

    # Create the dataportal configuration
    copick.from_czcdp_datasets(
        dataset_ids=dataset_ids,
        overlay_root=overlay_root,
        overlay_fs_args={"auto_mkdir": True},
        output_path=config_path,
    )

    return config_path


def ensure_pickable_objects(
    source_root: CopickRoot,
    target_root: CopickRoot,
    target_config_path: str,
    source_objects_list: List[str],
    target_objects_dict: Dict[str, str],
    log: bool = False,
) -> None:
    """Ensure that all required pickable objects exist in the target project.

    Creates missing pickable objects in the target project by copying them from
    the source project, respecting the intended target names. Saves the target
    configuration after creating new objects.

    Args:
        source_root: The source Copick project root.
        target_root: The target Copick project root.
        target_config_path: Path to the target configuration file to save.
        source_objects_list: List of source object names to sync.
        target_objects_dict: Dictionary mapping source object names to target names.
        log: Whether to log the object creation process.
    """
    logger = get_logger(__name__)

    # Get all target object names we need to ensure exist
    target_objects_needed = set()
    for source_obj in source_objects_list:
        target_obj = target_objects_dict.get(source_obj, source_obj)
        target_objects_needed.add(target_obj)

    # Check which objects already exist in target
    existing_target_objects = {obj.name for obj in target_root.pickable_objects}

    # Find objects that need to be created
    objects_to_create = target_objects_needed - existing_target_objects

    if not objects_to_create:
        if log:
            logger.info("All required pickable objects already exist in target project.")
        return

    # Create missing objects by copying from source
    objects_created = False
    for source_obj in source_objects_list:
        target_obj = target_objects_dict.get(source_obj, source_obj)

        if target_obj not in objects_to_create:
            continue

        # Find the source object definition
        source_obj_def = source_root.get_object(source_obj)
        if source_obj_def is None:
            logger.warning(f"Source object '{source_obj}' not found in source project - skipping")
            continue

        # Copy the object definition to target, using the target name
        # Find an available label to avoid conflicts
        existing_labels = {obj.label for obj in target_root.pickable_objects}
        target_label = source_obj_def.label
        while target_label in existing_labels:
            target_label += 1

        try:
            target_root.new_object(
                name=target_obj,
                is_particle=source_obj_def.is_particle,
                label=target_label,  # Use a non-conflicting label
                color=source_obj_def.color,
                emdb_id=source_obj_def.emdb_id,
                pdb_id=source_obj_def.pdb_id,
                identifier=source_obj_def.identifier,
                map_threshold=source_obj_def.map_threshold,
                radius=source_obj_def.radius,
                exist_ok=True,
            )

            objects_created = True
            if log:
                logger.info(f"Created pickable object '{target_obj}' in target project (copied from '{source_obj}')")

        except Exception as e:
            logger.error(f"Failed to create pickable object '{target_obj}': {e}")
            raise

    # Save the target configuration if any objects were created
    if objects_created:
        try:
            target_root.save_config(target_config_path)
            if log:
                logger.info(f"Saved target configuration to {target_config_path}")
        except Exception as e:
            logger.error(f"Failed to save target configuration: {e}")
            raise
