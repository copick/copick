# copick

**copick** is a cross-platform, storage-agnostic and server-less dataset API for cryoET datasets. Access to the data is
provided through an object-oriented API that abstracts away the underlying storage using the
[fsspec](https://filesystem-spec.readthedocs.io/en/latest/)-family of libraries.

## Why copick?

<div class="grid cards" markdown>

-   :fontawesome-solid-hard-drive:{ .lg .middle }   __storage-agnostic__

    ---

    Access data on [local](examples/setup/local.md) or [shared](examples/setup/shared.md) storage, via
    [SSH](examples/setup/ssh.md) or on the [cloud](examples/setup/aws_s3.md) with the same API. No
    need for your own boilerplate!

    [:octicons-arrow-right-24: Get started now ](quickstart.md)

-   :fontawesome-solid-cloud:{ .lg .middle }   __cloud-ready__

    ---

    Access image data quickly and in parallel thanks to multiscale OME-Zarr. Easily load data from the [CZ cryoET Data
    Portal](https://cryoetdataportal.czscience.com/)!

    [:octicons-arrow-right-24: Learn more](examples/tutorials/data_portal.md)

-   :fontawesome-solid-server:{ .lg .middle } __server-less__

    ---

    No need for a dedicated server or database to access your data, just point **copick** to your data
    and go!

    [:octicons-arrow-right-24: Deploy copick using album](examples/tutorials/album.md)

-   :fontawesome-solid-layer-group:{ .lg .middle } __cross-platform__

    ---

    **copick** works on any platform that supports Python. Compute on Linux, visualize on Windows or
    Mac!

    [:octicons-arrow-right-24: Learn about copick and HPC](examples/tutorials/hpc.md)

-   :fontawesome-solid-circle-nodes:{ .lg .middle } __ecosystem__

    ---

    Using the copick API allows visualizing and curating data in ChimeraX and Napari right away!

    [:octicons-arrow-right-24: Explore tools](tools.md)

-   :material-scale-balance:{ .lg .middle } __open source__

    ---

    Copick is released under the open source MIT license.

    [:octicons-arrow-right-24: License](https://github.com/copick/copick/blob/main/LICENSE)

</div>

## Data

Currently, copick supports the following types of data frequently encountered in cryoET datasets:

- tomograms
- feature maps
- dense segmentations
- mesh annotations
- point annotations

## Storage backends

Copick should support any storage backend that is supported by fsspec.

The following backends are included in tests and should work out of the box:

- local filesystem
- s3
- smb
- access via ssh
