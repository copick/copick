"""Import smoke tests for implementation modules under supported Zarr 3 versions."""

import importlib
import pkgutil

import pytest


def _implementation_modules():
    modules = ["copick.models"]
    for package_name in ("copick.impl", "copick.ops", "copick.util"):
        package = importlib.import_module(package_name)
        modules.extend(module.name for module in pkgutil.walk_packages(package.__path__, f"{package_name}."))
    return sorted(modules)


@pytest.mark.parametrize("module_name", _implementation_modules())
def test_implementation_module_imports_with_zarr_3(module_name):
    assert importlib.import_module(module_name) is not None
