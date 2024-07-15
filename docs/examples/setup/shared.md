<figure markdown="span">
  ![shared-project](../../assets/smb_light.png#only-light)
  ![shared-project](../../assets/smb_dark.png#only-dark)
  <figcaption>copick project setup with SMB shared drive.</figcaption>
</figure>

There are four ways of setting up local **copick** projects via SMB share:

<div class="grid cards" markdown>

-   :fontawesome-solid-hard-drive:{ .lg .middle }   __Option 1__: overlay-only

    ---

    Using this method, there will be a single, shared project directory, all entities in the copick project
    will be writable.

    [:octicons-arrow-right-24: Get config template](#option-1-setting-up-an-overlay-only-copick-project)


-   :fontawesome-solid-hard-drive:{ .lg .middle }   __Option 2__: static/overlay

    ---

    Using this method there will be two project directories, static and overlay, respectively. Files
    in the "static"-project directory will be read-only within copick, while files in the "overlay"-directory will be
    writeable. This is a good choice if you want to maintain the input data.

    [:octicons-arrow-right-24: Get config template](#option-2-setting-up-a-staticoverlay-copick-project)

-   :fontawesome-solid-arrows-split-up-and-left:{ .lg .middle } __Option 3__: overlay/other static

    ---

    Using this method, any user-created copick entities will be stored in a shared overlay, while static data (e.g.
    tomograms and baseline annotations) are stored in a different storage backend. This will be useful when multiple
    users are curating a dataset and have access to local copies of the static data.

    [:octicons-arrow-right-24: Get config templates](#option-3-smb-overlay-other-static-backend)

-   :fontawesome-solid-arrows-split-up-and-left:{ .lg .middle } __Option 4__: other overlay/static

    ---

    Using this method, the static part of the project will be stored in a shared directory, while new copick entities
    are written to another storage backend. This could be useful when curating a large set of data with a group.

    [:octicons-arrow-right-24: Get config templates](#option-4-other-overlay-smb-static-backend)
</div>
---

## Option 1: Setting up an overlay-only copick project

### Set up your project root directory

The following example assumes that you have a shared directory on a network drive that you can access via SMB.

### Create the config file

All information necessary to use the copick API is stored in a config file in `json`-Format. This has to be created
before accessing the data is possible.


Create a json file with your favorite editor and paste the below template. Fill in the abolute path of the copick
root directory as indicated below.

```bash
vi copick_config.json
```

??? example "Cofiguration Template"
    ```json
    --8<-- "configs/overlay_smb.json"
    ```

The project is now set up, you can now add objects, add tomograms or store annotations.

---

## Option 2: Setting up a static/overlay copick project

### Set up your project root directory

The following example assumes that you have two shared directories on a network drive that you can access via SMB.

### Create the config file

All information necessary to use the copick API is stored in a config file in `json`-Format. This has to be created
before accessing the data is possible.


Create a json file with your favorite editor and paste the below template. Fill in the abolute path of the copick
root directory as indicated below.

```bash
vi copick_config.json
```

??? example "Cofiguration Template"
    ```json
    --8<-- "configs/overlay_smb_static_smb.json"
    ```

---

## Option 3: SMB overlay, other static backend

Choose your static backend:

=== "CZ cryoET Data Portal"
    ??? example "Cofiguration Template"
        ```json
        --8<-- "configs/overlay_smb_static_data_portal.json"
        ```

    --8<-- "instructions/shared_overlay.md"

    --8<-- "instructions/data_portal_static.md"


=== "Local"
    ??? example "Cofiguration Template"
        ```json
        --8<-- "configs/overlay_smb_static_local.json"
        ```

    --8<-- "instructions/shared_overlay.md"

    --8<-- "instructions/local_static.md"

=== "AWS S3"
    ??? example "Cofiguration Template"
        ```json
        --8<-- "configs/overlay_smb_static_s3.json"
        ```

    --8<-- "instructions/shared_overlay.md"

    --8<-- "instructions/s3_static.md"

=== "SSH"
    ??? example "Cofiguration Template"
        ```json
        --8<-- "configs/overlay_smb_static_ssh.json"
        ```

    --8<-- "instructions/shared_overlay.md"

    --8<-- "instructions/ssh_static.md"

---

## Option 4: Other overlay, SMB static backend

Choose your overlay backend:

=== "Local"
    ??? example "Cofiguration Template"
        ```json
        --8<-- "configs/overlay_local_static_smb.json"
        ```

    --8<-- "instructions/local_overlay.md"

    --8<-- "instructions/shared_static.md"

=== "AWS S3"
    ??? example "Cofiguration Template"
        ```json
        --8<-- "configs/overlay_s3_static_smb.json"
        ```

    --8<-- "instructions/s3_overlay.md"

    --8<-- "instructions/shared_static.md"

=== "SSH"
    ??? example "Cofiguration Template"
        ```json
        --8<-- "configs/overlay_ssh_static_smb.json"
        ```

    --8<-- "instructions/ssh_overlay.md"

    --8<-- "instructions/shared_static.md"
