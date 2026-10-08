"""Tests for ops-level export functions."""

import os
from typing import Any, Dict

import copick
import mrcfile
import pytest
import zarr
from copick.ops.export import (
    export_picks,
    export_picks_combined,
    export_run,
    export_segmentation,
    export_tomogram,
)
from copick.util.ome import get_level_path


@pytest.fixture(params=pytest.common_cases)
def test_payload(request) -> Dict[str, Any]:
    payload = request.getfixturevalue(request.param)
    payload["root"] = copick.from_file(payload["cfg_file"])
    return payload


def _get_picks(test_payload):
    """Helper to get existing picks from the sample project."""
    root = test_payload["root"]
    for run in root.runs:
        picks_list = run.picks
        if picks_list:
            return picks_list[0], run
    return None, None


def _get_tomogram(test_payload):
    """Helper to get an existing tomogram from the sample project."""
    root = test_payload["root"]
    for run in root.runs:
        for vs in run.voxel_spacings:
            if vs.tomograms:
                return vs.tomograms[0], run
    return None, None


def _get_segmentation(test_payload):
    """Helper to get an existing segmentation from the sample project."""
    root = test_payload["root"]
    for run in root.runs:
        segs = run.segmentations
        if segs:
            return segs[0], run
    return None, None


class TestExportPicks:
    """Test cases for export_picks."""

    def test_export_picks_csv(self, test_payload, tmp_path):
        """Export picks to CSV format."""
        picks, run = _get_picks(test_payload)
        if picks is None:
            pytest.skip("No picks in sample project")

        output_path = str(tmp_path / "picks.csv")
        result = export_picks(picks, output_path, "csv", run_name=run.name)
        assert os.path.exists(result)
        assert os.path.getsize(result) > 0

    def test_export_picks_star(self, test_payload, tmp_path):
        """Export picks to STAR format."""
        picks, run = _get_picks(test_payload)
        if picks is None:
            pytest.skip("No picks in sample project")

        output_path = str(tmp_path / "picks.star")
        result = export_picks(picks, output_path, "star", voxel_spacing=10.0)
        assert os.path.exists(result)

    def test_export_picks_em(self, test_payload, tmp_path):
        """Export picks to EM format."""
        picks, run = _get_picks(test_payload)
        if picks is None:
            pytest.skip("No picks in sample project")

        output_path = str(tmp_path / "picks.em")
        result = export_picks(
            picks,
            output_path,
            "em",
            voxel_spacing=10.0,
        )
        assert os.path.exists(result)

    def test_export_picks_dynamo(self, test_payload, tmp_path):
        """Export picks to Dynamo format."""
        picks, run = _get_picks(test_payload)
        if picks is None:
            pytest.skip("No picks in sample project")

        output_path = str(tmp_path / "picks.tbl")
        result = export_picks(picks, output_path, "dynamo", voxel_spacing=10.0)
        assert os.path.exists(result)

    def test_export_picks_unsupported_format_raises(self, test_payload, tmp_path):
        """Unsupported format raises ValueError."""
        picks, _ = _get_picks(test_payload)
        if picks is None:
            pytest.skip("No picks in sample project")

        output_path = str(tmp_path / "picks.xyz")
        with pytest.raises(ValueError, match="Unsupported output format"):
            export_picks(picks, output_path, "xyz")

    def test_export_picks_em_missing_voxel_spacing_raises(self, test_payload, tmp_path):
        """EM export without voxel_spacing raises ValueError."""
        picks, _ = _get_picks(test_payload)
        if picks is None:
            pytest.skip("No picks in sample project")

        output_path = str(tmp_path / "picks.em")
        with pytest.raises(ValueError, match="voxel_spacing is required"):
            export_picks(picks, output_path, "em", voxel_spacing=None)

    def test_export_picks_star_missing_voxel_spacing_raises(self, test_payload, tmp_path):
        """STAR export without voxel_spacing raises ValueError."""
        picks, _ = _get_picks(test_payload)
        if picks is None:
            pytest.skip("No picks in sample project")

        output_path = str(tmp_path / "picks.star")
        with pytest.raises(ValueError, match="voxel_spacing is required"):
            export_picks(picks, output_path, "star", voxel_spacing=None)

    def test_export_picks_dynamo_missing_voxel_spacing_raises(self, test_payload, tmp_path):
        """Dynamo export without voxel_spacing raises ValueError."""
        picks, _ = _get_picks(test_payload)
        if picks is None:
            pytest.skip("No picks in sample project")

        output_path = str(tmp_path / "picks.tbl")
        with pytest.raises(ValueError, match="voxel_spacing is required"):
            export_picks(picks, output_path, "dynamo", voxel_spacing=None)


