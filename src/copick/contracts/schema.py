"""JSON Schemas of the contract documents, for readers that are not written in Python.

The schemas shipped in ``copick/data/contracts/v<version>`` are generated from these models::

    python -m copick.contracts.schema            # rewrite the shipped schemas
    python -m copick.contracts.schema --check    # exit 1 if they are out of date

JSON Schema expresses field types and value ranges. Rules relating several fields (for example "an inferred label
targets the background class") are enforced by the Python models; the fixtures in ``fixtures/index.json`` record
which rules a pure JSON Schema validator can and cannot detect.
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict

from copick.contracts._common import CONTRACT_VERSION
from copick.contracts.annotation import AnnotationRevision
from copick.contracts.identity import Geometry, ReconstructionRef, SegmentationRef
from copick.contracts.labels import InferredLabels, LabelSchema
from copick.contracts.operations import BackendCapabilities, FeatureProvenance, Offer, Requirement, ResultManifest

DOCUMENTS = {
    "geometry": Geometry,
    "reconstruction": ReconstructionRef,
    "segmentation": SegmentationRef,
    "label-schema": LabelSchema,
    "inferred-labels": InferredLabels,
    "annotation-revision": AnnotationRevision,
    "capabilities": BackendCapabilities,
    "requirement": Requirement,
    "offer": Offer,
    "feature-provenance": FeatureProvenance,
    "result-manifest": ResultManifest,
}
"""Document name -> model. A document is stored as ``<name>.schema.json``."""

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "data" / "contracts" / f"v{CONTRACT_VERSION}"


def json_schemas() -> Dict[str, Dict[str, Any]]:
    """The JSON Schema (draft 2020-12) of every document."""
    schemas = {}
    for name, model in DOCUMENTS.items():
        schema = model.model_json_schema()
        schemas[name] = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"copick-contracts/v{CONTRACT_VERSION}/{name}.schema.json",
            **schema,
        }
    return schemas


def _render(schema: Dict[str, Any]) -> str:
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write(directory: Path = SCHEMA_DIR) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name, schema in json_schemas().items():
        (directory / f"{name}.schema.json").write_text(_render(schema))


def stale(directory: Path = SCHEMA_DIR) -> list:
    """Names of shipped schemas that differ from the models."""
    return [
        name
        for name, schema in json_schemas().items()
        if not (directory / f"{name}.schema.json").is_file()
        or (directory / f"{name}.schema.json").read_text() != _render(schema)
    ]


if __name__ == "__main__":
    if "--check" in sys.argv:
        out_of_date = stale()
        print("out of date: " + ", ".join(out_of_date) if out_of_date else "schemas are current")
        sys.exit(1 if out_of_date else 0)
    write()
