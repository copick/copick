import json
import shutil
import tempfile
from pathlib import Path, PurePath

import fsspec
import pooch
import pytest

OZ = pooch.os_cache("test_data")  # Path("/Users/utz.ermel/Documents/copick/testproject")  # pooch.os_cache("test_data")
TOTO = pooch.create(
    path=OZ,
    base_url="doi:10.5281/zenodo.11238625",
    registry={
        "sample_project.zip": "md5:b06ee6f4541b1ad06c988c8ca8d09945",
    },
)


CLEANUP = True


@pytest.fixture(scope="session")
def local_path() -> Path:
    TOTO.fetch("sample_project.zip", processor=pooch.Unzip(extract_dir="sample_project"))
    yield OZ / "sample_project"

    if CLEANUP:
        shutil.rmtree(OZ / "sample_project")


@pytest.fixture(scope="session")
def base_project_directory(local_path) -> Path:
    return local_path / "sample_project"


@pytest.fixture(scope="session")
def base_overlay_directory(local_path) -> Path:
    return local_path / "sample_overlay"


@pytest.fixture(scope="session")
def base_config_overlay_only(local_path) -> Path:
    return local_path / "filesystem_overlay_only.json"


@pytest.fixture(scope="session")
def base_config(local_path) -> Path:
    return local_path / "filesystem.json"


COMMON_CASES = []


@pytest.fixture
def local_overlay_only(base_project_directory, base_config_overlay_only):
    # Copy project to temp directory
    temp_dir = Path(tempfile.mkdtemp())
    project_directory = temp_dir / "sample_project_overlay"
    config = temp_dir / "local_overlay_only.json"
    shutil.copytree(base_project_directory, project_directory)

    # Open baseline config
    with open(base_config_overlay_only, "r") as f:
        cfg = json.load(f)

    # Set the overlay root to the sample project
    cfg["overlay_root"] = "local://" + str(project_directory)
    cfg["overlay_fs_args"] = {"auto_mkdir": True}

    # Write the config to the local path
    with open(config, "w") as f:
        json.dump(cfg, f)

    payload = {
        "cfg_file": config,
        "testfs_static": None,
        "testpath_static": None,
        "testfs_overlay": fsspec.filesystem("local"),
        "testpath_overlay": PurePath(project_directory),
    }

    yield payload

    if CLEANUP:
        shutil.rmtree(temp_dir)


@pytest.fixture
def local(base_project_directory, base_overlay_directory, base_config):
    # Copy project to temp directory
    temp_dir = Path(tempfile.mkdtemp())
    project_directory = temp_dir / "sample_project"
    overlay_directory = temp_dir / "sample_overlay"
    config = temp_dir / "local.json"
    shutil.copytree(base_project_directory, project_directory)
    shutil.copytree(base_overlay_directory, overlay_directory)

    with open(base_config, "r") as f:
        cfg = json.load(f)

    # Set the overlay root to the sample project overlay
    cfg["overlay_root"] = "local://" + str(overlay_directory)
    cfg["overlay_fs_args"] = {"auto_mkdir": True}

    # Set the static root to the sample project
    cfg["static_root"] = "local://" + str(project_directory)
    cfg["static_fs_args"] = {"auto_mkdir": False}

    # Write the config to the local path
    with open(config, "w") as f:
        json.dump(cfg, f)

    payload = {
        "cfg_file": config,
        "testfs_static": fsspec.filesystem("local"),
        "testpath_static": PurePath(project_directory),
        "testfs_overlay": fsspec.filesystem("local"),
        "testpath_overlay": PurePath(overlay_directory),
    }

    yield payload

    if CLEANUP:
        shutil.rmtree(temp_dir)


COMMON_CASES.extend(["local_overlay_only", "local"])

# try:
#     import s3fs
#
#     @pytest.fixture(scope="session")
#     def s3_params():
#         pass
#
#     @pytest.fixture(scope="session")
#     def cfg_s3_overlay_only():
#         pass
#
# except ImportError:
#     pass
#
#
# try:
#     import smbclient
#
#     @pytest.fixture(scope="session")
#     def smb_params():
#         pass
#
#     @pytest.fixture(scope="session")
#     def cfg_smb_overlay_only():
#         pass
#
#     def cfg_smb_local():
#         pass
#
# except ImportError:
#     pass
#
#
# try:
#     import sshfs
#
#     @pytest.fixture(scope="session")
#     def ssh_params():
#         pass
#
#     @pytest.fixture(scope="session")
#     def cfg_ssh_overlay_only():
#         pass
#
#     @pytest.fixture(scope="session")
#     def cfg_ssh_local():
#         pass
#
# except ImportError:
#     pass


def pytest_configure():
    pytest.common_cases = COMMON_CASES
