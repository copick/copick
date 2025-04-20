import atexit
import logging
import os
import sys
import termios
from typing import List, Union

from rich.highlighter import ReprHighlighter
from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.logging import TextualHandler
from textual.widgets import Footer, Header, Markdown, Tree
from textual.widgets.tree import TreeNode

import copick
from copick.models import (
    CopickFeatures,
    CopickMesh,
    CopickObject,
    CopickPicks,
    CopickRoot,
    CopickRun,
    CopickSegmentation,
    CopickTomogram,
    CopickVoxelSpacing,
)
from copick.ops._markdown import ENTITY_TO_MD

logging.basicConfig(
    level="DEBUG",
    handlers=[TextualHandler()],
)

_copick_types = Union[
    CopickRoot,
    CopickRun,
    CopickVoxelSpacing,
    CopickTomogram,
    CopickFeatures,
    CopickSegmentation,
    CopickMesh,
    CopickPicks,
    CopickObject,
]


# Emoji icons for different entities
ICONS = {
    "root": "🗂",  # Card Index Dividers
    "run": "🏃",  # Runner
    "voxel_spacing": "📏",  # Ruler
    "tomogram": "🧊",  # Ice Cube
    "feature": "🔢",  # Input Numbers
    "pick": "📍",  # Round Pushpin
    "mesh": "🕸",  # Spider Web
    "segmentation": "🖌",  # Paint Brush
    "object": "🦠",  # Microbe
    "folder": "📁",  # File Folder
}


def copick_to_label(entity: _copick_types, include_metadata: bool = True) -> Text:
    highlighter = ReprHighlighter()

    if isinstance(entity, CopickRoot):
        label = Text.assemble(Text(ICONS["root"]), Text.from_markup("[b]Copick Project[/b]"))
    elif isinstance(entity, CopickRun):
        label = Text.assemble(Text(ICONS["run"]), Text.from_markup(f" [b]Run[/b] {entity.name}:"))
    elif isinstance(entity, CopickVoxelSpacing):
        label = Text.assemble(
            Text(ICONS["voxel_spacing"]),
            Text.from_markup(f" [b]Voxel Spacing[/b] {entity.voxel_size}"),
        )
    elif isinstance(entity, CopickTomogram):
        label = Text.assemble(Text(ICONS["tomogram"]), Text.from_markup(f" [b]Tomogram[/b] {entity.tomo_type}:"))
    elif isinstance(entity, CopickFeatures):
        label = Text.assemble(Text(ICONS["feature"]), Text.from_markup(f" [b]Features[/b] {entity.feature_type}:"))
    elif isinstance(entity, CopickSegmentation):
        label = Text.assemble(Text(ICONS["segmentation"]), Text.from_markup(f" [b]Segmentation[/b] {entity.name}:"))
    elif isinstance(entity, CopickMesh):
        label = Text.assemble(Text(ICONS["mesh"]), Text.from_markup(" [b]Mesh[/b]:"))
    elif isinstance(entity, CopickPicks):
        label = Text.assemble(Text(ICONS["pick"]), Text.from_markup(" [b]Picks[/b]:"))
    elif isinstance(entity, CopickObject):
        label = Text.assemble(Text(ICONS["object"]), Text.from_markup(f" [b]Object[/b] {entity.name}"))

    if include_metadata:
        metadata = entity.meta if hasattr(entity, "meta") else None
        if metadata:
            label = Text.assemble(label, highlighter(f" {metadata}"))

    return label


