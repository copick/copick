"""Format handlers for reading/writing volumes and picks.

This package provides a pluggable handler system for various file formats.
Handlers are automatically registered when their modules are imported.

Usage:
    from copick.ops.handlers import FormatRegistry

    # Get handler by format name or auto-detect from path
    handler = FormatRegistry.get_volume_handler("mrc")
    handler = FormatRegistry.get_volume_handler("/path/to/file.mrc")

    # Read volume
    volume, voxel_size = handler.read("/path/to/file.mrc")

    # List available formats
    formats = FormatRegistry.list_volume_formats()
"""

# isort: off
# Import base types and registry (MUST be first - subpackages depend on these)
from copick.util.handlers.base import (
    FormatCapabilities,
    PicksFormatHandler,
    VolumeFormatHandler,
)
from copick.util.handlers.registry import (
    FormatRegistry,
    get_picks_format_from_path,
    get_volume_format_from_path,
)

# Import sub-packages to trigger handler registration (MUST be after base imports)
from copick.util.handlers import picks  # noqa: F401
from copick.util.handlers import volume  # noqa: F401

# isort: on

__all__ = [
    "FormatRegistry",
    "FormatCapabilities",
    "VolumeFormatHandler",
    "PicksFormatHandler",
    "get_volume_format_from_path",
    "get_picks_format_from_path",
]
