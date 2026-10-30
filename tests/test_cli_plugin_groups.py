"""Every entry-point-fed command group in ``PLUGIN_GROUPS`` is wired into the CLI.

``PLUGIN_GROUPS`` (ext.py), the click groups and ``add_plugin_commands`` (cli.py) and ``COMMAND_CATEGORIES`` must be kept
in sync by hand; these tests catch a group that is listed in one place but not another.
"""

import click
import pytest
from click.testing import CliRunner
from copick.cli import cli as cli_module
from copick.cli.ext import PLUGIN_GROUPS

PLUGIN_SUBGROUPS = [group for group in PLUGIN_GROUPS if group != "main"]


def _click_group(name: str) -> click.Group:
    groups = [
        obj
        for obj in vars(cli_module).values()
        if isinstance(obj, click.Group) and obj.name == name and obj is not cli_module._cli
    ]
    assert len(groups) == 1, f"expected one click group named {name!r} in copick.cli.cli, found {len(groups)}"
    return groups[0]


@click.command("fake", short_help="A fake plugin command.")
def _fake():
    """A fake plugin command."""
    click.echo("fake ran")


@pytest.fixture
def plugin_in(monkeypatch):
    """Register the fake command in a single plugin group and restore the group afterwards."""
    restored = []

    def register(group: str) -> None:
        def load(entry_point: str = "main"):
            return [(_fake, "fake-plugin")] if entry_point == group else []

        monkeypatch.setattr(cli_module, "load_plugin_commands", load)
        click_group = _click_group(group)
        restored.append((click_group, dict(click_group.commands)))

    yield register

    for click_group, commands in restored:
        click_group.commands.clear()
        click_group.commands.update(commands)


@pytest.mark.parametrize("group", PLUGIN_SUBGROUPS)
def test_plugin_group_has_click_group(group):
    assert _click_group(group).name == group


@pytest.mark.parametrize("group", PLUGIN_SUBGROUPS)
def test_plugin_group_has_category(group):
    categorized = [name for names in cli_module.COMMAND_CATEGORIES.values() for name in names]
    assert group in categorized


@pytest.mark.parametrize("group", PLUGIN_SUBGROUPS)
def test_plugin_group_is_populated_from_entry_points(group, plugin_in):
    plugin_in(group)
    root = cli_module.add_plugin_commands(click.Group("copick"))

    assert list(root.commands) == [group]
    assert "fake" in root.commands[group].commands


def test_match_plugin_command_runs(plugin_in):
    plugin_in("match")
    root = cli_module.add_plugin_commands(click.Group("copick"))

    result = CliRunner().invoke(root, ["match", "fake", "--help"])
    assert result.exit_code == 0, result.output
    assert "A fake plugin command." in result.output

    result = CliRunner().invoke(root, ["match", "fake"])
    assert result.exit_code == 0, result.output
    assert "fake ran" in result.output


def test_group_without_plugins_is_hidden(monkeypatch):
    monkeypatch.setattr(cli_module, "load_plugin_commands", lambda entry_point="main": [])
    root = cli_module.add_plugin_commands(click.Group("copick"))

    assert root.commands == {}
