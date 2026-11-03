"""Tilt series on every storage backend."""

import logging
from typing import Any, Dict

import copick
import numpy as np
import pytest
import zarr
from cets_schema import validate_tilt_series_block
from copick.models import CopickCTF, CopickTiltImage, CopickTiltSeries, CopickTiltSeriesMetadata
from copick.util.cets import COPICK_ATTRS_KEY
from copick.util.ome import (
    TILT_SERIES_CHUNKS,
    get_pixel_size_from_zarr,
    get_voxel_size_from_zarr,
    write_ome_zarr_tilt_series,
)
from pydantic import ValidationError

SHAPE = (5, 70, 96)
PIXEL_SIZE = 1.5401


@pytest.fixture(params=pytest.common_cases)
def test_payload(request) -> Dict[str, Any]:
    payload = request.getfixturevalue(request.param)
    payload["root"] = copick.from_file(payload["cfg_file"])
    return payload


def _stack(shape=SHAPE, seed=0) -> np.ndarray:
    return np.random.default_rng(seed).random(shape, dtype=np.float32)


def _metadata(n=SHAPE[0], height=SHAPE[1], width=SHAPE[2], pixel_size=PIXEL_SIZE) -> CopickTiltSeriesMetadata:
    order = [2, 1, 3, 0, 4, 5, 6][:n]
    return CopickTiltSeriesMetadata(
        pixel_size=pixel_size,
        width=width,
        height=height,
        tilt_axis_angle=85.3,
        voltage=300.0,
        spherical_aberration=2.7,
        amplitude_contrast=0.07,
        amplitude_contrast_source="user",
        images=[
            CopickTiltImage(
                section=i,
                nominal_tilt_angle=-6.0 + 3.0 * i,
                acquisition_order=order[i],
                accumulated_dose=3.5 * order[i],
                exposure_dose=3.5,
                frame_path=f"TS_001_{i:03d}.eer",
                ctf=CopickCTF(defocus_u=31000.0 + 10 * i, defocus_v=30000.0, defocus_angle=12.0, fit_resolution=7.0),
            )
            for i in range(n)
        ],
    )


def _fresh_run(payload, name="TS_001"):
    return copick.from_file(payload["cfg_file"]).get_run(name)


def test_new_tilt_series_pyramid(test_payload: Dict[str, Any]):
    from skimage.transform import downscale_local_mean

    run = test_payload["root"].get_run("TS_001")
    assert run.tilt_series == []

    ts = run.new_tilt_series("raw")
    assert ts.metadata is None and ts.shape is None and ts.n_sections == 0

    data = _stack()
    ts.from_numpy(data, pixel_size=PIXEL_SIZE)
    assert ts.pixel_size == 1.54
    assert ts.shape == SHAPE

    group = zarr.open_group(ts.zarr(), mode="r")
    level0, level1, level2 = (group[str(i)][:] for i in range(3))
    assert level0.shape == SHAPE and level1.shape == (5, 35, 48) and level2.shape == (5, 18, 24)
    np.testing.assert_array_equal(level0, data)
    np.testing.assert_allclose(level1, downscale_local_mean(level0, (1, 2, 2)), atol=1e-6)
    np.testing.assert_allclose(level2, downscale_local_mean(level1, (1, 2, 2)), atol=1e-6)
    assert all(group[str(i)].chunks == TILT_SERIES_CHUNKS for i in range(3))
    assert all(group[str(i)].dtype == np.float32 for i in range(3))

    multiscales = group.attrs["multiscales"][0]
    assert [a["name"] for a in multiscales["axes"]] == ["z", "y", "x"]
    assert all(a["type"] == "space" and a["unit"] == "angstrom" for a in multiscales["axes"])
    scales = [d["coordinateTransformations"][0]["scale"] for d in multiscales["datasets"]]
    assert scales == [[1.54, 1.54, 1.54], [1.54, 3.08, 3.08], [1.54, 6.16, 6.16]]
    assert get_voxel_size_from_zarr(group) == pytest.approx(1.54)
    assert get_pixel_size_from_zarr(group, level=2) == pytest.approx(6.16)
    validate_tilt_series_block(group.attrs[COPICK_ATTRS_KEY])

    fresh = _fresh_run(test_payload)
    assert [t.ts_type for t in fresh.tilt_series] == ["raw"]
    reread = fresh.get_tilt_series("raw")
    np.testing.assert_array_equal(reread.numpy(), data)
    np.testing.assert_array_equal(reread.numpy(zarr_group="1", sections=slice(1, 3)), level1[1:3])
    np.testing.assert_array_equal(reread.section(4), data[4])
    assert reread.metadata.pixel_size == 1.54 and reread.metadata.images == []


