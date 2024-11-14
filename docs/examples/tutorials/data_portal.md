## copick :fontawesome-solid-heart: [CZ cryoET Data Portal](https://cryoetdataportal.czscience.com/)

The CZ cryoET Data Portal provides a standardized access to cryoET datasets and annotations. This tutorial demonstrates
how to datasets and annotations stored on the CZ cryoET Data Portal as static data in a copick project.

### Step 1: Install copick

See the [quickstart guide](../../quickstart.md) for instructions on how to install copick.

### Step 2: Setup your project

We will create a project that uses [dataset 10301](https://cryoetdataportal.czscience.com/datasets/10301) from the CZ
cryoET Data Portal. We will store locally created annotations in a local directory, called the "overlay". In the following,
we will create a configuration file `copick_config.json` that describes the project.

The configuration file is a JSON file that contains all information necessary to access the data. We first provide
general information about the project, such as the project name, description, and version.

```json
{
  "config_type": "cryoet_data_portal",
  "name": "Example Project",
  "description": "This is an example project.",
  "version": "0.5.0"
}
```

Next, we define the objects that can be accessed and created using the copick API. Dataset 10301 already contains
annotations from multiple authors, which we can access from within copick. In order to make data portal annotations
available, we need to include the [Gene Ontology IDs](https://geneontology.org/docs/ontology-documentation/) or [UniProtKB accessions](https://www.uniprot.org/help/accession_numbers) (`identifier`) of the objects we want to access. Any portal annotation
that has a matching GO ID will be available in the copick project.

In this case, we will obtain pre-existing annotations for the ribosome, ATPase, and membrane. We will also create a new
object called "prohibitin" that will be stored in the overlay directory, but is not available on the data portal.

```json
{
  "pickable_objects": [
    {
      "name": "ribosome",
      "is_particle": true,
      "identifier": "GO:0022626",
      "label": 1,
      "color": [  0, 117, 220, 255],
      "radius": 150
    },
    {
      "name": "atpase",
      "is_particle": true,
      "identifier": "GO:0045259",
      "label": 2,
      "color": [251, 192, 147, 255],
      "radius": 150
    },
    {
      "name": "membrane",
      "is_particle": false,
      "identifier": "GO:0016020",
      "label": 3,
      "color": [200, 200, 200, 255],
      "radius": 10
    },
    {
      "name": "prohibitin",
      "is_particle": true,
      "label": 4,
      "color": [  155, 117, 220, 255],
      "radius": 10
    }
  ]
}
```

Finally, we define the overlay directory where the new annotations will be stored, and the dataset ID of dataset 10301
on the CZ cryoET Data Portal.

```json
{
  "overlay_root": "local:///home/bob/copick_project/",
  "overlay_fs_args": {
    "auto_mkdir": true
  },
  "dataset_ids" : [10301]
}
```


??? example "Full Configuration Template"
    ```json
    {
        "config_type": "cryoet_data_portal",
        "name": "Example Project",
        "description": "This is an example project.",
        "version": "0.5.0",
        "pickable_objects": [
            {
                "name": "ribosome",
                "is_particle": true,
                "identifier": "GO:0022626",
                "label": 1,
                "color": [  0, 117, 220, 255],
                "radius": 150
            },
            {
                "name": "atpase",
                "is_particle": true,
                "identifier": "GO:0045259",
                "label": 2,
                "color": [251, 192, 147, 255],
                "radius": 150
            },
            {
                "name": "membrane",
                "is_particle": false,
                "identifier": "GO:0016020",
                "label": 3,
                "color": [200, 200, 200, 255],
                "radius": 10
            }
        ],
        "overlay_root": "local:///Users/utz.ermel/Documents/chlamy_proc/random_points/",
        "overlay_fs_args": {
            "auto_mkdir": true
        },
        "dataset_ids" : [10301]
    }
    ```

### Step 3: Visualize, curate or process the data

You can now use the copick API to access the data from dataset 10301 and the overlay directory. As a first step, you can
print the available objects and runs.

```python
--8<-- "root_list_objects_runs.py"
```

Visualization works as with any other copick project. For more information, see the
[tutorial on ChimeraX-copick integration.](chimerax.md), or check out [CellCanvas](../../tools.md#cellcanvas) or
[napari-copick](../../tools.md#napari-copick) for alternative visualization options.
