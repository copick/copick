### Set up your project overlay

This directory will contain all newly created data for your project.

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
