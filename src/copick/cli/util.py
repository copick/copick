import click


def add_config_option(func: click.Command) -> click.Command:
    """
    Add a configuration file option to a Click command.

    Args:
        func (click.Command): The Click command to which the option will be added.

    Returns:
        click.Command: The Click command with the configuration option added.
    """
    opts = [
        click.option(
            "-c",
            "--config",
            type=str,
            help="Path to the configuration file.",
            required=False,
            metavar="PATH",
            envvar="COPICK_CONFIG",
            show_envvar=True,
        ),
    ]

    for opt in opts:
        func = opt(func)

    return func


def add_debug_option(func: click.Command) -> click.Command:
    """
    Add a debug option to a Click command.

    Args:
        func (click.Command): The Click command to which the option will be added.

    Returns:
        click.Command: The Click command with the debug option added.
    """
    opts = [
        click.option(
            "--debug/--no-debug",
            is_flag=True,
            help="Enable debug logging.",
            show_default=True,
            default=False,
        ),
    ]

    for opt in opts:
        func = opt(func)

    return func


def add_create_overwrite_options(func: click.Command) -> click.Command:
    """
    Add create and overwrite options to a Click command.

    Args:
        func (click.Command): The Click command to which the options will be added.

    Returns:
        click.Command: The Click command with the create and overwrite options added.
    """
    opts = [
        click.option(
            "--create/--no-create",
            is_flag=True,
            help="Create the object if it does not exist.",
            default=True,
            show_default=True,
        ),
        click.option(
            "--overwrite/--no-overwrite",
            is_flag=True,
            help="Overwrite the object if it exists.",
            default=False,
            show_default=True,
        ),
    ]

    for opt in opts:
        func = opt(func)

    return func
