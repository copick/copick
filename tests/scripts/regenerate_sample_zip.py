"""Regenerate the test sample_project.zip (the legacy, Zarr v2 tree).

Downloads the current sample_project.zip from Zenodo via pooch, extracts it, and
rebuilds the legacy project the copick test suite reads:

1. drops the Zarr v3 twin that the 2.0 line adds to the same archive
   (``*_v3`` paths and ``wbp_multifeature_features.zarr``), so the result is a
   legacy-only archive whichever version it started from;
2. adds the segmentation-type fixtures (an instance and a panoptic
   segmentation, see ``add_segmentation_type_fixtures``) with this copick;
3. replaces the configs' storage roots with placeholders, which every test
   fixture overwrites, so no path of the machine that built the archive ships;
4. re-exports ``sample_project/Croissant/`` with an empty ``copick:baseUrl`` so
   its URLs stay relative (portable across users' pooch caches);
5. refuses to pack if any metadata file still names a local path;
6. packs the archive with sorted entries and fixed timestamps, and prints its md5.

Two regenerations hold the same data but not the same bytes (the Croissant lists
rows in directory order, and compressed chunks may differ), so the md5 changes
from run to run; test the archive you upload.

Run it with the 1.x (``main``) line of copick, which writes the Zarr v2 stores
the legacy tree holds. The 2.0 line then builds its Zarr v3 twin from the
result with ``tests/scripts/build_v3_twin.py``; that archive is the one to
upload, and both lines' test configurations point at it.

Usage:
    python tests/scripts/regenerate_sample_zip.py [--output-dir /tmp] [--keep-workdir]
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Iterator

import numpy as np

CURRENT_DOI = "doi:10.5281/zenodo.23171726"
CURRENT_MD5 = "md5:fd2be0b41c2d82f0cddcbe693d9858d4"
ARCHIVE_NAME = "sample_project.zip"

#: Storage roots written into the shipped configs. The test fixtures replace both; the leaf names are kept because
#: the 2.0 line's twin builder maps them to ``*_v3``.
PLACEHOLDER_ROOT = "local:///PATH/TO/EXTRACTED"
PLACEHOLDER_ROOTS = {
    "overlay_root": f"{PLACEHOLDER_ROOT}/sample_overlay",
    "static_root": f"{PLACEHOLDER_ROOT}/sample_project",
}

#: Paths the Zarr v3 twin adds to the archive; the legacy tree never contains them.
TWIN_ARTIFACTS = (
    "sample_project_v3",
    "sample_overlay_v3",
    "filesystem_v3.json",
    "filesystem_overlay_only_v3.json",
    "wbp_multifeature_features.zarr",
)

# Fixed archive timestamp, so the same tree always packs to the same bytes.
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)

# Metadata files checked for local paths (chunk files are binary and skipped).
TEXT_SUFFIXES = {".json", ".csv", ".md", ".txt", ".yaml", ".yml", ".star", ".tsv"}
ZARR_METADATA = {".zattrs", ".zarray", ".zgroup", ".zmetadata", "zarr.json"}
LOCAL_PATH_MARKERS = ("/hpc/", "/home/", "/Users/", "/tmp/", "/scratch/", "/mnt/", "file://", "C:\\")


def md5_of(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def download_current_zip(target_dir: Path) -> Path:
    """Fetch the current Zenodo zip via pooch and return its path."""
    import pooch

    registry = pooch.create(
        path=target_dir,
        base_url=CURRENT_DOI,
        registry={ARCHIVE_NAME: CURRENT_MD5},
    )
    path = registry.fetch(ARCHIVE_NAME)
    return Path(path)


def strip_twin_artifacts(archive_top: Path) -> None:
    """Remove the Zarr v3 twin, if the downloaded archive carries one."""
    for name in TWIN_ARTIFACTS:
        path = archive_top / name
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()


@contextlib.contextmanager
def project_at(data_dir: Path, config_path: Path) -> Iterator[tuple]:
    """Open the project whose data lives at ``data_dir`` (as its overlay, so it is writable) with the pickable
    objects of ``config_path``. Yields ``(root, config)``; the temporary config file is removed afterwards."""
    import copick

    with open(config_path) as f:
        cfg = json.load(f)
    cfg["overlay_root"] = "local://" + str(data_dir)
    cfg["overlay_fs_args"] = {"auto_mkdir": True}
    cfg.pop("static_root", None)
    cfg.pop("static_fs_args", None)

    patched_path = data_dir / "_regen_config.json"
    with open(patched_path, "w") as f:
        json.dump(cfg, f)
    try:
        yield copick.from_file(str(patched_path)), cfg
    finally:
        patched_path.unlink(missing_ok=True)


def _sphere(shape, center, radius) -> np.ndarray:
    zz, yy, xx = np.indices(shape)
    return (zz - center[0]) ** 2 + (yy - center[1]) ** 2 + (xx - center[2]) ** 2 <= radius**2


def add_segmentation_type_fixtures(root) -> list:
    """Add one instance and one panoptic segmentation to run TS_002, deterministically.

    Same grid as the archive's other segmentations (64^3 at 10 A, three pyramid levels):

    - ``InstanceSegmentations/10.000_annotator_1_ribosome.zarr``: three ribosomes, IDs 1-3.
    - ``PanopticSegmentations/10.000_annotator_1_cell.zarr``: a membrane slab (label 3, no instance), the same three
      ribosomes (label 2, IDs 1-3, matching the instance segmentation) and one proteasome (label 1, ID 1).

    Returns:
        The written segmentations.
    """
    shape = (64, 64, 64)
    ribosomes = np.zeros(shape, dtype=np.uint16)
    for instance_id, center in enumerate([(16, 16, 16), (16, 44, 40), (40, 20, 44)], start=1):
        ribosomes[_sphere(shape, center, 7)] = instance_id

    labels = np.zeros(shape, dtype=np.uint16)
    instances = np.zeros(shape, dtype=np.uint16)
    labels[52:58, :, :] = root.get_object("membrane").label
    labels[ribosomes > 0] = root.get_object("ribosome").label
    instances[ribosomes > 0] = ribosomes[ribosomes > 0]
    proteasome = _sphere(shape, (40, 48, 16), 5)
    labels[proteasome] = root.get_object("proteasome").label
    instances[proteasome] = 1

    run = root.get_run("TS_002")
    instance = run.new_segmentation(10.0, "ribosome", "1", user_id="annotator", is_instance=True, exist_ok=True)
    instance.from_numpy(ribosomes, levels=3)
    panoptic = run.new_segmentation(10.0, "cell", "1", user_id="annotator", is_panoptic=True, exist_ok=True)
    panoptic.from_numpy(np.stack([labels, instances]), levels=3)

    assert instance.instance_ids().tolist() == [1, 2, 3]
    assert panoptic.segments() == [
        ("membrane", 0),
        ("proteasome", 1),
        ("ribosome", 1),
        ("ribosome", 2),
        ("ribosome", 3),
    ]
    return [instance, panoptic]


def export_croissant_for(root, cfg: dict, data_dir: Path) -> None:
    """Write ``data_dir/Croissant/`` with relative URLs, replacing an existing one."""
    from copick.ops.croissant import export_croissant

    export_croissant(
        root,
        project_root=str(data_dir),
        base_url="",  # relative URLs in CSVs and in distribution contentUrls
        dataset_name=cfg.get("name", "copick-sample"),
        description="Sample copick project used for mlcroissant backend tests.",
        force=True,
    )


def sanitize_configs(archive_top: Path) -> list:
    """Point every shipped config's storage roots at placeholders. Returns the configs rewritten."""
    rewritten = []
    for config_path in sorted(archive_top.glob("filesystem*.json")):
        cfg = json.loads(config_path.read_text())
        for key, placeholder in PLACEHOLDER_ROOTS.items():
            if key in cfg:
                cfg[key] = placeholder
        config_path.write_text(json.dumps(cfg, indent=4) + "\n")
        rewritten.append(config_path.name)
    return rewritten


