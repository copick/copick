"""Unit tests for copick.util.segmentation: label dtypes and segmentation store names."""

import numpy as np
import pytest
from copick.util.segmentation import (
    checked_label_cast,
    label_dtype,
    parse_segmentation_store_name,
    segmentation_directory,
    segmentation_store_name,
    segmentation_type,
)


@pytest.mark.parametrize(
    "is_multilabel,is_instance,suffix,directory",
    [
        (False, False, "", "Segmentations"),
        (True, False, "-multilabel", "Segmentations"),
        (False, True, "", "InstanceSegmentations"),
    ],
)
def test_store_name_round_trip(is_multilabel, is_instance, suffix, directory):
    name = segmentation_store_name(
        10.0,
        "tracer",
        "7",
        "microtubule",
        is_multilabel=is_multilabel,
        is_instance=is_instance,
    )
    assert name == f"10.000_tracer_7_microtubule{suffix}.zarr"
    assert segmentation_directory(is_multilabel, is_instance) == directory
    assert parse_segmentation_store_name(name, directory) == {
        "voxel_size": 10.0,
        "user_id": "tracer",
        "session_id": "7",
        "name": "microtubule",
        "is_multilabel": is_multilabel,
        "is_instance": is_instance,
    }


def test_store_name_type_is_the_suffix_only():
    # A user, session or name merely containing a type word does not change the type.
    parsed = parse_segmentation_store_name("10.000_multilabel-tool_instance-run_membrane-x.zarr")
    assert parsed["user_id"] == "multilabel-tool" and parsed["name"] == "membrane-x"
    assert not parsed["is_multilabel"] and not parsed["is_instance"]


@pytest.mark.parametrize(
    "store_name",
    ["garbage.zarr", "10.0_too_few.zarr", "abc_user_session_name.zarr", "10.0_user_session_-multilabel.zarr"],
)
def test_store_name_unparsable(store_name):
    assert parse_segmentation_store_name(store_name) is None


def test_type_is_the_directory_outside_segmentations():
    # In InstanceSegmentations every store is an instance segmentation, whatever its name ends in.
    parsed = parse_segmentation_store_name("10.000_u_s_vesicle-multilabel.zarr", "InstanceSegmentations")
    assert parsed["is_instance"] and not parsed["is_multilabel"] and parsed["name"] == "vesicle-multilabel"
    with pytest.raises(ValueError):
        parse_segmentation_store_name("10.000_u_s_n.zarr", "Picks")


def test_segmentation_type_exclusive():
    assert segmentation_type(False, False) == "binary"
    with pytest.raises(ValueError):
        segmentation_type(True, True)
    with pytest.raises(ValueError):
        segmentation_store_name(1.0, "u", "s", "n", is_multilabel=True, is_instance=True)


def test_label_dtype():
    assert label_dtype(np.array([0, 1])) == np.uint8
    assert label_dtype(np.array([0, 1]), floor=np.uint16) == np.uint16
    assert label_dtype(np.array([0, 70000])) == np.uint32
    assert label_dtype(np.array([0.0, 2.0])) == np.uint8
    assert label_dtype(np.array([True, False])) == np.uint8
    with pytest.raises(ValueError, match="non-negative"):
        label_dtype(np.array([-1, 2]))
    with pytest.raises(ValueError, match="finite"):
        label_dtype(np.array([np.nan]))


def test_checked_label_cast():
    data = np.array([0, 300])
    assert checked_label_cast(data, np.uint16).dtype == np.uint16
    with pytest.raises(ValueError, match="do not fit uint8"):
        checked_label_cast(data, np.uint8)
    assert checked_label_cast(np.array([2**24]), np.float32)[0] == 2**24
    with pytest.raises(ValueError, match="not exactly representable"):
        checked_label_cast(np.array([2**24 + 1]), np.float32)
    with pytest.raises(ValueError, match="do not fit bool"):
        checked_label_cast(np.array([0, 2]), bool)
    assert checked_label_cast(data, None) is data
