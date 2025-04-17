import logging
import sys


def get_logger(
    name: str,
    level=logging.INFO,
    log_format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    date_format="%Y-%m-%d %H:%M:%S",
):
    """
    Configure basic console logging using basicConfig.

    Args:
        name: Name of the logger
        level: Logging level (default: INFO)
        log_format: Format string for log messages
        date_format: Format string for timestamps

    Returns:
        The root logger
    """
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
