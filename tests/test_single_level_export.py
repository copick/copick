"""Contracts for bounded single-level OME-Zarr export."""

import math
import tracemalloc

import numpy as np
import pytest
import zarr
from copick.util.ome import copy_array_chunkwise, get_level_path, get_multiscales, write_single_level_ome_zarr_v2
from ome_zarr.format import FormatV04
from ome_zarr.io import parse_url
from ome_zarr.reader import Reader
from zarr.storage import LocalStore


def _source_group(path, zarr_format):
    group = zarr.group(store=LocalStore(path), zarr_format=zarr_format)
    kwargs = {"chunks": (2, 3, 4), "fill_value": -1, "attributes": {"source-array": True}}
    if zarr_format == 3:
        kwargs["shards"] = (4, 6, 8)
    values = np.arange(5 * 7 * 9, dtype=np.int16).reshape(5, 7, 9)
    group.create_array("s0", data=values, **kwargs)
    group.create_array("s1", data=values[:2, :3, :4], chunks=(2, 3, 4))
    multiscales = [
        {
            "version": "0.5" if zarr_format == 3 else "0.4",
            "name": "source",
            "axes": [
                {"name": "z", "type": "space", "unit": "angstrom"},
                {"name": "y", "type": "space", "unit": "angstrom"},
                {"name": "x", "type": "space", "unit": "angstrom"},
            ],
            "datasets": [
                {
                    "path": "s0",
                    "coordinateTransformations": [{"type": "scale", "scale": [10.0, 10.0, 10.0]}],
                },
                {
                    "path": "s1",
                    "coordinateTransformations": [{"type": "scale", "scale": [20.0, 20.0, 20.0]}],
                },
            ],
        },
    ]
    if zarr_format == 3:
        group.attrs["ome"] = {"version": "0.5", "multiscales": multiscales}
    else:
        group.attrs["multiscales"] = multiscales
    group.attrs["unrelated"] = "must not cross the format boundary"
    return group, values


@pytest.mark.parametrize("source_format", [2, 3])
def test_single_level_export_rebuilds_v2_metadata_and_preserves_array_contract(tmp_path, source_format):
    source, values = _source_group(tmp_path / "source.zarr", source_format)
    target_path = tmp_path / "target.zarr"

    write_single_level_ome_zarr_v2(source, LocalStore(target_path))

    target = zarr.open_group(LocalStore(target_path), mode="r")
    assert target.metadata.zarr_format == 2
    assert set(target.attrs) == {"multiscales"}
    multiscale = target.attrs["multiscales"][0]
    assert multiscale["version"] == "0.4"
    assert multiscale["axes"] == get_multiscales(source)[0]["axes"]
    assert multiscale["datasets"] == [
        {
            "path": "0",
            "coordinateTransformations": [{"type": "scale", "scale": [10.0, 10.0, 10.0]}],
        },
    ]
    assert get_level_path(target, 0) == "0"

    exported = target[get_level_path(target, 0)]
    assert exported.dtype == source["s0"].dtype
    assert exported.shape == source["s0"].shape
    assert exported.chunks == source["s0"].chunks
    assert exported.fill_value == source["s0"].fill_value
    assert dict(exported.attrs) == dict(source["s0"].attrs)
    np.testing.assert_array_equal(exported[:], values)
    assert not (target_path / "zarr.json").exists()

    location = parse_url(target_path, mode="r", fmt=FormatV04())
    assert location is not None
    nodes = list(Reader(location)())
    assert len(nodes) == 1
    assert len(nodes[0].data) == 1


class _RecordingArray:
    def __init__(self, shape, chunks):
        self.shape = shape
        self.chunks = chunks
        self.selections = []

    def __getitem__(self, selection):
        self.selections.append(selection)
        return np.zeros(tuple(axis.stop - axis.start for axis in selection), dtype=np.uint8)


class _TargetArray:
    def __init__(self):
        self.selections = []

    def __setitem__(self, selection, value):
        self.selections.append((selection, value.shape))


def test_chunkwise_copy_bounds_every_read_to_one_inner_chunk():
    source = _RecordingArray(shape=(9, 10, 11), chunks=(4, 4, 4))
    target = _TargetArray()

    copy_array_chunkwise(source, target)

    assert len(source.selections) == math.ceil(9 / 4) * math.ceil(10 / 4) * math.ceil(11 / 4)
    assert len(target.selections) == len(source.selections)
    for selection in source.selections:
        extents = tuple(axis.stop - axis.start for axis in selection)
        assert all(0 < extent <= chunk for extent, chunk in zip(extents, source.chunks, strict=True))
        assert math.prod(extents) <= math.prod(source.chunks)


def test_single_level_export_keeps_peak_python_memory_below_volume_size(tmp_path):
    source_path = tmp_path / "large-source.zarr"
    source = zarr.group(store=LocalStore(source_path), zarr_format=2)
    shape = (512, 512, 512)
    chunks = (64, 64, 64)
    source.create_array("s0", shape=shape, chunks=chunks, dtype="u1", fill_value=0)
    source.attrs["multiscales"] = [
        {
            "version": "0.4",
            "axes": [
                {"name": "z", "type": "space"},
                {"name": "y", "type": "space"},
                {"name": "x", "type": "space"},
            ],
            "datasets": [{"path": "s0"}],
        },
    ]

    tracemalloc.start()
    try:
        write_single_level_ome_zarr_v2(source, LocalStore(tmp_path / "large-target.zarr"))
        _, peak_bytes = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    logical_volume_bytes = math.prod(shape)
    assert peak_bytes < 32 * 1024 * 1024
    assert peak_bytes < logical_volume_bytes // 4

    target = zarr.open_group(LocalStore(tmp_path / "large-target.zarr"), mode="r")
    target_array = target[get_level_path(target, 0)]
    assert target_array.shape == shape
    assert target_array.chunks == chunks
    assert target_array[0, 0, 0] == 0
