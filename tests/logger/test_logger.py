"""
Tests for console-only logging.
"""

import logging
from collections.abc import Iterator

import pytest

from logger.config import configure_logging


@pytest.fixture(autouse=True)
def _restore_root() -> Iterator[None]:
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    root.handlers[:] = handlers
    root.setLevel(level)


def test_console_only_and_idempotent() -> None:
    """
    One stream handler, no file handlers, even after repeated calls.
    """
    configure_logging("DEBUG")
    configure_logging("INFO")
    handlers = logging.getLogger().handlers
    assert len(handlers) == 1
    assert type(handlers[0]) is logging.StreamHandler
    assert logging.getLogger().level == logging.INFO


def test_http_libraries_stay_quiet() -> None:
    """
    requests/urllib3 never log at DEBUG (their output contains the MAP_KEY URL).
    """
    configure_logging("DEBUG")
    assert logging.getLogger("urllib3").level == logging.WARNING
    assert logging.getLogger("requests").level == logging.WARNING
