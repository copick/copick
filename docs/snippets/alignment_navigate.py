"""Find the alignment and tilt series of a tomogram, and the alignments of a tilt series."""

import copick

root = copick.from_file("path/to/config.json")
run = root.get_run("TS_001")

# From a tomogram to the alignment it was reconstructed with, and on to the tilt series
tomogram = run.get_voxel_spacing(10.0).get_tomograms("wbp")[0]
alignment = tomogram.alignment
tilt_series = tomogram.tilt_series

# From a tilt series to its alignments: all of them, or only those from their authors (no placeholders), best first
tilt_series = run.get_tilt_series("raw")
for alignment in tilt_series.alignments:
    print(alignment.name, alignment.status, alignment.alignment_type, alignment.is_valid)
best = tilt_series.default_alignment

# Per-section parameters: refined tilt angle, in-plane rotation and shift (CETS frame, Angstrom)
for section in best.sections:
    print(section.section, section.tilt_angle, section.in_plane_rotation, section.shift_x, section.shift_y)
