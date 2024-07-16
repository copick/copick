## copick :fontawesome-solid-heart: [album](https://album.solutions/)

Album provides an easy way to deploy code and environments for processing tasks across platforms. Setting up an album
solution that iterates over all runs in a copick project is extremely simple. Below is a step-by-step guide to writing
an album solution that processes all runs in a copick project and stores a set of random points in each run.

A cookiecutter solution for copick can be found at the end of this page.

### Step 1: Install Album

Comprehensive installation instructions for Album can be found on the [Album docs website](https://docs.album.solutions/en/latest/installation-instructions.html).

TL;DR:
```bash
conda create -n album album -c conda-forge
conda activate album
```

### Step 2: Setup your copick project

In this example, we will create a solution that processes all runs in a copick project and stores a set of random points.
Here, we will use the runs from [dataset 10301](https://cryoetdataportal.czscience.com/datasets/10301) on the CZ cryoET
Data Portal and a local overlay project. Other overlay backends can be used as well, see [here](../setup/data_portal.md).

??? example "Cofiguration Template"
    ```json
    {
        "config_type": "cryoet_data_portal",
        "name": "Example Project",
        "description": "This is an example project.",
        "version": "0.5.0",
        "pickable_objects": [
            {
                "name": "random-points",
                "is_particle": true,
                "label": 1,
                "color": [
                    0,
                    117,
                    220,
                    255
                ],
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

### Step 3: Create your solution

#### Environment setup

Album solutions are single Python files that contain the code to be run and information about the environment in which
the code should be run. First, we will set up a baseline environment for copick projects, `scikit-image` and `numpy`.
This will be used by album to create a conda environment for the solution upon installation.

```python
--8<-- "solution_random_points.py:1:21"
```


#### Arguments

Album automatically parses command line arguments passed to the album runner. These arguments can be accessed using the
`get_args` function inside the `run` function. They can be defined as a list of dictionaries, which is passed to the
`album.runner.api.setup()` call in the last step. In case of copick, useful arguments could be the path to the copick
config, the run names and any output object definitions.

```python
--8<-- "solution_random_points.py:23:79"
```

#### Solution code

Next, we will write the code that will be run by album. This code has to be defined within a function called `run`. As
`run` will be executed in a different environment than the solution file, it is important to move all imports into the
body of the function.

```python
--8<-- "solution_random_points.py:82:89"
```

Next we will parse the input arguments passed from the album runner.

```python
--8<-- "solution_random_points.py:91:100"
```

Now we will define any function that we need to process the runs. In this case, we will generate a set of random points
for each run and store them in the copick project.

!!! note
    This function needs to be defined within the `run` function to ensure that it is available in the album environment.

```python
--8<-- "solution_random_points.py:103:115"
```

Next, we will iterate over all runs in the copick project and store a set of random points in each run.

```python
--8<-- "solution_random_points.py:117:148"
```

#### Album solution setup

Finally, we will set up the album solution. This is done by calling the `setup` function with the arguument list, the
solution code and the environment file.

```python
--8<-- "solution_random_points.py:151:164"
```

### Step 4: Run your solution

To run the solution, save the solution code to a file, e.g. `random_points.py`, and run the following command:

```bash
album install random_points.py
album run random_points.py --copick_config_path /path/to/copick_config.json --voxel_spacing 7.84
```

This will generate a set of 10 random points for each run in the copick project.

### Step 5: Visualize your results

You can visualize your output using [ChimeraX-copick](chimerax.md), [napari-copick](../../tools.md#napari-copick) or any
other visualization tool that supports the copick dataset API.

### Step 6: Share your solution

The album documentation provides [a comprehensive guide](https://album.solutions/remote_catalog) on how to share your
solution with others using the album catalog.

## TL;DR

Full code for the solution above:

??? example "Random Points"
    ```python
    --8<-- "solution_random_points.py"
    ```

## Cookiecutter template

A cookiecutter template for copick solutions can be found below:

??? example "Cookiecutter Template"
    ```python
    --8<-- "cookiecutter.py"
    ```
