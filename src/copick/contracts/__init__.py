"""Shared contracts between copick and the tools that annotate it, learn from it, or publish results into it.

The documents defined here identify a reconstruction and its voxel grid, a revision of a human annotation and the
meaning of its label values, what a model backend can do, and the manifest of a published model result. They are
plain data (pydantic models with JSON Schemas in ``copick/data/contracts``) and carry no model, server or GPU
dependencies, so viewers, annotation tools, training services and campaign managers can share them.
"""

from copick.contracts._common import CONTRACT_VERSION, indices_digest, label_digest
from copick.contracts.annotation import ANNOTATION_ATTRS_KEY, AnnotationRevision
from copick.contracts.identity import Geometry, ReconstructionRef, SegmentationRef
from copick.contracts.labels import UNKNOWN, InferredLabels, InstanceClass, LabelClass, LabelSchema
from copick.contracts.operations import (
    RESULT_ATTRS_KEY,
    AnnotationInput,
    BackendCapabilities,
    FeatureGrid,
    FeatureProvenance,
    ModelInfo,
    Offer,
    OperationCapability,
    Requirement,
    ResultManifest,
    negotiate,
)

__all__ = [
    "ANNOTATION_ATTRS_KEY",
    "CONTRACT_VERSION",
    "RESULT_ATTRS_KEY",
    "UNKNOWN",
    "AnnotationInput",
    "AnnotationRevision",
    "BackendCapabilities",
    "FeatureGrid",
    "FeatureProvenance",
    "Geometry",
    "InferredLabels",
    "InstanceClass",
    "LabelClass",
    "LabelSchema",
    "ModelInfo",
    "Offer",
    "OperationCapability",
    "ReconstructionRef",
    "Requirement",
    "ResultManifest",
    "SegmentationRef",
    "indices_digest",
    "label_digest",
    "negotiate",
]
