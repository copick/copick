"""Picks format handlers.

This package provides handlers for reading/writing particle picks in various formats.
All handlers are automatically registered with the FormatRegistry on import.
"""

from copick.util.handlers import FormatRegistry, csv_handler, dynamo_handler, em_picks_handler
from copick.util.handlers.picks.star import star_handler

# Register all picks handlers
FormatRegistry.register_picks_handler(star_handler)
FormatRegistry.register_picks_handler(em_picks_handler)
FormatRegistry.register_picks_handler(dynamo_handler)
FormatRegistry.register_picks_handler(csv_handler)

__all__ = [
    "star_handler",
    "em_picks_handler",
    "dynamo_handler",
    "csv_handler",
]
