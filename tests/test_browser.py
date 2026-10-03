"""Tests for the copick browser's dispatch from tree node tags to markdown renderers."""

import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

pytest.importorskip("termios")  # the browser module imports termios, which Windows lacks

import copick.ops.browser as browser  # noqa: E402
from copick.ops._markdown import ENTITY_TO_MD  # noqa: E402

# Tag the browser sets on a node -> key of the renderer it should use.
RENDERED_TAGS = {
    "root": "root",
    "object": "object",
    "run": "run",
    "voxel": "voxel_spacing",
    "tomogram": "tomogram",
    "feature": "features",
    "segmentation": "segmentation",
    "mesh": "mesh",
    "picks": "picks",
}
FOLDER_TAGS = ["objects_parent", "segmentation_parent", "picks_parent", "mesh_parent", "voxel_parent"]


def _highlight(tag, monkeypatch):
    renderers = {key: Mock(return_value=f"md:{key}") for key in ENTITY_TO_MD}
    monkeypatch.setattr(browser, "ENTITY_TO_MD", renderers)
    app = browser.CopickTreeApp(Mock())
    app.markdown = Mock()
    entity = object()
    app.on_tree_node_highlighted(SimpleNamespace(node=SimpleNamespace(data=(tag, entity))))
    return renderers, app.markdown, entity


@pytest.mark.parametrize("tag,key", sorted(RENDERED_TAGS.items()))
def test_highlight_uses_the_renderer_for_its_tag(tag, key, monkeypatch):
    renderers, markdown, entity = _highlight(tag, monkeypatch)
    renderers[key].assert_called_once_with(entity)
    markdown.update.assert_called_once_with(f"md:{key}")


@pytest.mark.parametrize("tag", FOLDER_TAGS)
def test_highlight_clears_markdown_for_folders(tag, monkeypatch):
    _, markdown, _ = _highlight(tag, monkeypatch)
    markdown.update.assert_called_once_with("")


def test_every_tag_the_browser_sets_is_covered():
    """Guard the tables above: a new node tag must be added to one of them."""
    source = Path(browser.__file__).read_text()
    tags = set(re.findall(r'data = \("([a-z_]+)",', source)) | set(re.findall(r'data=\("([a-z_]+)",', source))
    assert tags, "found no node tags in the browser source"
    assert tags <= set(RENDERED_TAGS) | set(FOLDER_TAGS)
