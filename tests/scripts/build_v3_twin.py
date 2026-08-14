"""Build the independent OME-Zarr 0.5 / Zarr v3 test-corpus twin.

This script intentionally imports zarr, ome-zarr, and ome-zarr-models directly;
it never imports copick. The legacy corpus is copied byte-for-byte and retained
beside new ``*_v3`` project, overlay, and configuration paths.

Usage:
    python tests/scripts/build_v3_twin.py SOURCE --output sample_project.zip

``SOURCE`` may be the extracted archive root or the legacy zip itself.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import shutil
import tempfile
import zipfile
from pathlib import Path

import numpy as np
import zarr
from ome_zarr.format import FormatV05
from ome_zarr.writer import write_multiscales_metadata
from ome_zarr_models.v05.image import Image
from zarr.codecs import Shuffle, ZstdCodec
from zarr.storage import LocalStore

EXPECTED_STORES = 23
EXPECTED_ARRAYS = 61
SPATIAL_CHUNKS = (128, 128, 128)
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def _digest(path: Path, algorithm: str = "sha256") -> str:
    hasher = hashlib.new(algorithm)
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def _archive_root(extracted: Path) -> Path:
    candidates = [extracted, *(path for path in extracted.iterdir() if path.is_dir())]
    for candidate in candidates:
        if (candidate / "sample_project").is_dir() and (candidate / "filesystem.json").is_file():
            return candidate
    raise FileNotFoundError("Could not find sample_project/ and filesystem.json in the source corpus")


def _multiscale(group: zarr.Group) -> dict:
    entries = group.attrs.get("multiscales")
    if not isinstance(entries, list) or len(entries) != 1:
        raise ValueError(f"Expected one legacy multiscale entry in {group.store_path}")
    return entries[0]


def _padded_shards(shape: tuple[int, ...], chunks: tuple[int, ...]) -> tuple[int, ...]:
    return tuple(chunk * math.ceil(size / chunk) for size, chunk in zip(shape, chunks, strict=True))


def _compressors(dtype: np.dtype) -> tuple:
    dtype = np.dtype(dtype)
    if np.issubdtype(dtype, np.bool_) or np.issubdtype(dtype, np.integer):
        return (ZstdCodec(level=3),)
    if np.issubdtype(dtype, np.floating):
        return (Shuffle(elementsize=dtype.itemsize), ZstdCodec(level=3))
    raise TypeError(f"Unsupported corpus dtype: {dtype}")


def _write_image(
    target_path: Path,
    arrays: list[np.ndarray],
    datasets: list[dict],
    axes: list[dict],
    *,
    array_attributes: list[dict] | None = None,
    multiscale_metadata: dict | None = None,
    name: str | None = None,
    feature_major: bool = False,
) -> zarr.Group:
    target = zarr.group(store=LocalStore(target_path), overwrite=True, zarr_format=3)
    written_datasets = []
    for level, (values, source_dataset) in enumerate(zip(arrays, datasets, strict=True)):
        path = str(level)
        chunks = (1, *SPATIAL_CHUNKS) if feature_major else SPATIAL_CHUNKS
        shards = (
            (1, *_padded_shards(values.shape[1:], SPATIAL_CHUNKS))
            if feature_major
            else _padded_shards(values.shape, chunks)
        )
        attributes = {} if array_attributes is None else copy.deepcopy(array_attributes[level])
        target.create_array(
            path,
            data=values,
            chunks=chunks,
            shards=shards,
            compressors=_compressors(values.dtype),
            chunk_key_encoding={"name": "v2", "separator": "/"},
            dimension_names=tuple(axis["name"] for axis in axes),
            attributes=attributes,
        )
        written_datasets.append(
            {
                "path": path,
                "coordinateTransformations": copy.deepcopy(source_dataset["coordinateTransformations"]),
            },
        )

    kwargs = {}
    if multiscale_metadata:
        kwargs["metadata"] = copy.deepcopy(multiscale_metadata)
    write_multiscales_metadata(
        target,
        written_datasets,
        fmt=FormatV05(),
        axes=copy.deepcopy(axes),
        name=name,
        **kwargs,
    )
    Image.from_zarr(target)
    return target


def _convert_store(source_path: Path, target_path: Path) -> int:
    source = zarr.open_group(LocalStore(source_path), mode="r")
    multiscale = _multiscale(source)
    datasets = multiscale["datasets"]
    arrays = []
    attributes = []
    for dataset in datasets:
        array = source[dataset["path"]]
        if array.ndim != 3:
            raise ValueError(f"Legacy corpus array {source_path / dataset['path']} is not 3D")
        arrays.append(np.asarray(array))
        attributes.append(dict(array.attrs))

    if target_path.exists():
        shutil.rmtree(target_path)
    target = _write_image(
        target_path,
        arrays,
        datasets,
        multiscale["axes"],
        array_attributes=attributes,
        multiscale_metadata=multiscale.get("metadata"),
        name=multiscale.get("name"),
    )
    for level, expected in enumerate(arrays):
        np.testing.assert_array_equal(target[str(level)][:], expected)
    return len(arrays)


def _add_feature_major_fixture(project_v3: Path, target_path: Path) -> Path:
    source_path = sorted(project_v3.rglob("*_features.zarr"))[0]
    source = zarr.open_group(LocalStore(source_path), mode="r")
    multiscale = source.attrs["ome"]["multiscales"][0]
    source_array = source[multiscale["datasets"][0]["path"]]
    values = np.stack((np.asarray(source_array), np.asarray(source_array)), axis=0)
    spatial_transform = multiscale["datasets"][0]["coordinateTransformations"][0]
    dataset = {
        "path": "0",
        "coordinateTransformations": [
            {
                "type": "scale",
                "scale": [1.0, *spatial_transform["scale"]],
            },
        ],
    }
    _write_image(
        target_path,
        [values],
        [dataset],
        [{"name": "feature"}, *multiscale["axes"]],
        feature_major=True,
    )
    return target_path


def _copy_config(source: Path, target: Path) -> None:
    config = json.loads(source.read_text(encoding="utf-8"))
    for key in ("static_root", "overlay_root"):
        if isinstance(config.get(key), str):
            config[key] = (
                config[key]
                .replace("sample_project", "sample_project_v3")
                .replace(
                    "sample_overlay",
                    "sample_overlay_v3",
                )
            )
    target.write_text(json.dumps(config, indent=4) + "\n", encoding="utf-8")


def _non_zarr_files(root: Path) -> dict[str, str]:
    result = {}
    for path in root.rglob("*"):
        if path.is_file() and not any(part.endswith(".zarr") for part in path.relative_to(root).parts):
            result[path.relative_to(root).as_posix()] = _digest(path)
    return result


def _pack(source: Path, output: Path) -> None:
    """Create a byte-reproducible archive independent of build time and umask."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            relative = path.relative_to(source).as_posix()
            info = zipfile.ZipInfo(relative, ZIP_TIMESTAMP)
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            if path.is_dir():
                info.filename = f"{relative.rstrip('/')}/"
                info.external_attr = (0o40755 << 16) | 0x10
                archive.writestr(info, b"")
            else:
                info.external_attr = 0o100644 << 16
                with path.open("rb") as source_file, archive.open(info, "w") as target_file:
                    shutil.copyfileobj(source_file, target_file)


