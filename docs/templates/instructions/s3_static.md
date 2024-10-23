**Set up your static project**

This S3 URI will contain all static data for your project.

Make sure the intended S3 bucket is writable:
```bash
echo "Hello, World!" > test.txt
aws s3 cp test.txt s3://your-bucket-name/copick_project_static/test.txt
aws s3 ls s3://your-bucket-name/copick_project_static/
aws s3 rm s3://your-bucket-name/copick_project_static/test.txt
# Replace s3://your-bucket-name/copick_project/ with your S3 URI
```

!!! note "AWS authentication"
    Make sure you have the necessary AWS credentials set up and available in the shell you're running the above
    commands in. Refer to the [AWS CLI documentation](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-quickstart.html)
    for more information.

In the config file, the location should be passed to the `static_root`-field. Any arguments specified to the
`static_fs_args`-field will be passed to [S3FileSystem](https://s3fs.readthedocs.io/en/latest/api.html#s3fs.core.S3FileSystem).
`profile` should be one of the profiles set up in your `~/.aws/credentials` file.

```json
{
  "static_root": "s3://bucket-name/copick_project_static/",
  "static_fs_args": {
        "profile": "example_profile"
    }
}
```

??? note "More about `static_fs_args` ..."
    Specifying `profile` is one possible way of setting up AWS credentials. Refer to the [S3FS documentation](https://s3fs.readthedocs.io/en/latest/api.html#s3fs.core.S3FileSystem)
    for detailed information.

    For local [MinIO](https://min.io/) buckets, the following config may be appropriate:

    ```json
    {
        "static_fs_args": {
            "key":"bucketkey",
            "secret":"bucketsecret",
            "endpoint_url":"http://10.30.121.49:7070",
            "client_kwargs":{
                "region_name":"us-east-1"
            }
    }
    ```
