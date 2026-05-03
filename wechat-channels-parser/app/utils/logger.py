"""Loguru-based structured logger; emits JSON lines to stderr."""

import os
import sys

from loguru import logger


def setup_logger(level: str | None = None) -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        level=level or os.getenv("LOG_LEVEL", "INFO"),
        serialize=True,  # JSON-line output for easy log aggregation
        backtrace=False,
        diagnose=False,
    )


__all__ = ["logger", "setup_logger"]
