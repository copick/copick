import json
import os
import warnings
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from copick import __version__
from copick.util.log import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from copick.impl.cryoet_data_portal import CopickRootCDP
    from copick.impl.embrella import CopickRootEmbrella, EmbrellaSessionSpec
    from copick.impl.filesystem import CopickRootFSSpec
    from copick.impl.mlcroissant import CopickRootMLC
    from copick.models import PickableObject


def from_string(data: str) -> Union["CopickRootFSSpec", "CopickRootCDP", "CopickRootMLC", "CopickRootEmbrella"]:
    """Create a Copick project from a JSON string.

    Args:
        data (str): JSON string containing the project configuration.

    Returns:
        CopickRootFSSpec, CopickRootCDP, CopickRootMLC, or CopickRootEmbrella: The initialized Copick project.
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
    elif data["config_type"] == "mlcroissant":
        from copick.impl.mlcroissant import CopickConfigMLCroissant, CopickRootMLC

        return CopickRootMLC(CopickConfigMLCroissant(**data))
    elif data["config_type"] == "embrella":
        from copick.impl.embrella import CopickConfigEmbrella, CopickRootEmbrella

        return CopickRootEmbrella(CopickConfigEmbrella(**data))
    else:
        raise ValueError(
            f"Unknown config_type: {data['config_type']}. Supported types are 'filesystem', "
            f"'cryoet_data_portal', 'mlcroissant', and 'embrella'.",
        )


def from_file(path: str) -> Union["CopickRootFSSpec", "CopickRootCDP", "CopickRootMLC", "CopickRootEmbrella"]:
    """Create a Copick project from a JSON file.
    Args:
        path (str): Path to the JSON file containing the project configuration.

    Returns:
        CopickRootFSSpec, CopickRootCDP, CopickRootMLC, or CopickRootEmbrella: The initialized Copick project.
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


def from_embrella(
    embrella_base_url: str,
    sessions: List[Union[Dict[str, Any], "EmbrellaSessionSpec"]],
    overlay_mode: str = "local",
    overlay_fs_args: Optional[Dict[str, Any]] = None,
    static_mode: str = "http",
    static_fs_args: Optional[Dict[str, Any]] = None,
    overlay_root: Optional[str] = None,
    overlay_root_fs_args: Optional[Dict[str, Any]] = None,
    clusters: Optional[Dict[str, Any]] = None,
    default_data_cluster: Optional[str] = None,
    scope: Optional[str] = None,
    pickable_objects: Optional[List["PickableObject"]] = None,
    objects_from_overlay: bool = True,
    proj_name: str = "Embrella project",
    proj_description: Optional[str] = None,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    output_path: Optional[str] = None,
) -> "CopickRootEmbrella":
    """Create a Copick project combining tomograms from Embrella sessions.

    Args:
        embrella_base_url: Base URL of the Embrella server.
        sessions: Session specs (dicts or EmbrellaSessionSpec): each names an Embrella
            session, the tomogram versions (proc_run + recon_type) to expose and
            optionally the overlay project to use.
        overlay_mode: Overlay access mode: "local", "ssh" or "http" (read-only).
        overlay_fs_args: Filesystem arguments for overlay access (e.g. sshfs host).
        static_mode: Static tomogram access mode: "http" or "local".
        static_fs_args: Filesystem arguments for static access.
        overlay_root: Optional project-level overlay URL for object templates.
        overlay_root_fs_args: Filesystem arguments for the project-level overlay.
        clusters: Optional override of the cluster file server locations.
        default_data_cluster: Cluster holding the tomogram zarrs (default "czii").
        scope: The "{scope}.processing" path segment (default "krios1").
        pickable_objects: Pickable objects for the project. When omitted and
            objects_from_overlay is True, objects are collected from the sessions'
            overlay project configs.
        objects_from_overlay: Whether to seed pickable objects from the overlay
            projects when none are given.
        proj_name: Name of the project.
        proj_description: Description of the project.
        user_id: The user ID to use for the project.
        session_id: The session ID to use for the project.
        output_path: The path to write the project configuration to.

    Returns:
        CopickRootEmbrella: The initialized Copick project.
    """
    from copick.impl.embrella import CopickConfigEmbrella, CopickRootEmbrella

    config_kwargs: Dict[str, Any] = {
        "name": proj_name,
        "description": proj_description
        or f"This copick project combines tomograms from Embrella sessions "
        f"{[s['name'] if isinstance(s, dict) else s.name for s in sessions]}.",
        "config_type": "embrella",
        "version": __version__,
        "pickable_objects": pickable_objects or [],
        "embrella_base_url": embrella_base_url,
        "sessions": sessions,
        "overlay_mode": overlay_mode,
        "overlay_fs_args": overlay_fs_args or {},
        "static_mode": static_mode,
        "static_fs_args": static_fs_args or {},
        "overlay_root": overlay_root,
        "overlay_root_fs_args": overlay_root_fs_args or {},
        "user_id": user_id,
        "session_id": session_id,
    }
    if clusters is not None:
        config_kwargs["clusters"] = clusters
    if default_data_cluster is not None:
        config_kwargs["default_data_cluster"] = default_data_cluster
    if scope is not None:
        config_kwargs["scope"] = scope

    config = CopickConfigEmbrella(**config_kwargs)
    root = CopickRootEmbrella(config)

    if not config.pickable_objects and objects_from_overlay:
        config.pickable_objects = root.overlay_pickable_objects()
        root._objects = None

    if output_path:
        dump = config.model_dump(exclude_unset=False, exclude={"runs", "voxel_spacings", "tomograms"})
        with open(output_path, "w") as f:
            f.write(json.dumps(dump, indent=4))

    return root


