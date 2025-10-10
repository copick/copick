import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict

import pytest

# Use the existing CLEANUP setting from conftest
from conftest import CLEANUP
from copick.ops.deposit import deposit


def _count_symlinks(directory: Path) -> int:
    """Count total number of symlinks in a directory recursively."""
    count = 0
    if not directory.exists():
        return count
    for item in directory.rglob("*"):
        if item.is_symlink():
            count += 1
    return count


def _verify_symlink_target(symlink_path: Path, source_root: Path) -> bool:
    """Verify that a symlink points to a valid file in the source root."""
    if not symlink_path.is_symlink():
        return False
    target = symlink_path.resolve()
    if not target.exists():
        return False
    # Check if target is within source root
    try:
        target.relative_to(source_root)
        return True
    except ValueError:
        return False


def _get_deposited_runs(target_dir: Path) -> list:
    """Get list of run names in the deposit directory."""
    exp_runs_dir = target_dir / "ExperimentRuns"
    if not exp_runs_dir.exists():
        return []
    return [d.name for d in exp_runs_dir.iterdir() if d.is_dir()]


def _check_directory_structure(target_dir: Path, expected_runs: list) -> bool:
    """Verify the deposit directory structure matches expectations."""
    exp_runs_dir = target_dir / "ExperimentRuns"
    if not exp_runs_dir.exists():
        return False

    deposited_runs = _get_deposited_runs(target_dir)
    return set(deposited_runs) == set(expected_runs)


@pytest.fixture(params=["local_overlay_only", "local"])
def test_payload(request) -> Dict[str, Any]:
    """Test deposit only with local filesystem configurations.

    Deposit operations require local filesystems because they create symlinks,
    which are not supported by remote filesystems (S3, SSH, SMB, etc.).
    """
    from copick.impl.filesystem import CopickRootFSSpec

    payload = request.getfixturevalue(request.param)
    payload["root"] = CopickRootFSSpec.from_file(payload["cfg_file"])
    return payload


def test_deposit_basic_picks_and_meshes(test_payload: Dict[str, Any]):
    """Test basic deposit with all picks and meshes."""
    temp_deposit = Path(tempfile.mkdtemp())

    try:
        deposit(
            config=str(test_payload["cfg_file"]),
            target_dir=str(temp_deposit),
            picks_uris=["*:*/*"],
            meshes_uris=["*:*/*"],
            n_workers=4,
        )

        # Verify ExperimentRuns directory exists
        assert (temp_deposit / "ExperimentRuns").exists(), "ExperimentRuns directory not created"

        # Verify all runs are deposited
        deposited_runs = _get_deposited_runs(temp_deposit)
        assert "TS_001" in deposited_runs, "TS_001 not deposited"
        assert "TS_002" in deposited_runs, "TS_002 not deposited"
        assert "TS_003" in deposited_runs, "TS_003 not deposited"

        # Verify picks directory and symlinks for TS_001
        picks_dir = temp_deposit / "ExperimentRuns" / "TS_001" / "Picks"
        assert picks_dir.exists(), "Picks directory not created for TS_001"

        picks = list(picks_dir.glob("*.json"))
        assert len(picks) > 0, "No picks deposited for TS_001"

        # Verify all picks are symlinks
        for pick in picks:
            assert pick.is_symlink(), f"{pick.name} is not a symlink"
            assert pick.resolve().exists(), f"Symlink target for {pick.name} does not exist"

        # Verify meshes directory and symlinks for TS_001
        meshes_dir = temp_deposit / "ExperimentRuns" / "TS_001" / "Meshes"
        assert meshes_dir.exists(), "Meshes directory not created for TS_001"

        meshes = list(meshes_dir.glob("*.glb"))
        assert len(meshes) > 0, "No meshes deposited for TS_001"

        # Verify all meshes are symlinks
        for mesh in meshes:
            assert mesh.is_symlink(), f"{mesh.name} is not a symlink"
            assert mesh.resolve().exists(), f"Symlink target for {mesh.name} does not exist"

    finally:
        if CLEANUP:
            shutil.rmtree(temp_deposit)


