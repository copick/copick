**Set up your overlay project**

This directory will contain all newly created data for your project.

Make sure it exists on the filesystem and is writable:
```bash
touch /path/to/copick_project
# Replace /path/to/copick_project with the path to your project overlay
```

If it does not yet exist, create it with the following command:
```bash
mkdir /path/to/copick_project
# Replace /path/to/copick_project with the path to your project overlay
```

In the config file, the location should be passed to the `overlay_root`-field. Any arguments specified to the
`overlay_fs_args`-field will be passed to [LocalFileSystem](https://filesystem-spec.readthedocs.io/en/latest/api.html#fsspec.implementations.local.LocalFileSystem).

```json
{
  "overlay_root": "local:///path/to/copick_project",
  "overlay_fs_args": {
    "auto_mkdir": true
  }
}
```

??? note "More about `overlay_fs_args` ..."
    The `auto_mkdir`-flag is necessary to create copick-directories if they do not yet exist.
