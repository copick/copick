<figure markdown="span">
  ![ssh-project](../../assets/ssh_light.png#only-light)
  ![ssh-project](../../assets/ssh_dark.png#only-dark)
  <figcaption>copick project setup with remote storage via SSH.</figcaption>
</figure>

In copick, a project has an overlay and (optionally) a static part. The overlay is where all user-created entities are stored and is writable. The static part is read-only and contains the input data. There are four ways of setting up SSH-based **copick** projects:

<div class="grid cards" markdown>

-   :fontawesome-solid-hard-drive:{ .lg .middle }   __Option 1__: SSH overlay-only

    ---

    Using this method, there will be a single, remote SSH project directory, all entities in the copick project
    will be writable. This is a good choice for when one wants to visualize and annotate data from a personal project
    that is stored on a remote SSH server.

    [:octicons-arrow-right-24: Get config template](#option-1-a-ssh-overlay-only-copick-project)


-   :fontawesome-solid-hard-drive:{ .lg .middle }   __Option 2__: SSH overlay, SSH static

    ---

    Using this method there will be two project directories, static and overlay, respectively. Files
    in the "static"-project directory will be read-only within copick, while files in the "overlay"-directory will be
    writeable. This is a good choice if you want to maintain the input data.

    [:octicons-arrow-right-24: Get config template](#option-2-a-ssh-overlay-ssh-static-copick-project)

-   :fontawesome-solid-arrows-split-up-and-left:{ .lg .middle } __Option 3__: SSH overlay, other static

    ---

    Using this method, any user-created copick entities will be stored in a remote SSH overlay, while static data (e.g.
    tomograms and baseline annotations) are stored in a different storage backend. This will be useful when one wants to
    curate a dataset and have the curated data directly accessible on a remote SSH server.

    [:octicons-arrow-right-24: Get config templates](#option-3-a-ssh-overlay-other-static-copick-project)

-   :fontawesome-solid-arrows-split-up-and-left:{ .lg .middle } __Option 4__: other overlay, SSH static

    ---

    Using this method, the static part of the project will be stored remotely via SSH, while new copick entities are written to
    another storage backend. This could be useful together with a group of people curating a large set of data.

    [:octicons-arrow-right-24: Get config templates](#option-4-an-other-overlay-ssh-static-copick-project)
</div>
---

## Option 1: A SSH overlay-only copick project

### Set up your project root directory

In order to create an `overlay-only`-project we first need to set up one project directory on a remote SSH server.

!!! note "SSH authentication"
    Copick will work best via SSH if you have set up passwordless SSH authentication. Refer to the
    [SSH documentation](https://www.ssh.com/ssh/copy-id) for more information. In general, adding plain text passwords
    into copick configuration files **is strongly discouraged**.

    In cases of mandatory 2-FA authentication, you may need to set up an SSH tunnel to the remote filesystem, e.g.

    ```bash
    ssh -L 2222:localhost:22 user.name@hpc.example.com
    ```
    and then use `localhost:2222` as the host in the config and commands below.

Make sure it exists on the remote SSH filesystem and is writable:
```bash
ssh -p 22 user.name@hpc.example.com "touch /path/to/copick_project"
# Replace port, user name and path to the project overlay with the correct values
```

If it does not yet exist, create it with the following command:
```bash
ssh -p 22 user.name@hpc.example.com "mkdir /path/to/copick_project"
# Replace port, user name and path to the project overlay with the correct values
```

### Create the config file

All information necessary to use the copick API is stored in a config file in `json`-Format. This has to be created
before accessing the data is possible.


Create a json file with your favorite editor and paste the below template. Fill in the abolute path of the copick
root directory on the remote SSH server as indicated below.

```bash
vi copick_config.json
```

??? example "Cofiguration Template"
    ```json
    --8<-- "configs/overlay_ssh.json"
    ```
In the config file, the location should be passed to the `overlay_root`-field. Any arguments specified to the
`overlay_fs_args`-field will be passed to [sshfs.SSHFileSystem](https://github.com/fsspec/sshfs?tab=readme-ov-file).

??? note "More about `overlay_fs_args` ..."
    The `username`, `host` and `port`-fields are necessary to set up the SSH connection. Refer to the
    [SSHFS documentation](https://github.com/fsspec/sshfs?tab=readme-ov-file) for detailed information.

    An easy way to use the SSH filesystem is to tunnel to the remote filesystem via SSH, e.g.

    ```bash
    ssh -L 2222:localhost:22 user.name@hpc.example.com
    ```

    and then use `localhost:2222` as the host in the config and commands above.

    ```json
    {
      "overlay_fs_args": {
          "username": "user.name",
          "host": "localhost",
          "port": 2222
      }
    }
    ```

The project is now set up, you can now add objects, add tomograms or store annotations.

---

## Option 2: A SSH overlay, SSH static copick project

### Set up your project root directory

In order to create an `static/overlay`-project we first need to set up two project directories, one to store the static
data, and another to store any new or curated annotations.

Make sure it exists on the remote SSH filesystem and is writable:
```bash
ssh -p 22 user.name@hpc.example.com "mkdir /path/to/copick_project"
ssh -p 22 user.name@hpc.example.com "mkdir /path/to/copick_project_static"
# Replace port, user name and path to the project overlay with the correct values
```

If it does not yet exist, create it with the following command:
```bash
ssh -p 22 user.name@hpc.example.com "mkdir /path/to/copick_project"
ssh -p 22 user.name@hpc.example.com "mkdir /path/to/copick_project_static"
# Replace port, user name and path to the project overlay with the correct values
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
    --8<-- "configs/overlay_ssh_static_ssh.json"
    ```

---

## Option 3: A SSH overlay, other static copick project

Choose your static backend:

=== "CZ cryoET Data Portal"
    ??? example "Cofiguration Template"
        ```json
        --8<-- "configs/overlay_ssh_static_data_portal.json"
        ```

    --8<-- "instructions/ssh_overlay.md"

    --8<-- "instructions/data_portal_static.md"


=== "SMB Share"
    ??? example "Cofiguration Template"
        ```json
        --8<-- "configs/overlay_ssh_static_smb.json"
        ```

    --8<-- "instructions/ssh_overlay.md"

    --8<-- "instructions/shared_static.md"

=== "AWS S3"
    ??? example "Cofiguration Template"
        ```json
        --8<-- "configs/overlay_ssh_static_s3.json"
        ```

    --8<-- "instructions/ssh_overlay.md"

    --8<-- "instructions/s3_static.md"

=== "Local"
    ??? example "Cofiguration Template"
        ```json
        --8<-- "configs/overlay_ssh_static_local.json"
        ```

    --8<-- "instructions/ssh_overlay.md"

    --8<-- "instructions/local_static.md"

---

## Option 4: An other overlay, SSH static copick project

Choose your overlay backend:

=== "SMB Share"
    ??? example "Cofiguration Template"
        ```json
        --8<-- "configs/overlay_smb_static_ssh.json"
        ```

    --8<-- "instructions/shared_overlay.md"

    --8<-- "instructions/ssh_static.md"

=== "AWS S3"
    ??? example "Cofiguration Template"
        ```json
        --8<-- "configs/overlay_s3_static_ssh.json"
        ```

    --8<-- "instructions/s3_overlay.md"

    --8<-- "instructions/ssh_static.md"

=== "Local"
    ??? example "Cofiguration Template"
        ```json
        --8<-- "configs/overlay_local_static_ssh.json"
        ```

    --8<-- "instructions/local_overlay.md"

    --8<-- "instructions/ssh_static.md"
