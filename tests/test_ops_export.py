"""Tests for ops-level export functions."""

import os
from typing import Any, Dict

import mrcfile
import pytest
import zarr
from copick.impl.filesystem import CopickRootFSSpec
from copick.ops.export import (
    export_picks,
    export_picks_combined,
    export_run,
    export_segmentation,
    export_tomogram,
)


@pytest.fixture(params=pytest.common_cases)
def test_payload(request) -> Dict[str, Any]:
    payload = request.getfixturevalue(request.param)
    payload["root"] = CopickRootFSSpec.from_file(payload["cfg_file"])
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
        out_group = zarr.open(result)
        assert "0" in out_group

    def test_export_tomogram_zarr_single_level(self, test_payload, tmp_path):
        """Export tomogram to Zarr with only level 0."""
        tomo, _ = _get_tomogram(test_payload)
        if tomo is None:
            pytest.skip("No tomograms in sample project")

        output_path = str(tmp_path / "tomo_single.zarr")
        result = export_tomogram(tomo, output_path, "zarr", copy_all_levels=False)
        assert os.path.exists(result)
        out_group = zarr.open(result)
        assert "0" in out_group

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
        out_group = zarr.open(result)
        assert "0" in out_group

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