def find_local_paths(archive_top: Path, forbidden: list) -> list:
    """Every metadata file that names a local path: one of ``forbidden`` (e.g. the build directory) or a common
    absolute-path prefix. Configs' storage roots must be the placeholders."""
    hits = []
    for path in sorted(archive_top.rglob("*")):
        if not path.is_file() or not (path.suffix in TEXT_SUFFIXES or path.name in ZARR_METADATA):
            continue
        text = path.read_text(errors="replace")
        found = [s for s in (*forbidden, *LOCAL_PATH_MARKERS) if s and s in text]
        if path.name.startswith("filesystem") and path.suffix == ".json":
            cfg = json.loads(text)
            found += [
                f"{key}={cfg[key]}"
                for key in PLACEHOLDER_ROOTS
                if key in cfg and not str(cfg[key]).startswith(PLACEHOLDER_ROOT)
            ]
        if found:
            hits.append(f"{path.relative_to(archive_top)}: {sorted(set(found))}")
    return hits


def pack(source: Path, output: Path) -> None:
    """Pack ``source`` (the archive's top level) reproducibly: sorted entries, fixed timestamps and modes, and every
    directory as an explicit entry, so empty ones such as ``sample_overlay/`` survive extraction."""
    if output.exists():
        output.unlink()
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


