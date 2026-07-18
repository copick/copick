"""Offline unit tests for the portal disk cache (copick.util.portal_cache).

These never contact the CryoET Data Portal: ``fetch_fn`` is a stub that returns canned data
and counts its own invocations, so we can assert the cache is read/written correctly and that
the portal is queried at most once.
"""

import json
import threading

import fsspec
import pytest
from copick.util import portal_cache


class FakeObject:
    def __init__(self, identifier):
        self.identifier = identifier


class FakeConfig:
    """Minimal stand-in for CopickConfigCDP with the attributes the cache reads."""

    config_type = "cryoet_data_portal"

    def __init__(
        self,
        overlay_root,
        dataset_ids=(10000,),
        identifiers=("GO:0000001", "GO:0000002"),
        enabled=True,
        ttl=86400,
        cache_dir=None,
        lock_timeout=30,
    ):
        self.overlay_root = overlay_root
        self.overlay_fs_args = {"auto_mkdir": True}
        self.dataset_ids = list(dataset_ids)
        self.pickable_objects = [FakeObject(i) for i in identifiers]
        self.portal_cache = enabled
        self.portal_cache_ttl_seconds = ttl
        self.portal_cache_dir = cache_dir
        self.portal_cache_lock_timeout_seconds = lock_timeout


def _sample_data():
    data = {k: [] for k in portal_cache.DATA_KEYS}
    data["runs"] = [{"id": 1, "name": "TS_1", "dataset_id": 10000}]
    data["voxel_spacings"] = [{"id": 11, "run_id": 1, "voxel_spacing": 10.0}]
    return data


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch, tmp_path):
    """Keep cache env overrides unset and redirect the XDG fallback into the temp dir."""
    for var in (
        "COPICK_PORTAL_CACHE",
        "COPICK_PORTAL_CACHE_TTL",
        "COPICK_PORTAL_CACHE_DIR",
        "COPICK_PORTAL_CACHE_LOCK_TIMEOUT",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))


@pytest.fixture
def overlay(tmp_path):
    root = str(tmp_path / "overlay")
    fs = fsspec.filesystem("file", auto_mkdir=True)
    fs.makedirs(root, exist_ok=True)
    return fs, root


class CountingFetch:
    def __init__(self, data=None):
        self.calls = 0
        self._data = data if data is not None else _sample_data()

    def __call__(self):
        self.calls += 1
        return self._data


# ---------------------------------------------------------------------------
# Fingerprint
# ---------------------------------------------------------------------------


def test_fingerprint_stable_and_sensitive():
    fp1 = portal_cache.compute_fingerprint([10000, 10001], ["GO:1", "GO:2"])
    fp2 = portal_cache.compute_fingerprint([10001, 10000], ["GO:2", "GO:1"])  # order-insensitive
    assert fp1 == fp2
    assert fp1 != portal_cache.compute_fingerprint([10000], ["GO:1", "GO:2"])
    assert fp1 != portal_cache.compute_fingerprint([10000, 10001], ["GO:1"])


def test_fingerprint_for_config_matches_manual():
    cfg = FakeConfig("mem://x", dataset_ids=[10000], identifiers=["GO:2", "GO:1"])
    assert portal_cache.fingerprint_for_config(cfg) == portal_cache.compute_fingerprint([10000], ["GO:1", "GO:2"])


# ---------------------------------------------------------------------------
# get_or_fetch: read/write, warm hit, force, disable
# ---------------------------------------------------------------------------


def _call(cfg, overlay, fetch, force=False):
    fs, root = overlay
    return portal_cache.get_or_fetch(
        fingerprint=portal_cache.fingerprint_for_config(cfg),
        dataset_ids=cfg.dataset_ids,
        settings=portal_cache.settings_from_config(cfg),
        fetch_fn=fetch,
        fs_overlay=fs,
        root_overlay=root,
        force=force,
    )


def test_cold_then_warm(overlay):
    cfg = FakeConfig(overlay[1])
    fetch = CountingFetch()

    first = _call(cfg, overlay, fetch)
    assert first == fetch._data
    assert fetch.calls == 1

    # Warm: a second construction reads the disk cache and does not query.
    second = _call(cfg, overlay, fetch)
    assert second == fetch._data
    assert fetch.calls == 1


def test_force_refetches(overlay):
    cfg = FakeConfig(overlay[1])
    fetch = CountingFetch()
    _call(cfg, overlay, fetch)
    _call(cfg, overlay, fetch, force=True)
    assert fetch.calls == 2


def test_disabled_passthrough(overlay):
    cfg = FakeConfig(overlay[1], enabled=False)
    fetch = CountingFetch()
    _call(cfg, overlay, fetch)
    _call(cfg, overlay, fetch)
    assert fetch.calls == 2  # no cache read or write when disabled

    # And nothing was written to the overlay cache dir.
    fs, root = overlay
    assert not fs.exists(f"{root}/.copick_cache")


