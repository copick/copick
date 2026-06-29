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

A copick project is described by a small JSON **config file**. The `copick config`
commands build one for you — no hand-editing required. Pick the tab that matches where
your data lives.

=== "From the CZ cryoET Data Portal"

    Build a project that streams tomograms and annotations straight from the
    [CZ cryoET Data Portal](https://cryoetdataportal.czscience.com/) — no downloads. Here
    we use [dataset 10301](https://cryoetdataportal.czscience.com/datasets/10301):

    ```shell
    copick config dataportal --dataset-id 10301 --overlay ./overlay --output config.json
    ```

    The pickable object types are discovered from the dataset automatically, so the
    tomograms **and** the existing (read-only) portal annotations are ready to use right
    away. Anything you create is written to the local `./overlay` directory. Pass
    `--dataset-id` more than once to combine several datasets into one project.

=== "From your own tomograms"

    Build a local project and import your own reconstructions. Each tomogram is converted
    to a multiscale OME-Zarr pyramid so it streams efficiently.

    ```shell
    # 1. Create a local project and declare the objects you'll annotate.
    #    --objects format: name,is_particle,[radius],[pdb_id]  (repeat per object)
    copick config filesystem \
        --config config.json \
        --overlay-root ./my_project \
        --objects ribosome,True,150,7P6Z \
        --objects membrane,False \
        --proj-name my-project --proj-description "My cryo-ET dataset"

    # 2. Import a tomogram (file type and voxel size are read from the MRC header;
    #    the run is named after the file unless you pass --run).
    copick add tomogram TS_001.mrc --config config.json --tomo-type wbp

    # 3. Or batch-import a whole folder of MRCs (run name taken from each filename).
    copick add tomogram "tomograms/*.mrc" --config config.json --tomo-type wbp
    ```

    copick also imports tomograms and picks from RELION and Dynamo — see the
    [`add` CLI reference](cli/add/index.md).

!!! tip "Skip the `--config` flag"
    Set `export COPICK_CONFIG=/path/to/config.json` once and every `copick` command picks it up automatically.

## See your data

With a `config.json` in hand, here are three ways to dig in.

**Browse in the terminal.** Explore runs, tomograms, picks, meshes, and segmentations in
an interactive TUI:

```shell
copick browse --config config.json
```

**Script it with Python.** The object-oriented API mirrors the data model — root → runs →
voxel spacings → tomograms, plus picks/meshes/segmentations:

```python
--8<-- "root_list_objects_runs.py"
```

**Visualize and annotate.** Open the project in a 3D viewer to inspect tomograms and
create picks. See the [ChimeraX-copick tutorial](examples/tutorials/chimerax.md), or the
[ecosystem](tools.md) for napari-copick, CellCanvas, and the web viewer.

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

The two paths above cover local files and the CZ cryoET Data Portal, but a copick
project's data and overlay can live almost anywhere — pick the setup that matches your
storage:

- **[Local](examples/setup/local.md)** / **[Shared](examples/setup/shared.md)** — data on
  a local or shared filesystem.
- **[AWS S3](examples/setup/aws_s3.md)** / **[SSH](examples/setup/ssh.md)** — data on
  object storage or a remote server.
- **[CZ cryoET Data Portal](examples/setup/data_portal.md)** — read from the portal API
  and write to any fsspec overlay.
- **[mlcroissant](examples/setup/croissant.md)** — read from a standards-compliant
  [Croissant 1.1](https://docs.mlcommons.org/croissant/docs/croissant-spec.html)
  manifest + CSV sidecars under a `Croissant/` subdirectory. Live auto-sync
  writes keep the manifest up to date as you annotate.
