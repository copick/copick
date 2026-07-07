"""Tests for the shared run-selection option (``--run-names``/``-r``).

Covers the helpers added in :mod:`copick.cli.util` (``add_run_names_option``,
``add_deprecated_run_alias``, ``resolve_run_names``) and their wiring on the real
``stats`` and ``export`` commands, including the hidden deprecated ``--runs``
alias and legacy comma-separated back-compat.
"""

import click
import pytest
from click.testing import CliRunner
from copick.cli.util import (
    add_deprecated_run_alias,
    add_run_names_option,
    resolve_run_names,
)


class _RecordingLogger:
    """Minimal logger stub that records ``warning`` calls."""

    def __init__(self):
        self.warnings = []

    def warning(self, msg, *args, **kwargs):
        self.warnings.append(msg)


# --------------------------------------------------------------------------- #
# resolve_run_names unit tests
# --------------------------------------------------------------------------- #
def test_resolve_empty_returns_none():
    assert resolve_run_names((), ()) is None
    assert resolve_run_names(()) is None


def test_resolve_repeatable_values():
    assert resolve_run_names(("TS_001", "TS_002")) == ["TS_001", "TS_002"]


def test_resolve_splits_legacy_comma_values_and_warns():
    logger = _RecordingLogger()
    assert resolve_run_names(("a,b", "c"), logger=logger) == ["a", "b", "c"]
    assert any("comma" in w.lower() for w in logger.warnings)


def test_resolve_merges_legacy_alias_and_warns():
    logger = _RecordingLogger()
    result = resolve_run_names((), ("x", "y"), legacy_flag="--runs", logger=logger)
    assert result == ["x", "y"]
    assert any("--runs" in w and "deprecated" in w.lower() for w in logger.warnings)


def test_resolve_combines_new_and_legacy():
    assert resolve_run_names(("a",), ("b,c",)) == ["a", "b", "c"]


def test_resolve_clean_input_does_not_warn():
    logger = _RecordingLogger()
    resolve_run_names(("a", "b"), logger=logger)
    assert logger.warnings == []


# --------------------------------------------------------------------------- #
# Decorator wiring on a throwaway command
# --------------------------------------------------------------------------- #
@click.command()
@add_run_names_option
@add_deprecated_run_alias("--runs")
def _dummy(run_names, legacy_run_names):
    resolved = resolve_run_names(run_names, legacy_run_names, legacy_flag="--runs")
    click.echo(repr(resolved))


@pytest.fixture
def runner():
    return CliRunner()


def test_help_shows_standard_option_hides_alias(runner):
    out = runner.invoke(_dummy, ["--help"]).output
    assert "--run-names" in out
    assert "-r" in out
    assert "--runs" not in out  # deprecated alias is hidden


def test_short_and_long_flags_repeatable(runner):
    assert runner.invoke(_dummy, ["-r", "a", "-r", "b"]).output.strip() == "['a', 'b']"
    assert runner.invoke(_dummy, ["--run-names", "a", "--run-names", "b"]).output.strip() == "['a', 'b']"


def test_deprecated_alias_still_works(runner):
    assert runner.invoke(_dummy, ["--runs", "a", "--runs", "b"]).output.strip() == "['a', 'b']"


def test_legacy_comma_values_split(runner):
    assert runner.invoke(_dummy, ["--run-names", "a,b,c"]).output.strip() == "['a', 'b', 'c']"


# --------------------------------------------------------------------------- #
# Real commands expose the standardized option
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("import_path", "subcommand"),
    [
        ("copick.cli.stats:stats", "picks"),
        ("copick.cli.stats:stats", "meshes"),
        ("copick.cli.stats:stats", "segmentations"),
        ("copick.cli.export:export", "picks"),
        ("copick.cli.export:export", "tomogram"),
        ("copick.cli.export:export", "segmentation"),
    ],
)
def test_real_commands_use_standard_option(runner, import_path, subcommand):
    import importlib

    module_name, group_name = import_path.split(":")
    group = getattr(importlib.import_module(module_name), group_name)
    out = runner.invoke(group, [subcommand, "--help"]).output
    assert "--run-names" in out
    assert "-r" in out


def test_stats_hides_deprecated_runs_alias(runner):
    from copick.cli.stats import stats

    out = runner.invoke(stats, ["picks", "--help"]).output
    assert "--runs" not in out  # replaced by --run-names, alias hidden
