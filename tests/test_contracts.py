import json
import subprocess
import sys
from datetime import datetime, timezone

import copick
import jsonschema
import numpy as np
import pytest
from copick.contracts import (
    CONTRACT_VERSION,
    AnnotationRevision,
    BackendCapabilities,
    FeatureProvenance,
    Geometry,
    InferredLabels,
    LabelSchema,
    ReconstructionRef,
    Requirement,
    ResultManifest,
    SegmentationRef,
    indices_digest,
    label_digest,
    negotiate,
)
from copick.contracts.schema import DOCUMENTS, SCHEMA_DIR, json_schemas, stale
from pydantic import ValidationError

FIXTURES = SCHEMA_DIR / "fixtures"
INDEX = json.loads((FIXTURES / "index.json").read_text())
T = datetime(2026, 11, 6, tzinfo=timezone.utc)


def _load(name):
    return json.loads((FIXTURES / name).read_text())


def test_shipped_schemas_match_models():
    assert stale() == []
    for schema in json_schemas().values():
        jsonschema.Draft202012Validator.check_schema(schema)


@pytest.mark.parametrize("entry", INDEX["fixtures"], ids=lambda e: e["file"])
def test_fixture(entry):
    """Each fixture is accepted or refused by the models, and a JSON Schema validator detects what it claims to."""
    data = _load(entry["file"])
    model = DOCUMENTS[entry["document"]]
    schema = json_schemas()[entry["document"]]
    schema_errors = list(jsonschema.Draft202012Validator(schema).iter_errors(data))
    if entry["valid"]:
        assert schema_errors == []
        assert model.model_validate(data).model_dump(mode="json") == data
        return
    with pytest.raises(ValidationError):
        model.model_validate(data)
    assert bool(schema_errors) == (entry["detected_by"] == "json-schema")


def test_negotiation_fixture():
    cases = _load("negotiation.json")
    requirements = [Requirement.model_validate(r) for r in cases["requirements"]]
    for case in cases["cases"]:
        offers = negotiate(BackendCapabilities.model_validate(_load(case["capabilities"])), requirements)
        assert [o.model_dump(mode="json") for o in offers] == case["offers"]


def test_negotiation_refuses_without_raising():
    capabilities = _load("capabilities-cellcanvas.json")
    need = [
        Requirement(operation="feature_learning.predict", public_model=True, outputs=["instance"]),
        Requirement(operation="feature_learning.train", label_policy="other.Policy"),
    ]
    private = dict(capabilities, model={"name": "internal", "public": False})
    predict, train = negotiate(private, need)
    assert not predict.available and len(predict.reasons) == 2
    assert not train.available
    future = dict(capabilities, contract_version="2", new_field=True)
    assert all("contract version" in o.reasons[0] for o in negotiate(future, need))


def test_label_roles_keep_unknown_background_and_inferred_apart():
    labels = LabelSchema.model_validate(_load("label-schema-membrane-compartment.json"))
    assert [labels.role_of(v) for v in (0, 1, 2, 3)] == ["unknown", "background", "object", "object"]
    assert labels.background_value() == 1
    with pytest.raises(ValueError, match="not declared"):
        labels.check_values(np.array([0, 4]))
    instances = LabelSchema.model_validate(_load("label-schema-instances.json"))
    assert [instances.role_of(v) for v in (0, 7)] == ["background", "instance"]
    seeds = InferredLabels.model_validate(_load("inferred-labels-seeded-background.json"))
    seeds.check_target(labels)
    with pytest.raises(ValueError):
        seeds.check_target(instances)
    assert indices_digest(np.array([99, 5, 17, 5])) == seeds.indices_digest


def test_annotation_revision_identifies_exact_labels():
    revision = AnnotationRevision.model_validate(_load("annotation-revision.json"))
    labels = np.zeros(revision.reconstruction.geometry.shape, np.uint8)
    labels[30, 70:75, 70:75] = 2
    labels[30, 10:14, 10:14] = 1
    revision.verify(labels)
    labels[0, 0, 0] = 1
    with pytest.raises(ValueError, match="not revision"):
        revision.verify(labels)
    with pytest.raises(ValueError, match="shape"):
        revision.verify(labels[:-1])
    assert label_digest(labels) != label_digest(labels.astype(np.uint16))


def test_result_manifest_publication_rules():
    manifest = ResultManifest.model_validate(_load("result-manifest-feature-learning.json"))
    prediction = np.ones(manifest.geometry.shape, np.uint8)
    prediction[25:35, 60:80, 60:80] = 3
    manifest.verify(prediction)
    changed = prediction.copy()
    changed[0, 0, 0] = 2
    with pytest.raises(ValueError, match="not version"):
        manifest.verify(changed)
    assert manifest.to_attrs()["copick_result"]["review"] == "proposal"
    data = _load("result-manifest-feature-learning.json")
    data.pop("features")
    with pytest.raises(ValidationError, match="annotation revision and features"):
        ResultManifest.model_validate(data)


