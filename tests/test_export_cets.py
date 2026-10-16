"""Export of a project as a CETS Dataset document."""

import json
from typing import Any, Dict

import copick
import numpy as np
import pytest
from cets_schema import validate_cets
from click.testing import CliRunner
from copick.models import (
    CopickCTF,
    CopickReferenceVolume,
    CopickSectionAlignment,
    CopickTiltImage,
    CopickTiltSeriesMetadata,
)
from copick.ops.cets_export import export_cets

N = 3


@pytest.fixture(params=pytest.common_cases)
def test_payload(request) -> Dict[str, Any]:
    payload = request.getfixturevalue(request.param)
    payload["root"] = copick.from_file(payload["cfg_file"])
    return payload


def _populate(run):
    ts = run.new_tilt_series("raw")
    ts.from_numpy(
        np.zeros((N, 16, 16), dtype=np.float32),
        metadata=CopickTiltSeriesMetadata(
            pixel_size=10.0,
            width=16,
            height=16,
            voltage=300.0,
            spherical_aberration=2.7,
            amplitude_contrast=0.07,
            images=[
                CopickTiltImage(
                    section=i,
                    nominal_tilt_angle=-3.0 + 3.0 * i,
                    acquisition_order=i,
                    accumulated_dose=3.0 * i,
                    ctf=CopickCTF(defocus_u=30000, defocus_v=29000, defocus_angle=10),
                )
                for i in range(N)
            ],
        ),
    )
    alignment = run.new_alignment(
        "aretomo3",
        ts,
        sections=[CopickSectionAlignment(section=i, tilt_angle=-3.0 + 3.0 * i, shift_x=1.0) for i in range(N)],
        reference_volume=CopickReferenceVolume(size=(64, 64, 64), voxel_size=10.0),
    )
    tomogram = run.get_voxel_spacing(10.0).new_tomogram("recon")
    tomogram.from_numpy(np.zeros((64, 64, 64), dtype=np.float32))
    tomogram.set_alignment(alignment)


def _check_references(dataset):
    """Every identifier a dataset refers to resolves within it."""
    sessions = {s["id"] for s in dataset["acquisition_sessions"]}
    instruments = {i["id"] for i in dataset["instruments"]}
    assert all(s["instrument_id"] in instruments for s in dataset["acquisition_sessions"])
    for region in dataset["regions"]:
        series = {ts["id"]: ts for ts in region["tilt_series"]}
        images = {image["id"] for ts in region["tilt_series"] for image in ts["images"]}
        assert all(ts["acquisition_session_id"] in sessions for ts in region["tilt_series"])
        for alignment in region["alignments"]:
            assert alignment["tilt_series_id"] in series
            assert all(p["tilt_image_id"] in images for p in alignment["projection_alignments"])
        assert all(t["tilt_series_id"] in series for t in region["tomograms"] if "tilt_series_id" in t)
    ids = [ts["id"] for r in dataset["regions"] for ts in r["tilt_series"]]
    assert len(ids) == len(set(ids))


def test_export_cets(test_payload: Dict[str, Any], tmp_path):
    _populate(test_payload["root"].get_run("TS_001"))
    _populate(test_payload["root"].get_run("TS_002"))
    output = export_cets(copick.from_file(test_payload["cfg_file"]), tmp_path / "dataset.cets.json")

    dataset = json.loads(output.read_text())
    validate_cets(dataset, "Dataset")
    _check_references(dataset)
    assert "defocus_handedness" not in output.read_text()

    region = next(r for r in dataset["regions"] if r["id"] == "TS_001")
    (ts,) = region["tilt_series"]
    assert ts["id"] == "TS_001/raw" and ts["images"][1]["id"] == "TS_001/raw_1"
    assert ts["path"].endswith("ExperimentRuns/TS_001/TiltSeries/raw.zarr") and "://" in ts["path"]
    (alignment,) = region["alignments"]
    assert alignment["tilt_series_id"] == "TS_001/raw"
    assert alignment["projection_alignments"][0]["id"] == "TS_001/raw_aretomo3_align_0"
    recon = next(t for t in region["tomograms"] if t["id"] == "TS_001/recon@10.000")
    assert recon["tilt_series_id"] == "TS_001/raw" and (recon["width"], recon["height"], recon["depth"]) == (64, 64, 64)
    assert recon["coordinate_transformations"][0]["sequence"][0]["translation"] == [-32.0, -32.0, -32.0]

    companion = json.loads((tmp_path / "dataset.cets.json.copick-companion.json").read_text())
    assert companion["schema"] == "copick-cets-companion/1"
    assert companion["alignments"]["TS_001/aretomo3"]["position"] == 0
    assert companion["alignments"]["TS_001/aretomo3"]["extensions"]["reference_volume"]["size"] == [64, 64, 64]
    assert companion["tomograms"]["TS_001/recon@10.000"] == {
        "alignment_id": "TS_001/aretomo3",
        "reference_offset": None,
        "link_source": "attrs",
    }
    assert companion["tilt_series"]["TS_001/raw"]["pixel_size"] == 10.0


def test_export_cets_selection(test_payload: Dict[str, Any], tmp_path):
    _populate(test_payload["root"].get_run("TS_001"))
    output = export_cets(
        copick.from_file(test_payload["cfg_file"]),
        tmp_path / "dataset.json",
        runs=["TS_001"],
        include_tomograms=False,
        with_paths=False,
        companion=False,
    )
    dataset = json.loads(output.read_text())
    assert [r["id"] for r in dataset["regions"]] == ["TS_001"]
    assert dataset["regions"][0]["tomograms"] == [] and "path" not in dataset["regions"][0]["tilt_series"][0]
    assert not (tmp_path / "dataset.json.copick-companion.json").exists()


def test_export_cets_cli(test_payload: Dict[str, Any], tmp_path):
    from copick.cli.cli import _cli

    _populate(test_payload["root"].get_run("TS_001"))
    output = tmp_path / "cli.cets.json"
    result = CliRunner().invoke(
        _cli,
        ["export", "cets", "-c", str(test_payload["cfg_file"]), "-o", str(output), "--run-names", "TS_001"],
    )
    assert result.exit_code == 0, result.output
    validate_cets(json.loads(output.read_text()), "Dataset")


def test_export_validates_with_cets_models_when_installed(test_payload: Dict[str, Any], tmp_path):
    pytest.importorskip("cets_data_model")
    from cets_data_model.models.models import Dataset

    _populate(test_payload["root"].get_run("TS_001"))
    output = export_cets(copick.from_file(test_payload["cfg_file"]), tmp_path / "dataset.json")
    Dataset.model_validate_json(output.read_text())
