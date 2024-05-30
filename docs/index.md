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
