from copick.impl.cryoet_data_portal import (
    CopickPicksCDP,
    CopickRootCDP,
    CopickRunCDP,
    CopickSegmentationCDP,
    CopickTomogramCDP,
)
from copick.impl.filesystem import CopickRootFSSpec, CopickRunFSSpec
from copick.models import (
    CopickFeatures,
    CopickMesh,
    CopickPicks,
    CopickRoot,
    CopickRun,
    CopickSegmentation,
    CopickTomogram,
    CopickVoxelSpacing,
    PickableObject,
)

DEFAULT_MARKDOWN = """\
# Metadata
"""

LOCAL_PROJECT = """\
# Local Copick Project

|
"""


def object_to_md(pickable_object: PickableObject) -> str:
    """Convert the PickableObject object to a markdown string."""
    md = "# PickableObject Metadata\n"
    md += f"## Object: {pickable_object.name}\n"

    if pickable_object.identifier.lower().startswith("go"):
        md += f"* Identifier: [{pickable_object.identifier}](https://amigo.geneontology.org/amigo/term/{pickable_object.identifier})\n"
    elif pickable_object.identifier.lower().startswith("uniprotkb"):
        ident = pickable_object.identifier.split(":")[-1]
        md += f"* Identifier: [{pickable_object.identifier}](https://www.uniprot.org/uniprotkb/{ident})\n"
    else:
        md += f"* Identifier: {pickable_object.identifier}\n"

    if pickable_object.emdb_id:
        md += f"* EMDB ID: [{pickable_object.emdb_id}](https://www.ebi.ac.uk/emdb/{pickable_object.emdb_id})\n"

    if pickable_object.pdb_id:
        md += f"* PDB ID: [{pickable_object.pdb_id}](https://www.rcsb.org/structure/{pickable_object.pdb_id})\n"

    typ = "particle/segmentation" if pickable_object.is_particle else "segmentation"
    md += f"* Type: {typ}\n"

    md += f"* Label: {pickable_object.label}\n"
    col = pickable_object.color
    md += f"* Color: {col} | #{col[0]:02x}{col[1]:02x}{col[2]:02x}{col[3]:02x}\n"
    md += f"* Map Threshold: {pickable_object.map_threshold}\n"
    md += f"* Radius: {pickable_object.radius}\n"

    return md


def root_to_md(root: CopickRoot) -> str:
    """Convert the CopickRoot object to a markdown string."""
    md = "# CopickRoot Metadata\n"

    md += f"## Project Name: {root.config.name}\n"

    if root.config.config_type == "filesystem":
        md += "* Project Type: Filesystem\n"
    elif root.config.config_type == "cryoet_data_portal":
        md += "* Project Type: CryoET Data Portal\n"

    if isinstance(root, CopickRootFSSpec):
        if root.static_is_overlay:
            md += f"* Location: {root.config.overlay_root}\n"
        else:
            md += f"* Static Location: {root.config.static_root}\n"
            md += f"* Overlay Location: {root.config.overlay_root}\n"
    elif isinstance(root, CopickRootCDP):
        md += "* Datasets: "
        for dataset in root.config.dataset_ids:
            md += f"[{dataset}](https://cryoetdataportal.czscience.com/datasets/{dataset}) "
        md += "\n"
        md += f"* Overlay Location: {root.config.overlay_root}\n"

    return md


def run_to_md(run: CopickRun) -> str:
    """Convert the CopickRun object to a markdown string."""
    md = "# CopickRun Metadata\n"
    md += f"## Run: {run.name}\n"

    if isinstance(run, CopickRunFSSpec):
        if run.static_is_overlay:
            md += f"* Location: {run.overlay_path}\n"
        else:
            md += f"* Static Location: {run.static_path}\n"
            md += f"* Overlay Location: {run.overlay_path}\n"
    elif isinstance(run, CopickRunCDP):
        md += f"* [cryoET Data portal: {run.portal_run_id}](https://cryoetdataportal.czscience.com/runs/{run.portal_run_id})\n"
        md += f"* Overlay Location: {run.overlay_path}\n"

    return md


def voxel_spacing_to_md(voxel_spacing: CopickVoxelSpacing) -> str:
    """Convert the CopickVoxelSpacing object to a markdown string."""
    md = "# CopickVoxelSpacing Metadata\n"
    md += f"## Voxel Spacing: {voxel_spacing.voxel_size}\n"

    return md


