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
    """
    Convert a Copick entity to a rich Text label.

    Args:
        entity: The Copick entity to convert.
        include_metadata: Whether to include metadata in the label.

    Returns:
        Text label.
    """
    ReprHighlighter()

    label = Text("")

    if isinstance(entity, CopickRoot):
        label = Text.assemble(Text(ICONS["root"]), Text.from_markup("[b]Copick Project[/b]"))
    elif isinstance(entity, CopickRun):
        label = Text.assemble(Text(ICONS["run"]), Text.from_markup(f" [b]Run[/b] {entity.name}"))
    elif isinstance(entity, CopickVoxelSpacing):
        label = Text.assemble(
            Text(ICONS["voxel_spacing"]),
            Text.from_markup(f" [b]Voxel Spacing[/b] {entity.voxel_size}"),
        )
    elif isinstance(entity, CopickTomogram):
        label = Text.assemble(Text(ICONS["tomogram"]), Text.from_markup(f" [b]Tomogram[/b] {entity.tomo_type}"))
    elif isinstance(entity, CopickFeatures):
        label = Text.assemble(Text(ICONS["feature"]), Text.from_markup(f" [b]Features[/b] {entity.feature_type}"))
    elif isinstance(entity, CopickSegmentation):
        color = entity.color
        colorbox = Text("  ", style=f"on rgb({color[0]},{color[1]},{color[2]})")
        if entity.is_multilabel:
            colorbox = Text("🌈")
        label = Text.assemble(
            Text(ICONS["segmentation"] + " "),
            colorbox,
            Text.from_markup(
                f" [b]Segmentation[/b] {entity.voxel_size:.3f}_{entity.user_id}_{entity.session_id}_{entity.name}",
            ),
        )
    elif isinstance(entity, CopickMesh):
        color = entity.color
        colorbox = Text("  ", style=f"on rgb({color[0]},{color[1]},{color[2]})")
        label = Text.assemble(
            Text(ICONS["mesh"] + " "),
            colorbox,
            Text.from_markup(f" [b]Mesh[/b] {entity.user_id}_{entity.session_id}_{entity.pickable_object_name}"),
        )
    elif isinstance(entity, CopickPicks):
        color = entity.color
        colorbox = Text("  ", style=f"on rgb({color[0]},{color[1]},{color[2]})")
        label = Text.assemble(
            Text(ICONS["pick"] + " "),
            colorbox,
            Text.from_markup(f" [b]Picks[/b] {entity.user_id}_{entity.session_id}_{entity.pickable_object_name}"),
        )
    elif isinstance(entity, CopickObject):
        color = entity.color
        colorbox = Text("  ", style=f"on rgb({color[0]},{color[1]},{color[2]})")
        label = Text.assemble(
            Text(ICONS["object"] + " "),
            colorbox,
            Text.from_markup(f" [b]Object[/b] {entity.name}"),
        )

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
    TITLE = "Copick Browser"
    # TODO: Add key bindings for search and other actions
    # BINDINGS = [
    #     ("^f", "search", "Search Runs"),
    # ]

    def __init__(self, copick_root: CopickRoot):
        """
        Initialize the CopickTreeApp.

        Args:
            copick_root: The CopickRoot object to browse.
        """
        super().__init__()
        self.copick_root = copick_root
        self.node_data = {}  # Dictionary to store node data
        self.markdown = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()
        with Horizontal():
            yield Tree("Copick Project")
            yield Markdown()

    def on_mount(self) -> None:
        """Initialize the tree with the root node."""
        # Initialize the Tree
        tree = self.query_one(Tree)
        tree.root.data = ("root", self.copick_root)
        self.add_object_folder_node(tree.root, self.copick_root.pickable_objects)
        self.add_runs_node(tree.root)

        # Initialize the metadata display
        self.markdown = self.query_one(Markdown)
        self.markdown.update(ENTITY_TO_MD["root"](self.copick_root))

    def on_tree_node_expanded(self, event: Tree.NodeExpanded) -> None:
        """
        Handle the tree node expanded event to load data lazily.

        Args:
            event: The event object containing the node that was expanded.
        """
        node = event.node
        data_type, data = node.data

        if data_type == "run":
            self.add_run_data_nodes(node, data)
        elif data_type == "voxel_parent":
            self.add_voxel_spacing_parent_nodes(node, data.voxel_spacings)
        elif data_type == "voxel":
            self.add_tomogram_data_nodes(node, data.tomograms)
        elif data_type == "tomogram":
            self.add_features_data_nodes(node, data.features)
        elif data_type == "segmentation_parent":
            self.add_segmentation_data_nodes(node, data.segmentations)
        elif data_type == "picks_parent":
            self.add_picks_data_nodes(node, data.picks)
        elif data_type == "mesh_parent":
            self.add_mesh_data_nodes(node, data.meshes)
        elif data_type == "objects_parent":
            self.add_object_data_node(node, data)

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted) -> None:
        """
        Handle the tree node highlighted event to display data.

        Args:
            event: The event object containing the node that was highlighted.
        """
        node = event.node
        data_type, data = node.data

        if data_type == "root":
            self.markdown.update(ENTITY_TO_MD["root"](data))
        elif data_type == "object":
            self.markdown.update(ENTITY_TO_MD["object"](data))
        elif data_type == "run":
            self.markdown.update(ENTITY_TO_MD["run"](data))
        elif data_type == "voxel":
            self.markdown.update(ENTITY_TO_MD["voxel_spacing"](data))
        elif data_type == "tomogram":
            self.markdown.update(ENTITY_TO_MD["tomogram"](data))
        elif data_type == "feature":
            self.markdown.update(ENTITY_TO_MD["feature"](data))
        elif data_type == "segmentation":
            self.markdown.update(ENTITY_TO_MD["segmentation"](data))
        elif data_type == "mesh":
            self.markdown.update(ENTITY_TO_MD["mesh"](data))
        elif data_type == "picks":
            self.markdown.update(ENTITY_TO_MD["picks"](data))
        elif data_type in ["objects_parent", "segmentation_parent", "picks_parent", "mesh_parent", "voxel_parent"]:
            self.markdown.update("")

    def add_object_folder_node(self, root_node: TreeNode, objects: List[CopickObject]) -> None:
        """
        Add parent node for objects to the root node.

        Args:
            root_node: The root node of the tree.
            objects: The list of Copick objects to add.
        """
        already_present = []
        for child in root_node.children:
            already_present.append(child.label.plain)

        if f"{ICONS['folder']} Objects" not in already_present:
            objects_node = root_node.add(f"{ICONS['folder']} Objects")
            objects_node.data = ("objects_parent", objects)

    def add_object_data_node(self, objects_node: TreeNode, objects: List[CopickObject]) -> None:
        """
        Add objects nodes to the objects folder node.

        Args:
            objects_node: The objects node to add the data to.
            objects: The list of Copick objects to add.
        """
        if len(objects) == len(list(objects_node.children)):
            # Already added
            return

        for _i, obj in enumerate(objects):
            obj_node = objects_node.add_leaf(copick_to_label(obj))
            obj_node.data = ("object", obj)

    def add_runs_node(self, root_node: TreeNode) -> None:
        """
        Add runs nodes to the root node.

        Args:
            root_node: The root node of the tree.
        """
        for _i, run in enumerate(self.copick_root.runs):
            run_node = root_node.add(copick_to_label(run))
            run_node.data = ("run", run)

    def add_run_data_nodes(self, run_node: TreeNode, run: CopickRun) -> None:
        """
        Add voxel spacings, picks, meshes, and segmentations nodes to the run node.

        Args:
            run_node: The run node to add the data to.
            run: The CopickRun object to add.
        """
        already_present = []
        for child in run_node.children:
            already_present.append(child.label.plain)

        if f"{ICONS['voxel_spacing']} Voxel Spacings" not in already_present:
            voxel_node = run_node.add(f"{ICONS['voxel_spacing']} Voxel Spacings")
            voxel_node.data = ("voxel_parent", run)

        if f"{ICONS['pick']} Picks" not in already_present:
            picks_node = run_node.add(f"{ICONS['pick']} Picks")
            picks_node.data = ("picks_parent", run)

        if f"{ICONS['mesh']} Meshes" not in already_present:
            meshes_node = run_node.add(f"{ICONS['mesh']} Meshes")
            meshes_node.data = ("mesh_parent", run)

        if f"{ICONS['segmentation']} Segmentations" not in already_present:
            segmentations_node = run_node.add(f"{ICONS['segmentation']} Segmentations")
            segmentations_node.data = ("segmentation_parent", run)

    def add_voxel_spacing_parent_nodes(
        self,
        voxel_parent_node: TreeNode,
        voxel_spacings: List[CopickVoxelSpacing],
    ) -> None:
        """
        Add tomograms nodes to the voxel spacing node.

        Args:
            voxel_parent_node: The voxel parent node to add the data to.
            voxel_spacings: The list of CopickVoxelSpacing objects to add.
        """
        if len(voxel_spacings) == len(list(voxel_parent_node.children)):
            # Already added
            return
        else:
            voxel_parent_node.remove_children()

        for _i, voxel_spacing in enumerate(voxel_spacings):
            spacing_node = voxel_parent_node.add(label=copick_to_label(voxel_spacing))
            spacing_node.data = ("voxel", voxel_spacing)

    def add_tomogram_data_nodes(self, voxel_node: TreeNode, tomograms: List[CopickTomogram]) -> None:
        """
        Add tomogram node to the voxel parent node.

        Args:
            voxel_node: The voxel node to add the tomograms to.
            tomograms: The list of CopickTomogram objects to add.
        """
        if len(tomograms) == len(list(voxel_node.children)):
            return
        else:
            voxel_node.remove_children()

        for tomogram in tomograms:
            tomogram_node = voxel_node.add(label=copick_to_label(tomogram))
            tomogram_node.data = ("tomogram", tomogram)

    def add_features_data_nodes(self, tomogram_node: TreeNode, features: List[CopickFeatures]) -> None:
        """
        Add features node to the tomogram node.

        Args:
            tomogram_node (TreeNode): The tomogram node to add the features to.
            features (list[CopickFeatures]): The list of features to add.
        """
        if len(features) == len(list(tomogram_node.children)):
            return
        else:
            tomogram_node.remove_children()

        for feature in features:
            feature_node = tomogram_node.add_leaf(label=copick_to_label(feature))
            feature_node.data = ("feature", feature)

    def add_segmentation_data_nodes(
        self,
        segmentation_parent_node: TreeNode,
        segmentations: List[CopickSegmentation],
    ) -> None:
        """
        Add segmentations to the segmentation parent node.

        Args:
            segmentation_parent_node (TreeNode): The segmentation parent node to add the segmentations to.
            segmentations (list[CopickSegmentation]): The list of segmentations to add.
        """
        if len(segmentations) == len(list(segmentation_parent_node.children)):
            return
        else:
            segmentation_parent_node.remove_children()

        for segmentation in segmentations:
            segmentation_node = segmentation_parent_node.add_leaf(label=copick_to_label(segmentation))
            segmentation_node.data = ("segmentation", segmentation)

    def add_mesh_data_nodes(
        self,
        mesh_parent_node: TreeNode,
        meshes: List[CopickMesh],
    ) -> None:
        """
        Add meshes to the mesh parent node.

        Args:
            mesh_parent_node (TreeNode): The mesh parent node to add the meshes to.
            meshes (list[CopickMesh]): The list of meshes to add.
        """
        if len(meshes) == len(list(mesh_parent_node.children)):
            return
        else:
            mesh_parent_node.remove_children()

        for mesh in meshes:
            mesh_node = mesh_parent_node.add_leaf(label=copick_to_label(mesh))
            mesh_node.data = ("mesh", mesh)

    def add_picks_data_nodes(
        self,
        picks_parent_node: TreeNode,
        picks: List[CopickPicks],
    ) -> None:
        """
        Add picks to the picks parent node.

        Args:
            picks_parent_node (TreeNode): The picks parent node to add the picks to.
            picks (list[CopickPicks]): The list of picks to add.
        """
        if len(picks) == len(list(picks_parent_node.children)):
            return
        else:
            picks_parent_node.remove_children()

        for pick in picks:
            pick_node = picks_parent_node.add_leaf(label=copick_to_label(pick))
            pick_node.data = ("picks", pick)


def launch_app(
    config_path: str = None,
    dataset_ids: List[int] = None,
    copick_root: CopickRoot = None,
):
    """
    Launch the Copick Tree App.

    Args:
        config_path: Path to the configuration file.
        dataset_ids: List of dataset IDs to include in the project.
    """
    if config_path:
        copick_root = copick.from_file(config_path)
    elif dataset_ids:
        copick_root = copick.from_czcdp_datasets(dataset_ids, "/tmp/overlay")
    elif copick_root:
        pass
    else:
        raise ValueError("Either config_path or dataset_ids must be provided.")

    def reset_terminal():
        if os.name == "posix":
            sys.stdout.write("\x1b[?1003l\x1b[?1006l\x1b[?1015l")
            sys.stdout.flush()
            fd = sys.stdin.fileno()
            termios.tcsetattr(fd, termios.TCSADRAIN, termios.tcgetattr(fd))

    atexit.register(reset_terminal)

    logging.basicConfig(level=logging.ERROR)

    CopickTreeApp(copick_root).run()


if __name__ == "__main__":
    copick_root = copick.from_czcdp_datasets([10440], "/tmp/overlay")

    launch_app(copick_root=copick_root)
