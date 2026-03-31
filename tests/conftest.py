import json
import os
import shutil
import tempfile
import time
import uuid
from importlib import util as importlib_util
from pathlib import Path, PurePath

import fsspec
import pooch
import pytest

# Directory containing this conftest.py file - used for resolving relative paths
TESTS_DIR = Path(__file__).parent
DOCKER_COMPOSE_FILE = TESTS_DIR / "docker-compose.yml"

OZ = pooch.os_cache("test_data")  # Path("/Users/utz.ermel/Documents/copick/testproject")  # pooch.os_cache("test_data")
TOTO = pooch.create(
    path=OZ,
    base_url="doi:10.5281/zenodo.16996074",
    registry={
        "sample_project.zip": "md5:4d25e40fbbc3510756a0547d2e02b9b4",
    },
)

# Determine if all tests should be run
RUN_ALL = bool(int(os.environ.get("RUN_ALL", 1)))

CLEANUP = True


def _copytree_world_writable(src: Path, dst: Path):
    """Copy directory tree with world-readable/writable permissions for Docker volume mounts."""
    shutil.copytree(src, dst)
    for root, dirs, files in os.walk(dst):
        for d in dirs:
            os.chmod(os.path.join(root, d), 0o777)
        for f in files:
            os.chmod(os.path.join(root, f), 0o666)


@pytest.fixture(scope="session")
def local_path() -> Path:
    # Test data is pre-extracted in pytest_configure to avoid xdist race conditions.
    # The pooch cache persists between runs — no cleanup needed for shared data.
    return OZ / "sample_project"


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


if importlib_util.find_spec("s3fs") and RUN_ALL:

    def _seed_s3(local_dir: Path, s3_prefix: str, endpoint_url: str):
        """Seed mock S3 with test data using boto3 (no subprocess overhead)."""
        import boto3

        parts = s3_prefix.replace("s3://", "").rstrip("/").split("/", 1)
        bucket = parts[0]
        key_prefix = (parts[1] + "/") if len(parts) > 1 else ""

        s3 = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id="test",
            aws_secret_access_key="test",
            region_name="us-west-2",
        )

        try:
            s3.head_bucket(Bucket=bucket)
        except Exception:
            s3.create_bucket(
                Bucket=bucket,
                CreateBucketConfiguration={"LocationConstraint": "us-west-2"},
            )

        for root, _dirs, files in os.walk(local_dir):
            for fname in files:
                local_file = Path(root) / fname
                rel = str(local_file.relative_to(local_dir))
                s3.upload_file(str(local_file), bucket, key_prefix + rel)

    @pytest.fixture(scope="session")
    def s3_container(worker_id):
        from moto.server import ThreadedMotoServer

        # Unique port per xdist worker (or default for non-xdist)
        port = 4001 if worker_id == "master" else 4001 + int(worker_id.replace("gw", "")) + 1

        server = ThreadedMotoServer(port=port, verbose=False)
        server.start()
        yield "s3://test-bucket/", f"http://127.0.0.1:{port}"
        server.stop()

    @pytest.fixture
    def s3_overlay_only(s3_container, base_project_directory, base_config_overlay_only):
        s3_prefix, endpoint_url = s3_container

        # Temp dir for config
        temp_dir = Path(tempfile.mkdtemp())
        config = temp_dir / "s3_overlay_only.json"

        # To ensure that each test has a unique project directory, generate UUID names
        project_directory = f"{s3_prefix}sample_project_overlay_only_{uuid.uuid1()}/"
        _seed_s3(base_project_directory, project_directory, endpoint_url)

        # Open baseline config
        with open(base_config_overlay_only, "r") as f:
            cfg = json.load(f)

        # Set the overlay root to the sample project
        cfg["overlay_root"] = str(project_directory)
        cfg["overlay_fs_args"] = {
            "key": "test",
            "secret": "test",
            "endpoint_url": endpoint_url,
            "client_kwargs": {"region_name": "us-west-2"},
        }

        # Write the config to the local path
        with open(config, "w") as f:
            json.dump(cfg, f)

        payload = {
            "cfg_file": config,
            "testfs_static": None,
            "testpath_static": None,
            "testfs_overlay": fsspec.filesystem("s3", **cfg["overlay_fs_args"]),
            "testpath_overlay": PurePath(project_directory.replace("s3://", "")),
        }

        yield payload

        if CLEANUP:
            shutil.rmtree(temp_dir)

    @pytest.fixture
    def s3(s3_container, base_project_directory, base_overlay_directory, base_config_overlay_only):
        s3_prefix, endpoint_url = s3_container

        # Temp dir for config
        temp_dir = Path(tempfile.mkdtemp())
        config = temp_dir / "s3.json"

        # To ensure that each test has a unique project directory, generate UUID names
        project_directory = f"{s3_prefix}sample_project_{uuid.uuid1()}/"
        _seed_s3(base_project_directory, project_directory, endpoint_url)

        overlay_directory = f"{s3_prefix}sample_overlay_{uuid.uuid1()}/"
        _seed_s3(base_overlay_directory, overlay_directory, endpoint_url)

        # Open baseline config
        with open(base_config_overlay_only, "r") as f:
            cfg = json.load(f)

        # Set the overlay root to the sample project
        cfg["overlay_root"] = str(overlay_directory)
        cfg["overlay_fs_args"] = {
            "key": "test",
            "secret": "test",
            "endpoint_url": endpoint_url,
            "client_kwargs": {"region_name": "us-west-2"},
        }

        # Set the static root to the sample project
        cfg["static_root"] = str(project_directory)
        cfg["static_fs_args"] = {
            "key": "test",
            "secret": "test",
            "endpoint_url": endpoint_url,
            "client_kwargs": {"region_name": "us-west-2"},
        }

        # Write the config to the local path
        with open(config, "w") as f:
            json.dump(cfg, f)

        payload = {
            "cfg_file": config,
            "testfs_static": fsspec.filesystem("s3", **cfg["static_fs_args"]),
            "testpath_static": PurePath(project_directory.replace("s3://", "")),
            "testfs_overlay": fsspec.filesystem("s3", **cfg["overlay_fs_args"]),
            "testpath_overlay": PurePath(overlay_directory.replace("s3://", "")),
        }

        yield payload

        if CLEANUP:
            shutil.rmtree(temp_dir)

    COMMON_CASES.extend(["s3_overlay_only", "s3"])


