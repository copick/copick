import click

from copick.cli._ops._add import AddRegistry


@click.group()
@click.pass_context
def cli(ctx):
    pass


@cli.group()
def list():
    pass


adders = AddRegistry()
cli.add_command(adders.cli_group())