def test_tilt_series_metadata_roundtrip(test_payload: Dict[str, Any]):
    run = test_payload["root"].get_run("TS_001")
    ts = run.new_tilt_series("raw")
    metadata = _metadata()
    ts.from_numpy(_stack(), metadata=metadata)

    reread = _fresh_run(test_payload).get_tilt_series("raw").metadata
    assert reread == metadata
    assert reread.ctf_status == "fitted"
    assert reread.nominal_tilt_angles == [-6.0, -3.0, 0.0, 3.0, 6.0]

    # Editing and storing again
    edited = reread.model_copy(update={"voltage": 200.0})
    edited.images[2].ctf = None
    fresh_ts = _fresh_run(test_payload).get_tilt_series("raw")
    fresh_ts.store_metadata(edited)
    stored = _fresh_run(test_payload).get_tilt_series("raw").metadata
    assert stored.voltage == 200.0 and stored.ctf_status == "partial"

    group = zarr.open_group(fresh_ts.zarr(), mode="r")
    validate_tilt_series_block(group.attrs[COPICK_ATTRS_KEY])


def test_from_numpy_keeps_or_replaces_metadata(test_payload: Dict[str, Any], caplog):
    ts = test_payload["root"].get_run("TS_001").new_tilt_series("raw")
    ts.from_numpy(_stack(), metadata=_metadata())

    # Same geometry: the per-image metadata is kept
    ts.from_numpy(_stack(seed=1))
    assert _fresh_run(test_payload).get_tilt_series("raw").metadata == _metadata()

    # Different geometry: replaced by the image geometry, with a warning
    with caplog.at_level(logging.WARNING):
        ts.from_numpy(_stack(shape=(4, 32, 32)))
    metadata = _fresh_run(test_payload).get_tilt_series("raw").metadata
    assert metadata.images == [] and (metadata.width, metadata.height, metadata.pixel_size) == (32, 32, 1.54)
    assert "does not fit" in caplog.text


def test_tilt_series_metadata_must_fit(test_payload: Dict[str, Any]):
    run = test_payload["root"].get_run("TS_001")
    ts = run.new_tilt_series("raw")

    with pytest.raises(ValueError, match="pixel size"):
        ts.from_numpy(_stack())
    with pytest.raises(ValueError, match="holds no images"):
        ts.store_metadata(_metadata())
    with pytest.raises(ValueError, match="does not fit"):
        ts.from_numpy(_stack(), metadata=_metadata(n=4))
    with pytest.raises(ValueError, match="differs"):
        ts.from_numpy(_stack(), pixel_size=2.0, metadata=_metadata())
    with pytest.raises(ValueError, match="a tilt series must have shape|must have shape"):
        ts.from_numpy(np.zeros((4, 4)), pixel_size=1.0)

    ts.from_numpy(_stack(), pixel_size=PIXEL_SIZE)
    with pytest.raises(ValueError, match="does not fit"):
        ts.store_metadata(_metadata(width=95))
    with pytest.raises(ValueError, match="pixel size"):
        ts.store_metadata(_metadata(pixel_size=2.0))
    with pytest.raises(ValidationError):
        CopickTiltSeriesMetadata(pixel_size=1.0, width=4, height=4, images=[CopickTiltImage(section=2)])


def test_tilt_series_names(test_payload: Dict[str, Any]):
    run = test_payload["root"].get_run("TS_001")
    first = run.new_tilt_series("raw")
    assert run.new_tilt_series("raw", exist_ok=True) is first
    with pytest.raises(ValueError, match="already exists"):
        run.new_tilt_series("raw")
    with pytest.raises(ValueError, match="'@'"):
        run.new_tilt_series("raw@2")
    run.new_tilt_series("dose_weighted")
    assert sorted(t.ts_type for t in run.tilt_series) == ["dose-weighted", "raw"]
    assert [t.ts_type for t in run.get_tilt_series_list(["raw"])] == ["raw"]
    assert run.get_tilt_series("missing") is None
    assert "len(tilt_series)=2" in repr(run)


