# copick

**copick** is a cross-platform, storage-agnostic and server-less dataset API for cryoET datasets. Access to the data is
provided through an object-oriented API that abstracts away the underlying storage using the
[fsspec](https://filesystem-spec.readthedocs.io/en/latest/)-family of libraries.

## Why copick?

- **storage-agnostic**: Access data on local or shared filesystems, via SSH or on the cloud with the same API. No
    need for your own boilerplate!
- **cloud-ready**: Access image data quickly and in parallel thanks to multiscale OME-Zarr!
- **server-less**: No need for a dedicated server or database to access your data, just point **copick** to your data
    and go!
- **cross-platform**: **copick** works on any platform that supports Python. Compute on Linux, visualize on Windows or
    Mac, all with the same dataset API!
- **ecosystem**: Using the **copick** API allows visualizing and curating data in ChimeraX and Napari right away!

## Documentation

For more information, see the [documentation](https://copick.github.io/copick/).

## Installation

copick can be installed using pip. Using the `all` extra installs necessary requirements for all tested filesystem
implementations from the fsspec family (`local`, `s3fs`, `smb`, `sshfs`). Separate `s3`, `smb`, and `ssh` extras are available.

```shell
pip install "copick[all]"
```

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

## Code of Conduct

This project adheres to the Contributor Covenant [code of conduct](https://github.com/chanzuckerberg/.github/blob/main/CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code. Please report unacceptable behavior to [opensource@chanzuckerberg.com](mailto:opensource@chanzuckerberg.com).

## Reporting Security Issues

If you believe you have found a security issue, please responsibly disclose by contacting us at [security@chanzuckerberg.com](mailto:security@chanzuckerberg.com).
