import logging
import sys


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
        stream=sys.stderr,
        force=True,
    )
    gql_logger = logging.getLogger("gql")
    gql_logger.setLevel(logging.WARN)
    return logging.getLogger(name)
