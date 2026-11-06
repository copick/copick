# Integration Contracts

Annotation clients (copick-web, napari-copick), learning services (CellCanvas), promptable models (nnInteractive)
and campaign tools exchange the same few facts about copick data. `copick.contracts` defines them once, as plain
pydantic models with JSON Schemas, so each tool can check what another wrote without sharing its code. The module has
no model, server or GPU dependencies.

| Document | Answers |
|---|---|
| `ReconstructionRef`, `Geometry` | Which tomogram, and which voxel grid (shape, scale and translation in Å, axes z, y, x)? |
| `SegmentationRef` | Which copick segmentation, and of which type (binary, multilabel, instance, panoptic)? |
| `LabelSchema`, `LabelClass` | What does each stored value mean? |
| `AnnotationRevision` | Which exact labels did a person save, with which meaning, on which reconstruction? |
| `InferredLabels` | Which training rows did a policy derive from unannotated voxels, reproducibly? |
| `BackendCapabilities`, `Requirement`, `negotiate` | Which operations can a backend run, and which controls should a client offer? |
| `FeatureProvenance` | Which model computed the features a result was learned from? |
| `ResultManifest` | Which complete model output was published, from which inputs? |

## Label meanings

- Value **0 in an annotation is unknown**: nobody labelled the voxel. Background is a class a person paints
  (`role="background"`). A model output may instead declare `zero="background"`.
- **Inferred labels** (for example background rows chosen from typical-looking unannotated voxels) are recorded as
  `InferredLabels` beside the annotation, with policy, implementation pin, parameters and a digest of the chosen
  voxels. They are never written into the annotation.
- Object classes state their **structure**: `membrane` (the bilayer), `compartment` (the volume it encloses),
  `particle`, `filament` or `other`. Instance IDs use `encoding="instance"` and copick's instance segmentation type.

## Results are proposals

A service publishes an output only once it is complete, verified against its `ResultManifest`
(`manifest.verify(array)`); a failed operation publishes nothing. The manifest records the annotation revision and
digest, inferred labels and features it was computed from, and refuses an output that would replace that annotation
or lie on another grid. A result stays a proposal until a person accepts it into a new `AnnotationRevision`
(`accepted_results`).

## Capability negotiation

```python
from copick.contracts import Requirement, negotiate

offers = negotiate(
    backend_report,  # BackendCapabilities or the JSON a backend returned
    [Requirement(operation="prompt_segmentation", prompts=["point"], negative_prompts=True)],
)
enabled = {o.operation for o in offers if o.available}
```

An unavailable offer lists its reasons. A report of another contract version disables every operation instead of
raising.

## Non-Python readers

JSON Schemas (draft 2020-12) and fixtures ship in `copick/data/contracts/v1/`. `fixtures/index.json` lists valid
and invalid examples; for each invalid one it states whether a JSON Schema validator detects it (`json-schema`) or
only the Python models do (`model`, rules that relate several fields). `fixtures/negotiation.json` gives expected
negotiation outcomes. Regenerate the schemas after changing a model with `python -m copick.contracts.schema`; the
tests fail while they are out of date.
