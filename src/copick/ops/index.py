import logging
from typing import Iterable, List, Union

from copick.models import (
    CopickRoot,
    CopickRun,
    CopickVoxelSpacing,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def index_segmentations(
    root: CopickRoot,
    run: Union[str, CopickRun],
    voxel_spacings: Union[float, Iterable[float], None] = None,
    do_print: bool = False,
    log_level: int = logging.INFO,
) -> Union[List[str], None]:
    """Index and optionally print the segmentations associated with a run."""

    logger.setLevel(log_level)

    if isinstance(run, str):
        run = root.get_run(name=run)
        if run is None:
            logger.error(f"Run {run} not found.")
            return None

    if voxel_spacings is None:
        voxel_spacings = []
    elif isinstance(voxel_spacings, float):
        voxel_spacings = run.get_voxel_spacing(voxel_spacings)
    elif isinstance(voxel_spacings, Iterable):
        voxel_spacings = [run.get_voxel_spacing(spacing) for spacing in voxel_spacings]

    segs = {}
    for seg in run.segmentations:
        seglist = segs.get(seg.voxel_size, [])
        seglist.append(seg)

    lines = []

    for spacing, seglist in segs.items():
        lines.append(f"Voxel Spacing: {spacing}")
        for seg in seglist:
            lines.append(f"\t{seg}")

    if do_print:
        for line in lines:
            print(line)

    return lines


def index_meshes(
    root: CopickRoot,
    run: Union[str, CopickRun],
    do_print: bool = False,
) -> Union[List[str], None]:
    """ "Index and optionally print the meshes associated with a run."""

    if isinstance(run, str):
        run = root.get_run(name=run)

    meshes = run.meshes

    lines = []

    for mesh in meshes:
        lines.append(f"{mesh}")

    if do_print:
        for line in lines:
            print(line)

    return lines


def index_picks(
    root: CopickRoot,
    run: Union[str, CopickRun],
    do_print: bool = False,
) -> Union[List[str], None]:
    """Index and optionally print the picks associated with a run."""

    if isinstance(run, str):
        run = root.get_run(name=run)

    picks = run.picks

    lines = []

    for pick in picks:
        lines.append(f"{pick}")

    if do_print:
        for line in lines:
            print(line)

    return lines


def index_voxelspacings(
    root: CopickRoot,
    run: Union[str, CopickRun],
    descend: bool = False,
    do_print: bool = False,
) -> Union[List[str], None]:
    """Index and optionally print the voxel spacings associated with a run."""

    if isinstance(run, str):
        run = root.get_run(name=run)

    voxelspacings = run.voxel_spacings

    lines = []

    for voxelspacing in voxelspacings:
        lines.append(f"{voxelspacing}")
        if descend:
            tlines = index_tomograms(root, run, voxelspacing, descend=True, do_print=False)
            for line in tlines:
                lines.append(f"\t{line}")

    if do_print:
        for line in lines:
            print(line)

    return lines


def index_tomograms(
    root: CopickRoot,
    run: Union[str, CopickRun],
    voxel_spacing: Union[CopickVoxelSpacing, float] = None,
    descend: bool = False,
    do_print: bool = False,
) -> Union[List[str], None]:
    """Index and optionally print the tomograms associated with a run."""
    pass
    # if isinstance(run, str):
    #     run = root.get_run(name=run)
    #
    # if voxel_spacing is not None:
    #     if isinstance(voxel_spacing, float):
    #         voxel_spacings = [run.get_voxel_spacing(voxel_spacing)
    #
    #
    # tomograms = run.get_tomogram(voxel_spacing)
    #
    # tomograms = run.
    #
    # lines = []
    #
    # for tomogram in tomograms:
    #     lines.append(f"{tomogram}")
    #
    # if do_print:
    #     for line in lines:
    #         print(line)
    #
    # return lines


def index_features(
    root: CopickRoot,
    run: Union[str, CopickRun],
    voxel_spacing: Union[float, None] = None,
    do_print: bool = False,
) -> Union[List[str], None]:
    """Print the contents of the picks object."""


def index_runs(
    root: CopickRoot,
):
    """Print the contents of the runs object."""

    for run in root.runs:
        print(run.name)


def index_run(
    run: CopickRun,
):
    """Print the contents of the run object."""
    pass


def index_root(
    root: CopickRoot,
    do_print: bool = False,
):
    """Print the contents of the root object."""
    pass
