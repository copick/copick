"""Tests for the direct-reader interoperability fixture."""

import hashlib
import json
import zipfile

import numpy as np
import zarr
from ome_zarr_models.v05.image import Image
from scripts import build_v3_interop_fixture as fixture


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_direct_reader_fixture_is_deterministic_and_canonical(tmp_path):
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"
    fixture.build_archive(first)
    fixture.build_archive(second)

    assert _sha256(first) == _sha256(second)
    assert first.read_bytes() == second.read_bytes()

    extracted = tmp_path / "extracted"
    with zipfile.ZipFile(first) as archive:
        archive.extractall(extracted)
    root = extracted / fixture.FIXTURE_NAME
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["schema_version"] == 1
    assert manifest["canonical_policy"]["ome_zarr_version"] == "0.5"
    assert manifest["canonical_policy"]["zarr_format"] == 3
    assert manifest["canonical_policy"]["one_shard_per_level"] is True
    assert set(manifest["stores"]) == {"boolean", "floating", "integer"}
    assert manifest["files"] == {
        str(path.relative_to(root)): _sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "manifest.json"
    }

    expected_codecs = {
        "boolean": ["bytes", "zstd"],
        "integer": ["bytes", "zstd"],
        "floating": ["bytes", "numcodecs.shuffle", "zstd"],
    }
    for name, store_manifest in manifest["stores"].items():
        group = zarr.open_group(root / store_manifest["path"], mode="r")
        assert Image.from_zarr(group).ome_zarr_version == "0.5"
        assert [dataset["path"] for dataset in store_manifest["multiscale"]["datasets"]] == ["0", "1"]
        for level in store_manifest["levels"]:
            array = group[level["path"]]
            values = np.asarray(array)
            assert level["shard_grid_shape"] == [1, 1, 1]
            assert level["inner_chunks"] == [128, 128, 128]
            assert level["dimension_names"] == ["z", "y", "x"]
            assert [codec["name"] for codec in level["inner_codecs"]] == expected_codecs[name]
            assert hashlib.sha256(values.tobytes(order="C")).hexdigest() == level["decoded_sha256"]
            assert (root / store_manifest["path"] / level["shard_key"]).is_file()
            for sample in level["samples"]:
                coordinate = tuple(sample["coordinate_zyx"])
                assert values[coordinate].item() == sample["value"]
