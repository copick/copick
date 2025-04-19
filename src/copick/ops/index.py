import atexit
import logging
import os
import sys
import termios
from typing import Union

from rich.highlighter import ReprHighlighter
from rich.text import Text
from textual.app import App, ComposeResult
from textual.logging import TextualHandler
from textual.widgets import Footer, Header, Tree
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
}


def copick_to_label(entity: _copick_types, include_metadata: bool = True) -> Text:
    highlighter = ReprHighlighter()

    if isinstance(entity, CopickRoot):
        label = Text.assemble(Text(ICONS["root"]), Text.from_markup("[b]Copick Project[/b]"))
    elif isinstance(entity, CopickRun):
        label = Text.assemble(Text(ICONS["run"]), Text.from_markup(f" [b]Run[/b] {entity.name}:"))
    elif isinstance(entity, CopickVoxelSpacing):
        label = Text.assemble(Text(ICONS["voxel_spacing"]), Text.from_markup(" [b]Voxel Spacing[/b]:"))
    elif isinstance(entity, CopickTomogram):
        label = Text.assemble(Text(ICONS["tomogram"]), Text.from_markup(" [b]Tomogram[/b]:"))
    elif isinstance(entity, CopickFeatures):
        label = Text.assemble(Text(ICONS["feature"]), Text.from_markup(" [b]Features[/b]:"))
    elif isinstance(entity, CopickSegmentation):
        label = Text.assemble(Text(ICONS["segmentation"]), Text.from_markup(" [b]Segmentation[/b]:"))
    elif isinstance(entity, CopickMesh):
        label = Text.assemble(Text(ICONS["mesh"]), Text.from_markup(" [b]Mesh[/b]:"))
    elif isinstance(entity, CopickPicks):
        label = Text.assemble(Text(ICONS["pick"]), Text.from_markup(" [b]Picks[/b]:"))
    elif isinstance(entity, CopickObject):
        label = Text.assemble(Text(ICONS["object"]), Text.from_markup(" [b]Object[/b]:"))

    if include_metadata:
        metadata = entity.meta if hasattr(entity, "meta") else None
        if metadata:
            label = Text.assemble(label, highlighter(f" {metadata}"))

    return label


class CopickTreeApp(App):
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
        yield Tree("Copick Project")

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
        tree = self.query_one(Tree)
        tree.root.tree_node_id = "root"
        self.add_objects_node(tree.root)
        self.add_runs_node(tree.root)

    def on_tree_node_expanded(self, event: Tree.NodeExpanded) -> None:
        """Handle the tree node expanded event to load data lazily."""
        node = event.node
        node_id = node.tree_node_id
        if node_id in self.node_data:
            data_type, data = self.node_data[node_id]
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

    def add_runs_node(self, root_node: TreeNode) -> None:
        """Add runs node to the root node."""
        for i, run in enumerate(self.copick_root.runs):
            run_node = root_node.add(copick_to_label(run))
            run_node_id = f"run_{i}"
            run_node.tree_node_id = run_node_id
            self.node_data[run_node_id] = ("run", run)

    def add_objects_node(self, root_node: TreeNode) -> None:
        """Add objects node to the root node."""
        for i, obj in enumerate(self.copick_root.pickable_objects):
            obj_node = root_node.add(copick_to_label(obj))
            obj_node_id = f"object_{i}"
            obj_node.tree_node_id = obj_node_id
            self.node_data[obj_node_id] = ("object", obj)

    def add_run_data_nodes(self, run_node: TreeNode, run) -> None:
        """Add voxel spacings, picks, meshes, and segmentations nodes to the run node."""
        already_present = []
        for child in run_node.children:
            already_present.append(child.label.plain)

        if f"{ICONS['voxel_spacing']} Voxel Spacings" not in already_present:
            voxel_node = run_node.add(f"{ICONS['voxel_spacing']} Voxel Spacings")
            voxel_node_id = f"voxel_{run.meta}"
            voxel_node.tree_node_id = voxel_node_id
            self.node_data[voxel_node_id] = ("voxel_parent", run.voxel_spacings)

        if f"{ICONS['pick']} Picks" not in already_present:
            picks_node = run_node.add(f"{ICONS['pick']} Picks")
            picks_node_id = f"picks_{run.meta}"
            picks_node.tree_node_id = picks_node_id
            self.node_data[picks_node_id] = ("picks", run.picks)

        if f"{ICONS['mesh']} Meshes" not in already_present:
            meshes_node = run_node.add(f"{ICONS['mesh']} Meshes")
            meshes_node_id = f"meshes_{run.meta}"
            meshes_node.tree_node_id = meshes_node_id
            self.node_data[meshes_node_id] = ("meshes", run.meshes)

        if f"{ICONS['segmentation']} Segmentations" not in already_present:
            segmentations_node = run_node.add(f"{ICONS['segmentation']} Segmentations")
            segmentations_node_id = f"segmentation_{run.meta}"
            segmentations_node.tree_node_id = segmentations_node_id
            self.node_data[segmentations_node_id] = ("segmentation", run.segmentations)

    def add_voxel_spacing_parent_nodes(self, voxel_node: TreeNode, voxel_spacings) -> None:
        """Add tomograms node to the voxel spacing node."""
        if len(voxel_spacings) == len(list(voxel_node.children)):
            # Already added
            return

        for i, voxel_spacing in enumerate(voxel_spacings):
            spacing_node = voxel_node.add(label=copick_to_label(voxel_spacing))
            spacing_node_id = f"tomogram_{i}"
            spacing_node.tree_node_id = spacing_node_id
            self.node_data[spacing_node_id] = ("voxel", voxel_spacing.tomograms)

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

        for i, tomogram in enumerate(tomograms):
            tomogram_node = voxel_node.add(label=copick_to_label(tomogram))
            tomogram_node_id = f"tomogram_{i}"
            tomogram_node.tree_node_id = tomogram_node_id
            self.node_data[tomogram_node_id] = ("tomogram", tomogram.features)

    def add_features_data_nodes(self, tomogram_node: TreeNode, features) -> None:
        """Add features node to the tomogram node."""
        if len(features) == len(list(tomogram_node.children)):
            # Already added
            return
        for i, feature in enumerate(features):
            feature_node = tomogram_node.add(label=copick_to_label(feature))
            feature_node_id = f"feature_{i}"
            feature_node.tree_node_id = feature_node_id
            self.node_data[feature_node_id] = ("feature", feature)

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
