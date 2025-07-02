<figure markdown="span">
  ![s3-project](../../assets/s3_light.png#only-light)
  ![s3-project](../../assets/s3_dark.png#only-dark)
  <figcaption>copick project setup with an S3 bucket.</figcaption>
</figure>

In copick, a project has an overlay and (optionally) a static part. The overlay is where all user-created entities are stored and is writable. The static part is read-only and contains the input data. There are four ways of setting up local **copick** projects via AWS or local S3 buckets (e.g. MinIO):

<div class="grid cards" markdown>

-   :fontawesome-solid-hard-drive:{ .lg .middle }   __Option 1__: S3 overlay-only

    ---

    Using this method, there will be a single, shared project S3-prefix, all entities in the copick project
    will be writable.

    [:octicons-arrow-right-24: Get config template](#option-1-a-s3-overlay-only-copick-project)


-   :fontawesome-solid-hard-drive:{ .lg .middle }   __Option 2__: S3 static, S3 overlay

    ---

    Using this method there will be two S3-prefixes, static and overlay, respectively. Files
    with the "static"-project prefixes will be read-only within copick, while files with the "overlay"-prefixes will be
    writeable. This is a good choice if you want to maintain the input data.

    [:octicons-arrow-right-24: Get config template](#option-2-a-s3-overlay-s3-static-copick-project)

-   :fontawesome-solid-arrows-split-up-and-left:{ .lg .middle } __Option 3__: S3 overlay, other static

    ---

    Using this method, any user-created copick entities will be stored in a shared overlay, while static data (e.g.
    tomograms and baseline annotations) are stored in a different storage backend. This will be useful when multiple
    users are curating a dataset and have access to local copies of the static data.

    [:octicons-arrow-right-24: Get config templates](#option-3-a-s3-overlay-other-static-copick-project)

-   :fontawesome-solid-arrows-split-up-and-left:{ .lg .middle } __Option 4__: other overlay, S3 static

    ---

    Using this method, the static part of the project will be stored in a shared directory, while new copick entities
    are written to another storage backend. This could be useful when curating a large set of data with a group.

    [:octicons-arrow-right-24: Get config templates](#option-4-an-other-overlay-s3-static-copick-project)
</div>
---

## Option 1: A S3 overlay-only copick project

### Set up your project root prefix

The following example assumes that you have a shared bucket on AWS S3 or a local S3 instance that you can access. To test
access:

```bash
```bash
echo "Hello, World!" > test.txt
aws s3 cp test.txt s3://your-bucket-name/copick_project/test.txt
aws s3 ls s3://your-bucket-name/copick_project/
aws s3 rm s3://your-bucket-name/copick_project/test.txt
# Replace s3://your-bucket-name/copick_project/ with your S3 URI
```

!!! note "AWS authentication"
    Make sure you have the necessary AWS credentials set up and available in the shell you're running the above
    commands in. Refer to the [AWS CLI documentation](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-quickstart.html)
    for more information.

### Create the config file

All information necessary to use the copick API is stored in a config file in `json`-Format. This has to be created
before accessing the data is possible.


Create a json file with your favorite editor and paste the below template. Fill in the S3 URI of the copick
root prefix as indicated below.

```bash
vi copick_config.json
```

??? example "Cofiguration Template"
    ```json
    --8<-- "configs/overlay_s3.json"
    ```

The project is now set up, you can now add objects, add tomograms or store annotations.

??? note "More about `overlay_fs_args` ..."
    Specifying `profile` is one possible way of setting up AWS credentials. Refer to the [S3FS documentation](https://s3fs.readthedocs.io/en/latest/api.html#s3fs.core.S3FileSystem)
    for detailed information.

    For local [MinIO](https://min.io/) buckets, the following config may be appropriate:

    ```json
    {
        "overlay_fs_args": {
            "key":"bucketkey",
            "secret":"bucketsecret",
            "endpoint_url":"http://10.30.121.49:7070",
            "client_kwargs":{
                "region_name":"us-east-1"
            }
    }
    ```

---

## Option 2: A S3 overlay, S3 static copick project

### Set up your project root prefix

The following example assumes that you have a shared bucket on AWS S3 or a local S3 instance that you can access. Test
access as above.

### Create the config file

All information necessary to use the copick API is stored in a config file in `json`-Format. This has to be created
before accessing the data is possible.


Create a json file with your favorite editor and paste the below template. Fill in the S3 URI of the copick
root as indicated below.

```bash
vi copick_config.json
```

??? example "Cofiguration Template"
    ```json
    --8<-- "configs/overlay_s3_static_s3.json"
    ```

---

## Option 3: A S3 overlay, other static copick project

Choose your other static backend:

=== "CZ cryoET Data Portal"
    ??? example "Cofiguration Template"
        ```json
        --8<-- "configs/overlay_s3_static_data_portal.json"
        ```

    --8<-- "instructions/s3_overlay.md"

    --8<-- "instructions/data_portal_static.md"


=== "SMB Share"
    ??? example "Cofiguration Template"
        ```json
        --8<-- "configs/overlay_s3_static_smb.json"
        ```

    --8<-- "instructions/s3_overlay.md"

    --8<-- "instructions/shared_static.md"

=== "Local"
    ??? example "Cofiguration Template"
        ```json
        --8<-- "configs/overlay_s3_static_local.json"
        ```

    --8<-- "instructions/s3_overlay.md"

    --8<-- "instructions/local_static.md"

=== "SSH"
    ??? example "Cofiguration Template"
        ```json
        --8<-- "configs/overlay_s3_static_ssh.json"
        ```

    --8<-- "instructions/s3_overlay.md"

    --8<-- "instructions/ssh_static.md"

---

## Option 4: An other overlay, S3 static copick project

Choose your otheroverlay backend:

=== "Local"
    ??? example "Cofiguration Template"
        ```json
        --8<-- "configs/overlay_local_static_s3.json"
        ```

    --8<-- "instructions/local_overlay.md"

    --8<-- "instructions/s3_static.md"

=== "SMB Share"
    ??? example "Cofiguration Template"
        ```json
        --8<-- "configs/overlay_smb_static_s3.json"
        ```

    --8<-- "instructions/shared_overlay.md"

    --8<-- "instructions/s3_static.md"

=== "SSH"
    ??? example "Cofiguration Template"
        ```json
        --8<-- "configs/overlay_ssh_static_s3.json"
        ```

    --8<-- "instructions/ssh_overlay.md"

    --8<-- "instructions/s3_static.md"
