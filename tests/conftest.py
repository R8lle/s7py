"""Pytest-Fixtures: Logging waehrend Tests vom App-Logfile fernhalten."""

import logging

import pytest


@pytest.fixture(scope="session", autouse=True)
def isolate_s7py_file_logging():
    """Verhindert, dass pytest-Meldungen in s7py/s7py.log landen."""
    from s7py.log import logger

    saved_handlers = list(logger.handlers)
    for handler in saved_handlers:
        logger.removeHandler(handler)
    logger.addHandler(logging.NullHandler())
    try:
        yield
    finally:
        logger.removeHandler(logging.NullHandler())
        for handler in saved_handlers:
            logger.addHandler(handler)
