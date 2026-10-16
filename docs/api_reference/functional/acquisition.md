# Acquisition Formats

The `copick.ops.acquisition` module imports tilt series, alignments and CTF fits from the files of AreTomo3, Warp,
RELION 5, IMOD, CTFFIND4 and SerialEM, and exports them to these formats. `copick.util.acquisition_formats` reads the
files, maps their rows to tilt-series sections and converts alignments between the tools' frames and copick's CETS
frame (see [Geometry](../../geometry.md#75-importing-and-exporting-alignments)).

## Import

::: copick.ops.acquisition.add_tilt_series_from_file
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick.ops.acquisition.add_alignment_from_file
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick.ops.acquisition.add_ctf_from_file
    options:
        show_root_heading: true
        show_root_full_path: true

## Export

::: copick.ops.acquisition.export_tilt_series
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick.ops.acquisition.export_alignment
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick.ops.acquisition.export_alignments
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick.ops.acquisition.export_ctf
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick.ops.acquisition.write_relion_alignments
    options:
        show_root_heading: true
        show_root_full_path: true

## Formats

::: copick.util.acquisition_formats.open_stack
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick.util.acquisition_formats.read_angles
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick.util.acquisition_formats.read_mdoc
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick.util.acquisition_formats.read_ctf
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick.util.acquisition_formats.read_native_alignment
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick.util.acquisition_formats.map_rows
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick.util.acquisition_formats.native_to_copick
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick.util.acquisition_formats.copick_to_native
    options:
        show_root_heading: true
        show_root_full_path: true

::: copick.util.acquisition_formats.rebase_sections
    options:
        show_root_heading: true
        show_root_full_path: true
