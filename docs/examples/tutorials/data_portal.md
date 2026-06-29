## copick :fontawesome-solid-heart: [CZ cryoET Data Portal](https://cryoetdataportal.czscience.com/)

The CZ cryoET Data Portal provides standardized access to cryoET datasets and annotations. This tutorial demonstrates
how to access datasets and annotations stored on the CZ cryoET Data Portal as static data in a copick project.

### Step 1: Install copick

See the [quickstart guide](../../quickstart.md) for instructions on how to install copick.

### Step 2: Set up your project

We will create a project that uses [dataset 10301](https://cryoetdataportal.czscience.com/datasets/10301) from the CZ
cryoET Data Portal, and store any locally created annotations in a local directory called the "overlay".

You no longer need to write a configuration file by hand — the `copick config dataportal` command builds it for you:

```bash
copick config dataportal \
    --dataset-id 10301 \
    --overlay ./overlay \
    --output copick_config.json
```

This writes a `copick_config.json` that reads tomograms, picks, and other annotations **directly from dataset 10301**
(the portal data stays read-only), while anything you create is written to the local `./overlay` directory. copick
**discovers the pickable objects automatically** from the dataset's portal annotations — their names, particle vs.
segmentation type, ontology/PDB/EMDB metadata, labels, and colors are all filled in for you, so there is no need to
list `pickable_objects` or look up [Gene Ontology IDs](https://geneontology.org/docs/ontology-documentation/) manually.

To combine several portal datasets into a single project, pass `--dataset-id` (`-ds`) once per dataset:

```bash
copick config dataportal \
    -ds 10301 -ds 10302 \
    --overlay ./overlay \
    --output copick_config.json
```

??? example "Generated configuration"
    ```json
    {
        "config_type": "cryoet_data_portal",
        "name": "CZ cryoET Data Portal Dataset",
        "description": "This copick project contains data from datasets [10301].",
        "pickable_objects": [
            {
                "name": "ribosome",
                "is_particle": true,
                "identifier": "GO:0022626",
                "label": 1,
                "color": [0, 117, 220, 255],
                "radius": 150.0
            },
            {
                "name": "membrane",
                "is_particle": false,
                "identifier": "GO:0016020",
                "label": 2,
                "color": [200, 200, 200, 255],
                "radius": 10.0
            }
            // ... remaining objects discovered from the dataset
        ],
        "overlay_root": "local://./overlay",
        "overlay_fs_args": {
            "auto_mkdir": true
        },
        "dataset_ids": [10301]
    }
    ```

#### Adding your own objects

You can also annotate structures that are not yet on the portal. Register a new object with `copick add object`; it is
stored only in the overlay, alongside the auto-discovered portal objects:

```bash
copick add object --config copick_config.json --name prohibitin \
    --object-type particle --radius 10 --color "155,117,220,255"
```

Objects added without an `--identifier` are overlay-only. Pass `--identifier GO:…` (a Gene Ontology ID or UniProtKB
accession) instead to link a new object to matching annotations already on the data portal.

### Step 3: Visualize, curate or process the data

You can now use the copick API to access the data from dataset 10301 and the overlay directory. As a first step, you can
print the available objects and runs — including the objects copick discovered from the portal.

```python
--8<-- "root_list_objects_runs.py"
```

Visualization works as with any other copick project. For more information, see the
[tutorial on ChimeraX-copick integration.](chimerax.md), or check out [CellCanvas](../../tools.md#cellcanvas) or
[napari-copick](../../tools.md#napari-copick) for alternative visualization options.
