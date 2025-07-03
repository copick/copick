from typing import List

import cryoet_data_portal as cdp
import distinctipy

from copick.models import PickableObject
from copick.util.escape import sanitize_name
from copick.util.log import get_logger

logger = get_logger(__name__)


def objects_from_datasets(dataset_ids: List[int]) -> List[PickableObject]:
    """
    Create copick objects from datasets.

    Args:
        dataset_ids: List of dataset IDs to include in the project.

    Returns:
        List[PickableObject]: The list of pickable objects.
    """
    client = cdp.Client()
    annotations = cdp.Annotation.find(client, [cdp.Annotation.run.dataset.id._in(dataset_ids)])
    annotation_shapes = cdp.AnnotationShape.find(
        client,
        [cdp.AnnotationShape.annotation.id._in([anno.id for anno in annotations])],
    )
    anno_id_to_shape = {}

    for shape in annotation_shapes:
        shapelist = anno_id_to_shape.get(shape.annotation_id, [])
        shapelist.append(shape.shape_type.lower())
        anno_id_to_shape[shape.annotation_id] = shapelist

    portal_objects = {}
    for anno in annotations:
        shapes = anno_id_to_shape[anno.id]

        # Should be considered point?
        is_particle = bool("point" in shapes or "orientedpoint" in shapes)

        # Has an EMD ID?
        emd_id = None
        apubs = []
        if anno.annotation_publication is not None:
            apubs = anno.annotation_publication.split(",")
            apubs = [ap.strip() for ap in apubs]
            emds = [pub for pub in apubs if pub.startswith("EMD")]
            emd_id = emds[0] if emds else None

        # Has a PDB id?
        pdb_id = None
        if apubs:
            pdb_ids = [pub for pub in apubs if pub.startswith("PDB")]
            pdb_id = pdb_ids[0] if pdb_ids else None

        # Overwrite all values but is_particle if the object is already in the dict
        po = portal_objects.get(anno.object_id, None)
        if po:
            is_particle = is_particle or po["is_particle"]

        portal_objects[anno.object_id] = {
            "name": sanitize_name(anno.object_name, suppress_warnings=True).lower(),
            "is_particle": is_particle,
            "emdb_id": emd_id,
            "pdb_id": pdb_id,
        }

    # An attempt to ensure reproducible labels and colors
    # We sort the objects by the hash of their ID
    portal_objects = dict(sorted(portal_objects.items(), key=lambda x: hash(x[0])))
    colors = distinctipy.get_colors(len(portal_objects), rng=42)

    copick_objects = []
    # TODO: zip(_,_,strict=True) when 3.9 support is dropped
    for idx, ((identifier, vals), col) in enumerate(zip(portal_objects.items(), colors)):
        col = tuple([int(c * 255) for c in col] + [255])
        copick_objects.append(
            PickableObject(
                name=vals["name"],
                is_particle=vals["is_particle"],
                label=idx + 1,
                color=col,
                emdb_id=vals["emdb_id"],
                pdb_id=vals["pdb_id"],
                identifier=identifier,
                map_threshold=None,
                radius=50,
            ),
        )

    return copick_objects
