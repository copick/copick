from dataclasses import dataclass

from copick.models import (
    CopickRoot,
)

_KNOWN_IMPORTERS = {
    "object": [],
    "tomogram": [],
    "features": [],
    "picks": [],
    "segmentation": [],
}


@dataclass
class ImportSpec:
    pass


@dataclass
class ImporterSpec:
    output_type: str


class CopickImporter:
    def __init__(self, root: CopickRoot):
        self.root = root
