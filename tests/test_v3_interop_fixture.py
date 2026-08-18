"""Tests for the direct-reader interoperability fixture."""

import hashlib
import importlib.util
import json
import zipfile
from pathlib import Path

import numpy as np
import zarr
from ome_zarr_models.v05.image import Image

_BUILDER_PATH = Path(__file__).parent / "scripts" / "build_v3_interop_fixture.py"
_BUILDER_SPEC = importlib.util.spec_from_file_location("copick_v3_interop_fixture", _BUILDER_PATH)
if _BUILDER_SPEC is None or _BUILDER_SPEC.loader is None:
    raise RuntimeError(f"Could not load fixture builder from {_BUILDER_PATH}")
fixture = importlib.util.module_from_spec(_BUILDER_SPEC)
_BUILDER_SPEC.loader.exec_module(fixture)


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_direct_reader_fixture_is_canonical(tmp_path):
    archive_path = tmp_path / "fixture.zip"
    fixture.build_archive(archive_path, source_revision="test-revision")

    extracted = tmp_path / "extracted"
    with zipfile.ZipFile(archive_path) as archive:
        archive.extractall(extracted)
    root = extracted / fixture.FIXTURE_NAME
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["schema_version"] == 2
    assert manifest["producer"]["source_revision"] == "test-revision"
    assert manifest["canonical_policy"]["ome_zarr_version"] == "0.5"
    assert manifest["canonical_policy"]["zarr_format"] == 3
    assert manifest["canonical_policy"]["one_spatial_shard_per_feature_volume"] is True
    assert set(manifest["stores"]) == {"boolean", "floating", "floating_features", "integer"}
    assert manifest["files"] == {
        str(path.relative_to(root)): _sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "manifest.json"
    }

    expected_codecs = {
        "boolean": ["bytes", "zstd"],
        "integer": ["bytes", "zstd"],
        "floating": ["bytes", "numcodecs.shuffle", "zstd"],
        "floating_features": ["bytes", "numcodecs.shuffle", "zstd"],
    }
    for name, store_manifest in manifest["stores"].items():
        group = zarr.open_group(root / store_manifest["path"], mode="r")
        assert Image.from_zarr(group).ome_zarr_version == "0.5"
        assert [dataset["path"] for dataset in store_manifest["multiscale"]["datasets"]] == ["0", "1"]
        for level in store_manifest["levels"]:
            array = group[level["path"]]
            values = np.asarray(array)
            if name == "floating_features":
                assert level["shard_grid_shape"] == [2, 1, 1, 1]
                assert level["inner_chunks"] == [1, 128, 128, 128]
                assert level["dimension_names"] == ["feature", "z", "y", "x"]
                assert len(level["shard_keys"]) == 2
            else:
                assert level["shard_grid_shape"] == [1, 1, 1]
                assert level["inner_chunks"] == [128, 128, 128]
                assert level["dimension_names"] == ["z", "y", "x"]
                assert len(level["shard_keys"]) == 1
            assert [codec["name"] for codec in level["inner_codecs"]] == expected_codecs[name]
            assert hashlib.sha256(values.tobytes(order="C")).hexdigest() == level["decoded_sha256"]
            for shard_key in level["shard_keys"]:
                assert (root / store_manifest["path"] / shard_key).is_file()
            for sample in level["samples"]:
                coordinate = tuple(sample["coordinate"])
                assert values[coordinate].item() == sample["value"]
