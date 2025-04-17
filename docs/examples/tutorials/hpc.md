## copick :fontawesome-solid-heart: HPC

A frequent issue encountered when working with cryoET datasets is the need to validate or visualize results of data
analysis run on a high-performance computing (HPC) cluster. Often the data is stored on a remote file system that the
user's machine does not have direct access to.

This tutorial demonstrates how to use copick to access data stored on an HPC cluster on your local machine.


### Step 1: Install copick

See the [quickstart guide](../../quickstart.md) for instructions on how to install copick. Copick must be installed
on both the HPC cluster and your local machine.


### Step 2: Setup your HPC project

On the HPC cluster we can access the data via the local filesystem. Here, we assume that we are working on the HPC
cluster `my_cluster`. For reproducibility's sake we will assume that the static dataset is dataset 10301, retrieved from
the cryoET data portal at [cryoetdataportal.czscience.com](https://cryoetdataportal.czscience.com/datasets/10301). We
will assume that the project overlay is stored in the directory `/hpc/data/copick_project` on the HPC cluster.

We will store this information in a configuration file `copick_config.json` on the HPC cluster.

!!! example "HPC Configuration"
    ```json
    {
        "config_type": "cryoet_data_portal",
        "name": "Example HPC Project",
        "description": "This project lives on an HPC cluster.",
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
        "overlay_root": "local:///hpc/data/copick_project/",
        "overlay_fs_args": {
            "auto_mkdir": true
        },
        "dataset_ids" : [10301]
    }
    ```

Note that the same concept can also be applied on fully locally stored datasets. A config for that case is provided
here, but will not be used in this tutorial.

??? example "HPC Configuration (data fully on cluster)"
    ```json
    {
        "config_type": "filesystem",
        "name": "Example HPC Project",
        "description": "This project lives on an HPC cluster.",
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
        "overlay_root": "local:///hpc/data/copick_project",
        "overlay_fs_args": {
            "auto_mkdir": true
        },
        "static_root": "local:///hpc/data/copick_project_static",
        "static_fs_args": {
            "auto_mkdir": true
        }
    }
    ```

### Step 3: Access the data on your local machine

To access the data on your local machine, we reuse most parts of the configuration file from the HPC cluster. We only
need to inform copick about the location of the project on the cluster and how to access it. For simplicity, we will
assume that passwordless login is set up on the HPC cluster, see the [SSH documentation](https://www.ssh.com/ssh/copy-id)
for more information.

!!! note "SSH Authentication"
    In cases of mandatory 2-FA authentication, you may need to set up an SSH tunnel to the remote filesystem, e.g.
    ```bash
    ssh -L 2222:localhost:22 user.name@]my_cluster
    ```
    and then use `"host":"localhost"` and `"port":2222` as the host in the config and commands below.


On our local machine, we create a new configuration file `copick_config_local.json` with the following content:

!!! example "Local Configuration"
    ```json hl_lines="33 34 35 36 37"
    {
        "config_type": "cryoet_data_portal",
        "name": "Example Local Project",
        "description": "This Project accesses data from an HPC cluster.",
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
        "overlay_root": "ssh:///hpc/data/copick_project/",
        "overlay_fs_args": {
            "host": "my_cluster",
            "username": "user.name"
        },
        "dataset_ids" : [10301]
    }
    ```

As before, we can also provide a configuration for a dataset that is fully stored on the HPC cluster. This will not be
used in this tutorial.

??? example "Local Configuration (data fully on cluster)"
    ```json hl_lines="33 34 35 36 37 38 39 40 41 42"
    {
        "config_type": "filesystem",
        "name": "Example Local Project",
        "description": "This Project accesses data from an HPC cluster.",
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
        "overlay_root": "ssh:///hpc/data/copick_project/",
        "overlay_fs_args": {
            "host": "my_cluster",
            "username": "user.name"
        },
        "static_root": "ssh:///hpc/data/copick_project_static",
        "static_fs_args": {
            "host": "my_cluster",
            "username": "user.name"
        }
    }
    ```


### Step 4: Modify the data on the HPC cluster

Using the configuration file `copick_config.json` from the previous step we can now access the data on the HPC cluster
and perform processing tasks. In lieu of a full processing example, we will demonstrate how read a set of picks from the
dataset save a random subset to a new file.

```python
import copick
import numpy as np

# Get applicable picks
root = copick.from_file("copick_config.json")
run = root.get_run("14069")
picks = run.get_picks(object_name="ribosome")[0]

# Get a random subset of picks
points = picks.points

# Create a new pick object (this will be saved in the overlay directory)
new_picks = run.new_picks(object_name="ribosome", user_id="subset", session_id="0")
new_picks.points = np.random.choice(points, 20, replace=False)
new_picks.store()
```


### Step 5: Access the modified data on your local machine

Using the configuration file `copick_config_local.json` from the previous step we can now access the modified data on
our local machine without additional downloads.

```python
import copick

# Get applicable picks
root = copick.from_file("copick_config_local.json")
run = root.get_run("14069")
picks = run.get_picks(object_name="ribosome", user_id="subset")[0]

# Confirm the number
print(f"Number of picks: {len(picks.points)}")
```


### Step 6: Visualize the data

In reality, you would likely want to visualize the data, instead of just counting the number of picks. For this, you can
use the ChimeraX-copick plugin. Visualization works as with any other copick project. For more information, see the
[tutorial on ChimeraX-copick integration.](chimerax.md), or check out [CellCanvas](../../tools.md#cellcanvas) or
[napari-copick](../../tools.md#napari-copick) for alternative visualization options.