class TestExportTomogram:
    """Test cases for export_tomogram."""

    def test_export_tomogram_mrc(self, test_payload, tmp_path):
        """Export tomogram to MRC format."""
        tomo, _ = _get_tomogram(test_payload)
        if tomo is None:
            pytest.skip("No tomograms in sample project")

        output_path = str(tmp_path / "tomo.mrc")
        result = export_tomogram(tomo, output_path, "mrc")
        assert os.path.exists(result)
        with mrcfile.open(result) as mrc:
            assert mrc.data is not None

    def test_export_tomogram_tiff(self, test_payload, tmp_path):
        """Export tomogram to TIFF format."""
        tomo, _ = _get_tomogram(test_payload)
        if tomo is None:
            pytest.skip("No tomograms in sample project")

        output_path = str(tmp_path / "tomo.tiff")
        result = export_tomogram(tomo, output_path, "tiff")
        assert os.path.exists(result)

    def test_export_tomogram_zarr_all_levels(self, test_payload, tmp_path):
        """Export tomogram to Zarr with all pyramid levels."""
        tomo, _ = _get_tomogram(test_payload)
        if tomo is None:
            pytest.skip("No tomograms in sample project")

        output_path = str(tmp_path / "tomo.zarr")
        result = export_tomogram(tomo, output_path, "zarr", copy_all_levels=True)
        assert os.path.exists(result)
        out_group = zarr.open(result, mode="r")
        assert "0" in out_group

    def test_export_tomogram_zarr_single_level(self, test_payload, tmp_path):
        """Export tomogram to Zarr with only level 0."""
        tomo, _ = _get_tomogram(test_payload)
        if tomo is None:
            pytest.skip("No tomograms in sample project")

        output_path = str(tmp_path / "tomo_single.zarr")
        result = export_tomogram(tomo, output_path, "zarr", copy_all_levels=False)
        assert os.path.exists(result)
        out_group = zarr.open(result, mode="r")
        assert "0" in out_group

    @pytest.mark.parametrize("copy_all_levels", [False, True])
    def test_export_tomogram_zarr_refuses_existing_output(self, test_payload, tmp_path, copy_all_levels):
        tomo, _ = _get_tomogram(test_payload)
        if tomo is None:
            pytest.skip("No tomograms in sample project")

        output_path = str(tmp_path / "existing-tomo.zarr")
        existing = zarr.open_group(output_path, mode="w", zarr_format=2)
        existing.create_array("keep", shape=(3,), dtype="u1")

        with pytest.raises(FileExistsError, match="not empty"):
            export_tomogram(tomo, output_path, "zarr", copy_all_levels=copy_all_levels)

        assert list(zarr.open_group(output_path, mode="r").array_keys()) == ["keep"]

    def test_export_tomogram_unsupported_format_raises(self, test_payload, tmp_path):
        """Unsupported format raises ValueError."""
        tomo, _ = _get_tomogram(test_payload)
        if tomo is None:
            pytest.skip("No tomograms in sample project")

        output_path = str(tmp_path / "tomo.xyz")
        with pytest.raises(ValueError, match="Unsupported output format"):
            export_tomogram(tomo, output_path, "xyz")


