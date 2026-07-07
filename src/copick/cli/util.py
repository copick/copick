from typing import List, Optional, Sequence

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
            type=click.Path(exists=True),
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


def add_run_names_option(func: click.Command) -> click.Command:
    """
    Add the standard ``--run-names`` / ``-r`` run-selection option.

    This is the single, uniform way for copick-internal commands to select which
    runs to operate on. It is repeatable (``multiple=True``) and yields a tuple in
    the ``run_names`` parameter; pass that tuple through :func:`resolve_run_names`
    to obtain a ``list[str] | None`` (``None`` meaning "all runs").

    Args:
        func (click.Command): The Click command to which the option will be added.

    Returns:
        click.Command: The Click command with the run-names option added.
    """
    opts = [
        click.option(
            "--run-names",
            "-r",
            multiple=True,
            help="Specific run names to process (default: all runs). Repeatable; pass -r once per run.",
        ),
    ]

    for opt in opts:
        func = opt(func)

    return func


# TODO:remove once deprecation takes effect
def add_deprecated_run_alias(*flags: str) -> "click.Command":
    """
    Add a hidden, deprecated alias for :func:`add_run_names_option`.

    Used for commands whose run-selection flag is being renamed (e.g. ``--runs``
    or ``--run-ids``). The alias keeps old invocations working while remaining
    hidden from ``--help``; its value lands in the ``legacy_run_names`` parameter,
    which :func:`resolve_run_names` merges in (emitting a deprecation warning).

    Args:
        *flags (str): The deprecated option flag(s), e.g. ``"--runs"`` or
            ``"--run-ids", "-runs"``.

    Returns:
        A decorator that adds the hidden alias option to a Click command.
    """

    def decorator(func: click.Command) -> click.Command:
        return click.option(
            *flags,
            "legacy_run_names",
            multiple=True,
            hidden=True,
            help="Deprecated: use --run-names/-r instead.",
        )(func)

    return decorator


def resolve_run_names(
    run_names: Sequence[str] = (),
    legacy_run_names: Sequence[str] = (),
    *,
    legacy_flag: Optional[str] = None,
    logger=None,
) -> Optional[List[str]]:
    """
    Normalize the standard and deprecated run-selection inputs into a run list.

    Merges the values from ``--run-names``/``-r`` with any values collected by a
    deprecated alias (see :func:`add_deprecated_run_alias`), transparently
    splitting legacy comma-joined values. Deprecation warnings are emitted (via
    ``logger``) when a deprecated alias or a comma-joined value is used.

    Args:
        run_names: Values from the standard ``--run-names``/``-r`` option.
        legacy_run_names: Values from a deprecated alias option, if any.
        legacy_flag: Human-readable name of the deprecated flag, used in the
            warning message (e.g. ``"--runs"``).
        logger: Optional logger for deprecation warnings.

    Returns:
        A list of run names, or ``None`` when no runs were specified (meaning
        "all runs").
    """
    values = list(run_names or ())

    # TODO:remove once deprecation takes effect -- legacy alias merge
    legacy = list(legacy_run_names or ())
    if legacy:
        if logger is not None:
            flag = legacy_flag or "This run-selection flag"
            logger.warning(f"{flag} is deprecated; use --run-names/-r (repeatable) instead.")
        values.extend(legacy)

    expanded: List[str] = []
    saw_comma = False
    for value in values:
        if value is None:
            continue
        # TODO:remove once deprecation takes effect -- legacy comma-joined values
        if "," in value:
            saw_comma = True
            expanded.extend(part.strip() for part in value.split(",") if part.strip())
        else:
            expanded.append(value)

    # TODO:remove once deprecation takes effect -- legacy comma-joined values
    if saw_comma and logger is not None:
        logger.warning("Comma-separated run names are deprecated; pass -r/--run-names once per run instead.")

    return expanded or None


# TODO:remove once deprecation takes effect
def resolve_deprecated_option(primary, legacy, *, old_flag: str, new_flag: str, logger=None):
    """
    Resolve a scalar option that has a hidden, deprecated alias.

    When ``legacy`` was provided (i.e. is not ``None``), emit a deprecation
    warning and use it (it overrides ``primary``); otherwise return ``primary``.
    This mirrors :func:`resolve_run_names` for single-valued flags being renamed.

    Args:
        primary: Value from the current/canonical option (or a value derived from
            a URI, etc.).
        legacy: Value from the deprecated alias option; ``None`` means "not given".
        old_flag: Human-readable name of the deprecated flag (for the warning).
        new_flag: Human-readable name of the replacement (for the warning).
        logger: Optional logger for the deprecation warning.

    Returns:
        The effective value.
    """
    if legacy is not None:
        if logger is not None:
            logger.warning(f"{old_flag} is deprecated; use {new_flag} instead.")
        return legacy
    return primary


def resolve_tomogram_uri(uri, tomo_alg, voxel_size, *, default_vs: float = 10.0, logger=None) -> str:
    """
    Resolve a tomogram input URI, falling back to deprecated tomo-alg/voxel-size.

    Prefers the standardized ``-i``/``--input`` URI. When it is absent but the
    deprecated ``--tomo-alg`` is given, warns and reconstructs a
    ``tomo_type@voxel_spacing`` URI from ``--tomo-alg``/``--voxel-size``.

    Args:
        uri: Value from ``-i``/``--input`` (``tomo_type@voxel_spacing``), or ``None``.
        tomo_alg: Deprecated ``--tomo-alg`` value, or ``None``.
        voxel_size: Deprecated ``--voxel-size`` value, or ``None``.
        default_vs: Voxel spacing to assume when neither the URI nor
            ``--voxel-size`` supplies one.
        logger: Optional logger for the deprecation warning.

    Returns:
        A ``tomo_type@voxel_spacing`` URI string.

    Raises:
        click.UsageError: If neither a URI nor ``--tomo-alg`` was provided.
    """
    if uri:
        return uri
    # TODO:remove once deprecation takes effect -- legacy --tomo-alg/--voxel-size fallback
    if tomo_alg is not None:
        if logger is not None:
            logger.warning(
                "--tomo-alg/--voxel-size are deprecated; use -i/--input <tomo_type>@<voxel_spacing> instead.",
            )
        vs = voxel_size if voxel_size is not None else default_vs
        return f"{tomo_alg}@{vs}"
    raise click.UsageError("Provide the input tomogram via -i/--input <tomo_type>@<voxel_spacing>.")


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
        click.option(
            "--run-name-prefix",
            required=False,
            type=str,
            default="",
            show_default=True,
            help="Prefix to prepend to run names after regex extraction.",
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
    Add common export options: --output-dir.

    Run selection is provided separately via :func:`add_run_names_option`.

    Args:
        func (click.Command): The Click command to which the options will be added.

    Returns:
        click.Command: The Click command with the export common options added.
    """
    opts = [
        click.option(
            "--output-dir",
            required=True,
            type=click.Path(file_okay=False, dir_okay=True),
            help="Output directory for exported files.",
            metavar="PATH",
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
