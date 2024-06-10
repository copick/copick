from dataclasses import dataclass
from typing import Dict, List

import click
import numpy as np

from copick.models import (
    CopickRoot,
    CopickTomogram,
)
from copick.ops._ops import OpsRegistry, OpsSpec


####################################################################################################
# Common setup
####################################################################################################
@dataclass
class ImporterSpec(OpsSpec):
    pass


common_args = [
    click.Argument(("path",), required=True, type=str),
]

common_opts = [
    click.Option(("-c", "--config"), type=str, help="Path to the configuration file.", required=True),
    click.Option(("--create",), is_flag=True, help="Create the object if it does not exist.", default=True),
    click.Option(("--overwrite",), is_flag=True, help="Overwrite the object if it exists.", default=False),
]
####################################################################################################

####################################################################################################
# Run importers
####################################################################################################
run_args = [
    click.Argument(("name",), required=True, type=str),
]


####################################################################################################

####################################################################################################
# Tomogram importers
####################################################################################################
tomo_opts = [
    click.Option(
        ("-r", "--run"),
        type=str,
        help="The run the tomogram is part of. Default: Name of the input file.",
        default=None,
    ),
    click.Option(
        ("-vs", "--voxel-spacing"),
        type=float,
        help="The voxel size of the tomogram. Default: Spacing of the input file.",
        default=None,
    ),
    click.Option(
        ("-tt", "--tomo-type"),
        type=str,
        help="The type of the tomogram in copick. Default: Name of the input file.",
        default=None,
    ),
    click.Option(
        ("-bf", "--bin-factors"),
        type=str,
        help="The multiscale binning factors of the tomogram to store (created if not present). Default: 1,2,4.",
        default="1,2,4",
    ),
]


def import_tomo(
    root: CopickRoot,
    volume: Dict[float, np.ndarray],
    tomo_type: str,
    run: str,
    voxel_spacing: float = None,
    create: bool = True,
    overwrite: bool = False,
    bin_factors: List[int] = None,
):
    """Import a tomogram into copick.

    Args:
        root (CopickRoot): The copick root object.
        volume (Dict[float, np.ndarray]): Multi-scale pyramid of the tomogram. Keys are the voxel size in Angstroms.
        create (bool, optional): Create the object if it does not exist. Defaults to True.
        overwrite (bool, optional): Overwrite the object if it exists. Defaults to False.
        run (str, optional): The run the tomogram is part of. Default: Name of the input file.


    """
    if bin_factors is None:
        bin_factors = [1, 2, 4]
    pass


def import_tomo_mrc():
    pass


tomo_mrc_spec = ImporterSpec(
    name="mrc",
    help="Import a tomogram from an MRC file.",
    op=import_tomo_mrc,
    args=common_args,
    opts=common_opts + tomo_opts,
    input_type=None,
    output_type=CopickTomogram,
)
####################################################################################################

_KNOWN_IMPORTERS = [
    tomo_mrc_spec,
]


class ImportRegistry(OpsRegistry):
    specs = _KNOWN_IMPORTERS
    name = "import"
    short_help = "Import data into copick."

    def __init__(self, root: CopickRoot):
        self.root = root
