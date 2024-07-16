###album catalog: mycatalog

from album.runner.api import get_args, setup

env_file = """
channels:
  - conda-forge
  - defaults
dependencies:
  - python=3.11
  - pip
  - zarr
  - ome-zarr
  - numpy<2
  - scipy
  - scikit-image
  - trimesh
  - pip:
    - album
    - "copick[all]>=0.5.2"
"""

args = [
    {
        "name": "copick_config_path",
        "description": "Path to the copick config file",
        "type": "string",
        "required": True,
    },
    {
        "name": "run_names",
        "description": "List of comma-separated run names to process",
        "type": "string",
        "required": False,
        "default": "",
    },
    {
        "name": "voxel_spacing",
        "description": "Voxel spacing for the tomograms",
        "type": "float",
        "required": False,
        "default": 10.0,
    },
    {
        "name": "tomo_type",
        "description": "Type of tomogram",
        "type": "string",
        "required": False,
        "default": "wbp",
    },
    {
        "name": "out_object",
        "description": "Name of the output pickable object.",
        "type": "string",
        "required": False,
        "default": "random-points",
    },
    {
        "name": "out_user",
        "description": "User/Tool name for output points.",
        "type": "string",
        "required": False,
        "default": "solution-01",
    },
    {
        "name": "out_session",
        "description": "Output session, indicating this set was generated by a tool.",
        "type": "string",
        "required": False,
        "default": "0",
    },
]


def run():
    # Imports
    import copick
    from copick.models import CopickRun

    # Parse arguments
    args = get_args()
    copick_config_path = args.copick_config_path

    run_names = args.run_names.split(",")

    # Function definitions
    def process_run(run: CopickRun):
        # some code ...
        pass

    # Load copick project root
    root = copick.from_file(copick_config_path)

    # If no run names are provided, process all runs
    if run_names == [""]:
        run_names = [r.name for r in root.runs]

    # Process runs
    for run_name in run_names:
        print(f"Processing run {run_name}")
        run = root.get_run(run_name)

        process_run(run)

        # Store result

    print("Processing complete.")


setup(
    group="copick",
    name="solution-name",
    version="0.1.0",
    title="Template",
    description="Description.",
    solution_creators=["Alice", "Bob"],
    tags=["copick"],
    license="MIT",
    album_api_version="0.5.1",
    args=args,
    run=run,
    dependencies={"environment_file": env_file},
)
