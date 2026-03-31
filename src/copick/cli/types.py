"""Custom Click parameter types for copick CLI commands.

Provides typed parameter types that carry metadata for UI generation.
"""

import click


class CopickURI(click.ParamType):
    """Click parameter type for copick URIs.

    Carries metadata about the expected object type and role so that
    UI generators can create appropriate widgets automatically.

    At the CLI level this behaves identically to a plain string — no
    validation is added (that happens downstream in the command logic).
    The metadata is purely for introspection by tools like the auto-
    generated Qt form widgets.

    Args:
        object_type: The copick object type this URI targets.
            One of: "picks", "mesh", "segmentation", "tomogram", "feature".
        role: The role of this URI parameter in the command.
            One of: "input", "output", "reference".

    Example usage in a Click command::

        @click.option(
            "--input", "-i", "input_uri",
            type=CopickURI("picks", "input"),
            required=True,
            help="Input picks URI.",
        )
    """

    name = "COPICK_URI"

    def __init__(self, object_type: str, role: str = "input"):
        self.object_type = object_type
        self.role = role

    def convert(self, value, param, ctx):
        if value is None:
            return None
        return str(value)

    def get_metavar(self, param):
        return "URI"

    def __repr__(self):
        return f"CopickURI({self.object_type!r}, {self.role!r})"