class TestExportSegmentation:
    """Test cases for export_segmentation."""

    def test_export_segmentation_mrc(self, test_payload, tmp_path):
        """Export segmentation to MRC format."""
        seg, _ = _get_segmentation(test_payload)
        if seg is None:
            pytest.skip("No segmentations in sample project")

        output_path = str(tmp_path / "seg.mrc")
        result = export_segmentation(seg, output_path, "mrc")
        assert os.path.exists(result)

    def test_export_segmentation_tiff(self, test_payload, tmp_path):
        """Export segmentation to TIFF format."""
        seg, _ = _get_segmentation(test_payload)
        if seg is None:
            pytest.skip("No segmentations in sample project")

        output_path = str(tmp_path / "seg.tiff")
        result = export_segmentation(seg, output_path, "tiff")
        assert os.path.exists(result)

    def test_export_segmentation_em(self, test_payload, tmp_path):
        """Export segmentation to EM format."""
        seg, _ = _get_segmentation(test_payload)
        if seg is None:
            pytest.skip("No segmentations in sample project")

        output_path = str(tmp_path / "seg.em")
        result = export_segmentation(seg, output_path, "em")
        assert os.path.exists(result)

    def test_export_segmentation_zarr_all_levels(self, test_payload, tmp_path):
        """Export segmentation to Zarr with all levels."""
        seg, _ = _get_segmentation(test_payload)
        if seg is None:
            pytest.skip("No segmentations in sample project")

        output_path = str(tmp_path / "seg.zarr")
        result = export_segmentation(seg, output_path, "zarr", copy_all_levels=True)
        assert os.path.exists(result)

    def test_export_segmentation_zarr_single_level(self, test_payload, tmp_path):
        """Export segmentation to Zarr with single level."""
        seg, _ = _get_segmentation(test_payload)
        if seg is None:
            pytest.skip("No segmentations in sample project")

        output_path = str(tmp_path / "seg_single.zarr")
        result = export_segmentation(seg, output_path, "zarr", copy_all_levels=False)
        assert os.path.exists(result)
        out_group = zarr.open(result, mode="r")
        assert "0" in out_group

    @pytest.mark.parametrize("copy_all_levels", [False, True])
    def test_export_segmentation_zarr_refuses_existing_output(self, test_payload, tmp_path, copy_all_levels):
        seg, _ = _get_segmentation(test_payload)
        if seg is None:
            pytest.skip("No segmentations in sample project")

        output_path = str(tmp_path / "existing-seg.zarr")
        existing = zarr.open_group(output_path, mode="w", zarr_format=2)
        existing.create_array("keep", shape=(3,), dtype="u1")

        with pytest.raises(FileExistsError, match="not empty"):
            export_segmentation(seg, output_path, "zarr", copy_all_levels=copy_all_levels)

        assert list(zarr.open_group(output_path, mode="r").array_keys()) == ["keep"]

    def test_export_segmentation_unsupported_format_raises(self, test_payload, tmp_path):
        """Unsupported format raises ValueError."""
        seg, _ = _get_segmentation(test_payload)
        if seg is None:
            pytest.skip("No segmentations in sample project")

        output_path = str(tmp_path / "seg.xyz")
        with pytest.raises(ValueError, match="Unsupported output format"):
            export_segmentation(seg, output_path, "xyz")


class TestExportRun:
    """Test cases for export_run."""

    def test_export_run_picks_only(self, test_payload, tmp_path):
        """Batch export of picks from a run."""
        root = test_payload["root"]
        run = root.get_run("TS_001")
        output_dir = str(tmp_path / "export_picks")

        results = export_run(run, output_dir, picks_uri="*:*/*", output_format="csv")
        assert isinstance(results, dict)
        assert "picks" in results
        assert "errors" in results

    def test_export_run_tomograms_only(self, test_payload, tmp_path):
        """Batch export of tomograms from a run."""
        root = test_payload["root"]
        run = root.get_run("TS_001")
        output_dir = str(tmp_path / "export_tomos")

        results = export_run(run, output_dir, tomogram_uri="*@*", output_format="mrc")
        assert isinstance(results, dict)
        assert "tomograms" in results

    def test_export_run_all_types(self, test_payload, tmp_path):
        """Batch export with all URI types specified."""
        root = test_payload["root"]
        run = root.get_run("TS_001")
        output_dir = str(tmp_path / "export_all")

        results = export_run(
            run,
            output_dir,
            picks_uri="*:*/*",
            segmentation_uri="*:*/*@*",
            tomogram_uri="*@*",
            output_format="csv",
        )
        assert isinstance(results, dict)
        assert "picks" in results
        assert "segmentations" in results
        assert "tomograms" in results

    def test_export_run_no_uris(self, test_payload, tmp_path):
        """No URIs returns zero counts."""
        root = test_payload["root"]
        run = root.get_run("TS_001")
        output_dir = str(tmp_path / "export_none")

        results = export_run(run, output_dir)
        assert results["picks"] == 0
        assert results["segmentations"] == 0
        assert results["tomograms"] == 0


