from dataclasses import dataclass
from functools import partial
from typing import Any, Callable, List, Optional, Type, Union

import click

from copick import from_file
from copick.models import (
    CopickFeatures,
    CopickObject,
    CopickPicks,
    CopickRun,
    CopickSegmentation,
    CopickTomogram,
)

EntityType = Union[
    Type[CopickFeatures],
    Type[CopickObject],
    Type[CopickPicks],
    Type[CopickRun],
    Type[CopickSegmentation],
    Type[CopickTomogram],
]

EntityInstance = Union[
    CopickFeatures,
    CopickObject,
    CopickPicks,
    CopickRun,
    CopickSegmentation,
    CopickTomogram,
]

ENTITY_ALIAS = {
    CopickFeatures: "features",
    CopickObject: "object",
    CopickPicks: "picks",
    CopickRun: "run",
    CopickSegmentation: "segmentation",
    CopickTomogram: "tomogram",
}

ENTITY_HELP = {
    CopickFeatures: "A set of features.",
    CopickObject: "A density map.",
    CopickPicks: "A set of picks.",
    CopickRun: "A run.",
    CopickSegmentation: "A segmentation.",
    CopickTomogram: "A tomogram.",
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
    is_command: bool = False


class OpsRegistry:
    name = ""
    short_help = ""
    specs: List[OpsSpec] = []

    def _ops_map(self):
        """Create a mapping of input/output types to operation specs."""
        return {(spec.input_type, spec.output_type): spec for spec in self.specs}

    def _run(self, spec: OpsSpec, config: str, *args, **kwargs) -> EntityInstance:
        """Run an operation spec."""

        root = from_file(config)

        return spec.op(root, *args, **kwargs)

    def cli_group(self):
        """Create a click.Group object for the registry."""
        main_group = click.Group(self.name, short_help=self.short_help)

        for s in self.specs:
            group = main_group

            params = []

            for aspec in s.args:
                params.append(aspec)

            for ospec in s.opts:
                params.append(ospec)

            if s.input_type:
                if ENTITY_ALIAS[s.input_type] not in group.commands:
                    ng = click.Group(ENTITY_ALIAS[s.input_type], short_help=ENTITY_HELP[s.input_type])
                    group.add_command(ng)
                    group = ng
                else:
                    group = group.commands[ENTITY_ALIAS[s.input_type]]

            if s.output_type:
                if ENTITY_ALIAS[s.output_type] not in group.commands:
                    if s.is_command:
                        ng = click.Command(
                            ENTITY_ALIAS[s.output_type],
                            callback=partial(self._run, s),
                            params=params,
                            help=s.help,
                        )
                        group.add_command(ng)
                        group = ng
                    else:
                        ng = click.Group(ENTITY_ALIAS[s.output_type], short_help=ENTITY_HELP[s.output_type])
                        group.add_command(ng)
                        group = ng
                else:
                    group = group.commands[ENTITY_ALIAS[s.output_type]]

            if not s.is_command:
                com = click.Command(s.name, callback=partial(self._run, s), params=params, help=s.help)
                group.add_command(com)

        return main_group