if importlib_util.find_spec("sshfs") and RUN_ALL:
    # Host-side directory for SSH test data, placed under the existing /config volume mount.
    # This maps to /config/test_data/ inside the SSH container — no extra docker-compose
    # volume needed.
    SSH_DATA_DIR = TESTS_DIR / "bin" / "ssh" / "test_data"

    @pytest.fixture(scope="session")
    def ssh_container():
        os.system(f"docker compose -f {DOCKER_COMPOSE_FILE} --profile sshfs up -d")
        # On startup we need to wait for the service to fully initialize (user creation, SSH setup).
        time.sleep(3)

        # Ensure host-side data directory exists and is world-writable so the SSH
        # user (UID 1000) can create new directories inside it (e.g. sync test targets).
        SSH_DATA_DIR.mkdir(parents=True, exist_ok=True)
        os.chmod(SSH_DATA_DIR, 0o777)

        yield "ssh:///config/test_data/"

        # Don't clean up SSH_DATA_DIR or stop the container here: with pytest-xdist,
        # other workers may still be using them. Individual test fixtures clean up their
        # own UUID directories. The container is ephemeral on CI and can be stopped
        # manually locally via `docker compose --profile sshfs down`.

    @pytest.fixture
    def ssh_overlay_only(ssh_container, base_project_directory, base_config_overlay_only):
        # Temp dir for config
        temp_dir = Path(tempfile.mkdtemp())
        config = temp_dir / "ssh_overlay_only.json"

        # To ensure that each test has a unique project directory, generate UUID names
        uid = uuid.uuid1()
        project_directory = f"{ssh_container}sample_project_{uid}"
        project_directory_stripped = project_directory.replace("ssh://", "")

        # Seed via volume mount (instant local copy instead of scp)
        local_seed_path = SSH_DATA_DIR / f"sample_project_{uid}"
        _copytree_world_writable(base_project_directory, local_seed_path)

        # Open baseline config
        with open(base_config_overlay_only, "r") as f:
            cfg = json.load(f)

        # Set the overlay root to the sample project
        cfg["overlay_root"] = str(project_directory)
        cfg["overlay_fs_args"] = {
            "host": "localhost",
            "port": 2222,
            "username": "test.user",
            "password": "password",
            "known_hosts": None,
        }

        # Write the config to the local path
        with open(config, "w") as f:
            json.dump(cfg, f, indent=4)

        payload = {
            "cfg_file": config,
            "testfs_static": None,
            "testpath_static": None,
            "testfs_overlay": fsspec.filesystem("ssh", **cfg["overlay_fs_args"]),
            "testpath_overlay": PurePath(project_directory_stripped),
        }

        yield payload

        if CLEANUP:
            shutil.rmtree(temp_dir)
            if local_seed_path.exists():
                shutil.rmtree(local_seed_path)

    @pytest.fixture
    def ssh(ssh_container, base_project_directory, base_overlay_directory, base_config_overlay_only):
        # Temp dir for config
        temp_dir = Path(tempfile.mkdtemp())
        config = temp_dir / "ssh.json"

        # To ensure that each test has a unique project directory, generate UUID names
        uid_proj = uuid.uuid1()
        project_directory = f"{ssh_container}sample_project_{uid_proj}"
        project_directory_stripped = project_directory.replace("ssh://", "")

        # Seed project via volume mount
        local_seed_proj = SSH_DATA_DIR / f"sample_project_{uid_proj}"
        _copytree_world_writable(base_project_directory, local_seed_proj)

        uid_overlay = uuid.uuid1()
        overlay_directory = f"{ssh_container}sample_overlay_{uid_overlay}"
        overlay_directory_stripped = overlay_directory.replace("ssh://", "")

        # Seed overlay via volume mount
        local_seed_overlay = SSH_DATA_DIR / f"sample_overlay_{uid_overlay}"
        _copytree_world_writable(base_overlay_directory, local_seed_overlay)

        # Open baseline config
        with open(base_config_overlay_only, "r") as f:
            cfg = json.load(f)

        # Set the overlay root to the sample project
        cfg["overlay_root"] = str(overlay_directory)
        cfg["overlay_fs_args"] = {
            "host": "localhost",
            "port": 2222,
            "username": "test.user",
            "password": "password",
            "known_hosts": None,
        }

        # Set the static root to the sample project
        cfg["static_root"] = str(project_directory)
        cfg["static_fs_args"] = {
            "host": "localhost",
            "port": 2222,
            "username": "test.user",
            "password": "password",
            "known_hosts": None,
        }

        # Write the config to the local path
        with open(config, "w") as f:
            json.dump(cfg, f, indent=4)

        payload = {
            "cfg_file": config,
            "testfs_static": fsspec.filesystem("ssh", **cfg["static_fs_args"]),
            "testpath_static": PurePath(project_directory_stripped),
            "testfs_overlay": fsspec.filesystem("ssh", **cfg["overlay_fs_args"]),
            "testpath_overlay": PurePath(overlay_directory_stripped),
        }

        yield payload

        if CLEANUP:
            shutil.rmtree(temp_dir)
            if local_seed_proj.exists():
                shutil.rmtree(local_seed_proj)
            if local_seed_overlay.exists():
                shutil.rmtree(local_seed_overlay)

    COMMON_CASES.extend(["ssh_overlay_only", "ssh"])


