"""Regenerate the test sample_project.zip with an added Croissant/ directory.

Downloads the current sample_project.zip from Zenodo via pooch, extracts it,
loads the filesystem project, runs `export_croissant` with an empty
`copick:baseUrl` so the generated Croissant is self-relative (portable across
users' pooch caches), repacks the zip, and prints the md5 for the user to
upload to Zenodo as a new version.

Usage:
    python copick/tests/scripts/regenerate_sample_zip.py \
        [--output-dir /tmp] [--overlay-too]

After the upload, update `copick/tests/conftest.py:18-25` with the new DOI
and md5.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
import zipfile
from pathlib import Path

CURRENT_DOI = "doi:10.5281/zenodo.19686100"
CURRENT_MD5 = "md5:8b8941350af1f621effd4903e75255c0"
ARCHIVE_NAME = "sample_project.zip"


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


def ensure_croissant_for(data_dir: Path, config_path: Path) -> None:
    """Load the filesystem project whose config lives at ``config_path`` and
    whose data lives at ``data_dir``, then write ``data_dir/Croissant/``."""
    import copick
    from copick.ops.croissant import export_croissant

    with open(config_path) as f:
        cfg = json.load(f)
    # Patch overlay_root so copick.from_file resolves to the extracted data dir
    cfg["overlay_root"] = "local://" + str(data_dir)
    cfg["overlay_fs_args"] = {"auto_mkdir": True}
    # Ensure we only use the overlay-only config (no static) so the export sees
    # the data at data_dir
    cfg.pop("static_root", None)
    cfg.pop("static_fs_args", None)

    patched_path = data_dir / "_regen_config.json"
    with open(patched_path, "w") as f:
        json.dump(cfg, f)

    try:
        root = copick.from_file(str(patched_path))
        # Empty base_url => shipped Croissant URLs are relative, portable.
        export_croissant(
            root,
            project_root=str(data_dir),
            base_url="",  # relative URLs in CSVs and in distribution contentUrls
            dataset_name=cfg.get("name", "copick-sample"),
            description="Sample copick project used for mlcroissant backend tests.",
        )
    finally:
        patched_path.unlink(missing_ok=True)


def repack_zip(source_dir: Path, zip_path: Path) -> None:
    """Pack ``source_dir`` contents into ``zip_path``, with the archive rooted at
    ``source_dir`` itself (top-level entries map to the archive's top-level).

    Empty directories are preserved as explicit directory entries (trailing
    slash), matching the layout of the original Zenodo archive. This matters
    because the copick test suite expects certain empty directories (e.g.
    ``sample_overlay/``) to exist after extraction.
    """
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for child in sorted(source_dir.rglob("*")):
            arcname = str(child.relative_to(source_dir))
            if child.is_dir():
                # Include every directory as an explicit entry; this keeps empty
                # directories (otherwise dropped by ZipFile.write on files only).
                zf.writestr(arcname.rstrip("/") + "/", b"")
            elif child.is_file():
                zf.write(child, arcname)


def main():
    parser = argparse.ArgumentParser(description="Regenerate copick sample_project.zip with Croissant/.")
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

    workdir = Path(tempfile.mkdtemp(prefix="copick_regen_"))
    try:
        print(f"[1/4] Downloading current {ARCHIVE_NAME} from Zenodo ({CURRENT_DOI})...")
        zip_in = download_current_zip(workdir)
        print(f"       got {zip_in} ({zip_in.stat().st_size / 1e6:.1f} MiB)")

        extract_root = workdir / "extracted"
        extract_root.mkdir()
        print(f"[2/4] Extracting to {extract_root}...")
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
            candidates = sorted(archive_top.glob("filesystem*.json"))
            if not candidates:
                raise FileNotFoundError(
                    f"No filesystem*.json config found at {archive_top}.",
                )
            config_path = candidates[0]

        print(f"       archive top: {archive_top}")
        print(f"       data dir:    {data_dir}")
        print(f"       config:      {config_path}")

        print(f"[3/4] Running export_croissant on {data_dir}...")
        ensure_croissant_for(data_dir, config_path)
        print(f"       wrote {data_dir / 'Croissant' / 'metadata.json'}")

        args.output_dir.mkdir(parents=True, exist_ok=True)
        zip_out = args.output_dir / ARCHIVE_NAME
        print(f"[4/4] Repacking {archive_top} to {zip_out}...")
        # Preserve the original archive top-level layout.
        repack_zip(archive_top, zip_out)

        new_md5 = md5_of(zip_out)
        print()
        print("==================================================================")
        print(f"Regenerated archive: {zip_out}")
        print(f"Size: {zip_out.stat().st_size / 1e6:.1f} MiB")
        print(f"md5:  {new_md5}")
        print()
        print("Next steps:")
        print(f"  1. Upload {zip_out.name} to Zenodo as a new version of record 19686100.")
        print("  2. Note the new DOI (e.g. 10.5281/zenodo.<NEW>).")
        print("  3. Update copick/tests/conftest.py:18-25:")
        print('         base_url="doi:10.5281/zenodo.<NEW>",')
        print(f'         registry={{"sample_project.zip": "md5:{new_md5}"}},')
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
