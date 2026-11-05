"""
Console-only logging setup.
"""

import logging
import sys

FORMAT = "%(asctime)s  |  %(levelname)s  |  %(name)s: %(message)s"
# These libraries log full request URLs at DEBUG, and the FIRMS MAP_KEY is part of the URL.
_QUIET = ("urllib3", "requests")


def configure_logging(level: str = "INFO") -> None:
    """
    Send logs to the console (stderr) only; safe to call repeatedly.

    Args:
        level: Standard level name such as `INFO` or `DEBUG`.
    """
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(FORMAT))
    root.addHandler(handler)
    root.setLevel(level.upper())
    for name in _QUIET:
        logging.getLogger(name).setLevel(logging.WARNING)