def test_feature_provenance_drops_local_paths():
    manifest = {
        "model": "DINOv2 ViT-B/14",
        "license": "Apache-2.0",
        "public": True,
        "source": "/some/local/tomogram.zarr",
        "grid": {"shape": [4, 5, 6], "axes": ["d", "z", "y", "x"], "resampling": "bilinear"},
        "checkpoint": {"path": "/home/user/.cache/x.pth", "sha256": "0" * 64},
        "implementation": {"source_tree": "/home/user/src"},
    }
    provenance = FeatureProvenance.from_manifest(manifest)
    assert "/" not in json.dumps(provenance.model_dump(mode="json")).replace("ViT-B/14", "")


def test_geometry_mismatches():
    a = Geometry(shape=[2, 3, 4], scale_angstrom=[10, 10, 10])
    assert a.mismatches(Geometry(shape=[2, 3, 4], scale_angstrom=[10, 10, 10.0000001])) == []
    problems = a.mismatches(Geometry(shape=[2, 3, 5], scale_angstrom=[10, 10, 10], translation_angstrom=[0, 0, 5]))
    assert len(problems) == 2
    nm = Geometry.from_ome_attrs(
        {
            "ome": {
                "multiscales": [
                    {
                        "axes": [{"name": n, "type": "space", "unit": "nanometer"} for n in "zyx"],
                        "datasets": [
                            {
                                "path": "0",
                                "coordinateTransformations": [
                                    {"type": "scale", "scale": [1.0, 1.0, 1.0]},
                                    {"type": "translation", "translation": [0.5, 0, 0]},
                                ],
                            },
                        ],
                    },
                ],
            },
        },
        [2, 3, 4],
    )
    assert nm.scale_angstrom == [10.0, 10.0, 10.0] and nm.translation_angstrom == [5.0, 0.0, 0.0]


def test_references_from_copick_project(tmp_path):
    """Identity read from a real copick overlay project round-trips through an annotation revision."""
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "name": "contracts",
                "version": "1.0.0",
                "pickable_objects": [
                    {"name": "membrane", "is_particle": False, "label": 1},
                    {"name": "mitochondrion", "is_particle": False, "label": 2},
                ],
                "overlay_root": f"local://{tmp_path / 'overlay'}",
                "overlay_fs_args": {"auto_mkdir": True},
                "config_type": "filesystem",
            },
        ),
    )
    root = copick.from_file(str(config))
    voxel_spacing = root.new_run("TS_1").new_voxel_spacing(10.0)
    tomogram = voxel_spacing.new_tomogram("wbp")
    tomogram.from_numpy(np.zeros((8, 6, 4), np.float32), levels=1)
    painting = voxel_spacing.run.new_segmentation(10.0, "painting", "1", True, user_id="annotator")
    labels = np.zeros((8, 6, 4), np.uint8)
    labels[2, 1:3, 1:3] = 2
    painting.from_numpy(labels)

    recon = ReconstructionRef.from_tomogram(tomogram, project="contracts")
    assert recon.key == "contracts/TS_1/10.000/wbp"
    assert recon.geometry == Geometry(shape=[8, 6, 4], scale_angstrom=[10.0] * 3)
    segmentation = SegmentationRef.from_segmentation(painting)
    assert segmentation.kind == "multilabel"
    schema = LabelSchema(
        encoding="semantic",
        classes=[
            {"value": 1, "name": "membrane", "role": "object", "structure": "membrane"},
            {"value": 2, "name": "mitochondrion", "role": "object", "structure": "compartment"},
        ],
    )
    revision = AnnotationRevision.of(
        painting.numpy(),
        reconstruction=recon,
        segmentation=segmentation,
        labels=schema,
        revision="r1",
        created_at=T,
    )
    reread = AnnotationRevision.model_validate_json(revision.model_dump_json())
    reread.verify(copick.from_file(str(config)).get_run("TS_1").get_segmentations(name="painting")[0].numpy())
    assert recon.mismatches(ReconstructionRef.from_tomogram(tomogram, project="other")) != []
    with pytest.raises(ValidationError, match="instance"):
        AnnotationRevision.of(
            labels,
            reconstruction=recon,
            segmentation=segmentation,
            labels=LabelSchema(encoding="instance", instance_class={"name": "m", "structure": "compartment"}),
            revision="r2",
            created_at=T,
        )


def test_contracts_import_no_model_runtime():
    code = "import sys, copick.contracts; print(sorted(m for m in ('torch', 'jax', 'tensorflow') if m in sys.modules))"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout
    assert out.strip() == "[]"
    assert INDEX["contract_version"] == CONTRACT_VERSION
