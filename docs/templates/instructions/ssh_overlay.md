**Set up your overlay project**

This directory will contain all newly created data for your project.

!!! note "SSH authentication"
    Copick will work best via SSH if you have set up passwordless SSH authentication. Refer to the
    [SSH documentation](https://www.ssh.com/ssh/copy-id) for more information. In general, adding plain text passwords
    into copick configuration files **is strongly discouraged**.

    In cases of mandatory 2-FA authentication, you may need to set up an SSH tunnel to the remote filesystem, e.g.

    ```bash
    ssh -L 2222:localhost:22 user.name@hpc.example.com
    ```
    and then use `localhost:2222` as the host in the config and commands below.


Make sure it exists on the remote filesystem and is writable:
```bash
ssh -p 22 user.name@hpc.example.com "touch /path/to/copick_project"
# Replace port, user name and path to the project overlay with the correct values
```

If it does not yet exist, create it with the following command:
```bash
ssh -p 22 user.name@hpc.example.com "mkdir /path/to/copick_project"
# Replace port, user name and path to the project overlay with the correct values
```

In the config file, the location should be passed to the `overlay_root`-field. Any arguments specified to the
`overlay_fs_args`-field will be passed to [sshfs.SSHFileSystem](https://github.com/fsspec/sshfs?tab=readme-ov-file).

```json
{
  "overlay_root": "ssh:///path/to/copick_project/",

    "overlay_fs_args": {
        "username": "user.name",
        "host": "hpc.example.com",
        "port": 22
    }
}
```

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
