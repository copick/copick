import logging

from rich.logging import RichHandler


class _ThirdPartyPathFilter(logging.Filter):
    """Drop log records originating from noisy third-party packages.

    Some libraries (notably ``mlcroissant``'s operation graph) log via the
    root logger using bare ``logging.info(...)``. Those records cannot be
    silenced by logger name because ``record.name == "root"``. Filter them
    by the source file's path instead so copick's own output stays clean.
    """

    _NOISY_PATH_FRAGMENTS = (
        "/mlcroissant/",
        "/numexpr/",
    )

    def filter(self, record: logging.LogRecord) -> bool:
        pathname = getattr(record, "pathname", "") or ""
        return not any(frag in pathname for frag in self._NOISY_PATH_FRAGMENTS)


def get_logger(
    name: str,
    debug: bool = False,
):
    """
    Configure basic console logging using basicConfig.

    Args:
        name: Name of the logger
        debug: If True, set the logging level to DEBUG; otherwise, set it to INFO.

    Returns:
        The root logger
    """

    date_format = "%Y-%m-%d %H:%M:%S"

    if debug:
        level = logging.DEBUG
        log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    else:
        level = logging.INFO
        log_format = "%(message)s"

    handler = RichHandler(level=level, show_time=debug, show_level=debug)
    if not debug:
        handler.addFilter(_ThirdPartyPathFilter())

    # Configure the root logger with basicConfig
    logging.basicConfig(
        level=level,
        format=log_format,
        datefmt=date_format,
        force=True,
        handlers=[handler],
    )
    gql_logger = logging.getLogger("gql")
    gql_logger.setLevel(logging.WARN if not debug else logging.DEBUG)

    sshfs_logger = logging.getLogger("sshfs")
    sshfs_logger.setLevel(logging.WARN if not debug else logging.DEBUG)

    asyncssh_logger = logging.getLogger("asyncssh")
    asyncssh_logger.setLevel(logging.WARN if not debug else logging.DEBUG)

    # mlcroissant's rdf parser logs the "JSON-LD @context is not standard"
    # warning through absl for every Croissant that extends the context
    # (which ours does, via `equivalentProperty`). Silence that at WARNING
    # level — real errors still surface.
    absl_logger = logging.getLogger("absl")
    absl_logger.setLevel(logging.ERROR if not debug else logging.DEBUG)

    # numexpr emits an INFO "defaulting to N threads" line on first import.
    numexpr_logger = logging.getLogger("numexpr")
    numexpr_logger.setLevel(logging.WARN if not debug else logging.DEBUG)

    return logging.getLogger(name)
