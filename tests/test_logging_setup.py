"""Tests for structured logging setup with dual handlers."""

from __future__ import annotations

import logging
import sys

from pythonjsonlogger.json import JsonFormatter

from email_triage.logging_setup import setup_logging


class TestSetupLogging:
    """Tests for setup_logging() configuration."""

    def test_returns_logger_with_correct_name(self):
        logger = setup_logging()
        assert logger.name == "email_triage"

    def test_console_handler_writes_to_stderr(self):
        logger = setup_logging()
        stream_handlers = [
            h for h in logger.handlers if isinstance(h, logging.StreamHandler)
            and not isinstance(h, logging.FileHandler)
        ]
        assert len(stream_handlers) == 1
        assert stream_handlers[0].stream is sys.stderr

    def test_log_level_is_configurable(self):
        logger = setup_logging(level="DEBUG")
        assert logger.level == logging.DEBUG

    def test_file_handler_not_added_without_log_file(self):
        logger = setup_logging(log_file=None)
        assert len(logger.handlers) == 1
        assert isinstance(logger.handlers[0], logging.StreamHandler)
        assert not isinstance(logger.handlers[0], logging.FileHandler)

    def test_file_handler_uses_json_formatter(self, tmp_path):
        log_file = str(tmp_path / "test.log")
        logger = setup_logging(log_file=log_file)

        file_handlers = [
            h for h in logger.handlers if isinstance(h, logging.FileHandler)
        ]
        assert len(file_handlers) == 1
        assert isinstance(file_handlers[0].formatter, JsonFormatter)

    def test_handlers_cleared_on_reinit(self):
        logger = setup_logging()
        initial_count = len(logger.handlers)
        setup_logging()
        assert len(logger.handlers) == initial_count
