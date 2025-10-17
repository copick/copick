import logging

from rich.logging import RichHandler


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

    # Configure the root logger with basicConfig
    logging.basicConfig(
        level=level,
        format=log_format,
        datefmt=date_format,
        force=True,
        handlers=[RichHandler(level=level, show_time=debug, show_level=debug)],
    )
    gql_logger = logging.getLogger("gql")
    gql_logger.setLevel(logging.WARN if not debug else logging.DEBUG)

    sshfs_logger = logging.getLogger("sshfs")
    sshfs_logger.setLevel(logging.WARN if not debug else logging.DEBUG)

    asyncssh_logger = logging.getLogger("asyncssh")
    asyncssh_logger.setLevel(logging.WARN if not debug else logging.DEBUG)
    return logging.getLogger(name)