if importlib_util.find_spec("smbclient") and RUN_ALL:

    @pytest.fixture(scope="session")
    def smb_container():
        os.system(f"docker compose -f {DOCKER_COMPOSE_FILE} --profile smb up -d")
        # On startup we need to wait for the service to fully initialize.
        time.sleep(3)
        yield "smb:///data/"
        os.system(f"docker compose -f {DOCKER_COMPOSE_FILE} --profile smb stop")

    @pytest.fixture
    def smb_overlay_only(smb_container, base_project_directory, base_config_overlay_only):
        # Temp dir for config
        temp_dir = Path(tempfile.mkdtemp())
        config = temp_dir / "smb_overlay_only.json"

        # To ensure that each test has a unique project directory, generate UUID names
        project_directory = f"{smb_container}sample_project_{uuid.uuid1()}"
        project_directory_stripped = project_directory.replace("smb:///data/", "")
        os.system(f'bash "{TESTS_DIR / "seed_smb.sh"}" "{base_project_directory}/*" "{project_directory_stripped}"')

        # Open baseline config
        with open(base_config_overlay_only, "r") as f:
            cfg = json.load(f)

        # Set the overlay root to the sample project
        cfg["overlay_root"] = str(project_directory)
        cfg["overlay_fs_args"] = {
            "host": "localhost",
            "username": "test.user",
            "password": "password",
            "auto_mkdir": True,
        }

        # Write the config to the local path
        with open(config, "w") as f:
            json.dump(cfg, f, indent=4)

        payload = {
            "cfg_file": config,
            "testfs_static": None,
            "testpath_static": None,
            "testfs_overlay": fsspec.filesystem("smb", **cfg["overlay_fs_args"]),
            "testpath_overlay": PurePath(project_directory.replace("smb://", "")),
        }

        yield payload

        if CLEANUP:
            shutil.rmtree(temp_dir)
            shutil.rmtree(TESTS_DIR / "bin" / "smb" / project_directory_stripped)

    @pytest.fixture
    def smb(smb_container, base_project_directory, base_overlay_directory, base_config_overlay_only):
        # Temp dir for config
        temp_dir = Path(tempfile.mkdtemp())
        config = temp_dir / "smb.json"

        # To ensure that each test has a unique project directory, generate UUID names
        project_directory = f"{smb_container}sample_project_{uuid.uuid1()}"
        project_directory_stripped = project_directory.replace("smb:///data/", "")
        os.system(f'bash "{TESTS_DIR / "seed_smb.sh"}" "{base_project_directory}/*" "{project_directory_stripped}"')

        overlay_directory = f"{smb_container}sample_overlay_{uuid.uuid1()}"
        overlay_directory_stripped = overlay_directory.replace("smb:///data/", "")
        os.system(f'bash "{TESTS_DIR / "seed_smb.sh"}" "{base_overlay_directory}/*" "{overlay_directory_stripped}"')

        # Open baseline config
        with open(base_config_overlay_only, "r") as f:
            cfg = json.load(f)

        # Set the overlay root to the sample project
        cfg["overlay_root"] = str(overlay_directory)
        cfg["overlay_fs_args"] = {
            "host": "localhost",
            "username": "test.user",
            "password": "password",
            "auto_mkdir": True,
        }

        # Set the overlay root to the sample project
        cfg["static_root"] = str(project_directory)
        cfg["static_fs_args"] = {
            "host": "localhost",
            "username": "test.user",
            "password": "password",
        }

        # Write the config to the local path
        with open(config, "w") as f:
            json.dump(cfg, f, indent=4)

        payload = {
            "cfg_file": config,
            "testfs_static": fsspec.filesystem("smb", **cfg["static_fs_args"]),
            "testpath_static": PurePath(project_directory.replace("smb://", "")),
            "testfs_overlay": fsspec.filesystem("smb", **cfg["overlay_fs_args"]),
            "testpath_overlay": PurePath(overlay_directory.replace("smb://", "")),
        }

        yield payload

        if CLEANUP:
            shutil.rmtree(temp_dir)
            shutil.rmtree(TESTS_DIR / "bin" / "smb" / project_directory_stripped)
            shutil.rmtree(TESTS_DIR / "bin" / "smb" / overlay_directory_stripped)

    # COMMON_CASES.extend(["smb_overlay_only", "smb"])


def pytest_configure(config):
    # Pre-extract test data in the controller process before xdist workers spawn.
    # This avoids race conditions where multiple workers try to unzip simultaneously.
    extract_path = OZ / "sample_project"
    if not (extract_path / "sample_project").exists():
        # Remove partial extractions if any
        if extract_path.exists():
            shutil.rmtree(extract_path)
        TOTO.fetch("sample_project.zip", processor=pooch.Unzip(extract_dir="sample_project"))

    pytest.common_cases = COMMON_CASES
