**Set up your static project**

This directory will contain all static data for your project.

Make sure it exists on the filesystem and is writable:
```bash
touch /path/to/copick_project_static
# Replace /path/to/copick_project with the path to your static project
```

If it does not yet exist, create it with the following command:
```bash
mkdir /path/to/copick_project_static
# Replace /path/to/copick_project with the path to your static project
```

In the config file, the location should be passed to the `static_root`-field. Any arguments specified to the
`static_fs_args`-field will be passed to [LocalFileSystem](https://filesystem-spec.readthedocs.io/en/latest/api.html#fsspec.implementations.local.LocalFileSystem).

```json
{
  "static_root": "local:///path/to/copick_project",
  "static_fs_args": {
    "auto_mkdir": true
  }
}
```

??? note "More about `static_fs_args` ..."
    The `auto_mkdir`-flag is necessary to create copick-directories if they do not yet exist.
