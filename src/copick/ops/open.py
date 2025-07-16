import json
import warnings
from typing import TYPE_CHECKING, Any, Dict, List, Union

from copick import __version__
from copick.util.log import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from copick.impl.cryoet_data_portal import CopickRootCDP
    from copick.impl.filesystem import CopickRootFSSpec


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
