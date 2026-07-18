"""CLI tests for `copick cache info` / `copick cache clear`.

These never contact the CryoET Data Portal: the commands operate purely on the config file and
the on-disk cache. The cache is seeded directly through ``portal_cache`` (with a stub fetch), so
no portal client is ever constructed.
"""

import json

import fsspec
import pytest
from click.testing import CliRunner
from copick.cli.cache import cache
from copick.util import portal_cache


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch, tmp_path):
    for var in (
        "COPICK_PORTAL_CACHE",
        "COPICK_PORTAL_CACHE_TTL",
        "COPICK_PORTAL_CACHE_DIR",
        "COPICK_PORTAL_CACHE_LOCK_TIMEOUT",
        "COPICK_CONFIG",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))


@pytest.fixture
def runner():
    return CliRunner()


def _cdp_config(tmp_path):
    overlay = tmp_path / "overlay"
    overlay.mkdir()
    data = {
        "config_type": "cryoet_data_portal",
        "name": "test",
        "description": "test",
        "overlay_root": str(overlay),
        "overlay_fs_args": {"auto_mkdir": True},
        "dataset_ids": [10000],
        "pickable_objects": [
            {"name": "ribosome", "is_particle": True, "label": 1, "identifier": "GO:0000001"},
            {"name": "membrane", "is_particle": False, "label": 2, "identifier": "GO:0000002"},
        ],
    }
    path = tmp_path / "cdp_config.json"
    path.write_text(json.dumps(data))
    return path, overlay


def _fs_config(tmp_path):
    data = {
        "config_type": "filesystem",
        "name": "test",
        "overlay_root": str(tmp_path / "ov"),
        "pickable_objects": [{"name": "ribosome", "is_particle": True, "label": 1}],
    }
    path = tmp_path / "fs_config.json"
    path.write_text(json.dumps(data))
    return path


def _seed_cache(config_path):
    """Write a valid cache file for the config, without touching the portal."""
    from copick.impl.cryoet_data_portal import CopickConfigCDP

    cfg = CopickConfigCDP(**json.loads(config_path.read_text()))
    fs, root = portal_cache.build_overlay_fs(cfg)
    portal_cache.get_or_fetch(
        fingerprint=portal_cache.fingerprint_for_config(cfg),
        dataset_ids=cfg.dataset_ids,
        settings=portal_cache.settings_from_config(cfg),
        fetch_fn=lambda: {k: [] for k in portal_cache.DATA_KEYS},
        fs_overlay=fs,
        root_overlay=root,
    )
    fp = portal_cache.fingerprint_for_config(cfg)
    return f"{root}/.copick_cache/portal_{fp}.json"


def test_info_missing(runner, tmp_path):
    config_path, _ = _cdp_config(tmp_path)
    result = runner.invoke(cache, ["info", "-c", str(config_path)])
    assert result.exit_code == 0, result.output


def test_info_and_clear_cycle(runner, tmp_path):
    config_path, _ = _cdp_config(tmp_path)
    cache_path = _seed_cache(config_path)

    fs = fsspec.filesystem("file")
    assert fs.exists(cache_path)

    # info succeeds while the cache exists
    assert runner.invoke(cache, ["info", "-c", str(config_path)]).exit_code == 0

    # clear removes the cache file
    result = runner.invoke(cache, ["clear", "-c", str(config_path), "-y"])
    assert result.exit_code == 0, result.output
    assert not fs.exists(cache_path)

    # clearing again is a no-op that still succeeds
    assert runner.invoke(cache, ["clear", "-c", str(config_path), "-y"]).exit_code == 0


def test_clear_all(runner, tmp_path):
    config_path, overlay = _cdp_config(tmp_path)
    _seed_cache(config_path)

    fs = fsspec.filesystem("file")
    cache_dir = f"{overlay}/.copick_cache"
    assert len(fs.glob(f"{cache_dir}/portal_*.json")) == 1

    result = runner.invoke(cache, ["clear", "-c", str(config_path), "--all", "-y"])
    assert result.exit_code == 0, result.output
    assert fs.glob(f"{cache_dir}/portal_*.json") == []


def test_clear_non_cdp_is_noop(runner, tmp_path):
    config_path = _fs_config(tmp_path)
    result = runner.invoke(cache, ["clear", "-c", str(config_path), "-y"])
    assert result.exit_code == 0, result.output


def test_missing_config_errors(runner):
    result = runner.invoke(cache, ["info"])
    assert result.exit_code != 0
