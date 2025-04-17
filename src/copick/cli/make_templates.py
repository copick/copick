import json

import click

from copick.impl.cryoet_data_portal import CopickConfigCDP
from copick.impl.filesystem import CopickConfigFSSpec
from copick.models import PickableObject

LOCAL_OVERLAY = {
    "overlay_root": "local:///path/to/copick_project/",
    "overlay_fs_args": {
        "auto_mkdir": True,
    },
}

SMB_OVERLAY = {
    "overlay_root": "smb:///shared_drive/copick_project/",
    "overlay_fs_args": {
        "host": "192.158.1.38",
        "username": "user.name",
        "password": "1234",
        "temppath": "/shared_drive",
        "auto_mkdir": True,
    },
}

S3_OVERLAY = {
    "overlay_root": "s3://bucket/copick_project/",
    "overlay_fs_args": {
        "profile": "your_profile",
    },
}

SSH_OVERLAY = {
    "overlay_root": "ssh:///hpc/storage/copick_project/",
    "overlay_fs_args": {
        "username": "user.name",
        "host": "hpc.example.com",
        "port": 22,
    },
}

LOCAL_STATIC = {
    "static_root": "local:///path/to/copick_project_static/",
    "static_fs_args": {
        "auto_mkdir": True,
    },
}

SMB_STATIC = {
    "static_root": "smb:///shared_drive/copick_project_static/",
    "static_fs_args": {
        "host": "192.158.1.38",
        "username": "user.name",
        "password": "1234",
        "temppath": "/shared_drive",
        "auto_mkdir": True,
    },
}

S3_STATIC = {
    "static_root": "s3://bucket/copick_project_static/",
    "static_fs_args": {
        "profile": "your_profile",
    },
}

SSH_STATIC = {
    "static_root": "ssh:///hpc/storage/copick_project_static/",
    "static_fs_args": {
        "username": "user.name",
        "password": "1234",
        "host": "hpc.example.com",
        "port": 22,
    },
}

DATA_PORTAL = {
    "dataset_ids": [10301, 10302],
}


OVERLAY_LOCATIONS = {
    "local": LOCAL_OVERLAY,
    "smb": SMB_OVERLAY,
    "s3": S3_OVERLAY,
    "ssh": SSH_OVERLAY,
}

STATIC_LOCATIONS = {
    "local": LOCAL_STATIC,
    "smb": SMB_STATIC,
    "s3": S3_STATIC,
    "ssh": SSH_STATIC,
}

OBJECTS = [
    PickableObject(
        name="ribosome",
        is_particle=True,
        identifier="GO:0022626",
        label=1,
        color=[0, 117, 220, 255],
        radius=150,
    ),
    PickableObject(
        name="atpase",
        is_particle=True,
        identifier="GO:0045259",
        label=2,
        color=[251, 192, 147, 255],
        radius=150,
    ),
    PickableObject(
        name="membrane",
        is_particle=False,
        identifier="GO:0016020",
        label=3,
        color=[200, 200, 200, 255],
        radius=10,
    ),
]


@click.command()
@click.option(
    "--outdir",
    "-o",
    default="docs/templates/configs/",
    help="Output directory for the templates.",
)
@click.pass_context
def create(ctx, outdir: str = "docs/templates/configs/") -> None:
    # Overlay only
    for overlay_type, overlay in OVERLAY_LOCATIONS.items():
        config = CopickConfigFSSpec(
            name="Example Project",
            description=f"This is an example project, demonstrating an overlay-only {overlay_type}-backend project.",
            version="0.5.0",
            pickable_objects=OBJECTS,
            user_id="example.user",
            **overlay,
        )
        config.config_type = "filesystem"
        with open(f"{outdir}/overlay_{overlay_type}.json", "w") as f:
            f.write(json.dumps(config.dict(exclude_unset=True), indent=4))

    # static/overlay
    for overlay_type, overlay in OVERLAY_LOCATIONS.items():
        for static_type, static in STATIC_LOCATIONS.items():
            config = CopickConfigFSSpec(
                name="Example Project",
                description=f"This is an example project, demonstrating overlaying a {overlay_type}-backend on"
                f"a project in a {static_type}-backend.",
                version="0.5.0",
                pickable_objects=OBJECTS,
                user_id="example.user",
                **overlay,
                **static,
            )
            config.config_type = "filesystem"
            with open(f"{outdir}/overlay_{overlay_type}_static_{static_type}.json", "w") as f:
                f.write(json.dumps(config.dict(exclude_unset=True), indent=4))

    # CDP
    for overlay_type, overlay in OVERLAY_LOCATIONS.items():
        config = CopickConfigCDP(
            name="Example Project",
            description=f"This is an example project, demonstrating overlaying a {overlay_type}-backend on"
            f" a CZ cryoET Data Portal dataset.",
            version="0.5.0",
            pickable_objects=OBJECTS,
            user_id="example.user",
            **overlay,
            **DATA_PORTAL,
        )
        config.config_type = "cryoet_data_portal"
        with open(f"{outdir}/overlay_{overlay_type}_static_data_portal.json", "w") as f:
            f.write(json.dumps(config.dict(exclude_unset=True), indent=4))


if __name__ == "__main__":
    create()
