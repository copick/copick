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


def add_run_options(func: click.Command) -> click.Command:
    """
    Add --run and --run-regex options for file-based run assignment.

    Args:
        func (click.Command): The Click command to which the options will be added.

    Returns:
        click.Command: The Click command with the run options added.
    """
    opts = [
        click.option(
            "--run",
            required=False,
            type=str,
            help="The name of the run. If not specified, will use the name of the file (stripping extension), "
            "ignored if PATH is glob pattern.",
            show_default=True,
            default="",
        ),
        click.option(
            "--run-regex",
            required=False,
            type=str,
            default="(.*)",
            show_default=True,
            help="Regular expression to extract the run name from the filename. If not provided, will use the file "
            "name without extension. The regex should capture the run name in the first group.",
        ),
    ]

    for opt in opts:
        func = opt(func)

    return func


def add_volume_transform_options(func: click.Command) -> click.Command:
    """
    Add --transpose and --flip options for volume manipulation.

    Args:
        func (click.Command): The Click command to which the options will be added.

    Returns:
        click.Command: The Click command with the volume transform options added.
    """
    opts = [
        click.option(
            "--transpose",
            required=False,
            type=str,
            default=None,
            help="Transpose volume axes. Specify target axis order, e.g., '2,1,0' to reverse all axes, "
            "'0,2,1' to swap Y and X. Default: no transposition.",
        ),
        click.option(
            "--flip",
            required=False,
            type=str,
            default=None,
            help="Flip (reverse) volume along specified axes. Comma-separated axis indices, "
            "e.g., '0' to flip Z, '0,2' to flip Z and X. Default: no flipping.",
        ),
    ]

    for opt in opts:
        func = opt(func)

    return func


def add_user_session_options(func: click.Command) -> click.Command:
    """
    Add --user-id and --session-id options for annotation attribution.

    Args:
        func (click.Command): The Click command to which the options will be added.

    Returns:
        click.Command: The Click command with the user/session options added.
    """
    opts = [
        click.option(
            "--user-id",
            required=False,
            type=str,
            default="copick",
            show_default=True,
            help="User ID for the annotation.",
        ),
        click.option(
            "--session-id",
            required=False,
            type=str,
            default="1",
            show_default=True,
            help="Session ID for the annotation.",
        ),
    ]

    for opt in opts:
        func = opt(func)

    return func


def add_max_workers_option(func: click.Command) -> click.Command:
    """
    Add --max-workers option for parallel processing.

    Args:
        func (click.Command): The Click command to which the option will be added.

    Returns:
        click.Command: The Click command with the max-workers option added.
    """
    opts = [
        click.option(
            "--max-workers",
            required=False,
            type=int,
            default=4,
            show_default=True,
            help="Maximum number of worker threads.",
        ),
    ]

    for opt in opts:
        func = opt(func)

    return func


def add_pyramid_create_options(func: click.Command) -> click.Command:
    """
    Add pyramid creation options: --create-pyramid, --pyramid-levels, --chunk-size.

    Args:
        func (click.Command): The Click command to which the options will be added.

    Returns:
        click.Command: The Click command with the pyramid creation options added.
    """
    opts = [
        click.option(
            "--create-pyramid/--no-create-pyramid",
            is_flag=True,
            required=False,
            type=bool,
            default=True,
            show_default=True,
            help="Compute the multiscale pyramid.",
        ),
        click.option(
            "--pyramid-levels",
            required=False,
            type=int,
            default=3,
            show_default=True,
            help="Number of pyramid levels (each level corresponds to downscaling by factor two).",
        ),
        click.option(
            "--chunk-size",
            required=False,
            type=str,
            default="256,256,256",
            show_default=True,
            help="Chunk size for the output Zarr file.",
        ),
    ]

    for opt in opts:
        func = opt(func)

    return func


def add_export_common_options(func: click.Command) -> click.Command:
    """
    Add common export options: --output-dir, --run-names.

    Args:
        func (click.Command): The Click command to which the options will be added.

    Returns:
        click.Command: The Click command with the export common options added.
    """
    opts = [
        click.option(
            "--output-dir",
            required=True,
            type=str,
            help="Output directory for exported files.",
            metavar="PATH",
        ),
        click.option(
            "--run-names",
            type=str,
            default="",
            help="Comma-separated list of run names to export. If not specified, exports from all runs.",
        ),
    ]

    for opt in opts:
        func = opt(func)

    return func


def add_pyramid_export_options(func: click.Command) -> click.Command:
    """
    Add pyramid export options: --level, --compression, --copy-all-levels.

    Args:
        func (click.Command): The Click command to which the options will be added.

    Returns:
        click.Command: The Click command with the pyramid export options added.
    """
    opts = [
        click.option(
            "--level",
            type=int,
            default=0,
            show_default=True,
            help="Pyramid level to export (for MRC and TIFF).",
        ),
        click.option(
            "--compression",
            type=click.Choice(["lzw", "zlib", "jpeg", "none"], case_sensitive=False),
            default=None,
            help="Compression method for TIFF output.",
        ),
        click.option(
            "--copy-all-levels/--level-only",
            is_flag=True,
            default=True,
            show_default=True,
            help="Copy all pyramid levels for Zarr output.",
        ),
    ]

    for opt in opts:
        func = opt(func)

    return func
