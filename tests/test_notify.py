"""Tests for the summary email notification module."""

from __future__ import annotations

import base64
from email import message_from_bytes
from unittest.mock import MagicMock

import pytest

from email_triage.models import RunStats
from email_triage.notify import (
    _build_summary_html,
    _build_summary_text,
    get_user_email,
    send_summary_email,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def basic_stats() -> RunStats:
    """RunStats with typical values for testing."""
    return RunStats(
        total_fetched=20,
        skipped_triaged=5,
        classified=12,
        ambiguous=2,
        errors=1,
        error_details=["Failed to classify 'Test email': API timeout"],
        categories={"Newsletter": 5, "Shopping": 4, "Finance": 3},
        api_calls_gmail=3,
        api_calls_llm=15,
        token_usage_prompt=1500,
        token_usage_completion=300,
        elapsed_seconds=42.5,
    )


@pytest.fixture
def zero_token_stats() -> RunStats:
    """RunStats with zero token usage (N/A case)."""
    return RunStats(
        classified=3,
        ambiguous=0,
        errors=0,
        categories={"Newsletter": 3},
        token_usage_prompt=0,
        token_usage_completion=0,
    )


@pytest.fixture
def mock_service() -> MagicMock:
    """Mock Gmail service with getProfile and messages.send."""
    service = MagicMock()
    service.users().getProfile().execute.return_value = {
        "emailAddress": "user@example.com",
    }
    service.users().messages().send().execute.return_value = {
        "id": "msg-12345",
    }
    return service


# ---------------------------------------------------------------------------
# get_user_email tests
# ---------------------------------------------------------------------------


class TestGetUserEmail:
    def test_returns_email_from_profile(self, mock_service: MagicMock) -> None:
        email = get_user_email(mock_service)
        assert email == "user@example.com"

    def test_calls_get_profile_with_me(self, mock_service: MagicMock) -> None:
        get_user_email(mock_service)
        mock_service.users().getProfile.assert_called_with(userId="me")


# ---------------------------------------------------------------------------
# HTML builder tests
# ---------------------------------------------------------------------------


class TestBuildSummaryHtml:
    def test_contains_classified_count(self, basic_stats: RunStats) -> None:
        html = _build_summary_html(basic_stats)
        assert "<strong>12</strong>" in html

    def test_contains_category_names(self, basic_stats: RunStats) -> None:
        html = _build_summary_html(basic_stats)
        assert "Newsletter" in html
        assert "Shopping" in html
        assert "Finance" in html

    def test_category_rows_sorted_by_count(self, basic_stats: RunStats) -> None:
        html = _build_summary_html(basic_stats)
        # Newsletter (5) should appear before Shopping (4) before Finance (3)
        nl_pos = html.index("Newsletter")
        sh_pos = html.index("Shopping")
        fi_pos = html.index("Finance")
        assert nl_pos < sh_pos < fi_pos

    def test_contains_error_count(self, basic_stats: RunStats) -> None:
        html = _build_summary_html(basic_stats)
        assert "1" in html  # error count
        assert "API timeout" in html

    def test_contains_token_usage(self, basic_stats: RunStats) -> None:
        html = _build_summary_html(basic_stats)
        assert "1,500" in html  # prompt tokens
        assert "300" in html  # completion tokens
        assert "1,800" in html  # total

    def test_shows_na_when_zero_tokens(self, zero_token_stats: RunStats) -> None:
        html = _build_summary_html(zero_token_stats)
        assert "N/A" in html

    def test_contains_elapsed_time(self, basic_stats: RunStats) -> None:
        html = _build_summary_html(basic_stats)
        assert "42.5s" in html

    def test_no_category_section_when_empty(self) -> None:
        stats = RunStats(classified=0, ambiguous=1)
        html = _build_summary_html(stats)
        assert "<h3>Categories</h3>" not in html


# ---------------------------------------------------------------------------
# Plain text builder tests
# ---------------------------------------------------------------------------


class TestBuildSummaryText:
    def test_contains_classified_count(self, basic_stats: RunStats) -> None:
        text = _build_summary_text(basic_stats)
        assert "Classified: 12" in text

    def test_contains_category_names(self, basic_stats: RunStats) -> None:
        text = _build_summary_text(basic_stats)
        assert "Newsletter: 5" in text
        assert "Shopping: 4" in text
        assert "Finance: 3" in text

    def test_contains_error_details(self, basic_stats: RunStats) -> None:
        text = _build_summary_text(basic_stats)
        assert "API timeout" in text

    def test_shows_na_when_zero_tokens(self, zero_token_stats: RunStats) -> None:
        text = _build_summary_text(zero_token_stats)
        assert "N/A" in text

    def test_contains_token_counts(self, basic_stats: RunStats) -> None:
        text = _build_summary_text(basic_stats)
        assert "1,500" in text
        assert "300" in text


# ---------------------------------------------------------------------------
# send_summary_email tests
# ---------------------------------------------------------------------------


class TestSendSummaryEmail:
    def test_calls_messages_send(
        self, mock_service: MagicMock, basic_stats: RunStats,
    ) -> None:
        result = send_summary_email(mock_service, basic_stats)
        assert result == "msg-12345"
        mock_service.users().messages().send.assert_called()

    def test_uses_real_email_not_me(
        self, mock_service: MagicMock, basic_stats: RunStats,
    ) -> None:
        """Verify To header uses actual email address, not 'me'."""
        send_summary_email(mock_service, basic_stats)

        # Extract the raw body from the send call
        call_kwargs = mock_service.users().messages().send.call_args
        raw_b64 = call_kwargs.kwargs.get("body", {}).get("raw") or \
            call_kwargs[1].get("body", {}).get("raw")

        if raw_b64 is None:
            # Try positional style from mock chain
            send_calls = mock_service.users().messages().send.call_args_list
            for call in send_calls:
                body = call.kwargs.get("body") or (call[1].get("body") if len(call) > 1 else None)
                if body and "raw" in body:
                    raw_b64 = body["raw"]
                    break

        assert raw_b64 is not None, "Could not find raw body in send call"
        raw_bytes = base64.urlsafe_b64decode(raw_b64)
        parsed = message_from_bytes(raw_bytes)
        assert "user@example.com" in parsed["To"]
        assert "me" != parsed["To"]

    def test_subject_contains_stats(
        self, mock_service: MagicMock, basic_stats: RunStats,
    ) -> None:
        send_summary_email(mock_service, basic_stats)

        # Extract the raw body from send call
        call_kwargs = mock_service.users().messages().send.call_args
        raw_b64 = call_kwargs.kwargs.get("body", {}).get("raw") or \
            call_kwargs[1].get("body", {}).get("raw")

        if raw_b64 is None:
            send_calls = mock_service.users().messages().send.call_args_list
            for call in send_calls:
                body = call.kwargs.get("body") or (call[1].get("body") if len(call) > 1 else None)
                if body and "raw" in body:
                    raw_b64 = body["raw"]
                    break

        assert raw_b64 is not None
        raw_bytes = base64.urlsafe_b64decode(raw_b64)
        parsed = message_from_bytes(raw_bytes)
        assert "12 classified" in parsed["Subject"]
        assert "1 errors" in parsed["Subject"]

    def test_returns_message_id(
        self, mock_service: MagicMock, basic_stats: RunStats,
    ) -> None:
        result = send_summary_email(mock_service, basic_stats)
        assert result == "msg-12345"
