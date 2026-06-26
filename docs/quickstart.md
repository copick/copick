# Quick Start

Get copick installed, open your first project, and see what you can do with it — in a few minutes.

## Install

copick runs on Python 3.10+ on Linux, macOS, and Windows. Install it with pip. The `all` extra pulls in the fsspec
backends copick is tested against (`local`, `s3`, `smb`, `ssh`); a separate `smb` extra is also available.

```shell
pip install "copick[all]"
```

!!! note
    `copick>=1.2.0` will fail to install with `pip~=25.1.0`. We recommend `pip>=25.2` or
    [`uv pip`](https://docs.astral.sh/uv/pip/) when installing copick.

## Open your first project

An example dataset is available on [Zenodo](https://doi.org/10.5281/zenodo.19686100).

1. Download and unpack the example dataset.
2. Point a config file at the unpacked `sample_project` directory:

    ```json
    {
        "name": "test",
        "description": "A test project.",
        "version": "1.0.0",

        "pickable_objects": [
            {
                "name": "proteasome",
                "is_particle": true,
                "pdb_id": "3J9I",
                "label": 1,
                "color": [255, 0, 0, 255],
                "radius": 60,
                "map_threshold": 0.0418
            },
            {
                "name": "ribosome",
                "is_particle": true,
                "pdb_id": "7P6Z",
                "label": 2,
                "color": [0, 255, 0, 255],
                "radius": 150,
                "map_threshold": 0.037
            },
            {
                "name": "membrane",
                "is_particle": false,
                "label": 3,
                "color": [0, 0, 0, 255]
            }
        ],

        // Change this path to the location of sample_project
        "overlay_root": "local:///PATH/TO/EXTRACTED/PROJECT/",

        "overlay_fs_args": {
            "auto_mkdir": true
        }
    }
    ```

3. Open the project and access the data through the copick API:

    ```python
    import zarr

    from copick.impl.filesystem import CopickRootFSSpec

    root = CopickRootFSSpec.from_file('path/to/filesystem_overlay_only.json')

    # Get a run, then a tomogram
    run = root.get_run("TS_001")
    tomogram = run.get_voxel_spacing(10).get_tomogram("wbp")

    # Access the image data
    group = zarr.open(tomogram.zarr())
    _, array = next(iter(group.arrays()))
    ```

!!! tip "Skip the `--config` flag"
    Set `export COPICK_CONFIG=/path/to/config.json` once and every `copick` command picks it up automatically.

## What can you do?

copick ships a toolbox of **processing tools** — convert between picks, segmentations, and meshes, clean up and filter
annotations, fit surfaces, and more — all from the command line. Scroll through a few, or browse the full gallery.

--8<-- "processing_carousel.snippet"

## Next steps

<div class="grid cards" markdown>

-   :fontawesome-solid-screwdriver-wrench:{ .lg .middle } __Processing tools__

    ---

    The full visual gallery of every convert / process / logical tool.

    [:octicons-arrow-right-24: Browse the gallery](processing_tools.md)

-   :fontawesome-solid-circle-nodes:{ .lg .middle } __Ecosystem tools__

    ---

    Viewers and apps that build on copick — ChimeraX, napari, the web, and more.

    [:octicons-arrow-right-24: Explore the ecosystem](tools.md)

-   :octicons-terminal-24:{ .lg .middle } __CLI reference__

    ---

    Every `copick` command, with options and examples.

    [:octicons-arrow-right-24: All commands](cli/index.md)

-   :fontawesome-solid-code:{ .lg .middle } __Python API__

    ---

    The object-oriented API for scripting copick projects.

    [:octicons-arrow-right-24: API reference](api_reference/api.md)

-   :fontawesome-solid-graduation-cap:{ .lg .middle } __Tutorials__

    ---

    Step-by-step, end-to-end workflows.

    [:octicons-arrow-right-24: Walk-throughs](examples/overview.md)

-   :fontawesome-solid-database:{ .lg .middle } __Other backends__

    ---

    Read from the CZ cryoET Data Portal or an mlcroissant manifest.

    [:octicons-arrow-right-24: Storage backends](#other-storage-backends)

</div>

## Other storage backends

Beyond local/fsspec-backed filesystem projects, copick supports:

- **[CZ cryoET Data Portal](examples/setup/data_portal.md)** — read from the
  portal API and write to any fsspec overlay.
- **[mlcroissant](examples/setup/croissant.md)** — read from a standards-compliant
  [Croissant 1.1](https://docs.mlcommons.org/croissant/docs/croissant-spec.html)
  manifest + CSV sidecars under a `Croissant/` subdirectory. Live auto-sync
  writes keep the manifest up to date as you annotate.
