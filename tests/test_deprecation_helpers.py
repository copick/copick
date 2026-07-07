"""Tests for the generic deprecation helpers in :mod:`copick.cli.util`.

Covers ``resolve_deprecated_option`` (scalar flag renames) and
``resolve_tomogram_uri`` (rebuilding a tomogram URI from the deprecated
``--tomo-alg``/``--voxel-size`` fallback).
"""

import click
import pytest
from copick.cli.util import resolve_deprecated_option, resolve_tomogram_uri


class _RecordingLogger:
    def __init__(self):
        self.warnings = []

    def warning(self, msg, *args, **kwargs):
        self.warnings.append(msg)


def test_resolve_deprecated_option_prefers_primary_when_no_legacy():
    log = _RecordingLogger()
    assert resolve_deprecated_option("a", None, old_flag="-t", new_flag="-mt", logger=log) == "a"
    assert log.warnings == []


def test_resolve_deprecated_option_uses_legacy_and_warns():
    log = _RecordingLogger()
    assert resolve_deprecated_option("a", "b", old_flag="-t", new_flag="-mt", logger=log) == "b"
    assert any("-t" in w and "deprecated" in w.lower() for w in log.warnings)


def test_resolve_tomogram_uri_prefers_uri():
    log = _RecordingLogger()
    assert resolve_tomogram_uri("wbp@10.0", None, None, logger=log) == "wbp@10.0"
    assert log.warnings == []


def test_resolve_tomogram_uri_rebuilds_from_legacy_and_warns():
    log = _RecordingLogger()
    assert resolve_tomogram_uri(None, "wbp", 10.0, logger=log) == "wbp@10.0"
    assert any("deprecated" in w.lower() for w in log.warnings)


def test_resolve_tomogram_uri_uses_default_vs():
    assert resolve_tomogram_uri(None, "wbp", None, default_vs=10.0) == "wbp@10.0"


def test_resolve_tomogram_uri_errors_without_input():
    with pytest.raises(click.UsageError):
        resolve_tomogram_uri(None, None, None)