class TestExportPicksCombined:
    """Test cases for export_picks_combined."""

    def test_export_picks_combined_csv(self, test_payload, tmp_path):
        """Combined CSV export collects picks from all runs."""
        config = str(test_payload["cfg_file"])
        output_file = str(tmp_path / "combined.csv")

        try:
            result = export_picks_combined(
                config,
                output_file,
                picks_uri="*:*/*",
                output_format="csv",
            )
            assert os.path.exists(result)
        except ValueError as e:
            if "No picks found" in str(e):
                pytest.skip("No picks available for combined export")
            raise

    def test_export_picks_combined_csv_keeps_instance_ids(self, test_payload, tmp_path):
        """Combined CSV export writes each point's instance ID and score."""
        import numpy as np
        import pandas as pd

        root = test_payload["root"]
        picks = root.get_run("TS_001").new_picks(object_name="ribosome", user_id="combined-ids", session_id="1")
        picks.from_numpy(np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]), instance_ids=[3, 4], scores=[0.5, 0.6])

        output_file = str(tmp_path / "combined.csv")
        export_picks_combined(str(test_payload["cfg_file"]), output_file, "ribosome:combined-ids/1", "csv")

        df = pd.read_csv(output_file)
        assert df["instance_id"].tolist() == [3, 4]
        assert df["score"].tolist() == pytest.approx([0.5, 0.6])

    def test_export_picks_combined_star(self, test_payload, tmp_path):
        """Combined STAR export with voxel_spacing."""
        config = str(test_payload["cfg_file"])
        output_file = str(tmp_path / "combined.star")

        try:
            result = export_picks_combined(
                config,
                output_file,
                picks_uri="*:*/*",
                output_format="star",
                voxel_spacing=10.0,
            )
            assert os.path.exists(result)
        except ValueError as e:
            if "No picks found" in str(e):
                pytest.skip("No picks available for combined export")
            raise

    def test_export_picks_combined_missing_index_map_raises(self, test_payload, tmp_path):
        """EM combined export without run_to_index raises ValueError."""
        config = str(test_payload["cfg_file"])
        output_file = str(tmp_path / "combined.em")

        with pytest.raises(ValueError, match="run_to_index"):
            export_picks_combined(
                config,
                output_file,
                picks_uri="*:*/*",
                output_format="em",
                voxel_spacing=10.0,
                run_to_index=None,
            )

    def test_export_picks_combined_missing_voxel_spacing_raises(self, test_payload, tmp_path):
        """STAR combined export without voxel_spacing raises ValueError."""
        config = str(test_payload["cfg_file"])
        output_file = str(tmp_path / "combined.star")

        with pytest.raises(ValueError, match="voxel_spacing"):
            export_picks_combined(
                config,
                output_file,
                picks_uri="*:*/*",
                output_format="star",
                voxel_spacing=None,
            )


class TestExportSegmentationLabels:
    """Labels survive export, or the export refuses."""

    @staticmethod
    def _segmentation(test_payload, value):
        import numpy as np

        run = test_payload["root"].get_run("TS_001")
        seg = run.new_segmentation(
            name="labels",
            user_id="export",
            session_id=str(value),
            is_multilabel=True,
            voxel_size=10.0,
            exist_ok=True,
        )
        data = np.zeros((4, 4, 4), dtype=np.int64)
        data[1, 1, 1] = value
        seg.from_numpy(data)
        return seg

    @pytest.mark.parametrize(
        "value,dtype",
        [(300, "int16"), (40000, "uint16"), (70000, "float32")],
    )
    def test_mrc_keeps_labels(self, test_payload, tmp_path, value, dtype):
        seg = self._segmentation(test_payload, value)
        path = export_segmentation(seg, str(tmp_path / "seg.mrc"), "mrc")
        with mrcfile.open(path) as mrc:
            assert mrc.data.dtype == dtype
            assert mrc.data[1, 1, 1] == value

    def test_mrc_refuses_inexact_labels(self, test_payload, tmp_path):
        seg = self._segmentation(test_payload, 2**24 + 1)
        with pytest.raises(ValueError, match="cannot be written to MRC"):
            export_segmentation(seg, str(tmp_path / "seg.mrc"), "mrc")

    def test_em_keeps_large_labels(self, test_payload, tmp_path):
        import emfile

        seg = self._segmentation(test_payload, 2**24 + 1)
        path = export_segmentation(seg, str(tmp_path / "seg.em"), "em")
        _, data = emfile.read(path)
        assert data.dtype == "int32" and data.max() == 2**24 + 1


def test_export_run_keeps_segmentation_types_apart(test_payload, tmp_path):
    """A binary and an instance segmentation with the same key export to their own directories."""
    import numpy as np

    run = test_payload["root"].get_run("TS_001")
    run.new_segmentation(10.0, "ribosome", "88", user_id="exp").from_numpy(np.ones((4, 4, 4), dtype=np.uint8))
    run.new_segmentation(10.0, "ribosome", "88", user_id="exp", is_instance=True).from_numpy(
        np.full((4, 4, 4), 3, dtype=np.uint16),
    )
    results = export_run(run, str(tmp_path), segmentation_uri="ribosome:exp/88@10.0", output_format="tiff")
    assert results["segmentations"] == 1, results  # an untyped URI selects the binary one
    uri = "ribosome:exp/88@10.0?instance=true"
    assert export_run(run, str(tmp_path), segmentation_uri=uri, output_format="tiff")["segmentations"] == 1
    assert os.path.exists(tmp_path / "TS_001" / "Segmentations" / "ribosome_exp_88.tiff")
    assert os.path.exists(tmp_path / "TS_001" / "InstanceSegmentations" / "ribosome_exp_88.tiff")