def test_listing_does_not_open_stores(test_payload: Dict[str, Any], monkeypatch):
    run = test_payload["root"].get_run("TS_001")
    for ts_type in ("raw", "aligned"):
        run.new_tilt_series(ts_type).from_numpy(_stack(shape=(2, 8, 8)), pixel_size=1.0)

    def refuse(*args, **kwargs):
        raise AssertionError("listing tilt series must not open their stores")

    monkeypatch.setattr(zarr, "open", refuse)
    monkeypatch.setattr(zarr, "open_group", refuse)
    monkeypatch.setattr(zarr.storage, "FSStore", refuse)
    assert sorted(t.ts_type for t in _fresh_run(test_payload).tilt_series) == ["aligned", "raw"]


def test_delete_and_refresh_tilt_series(test_payload: Dict[str, Any]):
    run = test_payload["root"].get_run("TS_001")
    run.new_tilt_series("raw").from_numpy(_stack(shape=(2, 8, 8)), pixel_size=1.0)
    run.new_tilt_series("aligned").from_numpy(_stack(shape=(2, 8, 8)), pixel_size=1.0)

    other = _fresh_run(test_payload)
    assert len(other.tilt_series) == 2
    run.delete_tilt_series("raw")
    assert [t.ts_type for t in run.tilt_series] == ["aligned"]
    assert [t.ts_type for t in _fresh_run(test_payload).tilt_series] == ["aligned"]

    if getattr(other.root, "mode", None) == "A":
        # A Croissant index is read once per root; changes by another root need a reload
        other.root.index.reload()
    other.refresh()
    assert [t.ts_type for t in other.tilt_series] == ["aligned"]
    other._invalidate_caches()
    assert other._tilt_series is None

    run.get_tilt_series("aligned").delete()
    assert run.tilt_series == []
    assert _fresh_run(test_payload).tilt_series == []


def test_static_tilt_series_are_read_only(test_payload: Dict[str, Any], tmp_path):
    from copick.impl.filesystem import CopickRootFSSpec

    root = test_payload["root"]
    if test_payload["testfs_static"] is None or not isinstance(root, CopickRootFSSpec):
        pytest.skip("needs a separate static filesystem source")

    # Build the store locally and upload it into the static source
    local = tmp_path / "raw.zarr"
    data = _stack()
    write_ome_zarr_tilt_series(zarr.storage.DirectoryStore(str(local), dimension_separator="/"), data, 1.54)
    directory = test_payload["testpath_static"] / "ExperimentRuns" / "TS_001" / "TiltSeries"
    test_payload["testfs_static"].put(str(local), str(directory / "raw.zarr"), recursive=True)

    run = _fresh_run(test_payload)
    (ts,) = run.tilt_series
    assert ts.read_only and isinstance(ts, CopickTiltSeries)
    np.testing.assert_array_equal(ts.numpy(), data)
    # No copick block: the metadata is derived from the OME-Zarr metadata
    assert (ts.metadata.pixel_size, ts.metadata.width, ts.metadata.height, ts.metadata.images) == (1.54, 96, 70, [])

    with pytest.raises(PermissionError):
        ts.from_numpy(data, pixel_size=1.54)
    with pytest.raises(PermissionError):
        ts.set_region(data[:1], sections=slice(0, 1))
    with pytest.raises(PermissionError):
        ts.store_metadata(_metadata(pixel_size=1.54))
    with pytest.raises(PermissionError):
        ts.delete()

    # A writable tilt series of another type sits next to it
    run.new_tilt_series("denoised").from_numpy(data, pixel_size=1.54)
    assert sorted((t.ts_type, t.read_only) for t in _fresh_run(test_payload).tilt_series) == [
        ("denoised", False),
        ("raw", True),
    ]


def test_croissant_mode_a_index_rows(test_payload: Dict[str, Any]):
    root = test_payload["root"]
    if getattr(root, "mode", None) != "A":
        pytest.skip("needs a self-contained (Mode A) Croissant project")

    run = root.get_run("TS_001")
    ts = run.new_tilt_series("raw")
    ts.from_numpy(_stack(shape=(2, 8, 8)), metadata=_metadata(n=2, height=8, width=8))
    rows = [r for r in root.index.tilt_series if r["run"] == "TS_001"]
    assert rows == [
        {
            "run": "TS_001",
            "ts_type": "raw",
            "url": "ExperimentRuns/TS_001/TiltSeries/raw.zarr",
            "portal_tiltseries_id": None,
        },
    ]

    root.index.reload()
    assert [r["ts_type"] for r in root.index.tilt_series] == ["raw"]
    reread = _fresh_run(test_payload).get_tilt_series("raw")
    assert reread.metadata == _metadata(n=2, height=8, width=8)

    reread.delete()
    assert copick.from_file(test_payload["cfg_file"]).index.tilt_series == []