def from_croissant(
    croissant_url: str,
    overlay_root: Optional[str] = None,
    croissant_base_url: Optional[str] = None,
    overlay_fs_args: Optional[Dict[str, Any]] = None,
    croissant_fs_args: Optional[Dict[str, Any]] = None,
    static_fs_args: Optional[Dict[str, Any]] = None,
    output_path: Optional[str] = None,
) -> "CopickRootMLC":
    """Create a Copick project from an mlcroissant manifest.

    Args:
        croissant_url: URL or path to the Croissant ``metadata.json``.
        overlay_root: Optional writable overlay (Mode B). When omitted, the
            backend writes to the Croissant's ``copick:baseUrl`` (Mode A).
        croissant_base_url: Optional override for ``copick:baseUrl`` (for
            moved / mirrored datasets).
        overlay_fs_args: Extra fsspec kwargs for the overlay filesystem.
        croissant_fs_args: Extra fsspec kwargs for fetching the Croissant.
        static_fs_args: Extra fsspec kwargs for resolving data URLs against
            the Croissant's ``base_url`` (e.g. SSH ``host``/``port``). Kept
            out of the shared Croissant manifest itself — supply them here
            in the local config.
        output_path: If set, write the generated copick config JSON to this
            path so that subsequent loads can use :func:`from_file`.

    Returns:
        CopickRootMLC: The initialized copick project.
    """
    from copick.impl.mlcroissant import CopickConfigMLCroissant, CopickRootMLC

    config = CopickConfigMLCroissant(
        config_type="mlcroissant",
        pickable_objects=[],  # filled in from copick:config on load
        croissant_url=croissant_url,
        croissant_base_url=croissant_base_url,
        overlay_root=overlay_root,
        overlay_fs_args=overlay_fs_args or {},
        croissant_fs_args=croissant_fs_args or {},
        static_fs_args=static_fs_args or {},
    )

    root = CopickRootMLC(config)

    if output_path:
        with open(output_path, "w") as f:
            f.write(json.dumps(root.config.model_dump(exclude_unset=False), indent=4))

    return root


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