def test_export_panoptic_segmentation(test_payload, tmp_path):
    """MRC, TIFF and EM hold one channel of a panoptic segmentation; Zarr keeps both."""
    import numpy as np
    from copick.util.formats import read_tiff_volume

    run = test_payload["root"].get_run("TS_001")
    data = np.zeros((2, 4, 4, 4), dtype=np.uint16)
    data[0, 1:3, 1:3, 1:3], data[1, 1:3, 1:3, 1:3] = 2, 5
    seg = run.new_segmentation(10.0, "cells", "4", user_id="exp", is_panoptic=True)
    seg.from_numpy(data)

    with pytest.raises(ValueError, match="--channel"):
        export_segmentation(seg, str(tmp_path / "pan.tif"), "tiff")
    path = export_segmentation(seg, str(tmp_path / "pan.tif"), "tiff", channel="instance")
    assert np.array_equal(read_tiff_volume(path), data[1])
    path = export_segmentation(seg, str(tmp_path / "pan.zarr"), "zarr")
    exported = zarr.open(path, mode="r")
    assert exported[get_level_path(exported, 0)].shape == (2, 4, 4, 4)

    results = export_run(
        run,
        str(tmp_path / "run"),
        segmentation_uri="cells:exp/4@10.0?panoptic=true",
        output_format="tiff",
    )
    assert results["segmentations"] == 1, results
    out = tmp_path / "run" / "TS_001" / "PanopticSegmentations"
    assert sorted(p.name for p in out.iterdir()) == ["cells_exp_4_instance.tiff", "cells_exp_4_label.tiff"]


# =============================================================================
# RELION coordinates: centered only, per-run tilt-series pixel sizes, the center's tomogram type
# =============================================================================


def _two_runs():
    import numpy as np

    return {
        "TS_A": (np.array([[100.0, 200.0, 300.0], [150.0, 250.0, 350.0]]), np.tile(np.eye(4), (2, 1, 1))),
        "TS_B": (np.array([[400.0, 300.0, 200.0]]), np.tile(np.eye(4), (1, 1, 1))),
    }


