"""What a model backend can do, and the manifest of a result it publishes.

Backends differ: a feature classifier learns from painted classes over precomputed features; a promptable model
segments one object from points, boxes, scribbles or lassos. A client asks for operations by :class:`Requirement`
and enables only what :func:`negotiate` reports available, so no control appears for a capability the backend
lacks.

A model output is published only once complete, with a :class:`ResultManifest`. It is a proposal: it becomes
supervision only when a person accepts it into a new :class:`~copick.contracts.annotation.AnnotationRevision`.
"""

from typing import Any, Dict, List, Literal, Optional, Union

import numpy as np
from pydantic import AwareDatetime, Field, ValidationError, model_validator

from copick.contracts._common import CONTRACT_VERSION, Contract, ContractVersion, Digest, Shape3, label_digest
from copick.contracts.annotation import check_kind
from copick.contracts.identity import Geometry, ReconstructionRef, SegmentationRef
from copick.contracts.labels import InferredLabels, LabelSchema

RESULT_ATTRS_KEY = "copick_result"
"""Zarr attribute under which a published result group records its :class:`ResultManifest`."""

OperationName = Literal["features.extract", "feature_learning.train", "feature_learning.predict", "prompt_segmentation"]
PromptKind = Literal["point", "bbox", "scribble", "lasso", "initial_mask"]
Encoding = Literal["semantic", "instance"]


class ModelInfo(Contract):
    """The model behind a backend. ``public`` models can be used without private code, weights or configuration."""

    name: str = Field(min_length=1)
    public: bool
    license: Optional[str] = None


class OperationCapability(Contract):
    """One operation a backend supports, and how."""

    operation: OperationName
    outputs: List[Encoding] = Field(default_factory=list, description="Label encodings the operation can produce.")
    prompts: List[PromptKind] = Field(default_factory=list, description="Prompt kinds (prompt_segmentation only).")
    negative_prompts: bool = Field(default=False, description="Prompts can mark voxels as not the object.")
    label_policies: List[str] = Field(
        default_factory=list,
        description="InferredLabels policies the operation can apply (feature_learning.train only).",
    )
    region_updates: bool = Field(default=False, description="Results can cover a region rather than the volume.")
    undo: bool = Field(default=False, description="The last interaction can be undone in the backend session.")

    @model_validator(mode="after")
    def _consistent(self) -> "OperationCapability":
        prompted = self.operation == "prompt_segmentation"
        if prompted != bool(self.prompts):
            raise ValueError("prompts are listed exactly for prompt_segmentation")
        if self.negative_prompts and not prompted:
            raise ValueError("negative_prompts applies to prompt_segmentation")
        if self.label_policies and self.operation != "feature_learning.train":
            raise ValueError("label_policies applies to feature_learning.train")
        return self


class BackendCapabilities(Contract):
    """What one backend instance offers, as it reports it to clients."""

    contract_version: ContractVersion = CONTRACT_VERSION
    backend: str = Field(min_length=1, description="Backend name, e.g. cellcanvas or nninteractive.")
    version: str = Field(min_length=1, description="Exact version or source pin of the backend.")
    model: ModelInfo
    operations: List[OperationCapability]

    @model_validator(mode="after")
    def _unique(self) -> "BackendCapabilities":
        names = [o.operation for o in self.operations]
        if len(set(names)) != len(names):
            raise ValueError("each operation is listed once")
        return self

    def get(self, operation: str) -> Optional[OperationCapability]:
        return next((o for o in self.operations if o.operation == operation), None)


class Requirement(Contract):
    """What a client needs from one operation in order to offer a control."""

    operation: OperationName
    outputs: List[Encoding] = Field(default_factory=list, description="Encodings the client can display.")
    prompts: List[PromptKind] = Field(default_factory=list)
    negative_prompts: bool = False
    label_policy: Optional[str] = None
    public_model: bool = Field(default=False, description="Only a public model is acceptable.")


class Offer(Contract):
    """Whether a required operation is available, and if not, why."""

    operation: OperationName
    available: bool
    reasons: List[str] = Field(default_factory=list)


def negotiate(
    capabilities: Union[BackendCapabilities, Dict[str, Any]],
    requirements: List[Requirement],
) -> List[Offer]:
    """Match a backend's reported capabilities to a client's requirements, one :class:`Offer` per requirement.

    A report of another contract version, or one that does not validate, makes every requirement unavailable
    instead of raising, so a client can keep working without that backend.
    """
    if not isinstance(capabilities, BackendCapabilities):
        try:
            capabilities = BackendCapabilities.model_validate(capabilities)
        except ValidationError as error:
            version = capabilities.get("contract_version") if isinstance(capabilities, dict) else None
            reason = (
                f"backend uses contract version {version!r}, this client {CONTRACT_VERSION!r}"
                if version != CONTRACT_VERSION
                else f"invalid capability report: {error.errors()[0]['msg']}"
            )
            return [Offer(operation=r.operation, available=False, reasons=[reason]) for r in requirements]

    offers = []
    for requirement in requirements:
        reasons = []
        offered = capabilities.get(requirement.operation)
        if offered is None:
            reasons.append(f"{capabilities.backend} does not offer {requirement.operation}")
        else:
            if requirement.public_model and not capabilities.model.public:
                reasons.append(f"model {capabilities.model.name} is not public")
            if requirement.outputs and not set(requirement.outputs) & set(offered.outputs):
                reasons.append(f"outputs {offered.outputs} include none of {requirement.outputs}")
            missing = sorted(set(requirement.prompts) - set(offered.prompts))
            if missing:
                reasons.append(f"prompt kinds {missing} are not supported")
            if requirement.negative_prompts and not offered.negative_prompts:
                reasons.append("negative prompts are not supported")
            if requirement.label_policy and requirement.label_policy not in offered.label_policies:
                reasons.append(f"label policy {requirement.label_policy} is not supported")
        offers.append(Offer(operation=requirement.operation, available=not reasons, reasons=reasons))
    return offers


