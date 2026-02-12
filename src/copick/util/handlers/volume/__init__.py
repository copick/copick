"""Volume format handlers.

This package provides handlers for reading/writing volume data in various formats.
All handlers are automatically registered with the FormatRegistry on import.
"""

from copick.util.handlers.registry import FormatRegistry
from copick.util.handlers.volume.em import em_handler
from copick.util.handlers.volume.mrc import mrc_handler
from copick.util.handlers.volume.tiff import tiff_handler
from copick.util.handlers.volume.zarr import zarr_handler

# Register all volume handlers
FormatRegistry.register_volume_handler(mrc_handler)
FormatRegistry.register_volume_handler(zarr_handler)
FormatRegistry.register_volume_handler(tiff_handler)
FormatRegistry.register_volume_handler(em_handler)

__all__ = [
    "mrc_handler",
    "zarr_handler",
    "tiff_handler",
    "em_handler",
]