class CopickTreeApp(App):
    DEFAULT_CSS = """
       Tree {
           width: 2fr; /* 75% of the space */
       }
       Markdown {
           width: 1fr; /* 25% of the space */
       }
       """

    BINDINGS = [
        ("a", "add", "Add node"),
        ("c", "clear", "Clear"),
        ("t", "toggle_root", "Toggle root"),
    ]

    def __init__(self, copick_root):
        super().__init__()
        self.copick_root = copick_root
        self.node_data = {}  # Dictionary to store node data

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()
        with Horizontal():
            yield Tree("Copick Project")
            yield Markdown()

    @classmethod
    def add_json(cls, node: TreeNode, json_data: object) -> None:
        """Adds JSON data to a node."""

        highlighter = ReprHighlighter()

        def add_node(name: str, node: TreeNode, data: object) -> None:
            """Adds a node to the tree."""
            if isinstance(data, dict):
                node.set_label(Text(f"{{}} {name}"))
                for key, value in data.items():
                    new_node = node.add("")
                    add_node(key, new_node, value)
            elif isinstance(data, list):
                node.set_label(Text(f"[] {name}"))
                for index, value in enumerate(data):
                    new_node = node.add("")
                    add_node(str(index), new_node, value)
            else:
                node.allow_expand = False
                if name:
                    label = Text.assemble(
                        Text.from_markup(f"[b]{name}[/b]="),
                        highlighter(repr(data)),
                    )
                else:
                    label = Text(repr(data))
                node.set_label(label)

        add_node("JSON", node, json_data)

    def on_mount(self) -> None:
        """Initialize the tree with the root node."""
        # Initialize the Tree
        tree = self.query_one(Tree)
        tree.root.data = ("root", self.copick_root)
        self.add_object_folder_node(tree.root, self.copick_root.pickable_objects)
        self.add_runs_node(tree.root)

        # Initialize the DataTable
        # datatable = self.query_one(DataTable)
        # datatable.add_columns("Column 1", "Column 2", "Column 3")  # Example columns
        # datatable.add_row("Row 1, Col 1", "Row 1, Col 2", "Row 1, Col 3")  # Example row
        self.markdown = self.query_one(Markdown)
        self.markdown.update(ENTITY_TO_MD["root"](self.copick_root))

    def on_tree_node_expanded(self, event: Tree.NodeExpanded) -> None:
        """Handle the tree node expanded event to load data lazily."""
        node = event.node
        data_type, data = node.data

        if data_type == "run":
            self.add_run_data_nodes(node, data)
        elif data_type == "voxel_parent":
            self.add_voxel_spacing_parent_nodes(node, data)
        elif data_type == "voxel":
            self.add_tomogram_data_nodes(node, data)
        elif data_type == "tomogram":
            self.add_features_data_nodes(node, data)
        elif data_type == "segmentation":
            self.add_segmentation_data_nodes(node, data)
        elif data_type == "objects_parent":
            self.add_object_data_node(node, data)

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        """Handle the tree node selected event to display data."""
        node = event.node
        data_type, data = node.data

        if data_type == "root":
            self.markdown.update(ENTITY_TO_MD["root"](data))
        elif data_type == "run":
            self.markdown.update(ENTITY_TO_MD["run"](data))
        elif data_type == "voxel_parent":
            self.markdown.update("ENTITY_TO_MD['voxel_parent'](node.data)")
        elif data_type == "voxel":
            self.markdown.update(ENTITY_TO_MD["voxelspacing"](data))
        elif data_type == "tomogram":
            self.markdown.update(ENTITY_TO_MD["tomogram"](data))
        elif data_type == "segmentation":
            self.markdown.update(ENTITY_TO_MD["segmentation"](data))
        elif data_type == "objects_parent":
            self.markdown.update("ENTITY_TO_MD['objects_parent'](node.data)")

    def add_object_folder_node(self, root_node: TreeNode, objects: List[CopickObject]) -> None:
        """Add voxel spacings, picks, meshes, and segmentations nodes to the run node."""
        already_present = []
        for child in root_node.children:
            already_present.append(child.label.plain)

        if f"{ICONS['folder']} Objects" not in already_present:
            objects_node = root_node.add(f"{ICONS['folder']} Objects")
            objects_node.data = ("objects_parent", objects)

    def add_object_data_node(self, objects_node: TreeNode, objects) -> None:
        """Add objects node to the objects folder node."""
        if len(objects) == len(list(objects_node.children)):
            # Already added
            return

        for _i, obj in enumerate(objects):
            obj_node = objects_node.add_leaf(copick_to_label(obj))
            obj_node.data = ("object", obj)

    def add_runs_node(self, root_node: TreeNode) -> None:
        """Add runs node to the root node."""
        for _i, run in enumerate(self.copick_root.runs):
            run_node = root_node.add(copick_to_label(run))
            run_node.data = ("run", run)

    def add_run_data_nodes(self, run_node: TreeNode, run) -> None:
        """Add voxel spacings, picks, meshes, and segmentations nodes to the run node."""
        already_present = []
        for child in run_node.children:
            already_present.append(child.label.plain)

        if f"{ICONS['voxel_spacing']} Voxel Spacings" not in already_present:
            voxel_node = run_node.add(f"{ICONS['voxel_spacing']} Voxel Spacings")
            voxel_node.data = ("voxel_parent", run.voxel_spacings)
            # self.node_data[voxel_node_id] = ("voxel_parent", run.voxel_spacings)

        if f"{ICONS['pick']} Picks" not in already_present:
            picks_node = run_node.add(f"{ICONS['pick']} Picks")
            picks_node.data = ("picks", run.picks)
            # self.node_data[picks_node_id] = ("picks", run.picks)

        if f"{ICONS['mesh']} Meshes" not in already_present:
            meshes_node = run_node.add(f"{ICONS['mesh']} Meshes")
            meshes_node.data = ("meshes", run.meshes)
            # self.node_data[meshes_node_id] = ("meshes", run.meshes)

        if f"{ICONS['segmentation']} Segmentations" not in already_present:
            segmentations_node = run_node.add(f"{ICONS['segmentation']} Segmentations")
            segmentations_node.data = ("segmentation", run.segmentations)
            # self.node_data[segmentations_node_id] = ("segmentation", run.segmentations)

    def add_voxel_spacing_parent_nodes(self, voxel_node: TreeNode, voxel_spacings: List[CopickVoxelSpacing]) -> None:
        """Add tomograms node to the voxel spacing node."""
        if len(voxel_spacings) == len(list(voxel_node.children)):
            # Already added
            return
        else:
            voxel_node.remove_children()

        for _i, voxel_spacing in enumerate(voxel_spacings):
            spacing_node = voxel_node.add(label=copick_to_label(voxel_spacing))
            spacing_node.data = ("voxel", voxel_spacing.tomograms)

    # def add_voxel_spacing_data_nodes(self, voxel_node: TreeNode, tomograms) -> None:
    #     """Add tomograms node to the voxel spacing node."""
    #     for i, voxel_spacing in enumerate(tomograms):
    #         tomogram_node = voxel_node.add(f"Voxel Spacing: {voxel_spacing.meta}")
    #         tomogram_node_id = f"tomogram_{i}"
    #         tomogram_node.tree_node_id = tomogram_node_id
    #         self.node_data[tomogram_node_id] = ("voxel", tomograms.features)

    def add_tomogram_data_nodes(self, voxel_node: TreeNode, tomograms) -> None:
        """Add tomogram node to the voxel parent node."""
        if len(tomograms) == len(list(voxel_node.children)):
            # Already added
            return
        else:
            voxel_node.remove_children()

        for _i, tomogram in enumerate(tomograms):
            tomogram_node = voxel_node.add(label=copick_to_label(tomogram))
            tomogram_node.data = ("tomogram", tomogram.features)

    def add_features_data_nodes(self, tomogram_node: TreeNode, features) -> None:
        """Add features node to the tomogram node."""
        if len(features) == len(list(tomogram_node.children)):
            # Already added
            return
        else:
            tomogram_node.remove_children()

        for _i, feature in enumerate(features):
            feature_node = tomogram_node.add(label=copick_to_label(feature))
            feature_node.data = ("feature", feature)

    def add_segmentation_data_nodes(self, segmentation_node: TreeNode, segmentations) -> None:
        """Add segmentation details to the segmentation node."""
        for _i, segmentation in enumerate(segmentations):
            try:
                color = segmentation.color
            except AttributeError:
                color = [128, 128, 128, 0] if segmentation.is_multilabel else None

            segmentation_data = {
                "meta": segmentation.meta,
                "zarr": segmentation.zarr,
                "from_tool": segmentation.from_tool,
                "from_user": segmentation.from_user,
                "user_id": segmentation.user_id,
                "session_id": segmentation.session_id,
                "is_multilabel": segmentation.is_multilabel,
                "voxel_size": segmentation.voxel_size,
                "name": segmentation.name,
                "color": color,
            }
            self.add_json(segmentation_node, segmentation_data)


if __name__ == "__main__":
    copick_root = copick.from_czcdp_datasets([10440], "/tmp/overlay")

    def reset_terminal():
        if os.name == "posix":
            sys.stdout.write("\x1b[?1003l\x1b[?1006l\x1b[?1015l")
            sys.stdout.flush()
            fd = sys.stdin.fileno()
            termios.tcsetattr(fd, termios.TCSADRAIN, termios.tcgetattr(fd))

    atexit.register(reset_terminal)

    logging.basicConfig(level=logging.ERROR)

    # Silence all other loggers except for errors
    for logger_name in logging.root.manager.loggerDict:
        logging.getLogger(logger_name).setLevel(logging.ERROR)

    CopickTreeApp(copick_root).run()
