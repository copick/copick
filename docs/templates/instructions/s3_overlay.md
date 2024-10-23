**Set up your overlay project**

This S3 URI will contain all newly created data for your project.

Make sure the intended S3 bucket is writable:
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

In the config file, the location should be passed to the `overlay_root`-field. Any arguments specified to the
`overlay_fs_args`-field will be passed to [S3FileSystem](https://s3fs.readthedocs.io/en/latest/api.html#s3fs.core.S3FileSystem).
`profile` should be one of the profiles set up in your `~/.aws/credentials` file.

```json
{
  "overlay_root": "s3://bucket-name/copick_project/",
  "overlay_fs_args": {
        "profile": "example_profile"
    }
}
```

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
