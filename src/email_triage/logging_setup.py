"""Structured logging setup with dual handlers: console (stderr) and JSON file.

Provides setup_logging() to configure the 'email_triage' logger with:
- Human-readable console output on stderr (cron-compatible)
- Optional JSON-structured file output via python-json-logger
"""

from __future__ import annotations

import logging
import sys

from pythonjsonlogger.json import JsonFormatter


def setup_logging(
    level: str = "INFO",
    log_file: str | None = None,
) -> logging.Logger:
    """Configure and return the 'email_triage' logger with dual handlers.

    Args:
        level: Log level name (e.g. "INFO", "DEBUG"). Defaults to "INFO".
        log_file: Optional path to a JSON log file. If None, only console
            handler is attached.

    Returns:
        Configured logger instance named 'email_triage'.
    """
    logger = logging.getLogger("email_triage")
    log_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(log_level)

    # Clear existing handlers to avoid duplicates on re-init
    logger.handlers.clear()

    # Console handler: human-readable on stderr (cron compatibility per OPS-01)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    logger.addHandler(console_handler)

    # Optional JSON file handler
    if log_file is not None:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(
            JsonFormatter(
                fmt="%(asctime)s %(name)s %(levelname)s %(message)s",
                rename_fields={"asctime": "timestamp", "levelname": "level"},
            )
        )
        logger.addHandler(file_handler)

    return logger