def test_deposit_filtered_picks_by_object(test_payload: Dict[str, Any]):
    """Test deposit with filtered picks by object name."""
    temp_deposit = Path(tempfile.mkdtemp())

    try:
        deposit(
            config=str(test_payload["cfg_file"]),
            target_dir=str(temp_deposit),
            picks_uris=["proteasome:*/*"],  # Only proteasome picks
            n_workers=4,
        )

        # Verify TS_001 picks
        picks_dir = temp_deposit / "ExperimentRuns" / "TS_001" / "Picks"
        if picks_dir.exists():
            picks = list(picks_dir.glob("*.json"))

            # All picks should contain "proteasome" in name
            for pick in picks:
                assert "proteasome" in pick.name, f"Non-proteasome pick found: {pick.name}"

    finally:
        if CLEANUP:
            shutil.rmtree(temp_deposit)


def test_deposit_filtered_picks_by_user(test_payload: Dict[str, Any]):
    """Test deposit with filtered picks by user."""
    temp_deposit = Path(tempfile.mkdtemp())

    try:
        deposit(
            config=str(test_payload["cfg_file"]),
            target_dir=str(temp_deposit),
            picks_uris=["*:gapstop/*"],  # Only gapstop user
            n_workers=4,
        )

        # Verify TS_001 picks
        picks_dir = temp_deposit / "ExperimentRuns" / "TS_001" / "Picks"
        if picks_dir.exists():
            picks = list(picks_dir.glob("*.json"))

            # All picks should start with "gapstop"
            for pick in picks:
                assert pick.name.startswith("gapstop_"), f"Non-gapstop pick found: {pick.name}"

    finally:
        if CLEANUP:
            shutil.rmtree(temp_deposit)


def test_deposit_segmentations_with_voxel_size(test_payload: Dict[str, Any]):
    """Test deposit of segmentations with voxel size filter."""
    temp_deposit = Path(tempfile.mkdtemp())

    try:
        deposit(
            config=str(test_payload["cfg_file"]),
            target_dir=str(temp_deposit),
            segmentations_uris=["*:*/*@10.0"],  # Only 10.0 voxel size
            n_workers=4,
        )

        # Verify TS_001 segmentations
        seg_dir = temp_deposit / "ExperimentRuns" / "TS_001" / "Segmentations"
        if seg_dir.exists():
            segs = list(seg_dir.glob("*.zarr"))

            # All segmentations should start with "10.000_"
            for seg in segs:
                assert seg.name.startswith("10.000_"), f"Wrong voxel size segmentation: {seg.name}"

    finally:
        if CLEANUP:
            shutil.rmtree(temp_deposit)


def test_deposit_tomograms(test_payload: Dict[str, Any]):
    """Test deposit of tomograms with tomo_type filter."""
    temp_deposit = Path(tempfile.mkdtemp())

    try:
        deposit(
            config=str(test_payload["cfg_file"]),
            target_dir=str(temp_deposit),
            tomograms_uris=["wbp@10.0"],  # Only wbp tomograms at 10.0
            n_workers=4,
        )

        # Verify TS_001 tomograms
        tomo_dir = temp_deposit / "ExperimentRuns" / "TS_001" / "VoxelSpacing10.000"
        if tomo_dir.exists():
            tomos = list(tomo_dir.glob("*.zarr"))

            # Should have wbp.zarr
            wbp_found = any(t.name == "wbp.zarr" for t in tomos)
            assert wbp_found, "wbp.zarr not found in deposited tomograms"

    finally:
        if CLEANUP:
            shutil.rmtree(temp_deposit)


def test_deposit_run_name_filtering(test_payload: Dict[str, Any]):
    """Test depositing specific runs only."""
    temp_deposit = Path(tempfile.mkdtemp())

    try:
        deposit(
            config=str(test_payload["cfg_file"]),
            target_dir=str(temp_deposit),
            run_names=["TS_001", "TS_002"],  # Only these runs
            picks_uris=["*:*/*"],
            n_workers=4,
        )

        deposited_runs = _get_deposited_runs(temp_deposit)

        # Only TS_001 and TS_002 should be deposited
        assert "TS_001" in deposited_runs, "TS_001 not deposited"
        assert "TS_002" in deposited_runs, "TS_002 not deposited"
        assert "TS_003" not in deposited_runs, "TS_003 should not be deposited"

    finally:
        if CLEANUP:
            shutil.rmtree(temp_deposit)