class TestRelionCoordinates:
    def test_centered_only(self):
        from copick.util.formats import build_relion_star_tables

        centers = {"TS_A": (300.0, 300.0, 100.0), "TS_B": (500.0, 500.0, 150.0)}
        particles, optics = build_relion_star_tables(
            _two_runs(),
            tomogram_centers=centers,
            tilt_series_pixel_size=2.0,
            coordinates="centered",
        )
        assert not {"rlnCoordinateX", "rlnCoordinateY", "rlnCoordinateZ"} & set(particles.columns)
        assert particles["rlnCenteredCoordinateXAngst"].tolist() == pytest.approx([-200.0, -150.0, -100.0])
        # The optics table still carries the tilt-series pixel size
        assert optics["rlnTomoTiltSeriesPixelSize"].tolist() == [2.0, 2.0]

        # "auto" adds rlnCoordinateX/Y/Z in tilt-series pixels
        auto, _ = build_relion_star_tables(_two_runs(), tomogram_centers=centers, tilt_series_pixel_size=2.0)
        assert auto["rlnCoordinateX"].tolist() == pytest.approx([50.0, 75.0, 200.0])

    def test_centered_needs_every_center(self):
        from copick.util.formats import build_relion_star_tables

        with pytest.raises(ValueError, match="No tomogram center for 1 run\\(s\\): TS_B"):
            build_relion_star_tables(
                _two_runs(),
                tomogram_centers={"TS_A": (300.0, 300.0, 100.0)},
                tilt_series_pixel_size=2.0,
                coordinates="centered",
            )
        # "auto" falls back to tilt-series pixels for every run
        particles, _ = build_relion_star_tables(
            _two_runs(),
            tomogram_centers={"TS_A": (300.0, 300.0, 100.0)},
            tilt_series_pixel_size=2.0,
        )
        assert "rlnCenteredCoordinateXAngst" not in particles.columns
        with pytest.raises(ValueError, match="coordinates must be one of"):
            build_relion_star_tables(_two_runs(), tilt_series_pixel_size=2.0, coordinates="pixels")

    def test_per_run_tilt_series_pixel_size(self):
        from copick.util.formats import build_relion_star_tables

        centers = {"TS_A": (300.0, 300.0, 100.0), "TS_B": (500.0, 500.0, 150.0)}
        particles, optics = build_relion_star_tables(
            _two_runs(),
            tomogram_centers=centers,
            tilt_series_pixel_size={"TS_A": 2.0, "TS_B": 4.0},
        )
        assert optics["rlnOpticsGroupName"].tolist() == ["TS_A", "TS_B"]
        assert optics["rlnTomoTiltSeriesPixelSize"].tolist() == [2.0, 4.0]
        assert particles["rlnOpticsGroup"].tolist() == [1, 1, 2]
        assert particles["rlnCoordinateX"].tolist() == pytest.approx([50.0, 75.0, 100.0])

        # A run without a value: no pixel coordinates and no optics table for any run
        particles, optics = build_relion_star_tables(
            _two_runs(),
            tomogram_centers=centers,
            tilt_series_pixel_size={"TS_A": 2.0},
        )
        assert optics is None
        assert "rlnCoordinateX" not in particles.columns
        assert "rlnCenteredCoordinateXAngst" in particles.columns

    def test_center_from_tomogram_type(self, test_payload, tmp_path):
        import numpy as np
        import starfile
        from copick.util.formats import get_tomogram_centers_from_copick
        from copick.util.relion import copick_tomogram_center

        root = test_payload["root"]
        run = root.get_run("TS_001")
        run.get_voxel_spacing(10.0).new_tomogram(tomo_type="center-test").from_numpy(
            np.zeros((20, 40, 80), dtype=np.float32),
            levels=1,
        )
        picks = run.new_picks(object_name="ribosome", user_id="center-test", session_id="1")
        picks.from_numpy(np.array([[500.0, 250.0, 120.0]]))

        assert get_tomogram_centers_from_copick(root, ["TS_001"], 10.0, "center-test")["TS_001"] == (
            400.0,
            200.0,
            100.0,
        )
        assert get_tomogram_centers_from_copick(root, ["TS_001"], None, "center-test")["TS_001"] == (
            400.0,
            200.0,
            100.0,
        )
        assert copick_tomogram_center(picks, 10.0, tomo_type="center-test") == (400.0, 200.0, 100.0)
        # No fallback to another type
        assert copick_tomogram_center(picks, 10.0, tomo_type="no-such-type") is None
        assert get_tomogram_centers_from_copick(root, ["TS_001"], 10.0, "no-such-type") == {}

        path = str(tmp_path / "typed.star")
        export_picks(picks, path, "star", voxel_spacing=10.0, tomo_type="center-test", coordinates="centered")
        particles = starfile.read(path)
        assert particles["rlnCenteredCoordinateXAngst"].tolist() == pytest.approx([100.0])
        assert particles["rlnCenteredCoordinateZAngst"].tolist() == pytest.approx([20.0])
        with pytest.raises(ValueError, match="No tomogram center"):
            export_picks(picks, path, "star", voxel_spacing=10.0, tomo_type="no-such-type", coordinates="centered")


# =============================================================================
# RELION import-coordinates layout and export_relion_particles
# =============================================================================


def _read_star(path):
    import starfile

    return starfile.read(path, always_dict=True)


class TestRelionImportBundle:
    def test_writer_splits_one_table(self, tmp_path, monkeypatch):
        from copick.util.formats import build_relion_star_tables, write_relion_import_bundle

        particles, _ = build_relion_star_tables(
            _two_runs(),
            tomogram_centers={"TS_A": (300.0, 300.0, 100.0), "TS_B": (500.0, 500.0, 150.0)},
            tilt_series_pixel_size=2.0,
            coordinates="centered",
        )
        assert "rlnOpticsGroup" in particles.columns
        monkeypatch.chdir(tmp_path)

        index_path, files = write_relion_import_bundle("Import/job001/particles.star", particles)

        # Paths are written as given: a relative job directory gives relative paths
        assert files == {"TS_A": "Import/job001/coordinates/TS_A.star", "TS_B": "Import/job001/coordinates/TS_B.star"}
        index = _read_star(index_path)
        assert list(index) == ["coordinate_files"]
        assert index["coordinate_files"]["rlnTomoName"].tolist() == ["TS_A", "TS_B"]
        assert index["coordinate_files"]["rlnTomoImportParticleFile"].tolist() == list(files.values())
        tables = [_read_star(path) for path in files.values()]
        assert [list(t) for t in tables] == [["particles"], ["particles"]]
        a, b = (t["particles"] for t in tables)
        assert list(a.columns) == list(b.columns)  # RELION appends the files, which needs identical columns
        assert "rlnOpticsGroup" not in a.columns
        assert a["rlnTomoName"].tolist() == ["TS_A", "TS_A"] and b["rlnTomoName"].tolist() == ["TS_B"]
        assert a["rlnCenteredCoordinateXAngst"].tolist() == pytest.approx([-200.0, -150.0])

        # No particles: an empty index
        index_path, files = write_relion_import_bundle("empty/particles.star", particles.iloc[:0])
        assert files == {}
        assert len(_read_star(index_path)["coordinate_files"]) == 0

    @pytest.mark.parametrize("name", ["a/b", "..", "."])
    def test_writer_refuses_names_that_are_not_file_names(self, tmp_path, name):
        import pandas as pd
        from copick.util.formats import write_relion_import_bundle

        with pytest.raises(ValueError, match="cannot name a coordinate file"):
            write_relion_import_bundle(str(tmp_path / "particles.star"), pd.DataFrame({"rlnTomoName": [name]}))


