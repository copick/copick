<figure markdown="span">
  ![local-project](../../assets/local_light.png#only-light)
  ![local-project](../../assets/local_dark.png#only-dark)
  <figcaption>copick project setup with local storage.</figcaption>
</figure>

There are four ways of setting up local **copick** projects:

<div class="grid cards" markdown>

-   :fontawesome-solid-hard-drive:{ .lg .middle }   __Option 1__: overlay-only

    ---

    Using this method, there will be a single, local project directory, all entities in the copick project
    will be writable. This is a good choice for test environments or projects you're working on alone on your own
    machine.

    [:octicons-arrow-right-24: Get config template](#option-1-setting-up-an-overlay-only-copick-project)


-   :fontawesome-solid-hard-drive:{ .lg .middle }   __Option 2__: static/overlay

    ---

    Using this method there will be two project directories, static and overlay, respectively. Files
    in the "static"-project directory will be read-only within copick, while files in the "overlay"-directory will be
    writeable. This is a good choice if you want to maintain the input data.

    [:octicons-arrow-right-24: Get config template](#option-2-setting-up-a-staticoverlay-copick-project)

-   :fontawesome-solid-arrows-split-up-and-left:{ .lg .middle } __Option 3__: overlay/other static

    ---

    Using this method, any user-created copick entities will be stored in a local overlay, while static data (e.g.
    tomograms and baseline annotations) are stored in a different storage backend. This will be useful when multiple
    users are curating a dataset that is available on a shared drive, in the cloud, via ssh or on the data portal.

    [:octicons-arrow-right-24: Get config templates](#option-3-local-overlay-other-static-backend)

-   :fontawesome-solid-arrows-split-up-and-left:{ .lg .middle } __Option 4__: other overlay/static

    ---

    Using this method, the static part of the project will be stored locally, while new copick entities are written to
    another storage backend. This could be useful when results should be uploaded to a common storage server, but a local
    copy of the data exists.

    [:octicons-arrow-right-24: Get config templates](#option-4-other-overlay-local-static-backend)
</div>
---

## Option 1: Setting up an overlay-only copick project

### Set up your project root directory

In order to create an `overlay-only`-project we first need to set up one project directory.

```bash
mkdir copick_project
```

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
    --8<-- "configs/overlay_local.json"
    ```

The project is now set up, you can now add objects, add tomograms or store annotations.

---

## Option 2: Setting up a static/overlay copick project

### Set up your project root directory

In order to create an `static/overlay`-project we first need to set up two project directories, one to store the static
data, and another to store any new or curated annotations.

```bash
mkdir copick_project_static
mkdir copick_project
```

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
    --8<-- "configs/overlay_local_static_local.json"
    ```

---

## Option 3: Local overlay, other static backend

Choose your static backend:

=== "CZ cryoET Data Portal"
    ??? example "Cofiguration Template"
        ```json
        --8<-- "configs/overlay_local_static_data_portal.json"
        ```

    --8<-- "instructions/local_overlay.md"

    --8<-- "instructions/data_portal_static.md"


=== "SMB Share"
    ??? example "Cofiguration Template"
        ```json
        --8<-- "configs/overlay_local_static_smb.json"
        ```

    --8<-- "instructions/local_overlay.md"

    --8<-- "instructions/shared_static.md"

=== "AWS S3"
    ??? example "Cofiguration Template"
        ```json
        --8<-- "configs/overlay_local_static_s3.json"
        ```

    --8<-- "instructions/local_overlay.md"

    --8<-- "instructions/s3_static.md"

=== "SSH"
    ??? example "Cofiguration Template"
        ```json
        --8<-- "configs/overlay_local_static_ssh.json"
        ```

    --8<-- "instructions/local_overlay.md"

    --8<-- "instructions/ssh_static.md"

---

## Option 4: Other overlay, local static backend

Choose your overlay backend:

=== "SMB Share"
    ??? example "Cofiguration Template"
        ```json
        --8<-- "configs/overlay_smb_static_local.json"
        ```

    --8<-- "instructions/shared_overlay.md"

    --8<-- "instructions/local_static.md"

=== "AWS S3"
    ??? example "Cofiguration Template"
        ```json
        --8<-- "configs/overlay_s3_static_local.json"
        ```

    --8<-- "instructions/s3_overlay.md"

    --8<-- "instructions/local_static.md"

=== "SSH"
    ??? example "Cofiguration Template"
        ```json
        --8<-- "configs/overlay_ssh_static_local.json"
        ```

    --8<-- "instructions/ssh_overlay.md"

    --8<-- "instructions/local_static.md"