def build(source: Path, output: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="copick-v3-twin-") as directory:
        workspace = Path(directory)
        if source.is_file():
            with zipfile.ZipFile(source) as archive:
                archive.extractall(workspace / "input")
            legacy_root = _archive_root(workspace / "input")
        else:
            legacy_root = _archive_root(source)

        built_root = workspace / "built"
        shutil.copytree(legacy_root, built_root)
        project = built_root / "sample_project"
        project_v3 = built_root / "sample_project_v3"
        overlay_v3 = built_root / "sample_overlay_v3"
        shutil.copytree(project, project_v3)
        shutil.copytree(built_root / "sample_overlay", overlay_v3)

        source_stores = sorted(path for path in project.rglob("*.zarr") if path.is_dir())
        if len(source_stores) != EXPECTED_STORES:
            raise ValueError(f"Expected {EXPECTED_STORES} stores, found {len(source_stores)}")
        array_count = 0
        for source_store in source_stores:
            relative = source_store.relative_to(project)
            array_count += _convert_store(source_store, project_v3 / relative)
        if array_count != EXPECTED_ARRAYS:
            raise ValueError(f"Expected {EXPECTED_ARRAYS} arrays, found {array_count}")

        feature_fixture = _add_feature_major_fixture(
            project_v3,
            built_root / "wbp_multifeature_features.zarr",
        )
        if _non_zarr_files(project) != _non_zarr_files(project_v3):
            raise ValueError("Non-Zarr files in the v3 project twin differ from the legacy corpus")

        _copy_config(built_root / "filesystem.json", built_root / "filesystem_v3.json")
        _copy_config(
            built_root / "filesystem_overlay_only.json",
            built_root / "filesystem_overlay_only_v3.json",
        )
        _pack(built_root, output)

    return {
        "stores": EXPECTED_STORES,
        "arrays": EXPECTED_ARRAYS,
        "feature_fixture": feature_fixture.name,
        "archive": str(output),
        "size": output.stat().st_size,
        "md5": _digest(output, "md5"),
        "sha256": _digest(output),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Legacy extracted corpus root or sample_project.zip")
    parser.add_argument("--output", type=Path, required=True, help="Output zip containing legacy and v3 twins")
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.output), indent=2))


if __name__ == "__main__":
    main()
