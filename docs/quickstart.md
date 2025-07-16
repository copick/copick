

## Requirements
copick runs on Python 3.9 and above on Linux, MacOS, and Windows.

It requires the following packages:

- fsspec
- pydantic
- numpy
- trimesh
- zarr

## Installation

copick can be installed using pip. Using the `all` extra installs necessary requirements for all tested filesystem
implementations from the fsspec family (`local`, `s3fs`, `smb`, `sshfs`). A separate `smb` extra is available.

```shell
pip install "copick[all]"
```

!!! note
    `copick==1.2.0` will fail to install with `pip>=25`. We recommend using [`uv pip`](https://docs.astral.sh/uv/pip/) or `pip<=25` when installing copick.


## Example dataset

An example dataset can be obtained from [Zenodo](https://doi.org/10.5281/zenodo.11238625).

To test with the example dataset:

1. Download and unpack the example dataset
2. Add the location of the `sample_project`-directory in the unpacked dataset to `filesystem_overlay_only.json`
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

3. Start copick with the configuration file

    ```python
    from copick.impl.filesystem import CopickRootFSSpec
    root = CopickRootFSSpec.from_file('path/to/filesystem_overlay_only.json')
    ```

4. Access the data using the copick API

    ```python
    import zarr

    from copick.impl.filesystem import CopickRootFSSpec
    root = CopickRootFSSpec.from_file('path/to/filesystem_overlay_only.json')

    # Get a run by name
    run = root.get_run("TS_001")

     # Get a tomogram by name
    tomogram = run.get_voxel_spacing(10).get_tomogram("wbp")

    # Access the data
    group = zarr.open(tomogram.zarr())
    arrays = list(group.arrays())
    _, array = arrays[0]
    ```
