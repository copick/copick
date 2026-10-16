"""Build the CryoET Data Portal test fixture for tilt series, alignments and CTF.

Converts a recorded run of dataset 10445 (``10445_TS_105_5.json`` from the cets-cryoet-data-portal test data, recorded
from the portal API) into the payloads copick's portal backend fetches: the client's ``to_dict()`` records, under the
keys of ``copick.util.portal_cache.DATA_KEYS`` (``annotations``) and ``ACQUISITION_DATA_KEYS`` (``acquisition``).
Identifiers of records the recording does not carry (voxel spacings, per-section rows, frames) are synthetic.

Usage::

    python tests/scripts/make_portal_acquisition_fixture.py path/to/10445_TS_105_5.json
"""

import argparse
import json
from pathlib import Path

OUTPUT = Path(__file__).resolve().parents[1] / "data" / "portal" / "10445_TS_105_5.json"
S3 = "s3://cryoet-data-portal-public/"
HTTPS = "https://files.cryoetdataportal.cziscience.com/"


def _s3(url):
    return None if url is None else url.replace(HTTPS, S3)


def build(recorded):
    run_id, ts_id = recorded["run_id"], recorded["tiltseries_id"]
    width, height, n_sections = recorded["size"]
    alignment = recorded["alignments"][0]
    hub = alignment["hub"]

    voxel_spacings = {}
    tomograms = []
    for tomogram in recorded["tomograms"]:
        vs_id = recorded["tomogram_voxel_spacing_ids"][str(tomogram["id"])]
        voxel_spacings[vs_id] = {"id": vs_id, "run_id": run_id, "voxel_spacing": tomogram["voxel_spacing"]}
        size_x, size_y, size_z = tomogram["size"]
        tomograms.append(
            {
                "id": tomogram["id"],
                "alignment_id": alignment["id"],
                "run_id": run_id,
                "tomogram_voxel_spacing_id": vs_id,
                "voxel_spacing": tomogram["voxel_spacing"],
                "size_x": size_x,
                "size_y": size_y,
                "size_z": size_z,
                "reconstruction_method": tomogram["reconstruction_method"],
                "processing": tomogram["processing"],
                "processing_software": tomogram.get("processing_software"),
                "reconstruction_software": tomogram.get("reconstruction_software"),
                "ctf_corrected": tomogram["ctf_corrected"],
                "is_portal_standard": tomogram["is_portal_standard"],
                "s3_omezarr_dir": _s3(tomogram["https_omezarr_dir"]),
                "https_omezarr_dir": tomogram["https_omezarr_dir"],
            },
        )

    annotations = {
        "runs": [{"id": run_id, "name": recorded["run_name"], "dataset_id": recorded["dataset_id"]}],
        "annotation_files": [],
        "annotation_shapes": [],
        "annotations": [],
        "annotation_authors": [],
        "voxel_spacings": list(voxel_spacings.values()),
        "tomograms": tomograms,
        "tomogram_authors": [],
    }

    per_section, frames = [], []
    for section in recorded["sections"]:
        z = section["z_index"]
        frames.append(
            {
                "id": 2000 + z,
                "run_id": run_id,
                "acquisition_order": section["acquisition_order_1b"] - 1,
                "accumulated_dose": section["accumulated_dose"],
                "exposure_dose": section["exposure_dose"],
                "s3_frame_path": _s3(section["frame_url"]),
                "https_frame_path": section["frame_url"],
            },
        )
        per_section.append(
            {
                "id": 1000 + z,
                "z_index": z,
                "raw_angle": section["raw_angle"],
                "frame_id": 2000 + z,
                "tiltseries_id": ts_id,
                "run_id": run_id,
                "major_defocus": section["major_defocus_a"],
                "minor_defocus": section["minor_defocus_a"],
                "astigmatic_angle": section["astigmatic_angle_deg"],
                "phase_shift": section["phase_shift_rad"],
                "max_resolution": None,
            },
        )

    volume, offset = hub["volume_dimension"], hub["volume_offset"]
    acquisition = {
        "tiltseries": [
            {
                "id": ts_id,
                "run_id": run_id,
                "s3_omezarr_dir": _s3(recorded["https_omezarr_dir"]),
                "https_omezarr_dir": recorded["https_omezarr_dir"],
                "https_mrc_file": recorded["https_mrc_file"],
                "pixel_spacing": recorded["pixel_spacing"],
                "size_x": width,
                "size_y": height,
                "size_z": n_sections,
                "is_aligned": recorded["is_aligned"],
                "acceleration_voltage": int(round(recorded["voltage_kv"] * 1000)),
                "spherical_aberration_constant": recorded["cs_mm"],
                "tilt_axis": recorded["tilt_axis_deg"],
            },
        ],
        "alignments": [
            {
                "id": alignment["id"],
                "run_id": run_id,
                "tiltseries_id": ts_id,
                "alignment_type": alignment["alignment_type"],
                "alignment_method": alignment["alignment_method"],
                "volume_x_dimension": volume["x"],
                "volume_y_dimension": volume["y"],
                "volume_z_dimension": volume["z"],
                "volume_x_offset": offset["x"],
                "volume_y_offset": offset["y"],
                "volume_z_offset": offset["z"],
                "x_rotation_offset": hub["x_rotation_offset"],
                "tilt_offset": hub["tilt_offset"],
                # The API returns the matrix as a Postgres array literal
                "affine_transformation_matrix": "{{1,0,0,0},{0,1,0,0},{0,0,1,0},{0,0,0,1}}",
                "https_alignment_metadata": alignment["https_alignment_metadata"],
                "is_portal_standard": alignment["is_portal_standard"],
            },
        ],
        "per_section_alignment_parameters": [
            {"id": 3000 + p["z_index"], "alignment_id": alignment["id"], **p}
            for p in hub["per_section_alignment_parameters"]
        ],
        "per_section_parameters": per_section,
        "frames": frames,
    }
    return {
        "source": "10445_TS_105_5.json (cets-cryoet-data-portal tests)",
        "annotations": annotations,
        "acquisition": acquisition,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("recorded", type=Path)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(build(json.loads(args.recorded.read_text())), indent=1) + "\n")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