def test_ttl_expiry(overlay):
    cfg = FakeConfig(overlay[1], ttl=1)
    fetch = CountingFetch()
    _call(cfg, overlay, fetch)

    # Rewrite the cache document with an old timestamp so it is considered stale.
    fs, root = overlay
    fp = portal_cache.fingerprint_for_config(cfg)
    path = f"{root}/.copick_cache/portal_{fp}.json"
    with fs.open(path, "r") as f:
        doc = json.load(f)
    doc["created"] = "2000-01-01T00:00:00+00:00"
    with fs.open(path, "w") as f:
        json.dump(doc, f)

    _call(cfg, overlay, fetch)
    assert fetch.calls == 2  # stale entry forced a refetch


def test_corrupt_file_is_miss(overlay):
    cfg = FakeConfig(overlay[1])
    fetch = CountingFetch()
    _call(cfg, overlay, fetch)

    fs, root = overlay
    fp = portal_cache.fingerprint_for_config(cfg)
    path = f"{root}/.copick_cache/portal_{fp}.json"
    with fs.open(path, "w") as f:
        f.write("{ this is not valid json ]")

    result = _call(cfg, overlay, fetch)
    assert result == fetch._data
    assert fetch.calls == 2  # corrupt cache treated as a miss and overwritten


def test_fingerprint_change_is_miss(overlay):
    fetch = CountingFetch()
    _call(FakeConfig(overlay[1], identifiers=["GO:1"]), overlay, fetch)
    # Different object set -> different fingerprint -> different file -> refetch.
    _call(FakeConfig(overlay[1], identifiers=["GO:1", "GO:2"]), overlay, fetch)
    assert fetch.calls == 2


def test_date_field_round_trips(overlay):
    import datetime

    cfg = FakeConfig(overlay[1])
    data = _sample_data()
    data["tomograms"] = [{"id": 5, "tomogram_voxel_spacing_id": 11, "release_date": datetime.date(2020, 1, 1)}]
    fetch = CountingFetch(data)

    _call(cfg, overlay, fetch)  # store must not raise on the date field (default=str)
    loaded = _call(cfg, overlay, fetch)
    assert fetch.calls == 1
    assert loaded["tomograms"][0]["release_date"] == "2020-01-01"  # coerced to string on disk


# ---------------------------------------------------------------------------
# Concurrency: the lock + double-check collapses the herd to a single fetch
# ---------------------------------------------------------------------------


def test_concurrent_cold_start_fetches_once(overlay):
    cfg = FakeConfig(overlay[1])

    lock = threading.Lock()
    calls = {"n": 0}

    def fetch():
        with lock:
            calls["n"] += 1
        import time

        time.sleep(0.05)  # widen the window so threads genuinely contend
        return _sample_data()

    barrier = threading.Barrier(6)
    results = []

    def worker():
        barrier.wait()
        results.append(_call(cfg, overlay, fetch))

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert calls["n"] == 1  # exactly one thread queried; the rest read the published cache
    assert all(r == _sample_data() for r in results)


# ---------------------------------------------------------------------------
# status_for_config / clear
# ---------------------------------------------------------------------------


def test_status_reports_fresh_then_missing(overlay):
    fs, root = overlay
    cfg = FakeConfig(root)
    fetch = CountingFetch()

    before = portal_cache.status_for_config(cfg, fs_overlay=fs, root_overlay=root)
    assert all(not s.exists for s in before)

    _call(cfg, overlay, fetch)
    after = portal_cache.status_for_config(cfg, fs_overlay=fs, root_overlay=root)
    assert after[0].exists and after[0].fresh


def test_clear_removes_current_fingerprint(overlay):
    fs, root = overlay
    cfg = FakeConfig(root)
    fetch = CountingFetch()
    _call(cfg, overlay, fetch)

    fp = portal_cache.fingerprint_for_config(cfg)
    path = f"{root}/.copick_cache/portal_{fp}.json"
    assert fs.exists(path)

    removed = portal_cache.clear(cfg, fs_overlay=fs, root_overlay=root)
    assert path in removed
    assert not fs.exists(path)


def test_clear_all_removes_every_portal_file(overlay):
    fs, root = overlay
    # Two different object sets -> two different cache files under the same overlay.
    cfg_a = FakeConfig(root, identifiers=["GO:1"])
    cfg_b = FakeConfig(root, identifiers=["GO:1", "GO:2"])
    _call(cfg_a, overlay, CountingFetch())
    _call(cfg_b, overlay, CountingFetch())

    cache_dir = f"{root}/.copick_cache"
    assert len(fs.glob(f"{cache_dir}/portal_*.json")) == 2

    removed = portal_cache.clear(cfg_a, remove_all=True, fs_overlay=fs, root_overlay=root)
    assert len(removed) == 2
    assert fs.glob(f"{cache_dir}/portal_*.json") == []
