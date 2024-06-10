from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Type, Union

import click

from copick.models import (
    CopickFeatures,
    CopickObject,
    CopickPicks,
    CopickSegmentation,
    CopickTomogram,
)

EntityType = Union[
    Type[CopickObject],
    Type[CopickTomogram],
    Type[CopickFeatures],
    Type[CopickPicks],
    Type[CopickSegmentation],
]

EntityInstance = Union[
    CopickObject,
    CopickTomogram,
    CopickFeatures,
    CopickPicks,
    CopickSegmentation,
]

ENTITY_ALIAS = {
    CopickObject: "object",
    CopickTomogram: "tomogram",
    CopickFeatures: "features",
    CopickPicks: "picks",
    CopickSegmentation: "segmentation",
}

ENTITY_HELP = {
    CopickObject: "A density map.",
    CopickTomogram: "A tomogram.",
    CopickFeatures: "A set of features.",
    CopickPicks: "A set of picks.",
    CopickSegmentation: "A segmentation.",
}


@dataclass
class ArgSpec:
    name: str
    type: Type
    help: str = ""
    default: Any = None


@dataclass
class OptionSpec:
    name: str
    type: Type
    help: str
    default: Any = None


@dataclass
class OpsSpec:
    name: str
    help: str
    op: Callable
    args: List[click.Argument]
    opts: List[click.Option]
    input_type: Optional[EntityType] = None
    output_type: Optional[EntityType] = None


class OpsRegistry:
    name = ""
    short_help = ""
    specs: List[OpsSpec] = []

    def _ops_map(self):
        """Create a mapping of input/output types to operation specs."""
        return {(spec.input_type, spec.output_type): spec for spec in self.specs}

    def _run(self, spec: OpsSpec, *args, **kwargs) -> EntityInstance:
        """Run an operation spec."""
        return spec.op(*args, **kwargs)

    def cli_group(self):
        """Create a click.Group object for the registry."""
        main_group = click.Group(self.name, short_help=self.short_help)

        for s in self.specs:
            op = s.op

            group = main_group

            if s.input_type:
                if ENTITY_ALIAS[s.input_type] not in group.commands:
                    ng = click.Group(ENTITY_ALIAS[s.input_type], short_help=ENTITY_HELP[s.input_type])
                    group.add_command(ng)
                    group = ng
                else:
                    group = group.commands[ENTITY_ALIAS[s.input_type]]

            if s.output_type:
                if ENTITY_ALIAS[s.output_type] not in group.commands:
                    ng = click.Group(ENTITY_ALIAS[s.output_type], short_help=ENTITY_HELP[s.output_type])
                    group.add_command(ng)
                    group = ng
                else:
                    group = group.commands[ENTITY_ALIAS[s.output_type]]

            params = []

            for aspec in s.args:
                params.append(aspec)

            for ospec in s.opts:
                params.append(ospec)

            com = click.Command(s.name, callback=op, params=params, help=s.help)
            group.add_command(com)

        return main_group