def test_deposit_run_name_prefix(test_payload: Dict[str, Any]):
    """Test depositing with run name prefix."""
    temp_deposit = Path(tempfile.mkdtemp())
    prefix = "test_prefix_"

    try:
        deposit(
            config=str(test_payload["cfg_file"]),
            target_dir=str(temp_deposit),
            run_name_prefix=prefix,
            picks_uris=["*:*/*"],
            n_workers=4,
        )

        deposited_runs = _get_deposited_runs(temp_deposit)

        # All runs should have the prefix
        for run in deposited_runs:
            assert run.startswith(prefix), f"Run {run} does not have prefix {prefix}"

        # Original run names should be present with prefix
        assert f"{prefix}TS_001" in deposited_runs, "Prefixed TS_001 not found"
        assert f"{prefix}TS_002" in deposited_runs, "Prefixed TS_002 not found"
        assert f"{prefix}TS_003" in deposited_runs, "Prefixed TS_003 not found"

    finally:
        if CLEANUP:
            shutil.rmtree(temp_deposit)


def test_deposit_run_name_regex(test_payload: Dict[str, Any]):
    """Test depositing with run name regex extraction."""
    temp_deposit = Path(tempfile.mkdtemp())

    try:
        # Use regex to extract just "TS_001" from "TS_001" (identity in this case)
        deposit(
            config=str(test_payload["cfg_file"]),
            target_dir=str(temp_deposit),
            run_name_regex=r"^(TS_\d+).*",  # Extract TS_XXX part
            picks_uris=["*:*/*"],
            n_workers=4,
        )

        deposited_runs = _get_deposited_runs(temp_deposit)

        # Should have extracted run names
        assert len(deposited_runs) > 0, "No runs deposited"
        assert "TS_001" in deposited_runs, "TS_001 not found"

    finally:
        if CLEANUP:
            shutil.rmtree(temp_deposit)


def test_deposit_idempotency(test_payload: Dict[str, Any]):
    """Test that running deposit twice is idempotent."""
    temp_deposit = Path(tempfile.mkdtemp())

    try:
        # First deposit
        deposit(
            config=str(test_payload["cfg_file"]),
            target_dir=str(temp_deposit),
            picks_uris=["*:*/*"],
            n_workers=4,
        )

        # Count symlinks after first deposit
        first_count = _count_symlinks(temp_deposit)
        assert first_count > 0, "No symlinks created in first deposit"

        # Second deposit (should be idempotent)
        deposit(
            config=str(test_payload["cfg_file"]),
            target_dir=str(temp_deposit),
            picks_uris=["*:*/*"],
            n_workers=4,
        )

        # Count symlinks after second deposit
        second_count = _count_symlinks(temp_deposit)

        # Counts should be the same
        assert first_count == second_count, "Deposit is not idempotent"

    finally:
        if CLEANUP:
            shutil.rmtree(temp_deposit)


def test_deposit_multiple_projects_same_target(test_payload: Dict[str, Any]):
    """Test depositing multiple projects to the same target directory."""
    temp_deposit = Path(tempfile.mkdtemp())

    try:
        # First deposit with prefix1
        deposit(
            config=str(test_payload["cfg_file"]),
            target_dir=str(temp_deposit),
            run_name_prefix="proj1_",
            picks_uris=["*:*/*"],
            n_workers=4,
        )

        # Second deposit with prefix2
        deposit(
            config=str(test_payload["cfg_file"]),
            target_dir=str(temp_deposit),
            run_name_prefix="proj2_",
            picks_uris=["*:*/*"],
            n_workers=4,
        )

        deposited_runs = _get_deposited_runs(temp_deposit)

        # Should have both sets of runs
        proj1_runs = [r for r in deposited_runs if r.startswith("proj1_")]
        proj2_runs = [r for r in deposited_runs if r.startswith("proj2_")]

        assert len(proj1_runs) > 0, "No proj1 runs deposited"
        assert len(proj2_runs) > 0, "No proj2 runs deposited"

        # Both should have TS_001
        assert "proj1_TS_001" in deposited_runs, "proj1_TS_001 not found"
        assert "proj2_TS_001" in deposited_runs, "proj2_TS_001 not found"

    finally:
        if CLEANUP:
            shutil.rmtree(temp_deposit)


def test_deposit_features(test_payload: Dict[str, Any]):
    """Test deposit of features."""
    temp_deposit = Path(tempfile.mkdtemp())

    try:
        deposit(
            config=str(test_payload["cfg_file"]),
            target_dir=str(temp_deposit),
            features_uris=["wbp@10.0:*"],  # All features for wbp at 10.0
            n_workers=4,
        )

        # Verify TS_001 features
        features_dir = temp_deposit / "ExperimentRuns" / "TS_001" / "VoxelSpacing10.000"
        if features_dir.exists():
            features = list(features_dir.glob("*_features.zarr"))

            # Should have feature files
            if len(features) > 0:
                # Verify they are symlinks
                for feature in features:
                    assert feature.is_symlink(), f"{feature.name} is not a symlink"
                    assert feature.resolve().exists(), f"Symlink target for {feature.name} does not exist"

    finally:
        if CLEANUP:
            shutil.rmtree(temp_deposit)


