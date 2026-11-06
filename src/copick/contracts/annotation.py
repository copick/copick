"""A revision of a human annotation: exact labels, on an exact reconstruction, with their meaning."""

from datetime import datetime
from typing import List, Optional

import numpy as np
from pydantic import AwareDatetime, Field, model_validator

from copick.contracts._common import CONTRACT_VERSION, Contract, ContractVersion, Digest, label_digest
from copick.contracts.identity import ReconstructionRef, SegmentationRef
from copick.contracts.labels import LabelSchema

ANNOTATION_ATTRS_KEY = "copick_annotation"
"""Zarr attribute under which a label group may record its current :class:`AnnotationRevision`."""

_SEMANTIC_KINDS = ("binary", "multilabel")


def check_kind(segmentation: SegmentationRef, labels: LabelSchema) -> None:
    """Refuse a label schema whose encoding the copick segmentation type cannot store."""
    expected = _SEMANTIC_KINDS if labels.encoding == "semantic" else ("instance",)
    if segmentation.kind not in expected:
        raise ValueError(f"a {labels.encoding} schema cannot be stored as a {segmentation.kind} segmentation")
    if segmentation.kind == "binary" and len(labels.classes) != 1:
        raise ValueError("a binary segmentation holds exactly one class")


class AnnotationRevision(Contract):
    """One saved state of a human annotation.

    ``revision`` is opaque and chosen by the writer; ``digest`` identifies the exact voxels, so a reader can tell
    whether the stored labels are still this revision. Value 0 is always unknown. ``accepted_results`` lists the
    operation IDs of model results a person accepted into this revision: a model proposal becomes supervision only
    through such a revision.
    """

    contract_version: ContractVersion = CONTRACT_VERSION
    reconstruction: ReconstructionRef
    segmentation: SegmentationRef
    labels: LabelSchema
    revision: str = Field(min_length=1)
    parent_revision: Optional[str] = None
    digest: Digest
    author: Optional[str] = Field(default=None, description="copick user_id of the person who saved it.")
    created_at: AwareDatetime
    accepted_results: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _consistent(self) -> "AnnotationRevision":
        if self.labels.zero != "unknown":
            raise ValueError("in an annotation, 0 means unknown; paint background as an explicit class")
        if abs(self.segmentation.voxel_size - self.reconstruction.voxel_size) > 1e-3:
            raise ValueError("segmentation and reconstruction voxel sizes differ")
        check_kind(self.segmentation, self.labels)
        return self

    def verify(self, array: np.ndarray) -> None:
        """Refuse labels that are not exactly this revision or that hold undeclared values."""
        if list(array.shape) != list(self.reconstruction.geometry.shape):
            raise ValueError(
                f"labels have shape {list(array.shape)}, the reconstruction grid is "
                f"{list(self.reconstruction.geometry.shape)}",
            )
        if label_digest(array) != self.digest:
            raise ValueError(f"labels are not revision {self.revision}")
        self.labels.check_values(array)

    @classmethod
    def of(
        cls,
        array: np.ndarray,
        *,
        reconstruction: ReconstructionRef,
        segmentation: SegmentationRef,
        labels: LabelSchema,
        revision: str,
        created_at: datetime,
        parent_revision: Optional[str] = None,
        author: Optional[str] = None,
        accepted_results: Optional[List[str]] = None,
    ) -> "AnnotationRevision":
        """Describe ``array`` as a revision, after checking its grid and values."""
        result = cls(
            reconstruction=reconstruction,
            segmentation=segmentation,
            labels=labels,
            revision=revision,
            parent_revision=parent_revision,
            digest=label_digest(array),
            author=author,
            created_at=created_at,
            accepted_results=accepted_results or [],
        )
        result.verify(array)
        return result
