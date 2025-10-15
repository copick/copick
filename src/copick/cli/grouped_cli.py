"""Custom Click Group for organizing commands into categories."""

from typing import Dict, List, Optional

import click


class GroupedCommandGroup(click.Group):
    """Custom Click Group that organizes commands into categories.

    Commands are displayed in categorized sections with headers in the help output.
    Each category displays its commands in alphabetical order.
    """

    def __init__(self, *args, **kwargs):
        """Initialize the grouped command group.

        The command_categories attribute should be a dict mapping category names
        to lists of command names in that category.
        """
        self.command_categories: Dict[str, List[str]] = kwargs.pop("command_categories", {})
        super().__init__(*args, **kwargs)

    def format_commands(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        """Format commands into categorized sections.

        This overrides the default Click behavior to group commands by category
        with section headers.
        """
        # Build a mapping from command name to command object
        commands = {}
        for subcommand in self.list_commands(ctx):
            cmd = self.get_command(ctx, subcommand)
            if cmd is None or cmd.hidden:
                continue
            commands[subcommand] = cmd

        # If no categories defined, fall back to default behavior
        if not self.command_categories:
            return super().format_commands(ctx, formatter)

        # Track which commands have been categorized
        categorized_commands = set()

        # Display each category
        for category_name, command_names in self.command_categories.items():
            # Filter to only commands that exist and haven't been shown yet
            category_commands = []
            for cmd_name in sorted(command_names):  # Sort alphabetically within category
                if cmd_name in commands and cmd_name not in categorized_commands:
                    category_commands.append((cmd_name, commands[cmd_name]))
                    categorized_commands.add(cmd_name)

            # Only display category if it has commands
            if category_commands:
                with formatter.section(f"{category_name}"):
                    self._format_command_list(formatter, category_commands)

        # Display any uncategorized commands
        uncategorized = []
        for cmd_name in sorted(commands.keys()):
            if cmd_name not in categorized_commands:
                uncategorized.append((cmd_name, commands[cmd_name]))

        if uncategorized:
            with formatter.section("Other Commands"):
                self._format_command_list(formatter, uncategorized)

    def _format_command_list(self, formatter: click.HelpFormatter, commands: List[tuple]) -> None:
        """Format a list of commands for display.

        Args:
            formatter: Click formatter to write to
            commands: List of (name, command) tuples
        """
        rows = []
        for cmd_name, cmd in commands:
            help_text = cmd.get_short_help_str(limit=formatter.width - 25)
            rows.append((cmd_name, help_text))

        if rows:
            formatter.write_dl(rows)


def create_grouped_cli(
    name: Optional[str] = None,
    command_categories: Optional[Dict[str, List[str]]] = None,
    **kwargs,
) -> GroupedCommandGroup:
    """Create a GroupedCommandGroup with the specified categories.

    Args:
        name: Name of the CLI group
        command_categories: Dict mapping category names to lists of command names
        **kwargs: Additional arguments passed to GroupedCommandGroup

    Returns:
        GroupedCommandGroup instance
    """
    if command_categories is None:
        command_categories = {}

    return GroupedCommandGroup(name=name, command_categories=command_categories, **kwargs)