def test_deposit_empty_uris(test_payload: Dict[str, Any]):
    """Test deposit with no URIs (should not create anything)."""
    temp_deposit = Path(tempfile.mkdtemp())

    try:
        deposit(
            config=str(test_payload["cfg_file"]),
            target_dir=str(temp_deposit),
            # No URI parameters provided
            n_workers=4,
        )

        # When no URIs are provided, nothing should be deposited
        # The ExperimentRuns directory may or may not exist depending on implementation
        # but there should be no symlinks
        symlink_count = _count_symlinks(temp_deposit)
        assert symlink_count == 0, f"Expected no symlinks but found {symlink_count}"

        # If ExperimentRuns exists, it should be empty or have empty run directories
        exp_runs_dir = temp_deposit / "ExperimentRuns"
        if exp_runs_dir.exists():
            deposited_runs = _get_deposited_runs(temp_deposit)
            # Even if run directories exist, they should have no content symlinks
            for run_name in deposited_runs:
                run_dir = exp_runs_dir / run_name
                run_symlinks = sum(1 for _ in run_dir.rglob("*") if _.is_symlink())
                assert run_symlinks == 0, f"Run {run_name} has unexpected symlinks"

    finally:
        if CLEANUP:
            shutil.rmtree(temp_deposit)


def test_deposit_parallel_processing(test_payload: Dict[str, Any]):
    """Test deposit with different worker counts."""
    temp_deposit = Path(tempfile.mkdtemp())

    try:
        # Test with different worker counts
        for n_workers in [1, 4, 8]:
            # Clean up from previous iteration
            if temp_deposit.exists():
                shutil.rmtree(temp_deposit)
            temp_deposit.mkdir()

            deposit(
                config=str(test_payload["cfg_file"]),
                target_dir=str(temp_deposit),
                picks_uris=["*:*/*"],
                meshes_uris=["*:*/*"],
                n_workers=n_workers,
            )

            # Verify all runs deposited
            deposited_runs = _get_deposited_runs(temp_deposit)
            assert len(deposited_runs) == 3, f"Not all runs deposited with {n_workers} workers"

            # Verify picks exist
            picks_dir = temp_deposit / "ExperimentRuns" / "TS_001" / "Picks"
            assert picks_dir.exists(), f"Picks not deposited with {n_workers} workers"

    finally:
        if CLEANUP:
            shutil.rmtree(temp_deposit)


def test_deposit_combined_filters(test_payload: Dict[str, Any]):
    """Test deposit with multiple URI filters combined."""
    temp_deposit = Path(tempfile.mkdtemp())

    try:
        deposit(
            config=str(test_payload["cfg_file"]),
            target_dir=str(temp_deposit),
            picks_uris=["proteasome:*/*", "ribosome:gapstop/*"],
            meshes_uris=["membrane:*/*"],
            segmentations_uris=["*:*/*@10.0"],
            tomograms_uris=["wbp@10.0", "denoised@10.0"],
            n_workers=4,
        )

        # Verify TS_001 has expected content
        run_dir = temp_deposit / "ExperimentRuns" / "TS_001"
        assert run_dir.exists(), "TS_001 not deposited"

        # Check picks
        picks_dir = run_dir / "Picks"
        if picks_dir.exists():
            picks = list(picks_dir.glob("*.json"))
            # Should have proteasome and ribosome (from gapstop) picks
            pick_names = [p.name for p in picks]
            has_proteasome = any("proteasome" in name for name in pick_names)
            has_ribosome = any("ribosome" in name and "gapstop" in name for name in pick_names)
            assert has_proteasome or has_ribosome, "Expected picks not found"

        # Check meshes
        meshes_dir = run_dir / "Meshes"
        if meshes_dir.exists():
            meshes = list(meshes_dir.glob("*.glb"))
            # Should have membrane meshes
            has_membrane = any("membrane" in m.name for m in meshes)
            assert has_membrane, "Membrane mesh not found"

    finally:
        if CLEANUP:
            shutil.rmtree(temp_deposit)