def tomogram_to_md(tomogram: CopickTomogram) -> str:
    """Convert the tomogram object to a markdown string."""
    md = "# Tomogram Metadata\n"
    md += f"## Tomogram: {tomogram.tomo_type}\n"

    if isinstance(tomogram.voxel_spacing.run, CopickRunCDP) and isinstance(tomogram, CopickTomogramCDP):
        md += f"* cryoET Data portal: [Tomogram {tomogram.meta.portal_tomo_id}](https://cryoetdataportal.czscience.com/runs/{tomogram.voxel_spacing.run.portal_run_id}?table-tab=Tomograms)\n"

    return md


def features_to_md(features: CopickFeatures) -> str:
    """Convert the features object to a markdown string."""
    md = "# Features Metadata\n"
    md += f"## Features: {features.feature_type}\n"

    return md


def segmentation_to_md(segmentation: CopickSegmentation) -> str:
    """Convert the segmentation object to a markdown string."""
    md = "# Segmentation Metadata\n"
    md += f"## Segmentation: {segmentation.voxel_size:.3f}_{segmentation.user_id}_{segmentation.session_id}_{segmentation.name}\n"

    md += f"* Voxel Spacing: {segmentation.voxel_size:.3f}\n"
    md += f"* Name: {segmentation.name}\n"
    md += f"* User/Tool: {segmentation.user_id}\n"
    md += f"* Session: {segmentation.session_id}\n"
    md += f"* is_multilabel: {segmentation.is_multilabel}\n"
    col = segmentation.color
    md += f"* Color: {col} | #{col[0]:02x}{col[1]:02x}{col[2]:02x}{col[3]:02x}\n"

    if isinstance(segmentation.run, CopickRunCDP) and isinstance(segmentation, CopickSegmentationCDP):
        md += f"* cryoET Data portal: [Segmentation {segmentation.meta.portal_annotation_id}](https://cryoetdataportal.czscience.com/runs/{segmentation.run.portal_run_id}?table-tab=Annotations)\n"

    return md


def picks_to_md(picks: CopickPicks) -> str:
    """Convert the picks object to a markdown string."""
    md = "# Picks Metadata\n"
    md += f"## Picks: {picks.user_id}_{picks.session_id}_{picks.pickable_object_name}\n"

    md += f"* Name: {picks.pickable_object_name}\n"
    md += f"* User/Tool: {picks.user_id}\n"
    md += f"* Session: {picks.session_id}\n"
    md += f"* Count: {len(picks.points) if picks.points else 0}\n"
    md += f"* trust_orientation: {picks.trust_orientation}\n"
    col = picks.color
    md += f"* Color: {col} | #{col[0]:02x}{col[1]:02x}{col[2]:02x}{col[3]:02x}\n"

    if isinstance(picks.run, CopickRunCDP) and isinstance(picks, CopickPicksCDP):
        md += f"* cryoET Data portal: [Picks {picks.meta.portal_annotation_id}](https://cryoetdataportal.czscience.com/runs/{picks.run.portal_run_id}?table-tab=Annotations)\n"

    return md


def mesh_to_md(mesh: CopickMesh) -> str:
    """Convert the mesh object to a markdown string."""
    md = "# Mesh Metadata\n"
    md += f"## Mesh: {mesh.user_id}_{mesh.session_id}_{mesh.pickable_object_name}\n"

    md += f"* Name: {mesh.pickable_object_name}\n"
    md += f"* User/Tool: {mesh.user_id}\n"
    md += f"* Session: {mesh.session_id}\n"
    col = mesh.color
    md += f"* Color: {col} | #{col[0]:02x}{col[1]:02x}{col[2]:02x}{col[3]:02x}\n"

    # TODO: Add portal mesh metadata
    # if isinstance(mesh.run, CopickRunCDP) and isinstance(mesh, CopickMeshCDP):
    #     md += f"* cryoET Data portal: [Mesh {mesh.meta.portal_annotation_file_id}](https://cryoetdataportal.czscience.com/runs/{mesh.run.portal_run_id}?table-tab=Annotations)\n"

    return md


ENTITY_TO_MD = {
    "root": root_to_md,
    "object": object_to_md,
    "run": run_to_md,
    "voxel_spacing": voxel_spacing_to_md,
    "tomogram": tomogram_to_md,
    "features": features_to_md,
    "segmentation": segmentation_to_md,
    "picks": picks_to_md,
    "mesh": mesh_to_md,
}
