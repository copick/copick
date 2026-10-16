"""Helpers for tests that run on the mlcroissant backend."""

import pytest


def croissant_mode_a(root) -> bool:
    """Whether ``root`` is a self-contained (Mode A) Croissant project, which cannot hold filaments."""
    return getattr(root, "mode", None) == "A"


def skip_without_filaments(root) -> None:
    """Skip a test that writes Filaments on a backend that cannot hold them (a Mode A Croissant project)."""
    if croissant_mode_a(root):
        pytest.skip("Mode A Croissant projects cannot hold filaments")
