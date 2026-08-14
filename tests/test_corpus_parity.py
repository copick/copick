import ast
import hashlib
import zipfile
from pathlib import Path

import copick
import numpy as np
import pytest
import zarr
from conftest import BACKEND, TEST_ZARR_FORMAT, TESTS_DIR, ensure_test_data
from ome_zarr_models.v05.image import Image
from zarr.storage import LocalStore


class _LocalCorpus:
    def __init__(self, path: Path, archive: Path, digest: str):
        self.path = path
        self.archive = archive
        self.registry = {"sample_project.zip": digest}
        self.fetch_count = 0

    def fetch(self, name: str) -> str:
        assert name == "sample_project.zip"
        self.fetch_count += 1
        return str(self.archive)


def _write_test_archive(path: Path, marker: str) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name in (
            "sample_project_v3/",
            "sample_overlay_v3/",
            "filesystem_v3.json",
            "filesystem_overlay_only_v3.json",
        ):
            archive.writestr(name, b"")
        archive.writestr("sample_project_v3/version.txt", marker)


def _digest(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _multiscale(group: zarr.Group) -> dict:
    attrs = dict(group.attrs)
    return attrs.get("ome", attrs)["multiscales"][0]


def _non_zarr_files(root: Path) -> dict[str, str]:
    result = {}
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if path.is_file() and not any(part.endswith(".zarr") for part in relative.parts):
            result[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def test_corpus_cache_uses_the_registry_digest_for_cold_and_warm_runs(tmp_path):
    archive = tmp_path / "sample_project.zip"
    _write_test_archive(archive, "first")
    corpus = _LocalCorpus(tmp_path, archive, _digest(archive))

    extracted = ensure_test_data(corpus, zarr_format="v3")
    marker = extracted / "sample_project_v3" / "version.txt"
    assert marker.read_text() == "first"

    marker.write_text("warm cache must remain untouched")
    assert ensure_test_data(corpus, zarr_format="v3") == extracted
    assert marker.read_text() == "warm cache must remain untouched"

    _write_test_archive(archive, "second")
    corpus.registry["sample_project.zip"] = _digest(archive)
    assert ensure_test_data(corpus, zarr_format="v3") == extracted
    assert marker.read_text() == "second"
    assert corpus.fetch_count == 3


def test_v3_twin_builder_does_not_import_copick():
    source_path = TESTS_DIR / "scripts" / "build_v3_twin.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert "copick" not in imported


@pytest.fixture(params=pytest.common_cases)
def corpus_backend_root(request):
    payload = request.getfixturevalue(request.param)
    return copick.from_file(payload["cfg_file"])


@pytest.mark.corpus_parity
@pytest.mark.remote_corpus_parity
def test_selected_corpus_reads_and_region_writes(corpus_backend_root):
    run = corpus_backend_root.get_run("TS_001")
    voxel_spacing = run.get_voxel_spacing(10.0)

    tomogram = voxel_spacing.get_tomogram("denoised")
    assert tomogram.numpy().shape == (64, 64, 64)
    assert tomogram.numpy(z=slice(10, 40), y=slice(50, 60), x=slice(0, 30)).shape == (30, 10, 30)

    segmentation = run.get_segmentations(name="membrane")[0]
    assert segmentation.numpy(z=slice(20, 40), y=slice(20, 40), x=slice(20, 40)).shape == (20, 20, 20)

    source_feature = voxel_spacing.get_tomogram("wbp").get_features("sobel")
    assert source_feature.numpy(slices=(slice(20, 40),) * 3).shape == (20, 20, 20)

    written_feature = tomogram.new_features("corpus-parity")
    expected = np.arange(16**3, dtype=np.float32).reshape((16, 16, 16))
    written_feature.from_numpy(expected)
    update = np.full((4, 4, 4), -1.0, dtype=np.float32)
    written_feature.set_region(update, slices=(slice(4, 8),) * 3)
    expected[4:8, 4:8, 4:8] = update
    np.testing.assert_array_equal(written_feature.numpy(), expected)


@pytest.mark.corpus_parity
@pytest.mark.skipif(TEST_ZARR_FORMAT != "v3" or BACKEND != "local", reason="local v3 corpus parity gate")
def test_v3_corpus_matches_every_legacy_store_and_array(local_path):
    legacy_project = local_path / "sample_project"
    v3_project = local_path / "sample_project_v3"
    legacy_stores = sorted(path for path in legacy_project.rglob("*.zarr") if path.is_dir())
    assert len(legacy_stores) == 23

    array_count = 0
    for legacy_path in legacy_stores:
        v3_path = v3_project / legacy_path.relative_to(legacy_project)
        legacy = zarr.open_group(LocalStore(legacy_path), mode="r")
        twin = zarr.open_group(LocalStore(v3_path), mode="r")
        Image.from_zarr(twin)
        assert twin.metadata.zarr_format == 3

        legacy_multiscale = _multiscale(legacy)
        twin_multiscale = _multiscale(twin)
        assert twin_multiscale["axes"] == legacy_multiscale["axes"]
        assert len(twin_multiscale["datasets"]) == len(legacy_multiscale["datasets"])
        for legacy_dataset, twin_dataset in zip(
            legacy_multiscale["datasets"],
            twin_multiscale["datasets"],
            strict=True,
        ):
            assert twin_dataset["coordinateTransformations"] == legacy_dataset["coordinateTransformations"]
            np.testing.assert_array_equal(
                twin[twin_dataset["path"]][:],
                legacy[legacy_dataset["path"]][:],
            )
            array_count += 1

    assert array_count == 61
    assert _non_zarr_files(v3_project) == _non_zarr_files(legacy_project)

    feature_stores = sorted(local_path.glob("*_multifeature_features.zarr"))
    assert len(feature_stores) == 1
    feature_group = zarr.open_group(LocalStore(feature_stores[0]), mode="r")
    Image.from_zarr(feature_group)
    assert feature_group["0"].ndim == 4
