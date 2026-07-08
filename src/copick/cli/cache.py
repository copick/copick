import json

import click

from copick.cli.util import add_config_option, add_debug_option
from copick.util.log import get_logger


def _load_cdp_config(config_path, logger):
    """Load a config file as a ``CopickConfigCDP`` without constructing a root (no portal query).

    Returns the config object, or ``None`` when the config is not a CryoET Data Portal config
    (in which case there is no portal cache to manage).
    """
    with open(config_path) as f:
        data = json.load(f)

    if data.get("config_type") != "cryoet_data_portal":
        logger.info(
            f"Config '{config_path}' is not a CryoET Data Portal config (config_type="
            f"{data.get('config_type')!r}); no portal cache to manage.",
        )
        return None

    # Building the pydantic config model does not touch the portal; only CopickRootCDP.__init__ does.
    from copick.impl.cryoet_data_portal import CopickConfigCDP

    return CopickConfigCDP(**data)


@click.group(short_help="Inspect and invalidate the CryoET Data Portal query cache.")
@click.pass_context
def cache(ctx):
    """
    Inspect and invalidate the CryoET Data Portal query cache.

    Portal-backed copick projects persist the portal query results issued at project
    initialization to a small on-disk cache so that repeated process startups (e.g. many
    parallel processing jobs) read the cache instead of re-querying the portal. These
    commands report on and manually invalidate that cache. They never contact the portal.
    """
    pass


@cache.command(
    context_settings={"show_default": True},
    short_help="Show the portal cache location and freshness.",
)
@add_config_option
@add_debug_option
@click.pass_context
def info(ctx, config, debug=False):
    """
    Show the portal cache location and freshness.

    Reports each candidate cache location for the project (the overlay cache and any local
    fallback), whether a cache file is present, and whether it is fresh or stale relative to
    the configured TTL. Does not contact the CryoET Data Portal.

    Examples:

        \b
        # Inspect the cache for a portal-backed project
        copick cache info -c cdp_config.json

    See Also:

        \b
        copick cache clear: remove the portal cache
    """
    logger = get_logger(__name__, debug=debug)

    if not config:
        ctx.fail("Provide a configuration file via -c/--config (or the COPICK_CONFIG env var).")
        return

    from copick.util import portal_cache

    try:
        cfg = _load_cdp_config(config, logger)
    except Exception as e:
        logger.critical(f"Failed to load configuration: {e}")
        ctx.fail(f"Error loading configuration: {e}")
        return

    if cfg is None:
        return

    try:
        statuses = portal_cache.status_for_config(cfg)
    except Exception as e:
        logger.critical(f"Failed to inspect portal cache: {e}")
        ctx.fail(f"Error inspecting portal cache: {e}")
        return

    settings = portal_cache.settings_from_config(cfg)
    logger.info(f"Portal cache {'enabled' if settings.enabled else 'DISABLED'}, TTL {settings.ttl_seconds}s.")
    for status in statuses:
        if not status.exists:
            logger.info(f"  [missing]  {status.path}")
            continue
        state = "fresh" if status.fresh else "stale"
        age = f"{status.age_seconds:.0f}s" if status.age_seconds is not None else "unknown age"
        lock = "" if status.lockable else " (no lock on this backend)"
        logger.info(f"  [{state}]  {status.path} — created {status.created}, age {age}{lock}")


@cache.command(
    context_settings={"show_default": True},
    short_help="Remove the portal cache to force a refresh.",
)
@add_config_option
@click.option(
    "--all",
    "remove_all",
    is_flag=True,
    default=False,
    show_default=True,
    help="Remove every portal cache file in the cache directory, not just the current fingerprint "
    "(use after changing the project's pickable objects).",
)
@click.option(
    "--yes",
    "-y",
    "assume_yes",
    is_flag=True,
    default=False,
    show_default=True,
    help="Do not prompt for confirmation.",
)
@add_debug_option
@click.pass_context
def clear(ctx, config, remove_all=False, assume_yes=False, debug=False):
    """
    Remove the portal cache to force a refresh.

    Deletes the on-disk CryoET Data Portal query cache for the project so the next process
    re-queries the portal and rewrites the cache. Does not contact the portal itself. By
    default only the cache file matching the current configuration is removed; pass `--all`
    to clear every portal cache file in the cache directory (useful when the project's
    pickable objects changed and the old cache no longer matches).

    Examples:

        \b
        # Invalidate the cache for a portal-backed project
        copick cache clear -c cdp_config.json

        \b
        # Clear all portal cache files without confirmation
        copick cache clear -c cdp_config.json --all --yes

    See Also:

        \b
        copick cache info: show the portal cache location and freshness
    """
    logger = get_logger(__name__, debug=debug)

    if not config:
        ctx.fail("Provide a configuration file via -c/--config (or the COPICK_CONFIG env var).")
        return

    from copick.util import portal_cache

    try:
        cfg = _load_cdp_config(config, logger)
    except Exception as e:
        logger.critical(f"Failed to load configuration: {e}")
        ctx.fail(f"Error loading configuration: {e}")
        return

    if cfg is None:
        return

    scope = "all portal cache files" if remove_all else "the current portal cache file"
    if not assume_yes and not click.confirm(f"Remove {scope} for this project?", default=True):
        logger.info("Aborted; nothing removed.")
        return

    try:
        removed = portal_cache.clear(cfg, remove_all=remove_all)
    except Exception as e:
        logger.critical(f"Failed to clear portal cache: {e}")
        ctx.fail(f"Error clearing portal cache: {e}")
        return

    if removed:
        for path in removed:
            logger.info(f"Removed {path}.")
        logger.info(f"Removed {len(removed)} cache file(s).")
    else:
        logger.info("No portal cache files found; nothing to remove.")
