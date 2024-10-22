from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from copick.models import CopickConfig, CopickRoot


class CopickLayerConfig(BaseModel):
    readonly: Optional[bool] = True


class FSSpecLayerConfig(CopickLayerConfig):
    """Base class for fsspec-based Copick storage layer.

    Attributes:
        url (str): The URL to the storage location.
        fs_args (Dict[str, Any]): Additional arguments to pass to the fsspec filesystem.
        readonly (bool): Whether the layer is read-only.
    """

    url: str
    fs_args: Optional[Dict[str, Any]] = {}
    readonly: Optional[bool] = False


class CDPLayerConfig(CopickLayerConfig):
    """Base class for cryoET data portal layer.

    Attributes:

    """

    dataset_ids: List[str]


class CacheLayerConfig(CopickLayerConfig):
    """Base class for Copick storage layer.

    Attributes:

    """

    url: str
    fs_args: Optional[Dict[str, Any]] = {}
    readonly: Optional[bool] = False


class SQLiteLayerConfig(CopickLayerConfig):
    """Base class for sqlite-based Copick storage layer.

    Attributes:

    """

    path: str
    readonly: Optional[bool] = False


class CopickConfigML(CopickConfig):
    """Copick configuration for fsspec-based storage.

    Attributes:
        layers: List[FSSpecLayer]
    """

    config_type: str = "multilayer"
    layers: Dict[str, CopickLayerConfig]


class CopickRootML(CopickRoot):
    """CopickRoot class backed by multiple storage layers."""

    pass
    # def __init__(self, config: CopickConfigML):
    #     super().__init__(config)
    #
    #     self.layers = {}
    #
    #     for name, layer in config.layers.items():
    #         if isinstance(layer, FSSpecLayer):
    #             self.layers[name] = CopickRootFSSpec(layer)
    #         elif isinstance(layer, SQLiteLayer):
    #             self.layers[name] = CopickRootSQLite(layer)
    #         elif isinstance(layer, CDPLayer):
    #             self.layers[name] = CopickRootCDP(layer)
    #         elif isinstance(layer, CacheLayer):
    #             self.layers[name] = CopickRootCache(layer)
    #         else:
    #             raise ValueError(f"Unsupported layer type: {layer}")
    #
    # @classmethod
    # def from_file(cls, path: str) -> "CopickRootML":
    #     """Initialize a CopickRootML from a configuration file on disk.
    #
    #     Args:
    #         path: Path to the configuration file on disk.
    #
    #     Returns:
    #         CopickRootFSSpec: The initialized CopickRootFSSpec object.
    #     """
    #     with open(path, "r") as f:
    #         data = json.load(f)
    #
    #     return cls(CopickConfigML(**data))