class FeatureGrid(Contract):
    """The grid of a feature volume. ``shape`` is spatial (z, y, x) and must equal the reconstruction grid."""

    shape: Shape3
    axes: List[str] = Field(min_length=4, max_length=4, description="Axis order including the channel axis.")
    resampling: Optional[str] = Field(default=None, description="How the model's native grid was resampled.")


class FeatureProvenance(Contract):
    """Which model computed the features a result was learned from, and how. No local paths."""

    model: str = Field(min_length=1)
    license: str = Field(min_length=1)
    public: bool
    grid: FeatureGrid
    preprocessing: Dict[str, Any] = Field(default_factory=dict)
    checkpoint_sha256: Optional[str] = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @classmethod
    def from_manifest(cls, manifest: Dict[str, Any]) -> "FeatureProvenance":
        """Keep the shareable fields of a feature manifest; local source, checkpoint and code paths are dropped."""
        grid = manifest["grid"]
        return cls(
            model=manifest["model"],
            license=manifest["license"],
            public=manifest["public"],
            grid=FeatureGrid(shape=grid["shape"], axes=grid["axes"], resampling=grid.get("resampling")),
            preprocessing=dict(manifest.get("preprocessing") or {}),
            checkpoint_sha256=(manifest.get("checkpoint") or {}).get("sha256"),
        )


class AnnotationInput(Contract):
    """The exact annotation revision a result was computed from."""

    segmentation: SegmentationRef
    revision: str = Field(min_length=1)
    digest: Digest


class ResultManifest(Contract):
    """A complete, published model output and everything it was computed from.

    A writer stages the output, verifies it against this manifest, and only then makes it visible together with the
    manifest; a failed or interrupted operation publishes nothing and leaves the previous result in place. The output
    never replaces the annotation it was learned from, and it stays a proposal until a person accepts it.
    """

    contract_version: ContractVersion = CONTRACT_VERSION
    operation_id: str = Field(min_length=1, description="Client-chosen ID of the operation that produced it.")
    operation: Literal["feature_learning.predict", "prompt_segmentation"]
    backend: str = Field(min_length=1)
    backend_version: str = Field(min_length=1)
    model: ModelInfo
    reconstruction: ReconstructionRef
    annotation: Optional[AnnotationInput] = None
    inferred: List[InferredLabels] = Field(default_factory=list)
    features: Optional[FeatureProvenance] = None
    output: SegmentationRef
    labels: LabelSchema
    geometry: Geometry
    version: int = Field(ge=0, description="Increases with every publication to the same output.")
    digest: Digest
    status: Literal["complete"] = "complete"
    review: Literal["proposal"] = "proposal"
    created_at: AwareDatetime

    @model_validator(mode="after")
    def _consistent(self) -> "ResultManifest":
        problems = self.geometry.mismatches(self.reconstruction.geometry)
        if problems:
            raise ValueError(f"output grid differs from the reconstruction: {'; '.join(problems)}")
        if self.features is not None and list(self.features.grid.shape) != list(self.geometry.shape):
            raise ValueError("features are not on the reconstruction grid")
        if self.model.public and self.features is not None and not self.features.public:
            raise ValueError("a public model result cannot depend on non-public features")
        if self.annotation is not None and self.annotation.segmentation.same_segmentation(self.output):
            raise ValueError("a result must not overwrite the annotation it was computed from")
        if self.operation == "feature_learning.predict" and (self.annotation is None or self.features is None):
            raise ValueError("a feature-learning prediction records its annotation revision and features")
        for inferred in self.inferred:
            inferred.check_target(self.labels)
        check_kind(self.output, self.labels)
        return self

    def verify(self, array: np.ndarray) -> None:
        """Refuse output voxels that are not exactly this result or that hold undeclared values."""
        if list(array.shape) != list(self.geometry.shape):
            raise ValueError(f"output has shape {list(array.shape)}, expected {list(self.geometry.shape)}")
        if label_digest(array) != self.digest:
            raise ValueError(f"output is not version {self.version} of operation {self.operation_id}")
        self.labels.check_values(array)

    def to_attrs(self) -> Dict[str, Any]:
        return {RESULT_ATTRS_KEY: self.model_dump(mode="json")}
