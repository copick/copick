"""Format handler registry.

This module provides a central registry for format handlers, enabling
automatic format detection and handler lookup by format name or file extension.
"""

import os
from typing import Dict, List, Optional

from copick.util.handlers import PicksFormatHandler, VolumeFormatHandler


class FormatRegistry:
    """Central registry for format handlers.

    Handlers register themselves with the registry, enabling:
    - Lookup by format name (e.g., "mrc", "star")
    - Lookup by file extension (e.g., ".mrc", ".star")
    - Auto-detection from file paths
    """

    _volume_handlers: Dict[str, VolumeFormatHandler] = {}
    _picks_handlers: Dict[str, PicksFormatHandler] = {}
    _volume_extension_map: Dict[str, str] = {}
    _picks_extension_map: Dict[str, str] = {}

    @classmethod
    def register_volume_handler(cls, handler: VolumeFormatHandler) -> None:
        """Register a volume format handler.

        Args:
            handler: Handler instance implementing VolumeFormatHandler protocol
        """
        cls._volume_handlers[handler.format_name] = handler
        for ext in handler.extensions:
            cls._volume_extension_map[ext.lower()] = handler.format_name

    @classmethod
    def register_picks_handler(cls, handler: PicksFormatHandler) -> None:
        """Register a picks format handler.

        Args:
            handler: Handler instance implementing PicksFormatHandler protocol
        """
        cls._picks_handlers[handler.format_name] = handler
        for ext in handler.extensions:
            cls._picks_extension_map[ext.lower()] = handler.format_name

    @classmethod
    def get_volume_handler(
        cls,
        format_or_path: str,
    ) -> Optional[VolumeFormatHandler]:
        """Get a volume handler by format name or auto-detect from file path.

        Args:
            format_or_path: Either a format name (e.g., "mrc") or a file path

        Returns:
            VolumeFormatHandler or None if no handler found
        """
        # Try direct format name lookup first
        format_name = format_or_path.lower()
        if format_name in cls._volume_handlers:
            return cls._volume_handlers[format_name]

        # Try to detect from file extension
        ext = os.path.splitext(format_or_path)[1].lower()
        if ext in cls._volume_extension_map:
            return cls._volume_handlers[cls._volume_extension_map[ext]]

        # Check for zarr (directory-based)
        if (format_or_path.endswith(".zarr") or format_or_path.endswith(".zarr/")) and "zarr" in cls._volume_handlers:
            return cls._volume_handlers["zarr"]

        return None

    @classmethod
    def get_picks_handler(
        cls,
        format_or_path: str,
    ) -> Optional[PicksFormatHandler]:
        """Get a picks handler by format name or auto-detect from file path.

        Args:
            format_or_path: Either a format name (e.g., "star") or a file path

        Returns:
            PicksFormatHandler or None if no handler found
        """
        # Try direct format name lookup first
        format_name = format_or_path.lower()
        if format_name in cls._picks_handlers:
            return cls._picks_handlers[format_name]

        # Try to detect from file extension
        ext = os.path.splitext(format_or_path)[1].lower()
        if ext in cls._picks_extension_map:
            return cls._picks_handlers[cls._picks_extension_map[ext]]

        return None

    @classmethod
    def list_volume_formats(cls) -> List[str]:
        """List all registered volume format names."""
        return list(cls._volume_handlers.keys())

    @classmethod
    def list_picks_formats(cls) -> List[str]:
        """List all registered picks format names."""
        return list(cls._picks_handlers.keys())

    @classmethod
    def get_volume_handler_for_extension(cls, extension: str) -> Optional[VolumeFormatHandler]:
        """Get volume handler for a specific file extension.

        Args:
            extension: File extension (with or without leading dot)

        Returns:
            VolumeFormatHandler or None
        """
        ext = extension.lower()
        if not ext.startswith("."):
            ext = f".{ext}"
        if ext in cls._volume_extension_map:
            return cls._volume_handlers[cls._volume_extension_map[ext]]
        return None

    @classmethod
    def get_picks_handler_for_extension(cls, extension: str) -> Optional[PicksFormatHandler]:
        """Get picks handler for a specific file extension.

        Args:
            extension: File extension (with or without leading dot)

        Returns:
            PicksFormatHandler or None
        """
        ext = extension.lower()
        if not ext.startswith("."):
            ext = f".{ext}"
        if ext in cls._picks_extension_map:
            return cls._picks_handlers[cls._picks_extension_map[ext]]
        return None


def get_volume_format_from_path(path: str) -> Optional[str]:
    """Determine volume format from file path.

    Args:
        path: File path to analyze

    Returns:
        Format name or None if unknown
    """
    handler = FormatRegistry.get_volume_handler(path)
    return handler.format_name if handler else None


def get_picks_format_from_path(path: str) -> Optional[str]:
    """Determine picks format from file path.

    Args:
        path: File path to analyze

    Returns:
        Format name or None if unknown
    """
    handler = FormatRegistry.get_picks_handler(path)
    return handler.format_name if handler else None
