import json
import os
import warnings
from typing import TYPE_CHECKING, Any, Dict, List, Union

from copick import __version__
from copick.util.log import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from copick.impl.cryoet_data_portal import CopickRootCDP
    from copick.impl.filesystem import CopickRootFSSpec
    from copick.models import PickableObject


def from_string(data: str) -> Union["CopickRootFSSpec", "CopickRootCDP"]:
    """Create a Copick project from a JSON string.

    Args:
        data (str): JSON string containing the project configuration.

    Returns:
        CopickRootFSSpec or CopickRootCDP: The initialized Copick project.
    """

    from copick.impl.cryoet_data_portal import CopickConfigCDP, CopickRootCDP
    from copick.impl.filesystem import CopickConfigFSSpec, CopickRootFSSpec

    data = json.loads(data)

    if "config_type" not in data:
        data["config_type"] = "filesystem"
        warnings.warn(
            "config_type not found in config file, defaulting to filesystem",
            DeprecationWarning,
            stacklevel=2,
        )

    if data["config_type"] == "filesystem":
        return CopickRootFSSpec(CopickConfigFSSpec(**data))
    elif data["config_type"] == "cryoet_data_portal":
        return CopickRootCDP(CopickConfigCDP(**data))
    else:
        raise ValueError(
            f"Unknown config_type: {data['config_type']}. Supported types are 'filesystem' and "
            f"'cryoet_data_portal'.",
        )


def from_file(path: str) -> Union["CopickRootFSSpec", "CopickRootCDP"]:
    """Create a Copick project from a JSON file.
    Args:
        path (str): Path to the JSON file containing the project configuration.

    Returns:
        CopickRootFSSpec or CopickRootCDP: The initialized Copick project.
    """

    with open(path, "r") as f:
        data = f.read()

    return from_string(data)


def from_czcdp_datasets(
    dataset_ids: List[int],
    overlay_root: str,
    overlay_fs_args: Union[Dict[str, Any], None] = None,
    user_id: Union[str, None] = None,
    session_id: Union[str, None] = None,
    output_path: Union[str, None] = None,
) -> "CopickRootCDP":
    """Create a Copick project from datasets in the CZ cryoET Data Portal.

    Args:
        dataset_ids: List of dataset IDs to include in the project.
        overlay_root: The root path to the overlay directory.
        overlay_fs_args: Arguments to pass to the overlay filesystem.
        user_id: The user ID to use for the project.
        session_id: The session ID to use for the project.
        output_path: The path to write the project configuration to.

    Returns:
        CopickRootCDP: The initialized Copick project.
    """
    from copick.impl.cryoet_data_portal import CopickConfigCDP, CopickRootCDP
    from copick.util.portal import objects_from_datasets

    objects = objects_from_datasets(dataset_ids)
    config = CopickConfigCDP(
        name="CZ cryoET Data Portal Dataset",
        description=f"This copick project contains data from datasets {dataset_ids}.",
        config_type="cryoet_data_portal",
        version=__version__,
        pickable_objects=objects,
        overlay_root=overlay_root,
        overlay_fs_args=overlay_fs_args if overlay_fs_args else {},
        dataset_ids=dataset_ids,
        user_id=user_id,
        session_id=session_id,
    )

    if output_path:
        with open(output_path, "w") as f:
            f.write(json.dumps(config.model_dump(exclude_unset=True), indent=4))

    return CopickRootCDP(config)


def new_config(
    config: str,
    overlay_root: str,
    proj_name: str = "copick project",
    proj_description: str = "",
    pickable_objects: List["PickableObject"] = None,
) -> "CopickRootFSSpec":
    """
    Create a new Copick configuration file.

    Args:
        config: Path to the configuration file to create.
        proj_name: Name of the project.
        overlay_root: Root path for the overlay directory.
        proj_description: Description of the project.
        pickable_objects: List of pickable objects to include in the project.

    Returns:
        The initialized Copick project.
    """

    import copick

    config_data = {
        "config_type": "filesystem",
        "name": proj_name,
        "description": proj_description,
        "version": f"{copick.__version__}",
        "pickable_objects": [po.model_dump() for po in pickable_objects] if pickable_objects else [],
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

    return copick.from_file(config)
