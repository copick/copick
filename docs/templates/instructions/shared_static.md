**Set up your static project**

This SMB-share will contain all static data for your project.

In the config file, the location should be passed to the `static_root`-field. Any arguments specified to the
`static_fs_args`-field will be passed to [SMBFileSystem](https://filesystem-spec.readthedocs.io/en/latest/api.html#fsspec.implementations.smb.SMBFileSystem).

```json
{
    "static_root": "smb:///shared_drive/copick_project/",
    "static_fs_args": {
        "host": "192.158.1.38",
        "username": "user.name",
        "password": "1234",
        "temppath": "/shared_drive",
        "auto_mkdir": true,
    }
}
```


??? note "More about `static_fs_args` ..."
    The `auto_mkdir`-flag is necessary to create copick-directories if they do not yet exist. The `tmpath`-flag is not
    strictly necessary, this depends on your SMB setup (e.g. if only a specific directory is shared).

    ```json
    {
        "static_root": "smb:///shared_drive/copick_project/",
        "static_fs_args": {
            "host": "192.158.1.38",
            "username": "user.name",
            "password": "1234",
            "auto_mkdir": true,
        }
    }
    ```