def _relion_export_picks(root):
    import numpy as np

    for run_name, points in (
        ("TS_001", [[100.0, 200.0, 300.0], [110.0, 210.0, 310.0]]),
        ("TS_002", [[50.0, 60.0, 70.0]]),
    ):
        picks = root.get_run(run_name).new_picks(object_name="ribosome", user_id="relion-export", session_id="1")
        picks.from_numpy(np.array(points))


class TestExportRelionParticles:
    def test_import_layout_and_report(self, test_payload, tmp_path):
        from copick.ops.export import export_relion_particles

        root = test_payload["root"]
        _relion_export_picks(root)

        result = export_relion_particles(
            str(test_payload["cfg_file"]),
            "ribosome:relion-export/1",
            str(tmp_path / "AutoPick" / "particles.star"),
            voxel_spacing=10.0,
            layout="import",
            tomogram_centers={"TS_002": (0.0, 0.0, 0.0)},
            coordinates="centered",
        )

        assert result.layout == "import" and not result.filament and result.polarity == {}
        assert result.rows["TS_001"] == 2 and result.rows["TS_002"] == 1
        assert set(result.rows) == {run.name for run in root.runs}  # every run considered, 0 for runs without picks
        assert set(result.files) == {"TS_001", "TS_002"}
        index = _read_star(result.path)["coordinate_files"]
        assert index["rlnTomoImportParticleFile"].tolist() == [result.files["TS_001"], result.files["TS_002"]]
        ts1 = _read_star(result.files["TS_001"])["particles"]
        ts2 = _read_star(result.files["TS_002"])["particles"]
        # TS_001's center from its copick tomogram (320 A); TS_002's from the caller
        assert ts1["rlnCenteredCoordinateXAngst"].tolist() == pytest.approx([-220.0, -210.0])
        assert ts2["rlnCenteredCoordinateZAngst"].tolist() == pytest.approx([70.0])
        assert "rlnCoordinateX" not in ts1.columns

    def test_particles_layout_with_per_run_pixel_sizes(self, test_payload, tmp_path):
        from copick.ops.export import export_relion_particles

        root = test_payload["root"]
        _relion_export_picks(root)
        result = export_relion_particles(
            root,
            "ribosome:relion-export/1",
            str(tmp_path / "particles.star"),
            voxel_spacing=10.0,
            run_names=["TS_001", "TS_002"],
            tilt_series_pixel_size={"TS_001": 2.0, "TS_002": 4.0},
        )
        assert result.files == {} and result.rows == {"TS_001": 2, "TS_002": 1}
        data = _read_star(result.path)
        assert data["optics"]["rlnTomoTiltSeriesPixelSize"].tolist() == [2.0, 4.0]
        assert data["particles"]["rlnCoordinateX"].tolist() == pytest.approx([50.0, 55.0, 12.5])

    def test_errors_raise_and_empty_exports(self, test_payload, tmp_path):
        from copick.ops.export import export_relion_particles

        root = test_payload["root"]
        with pytest.raises(ValueError, match="Unknown runs: no-such-run"):
            export_relion_particles(root, "*:*/*", str(tmp_path / "x.star"), run_names=["no-such-run"])
        with pytest.raises(ValueError, match="No picks found to export"):
            export_relion_particles(root, "ribosome:nobody/1", str(tmp_path / "x.star"), voxel_spacing=10.0)
        with pytest.raises(ValueError, match="layout must be one of"):
            export_relion_particles(root, "ribosome:nobody/1", str(tmp_path / "x.star"), layout="flat")

        empty = export_relion_particles(
            root,
            "ribosome:nobody/1",
            str(tmp_path / "empty" / "particles.star"),
            layout="import",
            allow_empty=True,
        )
        assert empty.files == {} and sum(empty.rows.values()) == 0
        assert len(_read_star(empty.path)["coordinate_files"]) == 0

        flat = export_relion_particles(
            root,
            "ribosome:nobody/1",
            str(tmp_path / "flat.star"),
            allow_empty=True,
        )
        particles = next(iter(_read_star(flat.path).values()))
        assert len(particles) == 0 and "rlnCenteredCoordinateXAngst" in particles.columns

    def test_filament_polarity_report(self, test_payload, tmp_path):
        import numpy as np
        from copick.ops.export import export_relion_particles

        root = test_payload["root"]
        root.new_object(name="microtubule", is_particle=True, radius=120, filament={"polar": True})
        run = root.get_run("TS_001")
        line = np.array([[100.0, 100.0, 300.0], [182.0, 100.0, 300.0]])
        transforms = np.tile(np.eye(4), (6, 1, 1))
        transforms[:, :3, :3] = np.array([[0.0, 0.0, 1.0], [0.0, 1.0, 0.0], [-1.0, 0.0, 0.0]])  # +Z along +x
        picks = run.new_picks(object_name="microtubule", user_id="cleaned", session_id="1")
        picks.from_numpy(
            np.vstack([line, line + [0, 100, 0], line + [0, 200, 0]]),
            transforms,
            instance_ids=[1, 1, 2, 2, 3, 3],
        )
        trace = run.new_filaments("microtubule", "1", user_id="trace")
        trace.from_numpy([line, line + [0, 100, 0], line + [0, 200, 0]], polarity_known=[True, False, False])

        result = export_relion_particles(
            root,
            "microtubule:cleaned/1",
            str(tmp_path / "AutoPick" / "particles.star"),
            voxel_spacing=10.0,
            layout="import",
            filaments_uri="microtubule:trace/1",
        )
        assert result.filament
        assert result.polarity["TS_001"].source == "microtubule:trace/1"
        assert (result.polarity["TS_001"].known, result.polarity["TS_001"].unknown) == (1, 2)
        particles = _read_star(result.files["TS_001"])["particles"]
        assert particles["rlnAnglePsiFlipRatio"].tolist() == [0.0, 0.0, 0.5, 0.5, 0.5, 0.5]
        assert particles["rlnHelicalTubeID"].tolist() == [1, 1, 2, 2, 3, 3]

        # Without a source under the picks' own URI: no source, every filament of unknown polarity
        result = export_relion_particles(root, "microtubule:cleaned/1", str(tmp_path / "p.star"), voxel_spacing=10.0)
        assert result.polarity["TS_001"].source is None
        assert (result.polarity["TS_001"].known, result.polarity["TS_001"].unknown) == (0, 3)

        # A pick whose filament is not in the source is an error (a fresh root, which reads the changed Filaments)
        trace.from_numpy([line, line + [0, 100, 0]], polarity_known=[True, False])
        root.save_config(test_payload["cfg_file"])
        with pytest.raises(ValueError, match=r"1 filament IDs of microtubule:cleaned/1 in TS_001 .* \[3\]"):
            export_relion_particles(
                str(test_payload["cfg_file"]),
                "microtubule:cleaned/1",
                str(tmp_path / "q.star"),
                voxel_spacing=10.0,
                filaments_uri="microtubule:trace/1",
            )

    def test_cli_import_layout(self, test_payload, tmp_path):
        from click.testing import CliRunner
        from copick.cli.export import export

        _relion_export_picks(test_payload["root"])
        index = str(tmp_path / "import" / "particles.star")
        args = ["picks", "-c", str(test_payload["cfg_file"]), "--picks-uri", "ribosome:relion-export/1"]
        args += ["--output-format", "star", "--voxel-size", "10.0", "--star-layout", "import"]

        result = CliRunner().invoke(export, [*args, "--output-file", index, "--coordinates", "centered"])
        assert result.exit_code == 0, result.output
        assert _read_star(index)["coordinate_files"]["rlnTomoName"].tolist() == ["TS_001", "TS_002"]
        assert os.path.exists(os.path.join(str(tmp_path), "import", "coordinates", "TS_001.star"))

        result = CliRunner().invoke(export, [*args, "--output-dir", str(tmp_path / "per-run")])
        assert result.exit_code != 0 and "--star-layout import" in result.output


def test_star_particles_block_is_named_without_optics(test_payload, tmp_path):
    """RELION reads `data_particles` by name; an unnamed `data_` block would hold zero particles for it."""
    from copick.ops.export import export_relion_particles

    root = test_payload["root"]
    _relion_export_picks(root)
    per_run = export_picks(
        root.get_run("TS_001").get_picks("ribosome", "relion-export", "1")[0],
        str(tmp_path / "a.star"),
        "star",
        voxel_spacing=10.0,
    )
    combined = export_relion_particles(root, "ribosome:relion-export/1", str(tmp_path / "b.star"), voxel_spacing=10.0)
    for path in (per_run, combined.path):
        assert list(_read_star(path)) == ["particles"]
        with open(path) as f:
            assert "data_particles" in f.read()
