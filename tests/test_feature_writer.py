"""Contracts for backward-compatible 3D and feature-major 4D feature writes."""

import inspect
import math
from types import SimpleNamespace

import numpy as np
import pytest
import zarr
from copick.models import CopickFeatures, CopickFeaturesMeta
from copick.ops.add import add_features
from copick.util.ome import DEFAULT_SPATIAL_CHUNKS, get_level_path, get_multiscales
from ome_zarr_models.v05.image import Image
from zarr.storage import MemoryStore


class _MemoryFeatures(CopickFeatures):
    def __init__(self, voxel_size=10.0):
        tomogram = SimpleNamespace(voxel_spacing=SimpleNamespace(voxel_size=voxel_size))
        super().__init__(tomogram, CopickFeaturesMeta(tomo_type="test", feature_type="features"))
        self.store = MemoryStore()

    def zarr(self):
        return self.store

    def _delete_data(self):
        raise NotImplementedError


def _written_array(features):
    group = zarr.open_group(features.zarr(), mode="r")
    return group, group[get_level_path(group, 0)]


@pytest.mark.parametrize("shape", [(4, 5, 6), (3, 4, 5, 6)])
def test_feature_from_numpy_round_trips_supported_shapes(shape):
    features = _MemoryFeatures(voxel_size=7.5)
    values = np.arange(math.prod(shape), dtype=np.float32).reshape(shape)

    features.from_numpy(values)

    group, array = _written_array(features)
    np.testing.assert_array_equal(features.numpy(), values)
    assert Image.from_zarr(group).ome_zarr_version == "0.5"
    if len(shape) == 3:
        assert array.chunks == DEFAULT_SPATIAL_CHUNKS
        assert array.shards == DEFAULT_SPATIAL_CHUNKS
        assert array.metadata.dimension_names == ("z", "y", "x")
        expected_axes = ["z", "y", "x"]
        expected_scale = [7.5, 7.5, 7.5]
    else:
        assert array.chunks == (1, *DEFAULT_SPATIAL_CHUNKS)
        assert array.shards == (1, *DEFAULT_SPATIAL_CHUNKS)
        assert array.metadata.dimension_names == ("feature", "z", "y", "x")
        expected_axes = ["feature", "z", "y", "x"]
        expected_scale = [1.0, 7.5, 7.5, 7.5]
        data_keys = {key for key in features.store._store_dict if not key.endswith("zarr.json")}
        assert data_keys == {f"0/{feature}/0/0/0" for feature in range(shape[0])}

    multiscale = get_multiscales(group)[0]
    assert [axis["name"] for axis in multiscale["axes"]] == expected_axes
    assert multiscale["datasets"][0]["coordinateTransformations"] == [{"type": "scale", "scale": expected_scale}]


@pytest.mark.parametrize(
    ("shape", "chunks", "shards", "expected_chunks", "expected_shards"),
    [
        ((3, 5, 7), (2, 3, 4), (4, 6, 8), (2, 3, 4), (4, 6, 8)),
        ((3, 3, 5, 7), (2, 3, 4), None, (1, 2, 3, 4), (1, 4, 6, 8)),
        ((3, 3, 5, 7), (2, 2, 3, 4), (2, 4, 6, 8), (2, 2, 3, 4), (2, 4, 6, 8)),
    ],
)
def test_feature_from_numpy_honors_chunk_and_shard_overrides(
    shape,
    chunks,
    shards,
    expected_chunks,
    expected_shards,
):
    features = _MemoryFeatures()
    values = np.arange(math.prod(shape), dtype=np.int16).reshape(shape)

    features.from_numpy(values, chunks=chunks, shards=shards)

    _, array = _written_array(features)
    assert array.chunks == expected_chunks
    assert array.shards == expected_shards
    np.testing.assert_array_equal(array[:], values)


@pytest.mark.parametrize("shape", [(2, 3), (1, 2, 3, 4, 5)])
def test_feature_from_numpy_rejects_unsupported_dimensions(shape):
    features = _MemoryFeatures()
    with pytest.raises(ValueError, match="must be 3D .* or 4D"):
        features.from_numpy(np.zeros(shape))
    assert not features.store._store_dict


@pytest.mark.parametrize(
    ("shape", "chunks", "shards", "message"),
    [
        ((2, 3, 4), (2, 2), None, "chunk"),
        ((2, 3, 4, 5), (2, 2), None, "chunk"),
        ((2, 3, 4, 5), (1, 2, 2, 2), (2, 4, 4), "shards"),
    ],
)
def test_feature_from_numpy_rejects_dimension_mismatched_layouts(shape, chunks, shards, message):
    features = _MemoryFeatures()
    with pytest.raises(ValueError, match=message):
        features.from_numpy(np.zeros(shape), chunks=chunks, shards=shards)
    assert not features.store._store_dict


def test_feature_from_numpy_dtype_override_and_region_write():
    features = _MemoryFeatures()
    values = np.arange(2 * 3 * 4 * 5).reshape(2, 3, 4, 5)
    features.from_numpy(values, chunks=(2, 2, 2), dtype=np.float32)
    _, array = _written_array(features)
    layout_before = array.metadata.to_dict()

    replacement = np.full((1, 2, 2, 2), 99, dtype=np.float32)
    selection = (slice(1, 2), slice(1, 3), slice(1, 3), slice(1, 3))
    features.set_region(replacement, slices=selection)

    result = features.numpy()
    assert result.dtype == np.float32
    np.testing.assert_array_equal(result[selection], replacement)
    _, array = _written_array(features)
    assert array.metadata.to_dict() == layout_before


def test_feature_from_numpy_refuses_or_replaces_existing_data_explicitly():
    features = _MemoryFeatures()
    original = np.ones((3, 4, 5), dtype=np.float32)
    replacement = np.full((3, 4, 5), 2.0, dtype=np.float32)
    features.from_numpy(original)

    with pytest.raises(FileExistsError, match="not empty"):
        features.from_numpy(replacement, overwrite=False)

    np.testing.assert_array_equal(features.numpy(), original)
    features.from_numpy(replacement, overwrite=True)
    np.testing.assert_array_equal(features.numpy(), replacement)


def test_add_features_appends_shards_after_existing_parameters():
    parameters = list(inspect.signature(add_features).parameters)
    assert parameters[-1] == "shards"


def test_feature_from_numpy_overwrite_is_keyword_only_and_defaults_to_replace():
    parameter = inspect.signature(CopickFeatures.from_numpy).parameters["overwrite"]
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is True
