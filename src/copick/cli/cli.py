import click

from copick.ops.add import ImportRegistry


@click.group()
@click.pass_context
def cli(ctx):
    pass


@cli.group()
def list():
    pass


importers = ImportRegistry()
cli.add_command(importers.cli_group())
