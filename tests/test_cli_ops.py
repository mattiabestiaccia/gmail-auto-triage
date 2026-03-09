"""Tests for CLI operability: exit codes, error resilience, logging, notifications."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from email_triage.cli import main
from email_triage.models import EmailData


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_email(id_: str = "msg1", subject: str = "Test") -> EmailData:
    return EmailData(
        id=id_,
        thread_id="t1",
        sender="sender@example.com",
        subject=subject,
        date="Mon, 1 Jan 2026 00:00:00 +0000",
        snippet="snippet",
        label_ids=[],
    )


def _mock_classify_result(*, is_ambiguous: bool = False):
    """Return a mock ClassificationResult."""
    from email_triage.models import ClassificationResult

    if is_ambiguous:
        return ClassificationResult(categories=[], reasoning="test", is_ambiguous=True)
    return ClassificationResult(
        categories=[("Newsletter", 0.9)],
        reasoning="test",
        is_ambiguous=False,
    )


# ---------------------------------------------------------------------------
# Exit code tests
# ---------------------------------------------------------------------------


class TestExitCodes:
    def test_exit_0_on_success_no_emails(self, tmp_path):
        """Exit 0 when no emails found (successful empty run)."""
        cfg = tmp_path / "categories.yaml"
        cfg.write_text(
            "categories:\n"
            "  - name: Newsletter\n"
            "    description: Newsletters\n"
            "    examples: [weekly digest]\n"
        )
        with (
            patch("email_triage.cli.authenticate"),
            patch("email_triage.cli.get_gmail_service"),
            patch("email_triage.cli.fetch_unread_ids", return_value=[]),
            patch("email_triage.cli.setup_logging"),
            pytest.raises(SystemExit) as exc_info,
        ):
            main(["--config", str(cfg)])
        assert exc_info.value.code == 0

    def test_exit_1_on_fatal_config_error(self):
        """Exit 1 when config file does not exist (fatal error)."""
        with (
            patch("email_triage.cli.setup_logging"),
            pytest.raises(SystemExit) as exc_info,
        ):
            main(["--config", "/nonexistent/config.yaml"])
        assert exc_info.value.code == 1

    def test_exit_130_on_keyboard_interrupt(self, tmp_path):
        """Exit 130 on KeyboardInterrupt."""
        cfg = tmp_path / "categories.yaml"
        cfg.write_text(
            "categories:\n"
            "  - name: Newsletter\n"
            "    description: Newsletters\n"
            "    examples: [weekly digest]\n"
        )
        with (
            patch("email_triage.cli.authenticate", side_effect=KeyboardInterrupt),
            patch("email_triage.cli.setup_logging"),
            pytest.raises(SystemExit) as exc_info,
        ):
            main(["--config", str(cfg)])
        assert exc_info.value.code == 130

    def test_exit_0_on_successful_classification(self, tmp_path):
        """Exit 0 when classification succeeds (even with some errors)."""
        cfg = tmp_path / "categories.yaml"
        cfg.write_text(
            "categories:\n"
            "  - name: Newsletter\n"
            "    description: Newsletters\n"
            "    examples: [weekly digest]\n"
        )
        emails = [_make_email("m1", "Test Email")]

        with (
            patch("email_triage.cli.authenticate"),
            patch("email_triage.cli.get_gmail_service"),
            patch("email_triage.cli.fetch_unread_ids", return_value=["m1"]),
            patch("email_triage.cli.fetch_messages_batch", return_value=([{"id": "m1", "threadId": "t1", "payload": {"headers": [{"name": "From", "value": "a@b.com"}, {"name": "Subject", "value": "Test"}]}, "snippet": "s", "labelIds": [], "internalDate": "9999999999999"}], [])),
            patch("email_triage.cli.filter_by_window", return_value=emails),
            patch("email_triage.cli.create_genai_client"),
            patch("email_triage.cli.list_triage_labels", return_value={}),
            patch("email_triage.cli.classify_email", return_value=_mock_classify_result()),
            patch("email_triage.cli.ensure_label", return_value="lbl1"),
            patch("email_triage.cli.apply_labels"),
            patch("email_triage.cli.send_summary_email", return_value="msg-id"),
            patch("email_triage.cli.setup_logging"),
            patch("time.sleep"),
            pytest.raises(SystemExit) as exc_info,
        ):
            main(["--config", str(cfg)])
        assert exc_info.value.code == 0


# ---------------------------------------------------------------------------
# Error resilience tests
# ---------------------------------------------------------------------------


class TestErrorResilience:
    def test_single_email_error_does_not_crash_batch(self, tmp_path):
        """When classify_email raises on one email, others are still processed."""
        cfg = tmp_path / "categories.yaml"
        cfg.write_text(
            "categories:\n"
            "  - name: Newsletter\n"
            "    description: Newsletters\n"
            "    examples: [weekly digest]\n"
        )
        emails = [
            _make_email("m1", "Good Email 1"),
            _make_email("m2", "Bad Email"),
            _make_email("m3", "Good Email 3"),
        ]

        call_count = {"classify": 0}
        results_collected = []

        def classify_side_effect(client, email, cats, cfg_cls, fields=None):
            call_count["classify"] += 1
            if email.id == "m2":
                raise RuntimeError("LLM API timeout")
            result = _mock_classify_result()
            results_collected.append(email.id)
            return result

        with (
            patch("email_triage.cli.authenticate"),
            patch("email_triage.cli.get_gmail_service"),
            patch("email_triage.cli.fetch_unread_ids", return_value=["m1", "m2", "m3"]),
            patch("email_triage.cli.fetch_messages_batch", return_value=([{} for _ in range(3)], [])),
            patch("email_triage.cli.filter_by_window", return_value=emails),
            patch("email_triage.cli.parse_message", side_effect=emails),
            patch("email_triage.cli.create_genai_client"),
            patch("email_triage.cli.list_triage_labels", return_value={}),
            patch("email_triage.cli.classify_email", side_effect=classify_side_effect),
            patch("email_triage.cli.ensure_label", return_value="lbl1"),
            patch("email_triage.cli.apply_labels"),
            patch("email_triage.cli.send_summary_email", return_value="msg-id"),
            patch("email_triage.cli.setup_logging"),
            patch("time.sleep"),
            pytest.raises(SystemExit) as exc_info,
        ):
            main(["--config", str(cfg)])

        # All 3 emails were attempted
        assert call_count["classify"] == 3
        # m1 and m3 were successfully classified
        assert "m1" in results_collected
        assert "m3" in results_collected
        # Exit 0 despite error (batch continues)
        assert exc_info.value.code == 0

    def test_summary_email_failure_does_not_change_exit_code(self, tmp_path):
        """When send_summary_email raises, exit code is still 0."""
        cfg = tmp_path / "categories.yaml"
        cfg.write_text(
            "categories:\n"
            "  - name: Newsletter\n"
            "    description: Newsletters\n"
            "    examples: [weekly digest]\n"
        )
        emails = [_make_email("m1", "Test")]

        with (
            patch("email_triage.cli.authenticate"),
            patch("email_triage.cli.get_gmail_service"),
            patch("email_triage.cli.fetch_unread_ids", return_value=["m1"]),
            patch("email_triage.cli.fetch_messages_batch", return_value=([{}], [])),
            patch("email_triage.cli.filter_by_window", return_value=emails),
            patch("email_triage.cli.parse_message", return_value=emails[0]),
            patch("email_triage.cli.create_genai_client"),
            patch("email_triage.cli.list_triage_labels", return_value={}),
            patch("email_triage.cli.classify_email", return_value=_mock_classify_result()),
            patch("email_triage.cli.ensure_label", return_value="lbl1"),
            patch("email_triage.cli.apply_labels"),
            patch("email_triage.cli.send_summary_email", side_effect=RuntimeError("SMTP error")),
            patch("email_triage.cli.setup_logging"),
            patch("time.sleep"),
            pytest.raises(SystemExit) as exc_info,
        ):
            main(["--config", str(cfg)])

        assert exc_info.value.code == 0


# ---------------------------------------------------------------------------
# CLI flag tests
# ---------------------------------------------------------------------------


class TestCliFlags:
    def test_no_notify_prevents_summary_email(self, tmp_path):
        """--no-notify flag prevents send_summary_email from being called."""
        cfg = tmp_path / "categories.yaml"
        cfg.write_text(
            "categories:\n"
            "  - name: Newsletter\n"
            "    description: Newsletters\n"
            "    examples: [weekly digest]\n"
        )
        emails = [_make_email("m1", "Test")]
        mock_send = MagicMock(return_value="msg-id")

        with (
            patch("email_triage.cli.authenticate"),
            patch("email_triage.cli.get_gmail_service"),
            patch("email_triage.cli.fetch_unread_ids", return_value=["m1"]),
            patch("email_triage.cli.fetch_messages_batch", return_value=([{}], [])),
            patch("email_triage.cli.filter_by_window", return_value=emails),
            patch("email_triage.cli.parse_message", return_value=emails[0]),
            patch("email_triage.cli.create_genai_client"),
            patch("email_triage.cli.list_triage_labels", return_value={}),
            patch("email_triage.cli.classify_email", return_value=_mock_classify_result()),
            patch("email_triage.cli.ensure_label", return_value="lbl1"),
            patch("email_triage.cli.apply_labels"),
            patch("email_triage.cli.send_summary_email", mock_send),
            patch("email_triage.cli.setup_logging"),
            patch("time.sleep"),
            pytest.raises(SystemExit),
        ):
            main(["--config", str(cfg), "--no-notify"])

        mock_send.assert_not_called()

    def test_log_level_debug_accepted(self, tmp_path):
        """--log-level DEBUG is accepted and passed to setup_logging."""
        cfg = tmp_path / "categories.yaml"
        cfg.write_text(
            "categories:\n"
            "  - name: Newsletter\n"
            "    description: Newsletters\n"
            "    examples: [weekly digest]\n"
        )
        mock_setup = MagicMock()

        with (
            patch("email_triage.cli.setup_logging", mock_setup),
            patch("email_triage.cli.authenticate"),
            patch("email_triage.cli.get_gmail_service"),
            patch("email_triage.cli.fetch_unread_ids", return_value=[]),
            pytest.raises(SystemExit),
        ):
            main(["--config", str(cfg), "--log-level", "DEBUG"])

        mock_setup.assert_called_once_with("DEBUG", None)

    def test_log_file_passed_to_setup_logging(self, tmp_path):
        """--log-file path is forwarded to setup_logging."""
        cfg = tmp_path / "categories.yaml"
        cfg.write_text(
            "categories:\n"
            "  - name: Newsletter\n"
            "    description: Newsletters\n"
            "    examples: [weekly digest]\n"
        )
        mock_setup = MagicMock()
        log_path = str(tmp_path / "triage.log")

        with (
            patch("email_triage.cli.setup_logging", mock_setup),
            patch("email_triage.cli.authenticate"),
            patch("email_triage.cli.get_gmail_service"),
            patch("email_triage.cli.fetch_unread_ids", return_value=[]),
            pytest.raises(SystemExit),
        ):
            main(["--config", str(cfg), "--log-file", log_path])

        mock_setup.assert_called_once_with("INFO", log_path)

    def test_dry_run_skips_summary_email(self, tmp_path):
        """--dry-run prevents send_summary_email from being called."""
        cfg = tmp_path / "categories.yaml"
        cfg.write_text(
            "categories:\n"
            "  - name: Newsletter\n"
            "    description: Newsletters\n"
            "    examples: [weekly digest]\n"
        )
        emails = [_make_email("m1", "Test")]
        mock_send = MagicMock(return_value="msg-id")

        with (
            patch("email_triage.cli.authenticate"),
            patch("email_triage.cli.get_gmail_service"),
            patch("email_triage.cli.fetch_unread_ids", return_value=["m1"]),
            patch("email_triage.cli.fetch_messages_batch", return_value=([{}], [])),
            patch("email_triage.cli.filter_by_window", return_value=emails),
            patch("email_triage.cli.parse_message", return_value=emails[0]),
            patch("email_triage.cli.create_genai_client"),
            patch("email_triage.cli.list_triage_labels", return_value={}),
            patch("email_triage.cli.classify_email", return_value=_mock_classify_result()),
            patch("email_triage.cli.send_summary_email", mock_send),
            patch("email_triage.cli.setup_logging"),
            patch("time.sleep"),
            pytest.raises(SystemExit),
        ):
            main(["--config", str(cfg), "--dry-run"])

        mock_send.assert_not_called()
