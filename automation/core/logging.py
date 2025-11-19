"""Logging utilities shared across the automation package."""
from __future__ import annotations

import logging
import os


def configure_logging(level: str | None = None) -> None:
    """Initialize basic logging with a shared format and log level.

    The level can be provided directly or via the ``LOG_LEVEL`` environment
    variable (defaults to ``INFO``). This keeps the pipeline, CLI, and
    dashboard emitting consistent structured messages without extra setup.
    """

    resolved_level = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    logging.basicConfig(
        level=resolved_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