def main():
    parser = argparse.ArgumentParser(description="Regenerate copick's legacy sample_project.zip.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(tempfile.mkdtemp()),
        help="Directory to write the regenerated zip into (default: a temp dir).",
    )
    parser.add_argument(
        "--keep-workdir",
        action="store_true",
        help="Don't delete the intermediate extraction directory.",
    )
    args = parser.parse_args()

    import zarr

    if int(zarr.__version__.split(".")[0]) >= 3:
        raise SystemExit(
            "Run this with the 1.x (main) line of copick: the legacy tree holds Zarr v2 stores. The 2.0 line builds "
            "its twin from the result with build_v3_twin.py.",
        )

    workdir = Path(tempfile.mkdtemp(prefix="copick_regen_"))
    try:
        print(f"[1/6] Downloading current {ARCHIVE_NAME} from Zenodo ({CURRENT_DOI})...")
        zip_in = download_current_zip(workdir)
        print(f"       got {zip_in} ({zip_in.stat().st_size / 1e6:.1f} MiB)")

        extract_root = workdir / "extracted"
        extract_root.mkdir()
        print(f"[2/6] Extracting to {extract_root}...")
        with zipfile.ZipFile(zip_in) as zf:
            zf.extractall(extract_root)

        archive_top = _find_archive_top(extract_root)
        data_dir = archive_top / "sample_project"
        config_path = archive_top / "filesystem_overlay_only.json"
        if not data_dir.exists():
            raise FileNotFoundError(
                f"Expected sample_project/ data directory under {archive_top}; layout mismatch.",
            )
        if not config_path.exists():
            raise FileNotFoundError(f"No filesystem_overlay_only.json config found at {archive_top}.")
        strip_twin_artifacts(archive_top)

        print("[3/6] Adding the segmentation-type fixtures and re-exporting the Croissant...")
        with project_at(data_dir, config_path) as (root, cfg):
            for seg in add_segmentation_type_fixtures(root):
                print(f"       {seg.run.name}/{seg.directory}/{seg.filename} ({seg.segmentation_type})")
            export_croissant_for(root, cfg, data_dir)

        rewritten = sanitize_configs(archive_top)
        print(f"[4/6] Replaced storage roots with {PLACEHOLDER_ROOT}/... in {', '.join(rewritten)}")

        print("[5/6] Checking for local paths...")
        hits = find_local_paths(archive_top, [str(workdir), str(Path.home()), os.environ.get("USER", "")])
        if hits:
            raise RuntimeError("Local paths in the archive:\n  " + "\n  ".join(hits))

        args.output_dir.mkdir(parents=True, exist_ok=True)
        zip_out = args.output_dir / ARCHIVE_NAME
        print(f"[6/6] Packing {archive_top} to {zip_out}...")
        pack(archive_top, zip_out)

        new_md5 = md5_of(zip_out)
        print()
        print("==================================================================")
        print(f"Legacy archive: {zip_out}")
        print(f"Size: {zip_out.stat().st_size / 1e6:.1f} MiB")
        print(f"md5:  {new_md5}")
        print()
        print("Next steps:")
        print("  1. On the 2.0 line, add the Zarr v3 twin:")
        print(f"       python tests/scripts/build_v3_twin.py {zip_out} --output <dir>/sample_project.zip")
        print("  2. Upload that archive to Zenodo as a new version of the sample project record.")
        print("  3. Point both lines at the new DOI and md5 in tests/corpus_registry.py.")
        print("==================================================================")

    finally:
        if not args.keep_workdir:
            shutil.rmtree(workdir, ignore_errors=True)


def _find_archive_top(extract_root: Path) -> Path:
    """Locate the archive's top-level directory.

    Some zips have a single top-level subfolder that contains all the real
    entries (e.g. ``extract_root/sample_project/{sample_project, sample_overlay,
    filesystem.json, ...}``). Others extract flat (everything directly under
    ``extract_root``). Return the path that actually contains
    ``filesystem*.json`` and ``sample_project/``.
    """
    candidates = [extract_root]
    entries = [p for p in extract_root.iterdir() if p.is_dir()]
    if len(entries) == 1:
        candidates.append(entries[0])
    for c in candidates:
        has_config = any(c.glob("filesystem*.json"))
        has_data = (c / "sample_project").is_dir()
        if has_config and has_data:
            return c
    # Fallback: return whatever has filesystem.json somewhere
    for c in candidates:
        if any(c.glob("filesystem*.json")):
            return c
    return extract_root


if __name__ == "__main__":
    main()
