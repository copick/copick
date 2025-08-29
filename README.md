# copick

<div align="center">

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![PyPI version](https://badge.fury.io/py/copick.svg)](https://badge.fury.io/py/copick)
[![Python](https://img.shields.io/badge/python-3.9%20|%203.10%20|%203.11%20|%203.12%20|%203.13-green)](https://pypi.org/project/copick/)
[![Tests](https://github.com/copick/copick/workflows/tests/badge.svg)](https://github.com/copick/copick/actions/workflows/test.yml)
[![codecov](https://codecov.io/gh/copick/copick/branch/main/graph/badge.svg)](https://codecov.io/gh/copick/copick)
[![Docs](https://github.com/copick/copick/workflows/docs/badge.svg)](https://copick.github.io/copick/)

</div>

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
implementations from the fsspec family (`local`, `s3fs`, `smb`, `sshfs`). A separate `smb` extra is available.

```shell
pip install "copick[all]"
```

> [!NOTE]
> `copick>=1.2.0` will fail to install with `pip~=25.1.0`. We recommend using `pip>=25.2` or  [`uv pip`](https://docs.astral.sh/uv/pip/) when installing copick.


## Example dataset

An example dataset can be obtained from [Zenodo](https://doi.org/10.5281/zenodo.16996074).

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

## Contributing

We welcome contributions to copick! Here's how to get started:

### Development Setup

1. Clone the repository and install with development dependencies:
   ```bash
   git clone https://github.com/copick/copick.git
   cd copick
   pip install -e ".[dev,test]"
   ```

2. Install pre-commit hooks:
   ```bash
   pre-commit install
   ```

3. Run tests to ensure everything is working:
   ```bash
   pytest
   ```

### Code Quality

We use several tools to maintain code quality:

- **Black** for code formatting
- **Ruff** for linting and import sorting
- **Pre-commit hooks** to enforce standards

Before submitting a PR, ensure your code passes all checks:
```bash
black src/ tests/
ruff check --fix src/ tests/
pytest
```

### Conventional Commits

All pull requests must use [Conventional Commits](https://www.conventionalcommits.org/) for commit messages. This helps us automatically generate changelogs and determine version bumps.

Examples:
- `feat: add support for new tomogram format`
- `fix: resolve memory leak in zarr loading`
- `docs: update installation instructions`
- `test: add unit tests for mesh operations`

### Plugin System

Copick supports a plugin system that allows external Python packages to register CLI commands. Commands can be added to the main CLI or organized into groups like `inference`, `training`, `evaluation`, `process`, and `convert`.

See the [CLI documentation](https://copick.github.io/copick/cli/#plugin-system) for detailed plugin development instructions and the [copick-plugin-demo](https://github.com/copick/copick-plugin-demo) repository for a complete example.

## Code of Conduct

This project adheres to the Contributor Covenant [code of conduct](https://github.com/chanzuckerberg/.github/blob/main/CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code. Please report unacceptable behavior to [opensource@chanzuckerberg.com](mailto:opensource@chanzuckerberg.com).

## Reporting Security Issues

If you believe you have found a security issue, please responsibly disclose by contacting us at [security@chanzuckerberg.com](mailto:security@chanzuckerberg.com).
