"""Tests for Gmail fetch, pagination, filtering, and parsing."""

from __future__ import annotations

import ast
import time
from datetime import timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, call

from email_triage.gmail import (
    fetch_messages_batch,
    fetch_unread_ids,
    filter_by_window,
    parse_message,
)
from email_triage.models import EmailData


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_raw_message(
    msg_id: str = "msg1",
    thread_id: str = "thread1",
    sender: str = "alice@example.com",
    subject: str = "Hello",
    date: str = "Mon, 7 Mar 2026 10:00:00 +0000",
    snippet: str = "Preview text",
    label_ids: list[str] | None = None,
    internal_date: str | None = None,
) -> dict:
    """Build a raw Gmail API message dict for testing."""
    msg = {
        "id": msg_id,
        "threadId": thread_id,
        "snippet": snippet,
        "labelIds": label_ids or ["UNREAD", "INBOX"],
        "payload": {
            "headers": [
                {"name": "From", "value": sender},
                {"name": "Subject", "value": subject},
                {"name": "Date", "value": date},
            ],
        },
    }
    if internal_date is not None:
        msg["internalDate"] = internal_date
    return msg


def _mock_service_list(pages: list[list[str]]) -> MagicMock:
    """Create a mock Gmail service that returns paginated message lists.

    Args:
        pages: List of pages, each page is a list of message IDs.
    """
    service = MagicMock()
    users = service.users.return_value
    messages = users.messages.return_value

    # Build chained execute responses
    responses = []
    for i, page_ids in enumerate(pages):
        response = {
            "messages": [{"id": mid} for mid in page_ids],
            "resultSizeEstimate": len(page_ids),
        }
        if i < len(pages) - 1:
            response["nextPageToken"] = f"token_{i + 1}"
        responses.append(response)

    # First call to list() returns a request mock
    first_request = MagicMock()
    first_request.execute.return_value = responses[0]
    messages.list.return_value = first_request

    # list_next returns subsequent requests or None
    subsequent = []
    for resp in responses[1:]:
        req = MagicMock()
        req.execute.return_value = resp
        subsequent.append(req)
    subsequent.append(None)  # sentinel: no more pages

    messages.list_next.side_effect = subsequent

    return service


# ---------------------------------------------------------------------------
# Tests: fetch_unread_ids
# ---------------------------------------------------------------------------

def test_fetch_unread_ids_single_page():
    """Single page of 5 IDs, no pagination needed."""
    ids = ["m1", "m2", "m3", "m4", "m5"]
    service = _mock_service_list([ids])

    result = fetch_unread_ids(service, max_results=100)

    assert result == ids
    service.users().messages().list.assert_called_once()


def test_fetch_unread_ids_pagination():
    """Two pages of results, all IDs collected."""
    page1 = ["m1", "m2", "m3"]
    page2 = ["m4", "m5"]
    service = _mock_service_list([page1, page2])

    result = fetch_unread_ids(service, max_results=100)

    assert result == ["m1", "m2", "m3", "m4", "m5"]
    # list_next should have been called (pagination triggered)
    service.users().messages().list_next.assert_called()


def test_fetch_unread_ids_respects_max_results():
    """Even if service returns 200 IDs, only max_results are collected."""
    all_ids = [f"m{i}" for i in range(200)]
    # Single page with 200 IDs
    service = _mock_service_list([all_ids])

    result = fetch_unread_ids(service, max_results=50)

    assert len(result) == 50
    assert result == all_ids[:50]


def test_fetch_unread_ids_with_date_filter():
    """Verify after: is appended to query when after_date provided."""
    service = _mock_service_list([["m1"]])

    fetch_unread_ids(service, after_date="2026/03/06")

    # Check the query passed to list()
    call_kwargs = service.users().messages().list.call_args
    assert "after:2026/03/06" in call_kwargs.kwargs.get("q", call_kwargs[1].get("q", ""))


# ---------------------------------------------------------------------------
# Tests: parse_message
# ---------------------------------------------------------------------------

def test_parse_message_extracts_fields():
    """Verify EmailData has correct sender, subject, snippet, etc."""
    raw = _make_raw_message(
        msg_id="abc123",
        thread_id="t456",
        sender="bob@test.com",
        subject="Important",
        date="Tue, 8 Mar 2026 12:00:00 +0000",
        snippet="This is a preview",
        label_ids=["UNREAD", "INBOX", "CATEGORY_PERSONAL"],
    )

    result = parse_message(raw)

    assert isinstance(result, EmailData)
    assert result.id == "abc123"
    assert result.thread_id == "t456"
    assert result.sender == "bob@test.com"
    assert result.subject == "Important"
    assert result.date == "Tue, 8 Mar 2026 12:00:00 +0000"
    assert result.snippet == "This is a preview"
    assert result.label_ids == ["UNREAD", "INBOX", "CATEGORY_PERSONAL"]


def test_parse_message_truncates_snippet():
    """Snippet longer than snippet_length is truncated."""
    long_snippet = "A" * 1000
    raw = _make_raw_message(snippet=long_snippet)

    result = parse_message(raw, snippet_length=500)

    assert len(result.snippet) == 500
    assert result.snippet == "A" * 500


# ---------------------------------------------------------------------------
# Tests: filter_by_window
# ---------------------------------------------------------------------------

def test_filter_by_window_includes_recent():
    """Message with internalDate within window is included."""
    from datetime import datetime

    # internal date = now (well within 24h window)
    now_ms = str(int(time.time() * 1000))
    raw = _make_raw_message(msg_id="recent", internal_date=now_ms)
    email = parse_message(raw)

    result = filter_by_window([email], [raw], hours=24)

    assert len(result) == 1
    assert result[0].id == "recent"


def test_filter_by_window_excludes_old():
    """Message with internalDate outside window is excluded."""
    # internal date = 48 hours ago (outside 24h window)
    old_time = time.time() - (48 * 3600)
    old_ms = str(int(old_time * 1000))
    raw = _make_raw_message(msg_id="old", internal_date=old_ms)
    email = parse_message(raw)

    result = filter_by_window([email], [raw], hours=24)

    assert len(result) == 0


# ---------------------------------------------------------------------------
# Tests: fetch_messages_batch
# ---------------------------------------------------------------------------

def test_fetch_messages_batch_collects_results():
    """Mock batch request, verify results collected."""
    service = MagicMock()

    raw1 = _make_raw_message(msg_id="m1")
    raw2 = _make_raw_message(msg_id="m2")

    def mock_batch_execute(batch_mock, expected_results):
        """Simulate batch.execute() calling the callback for each message."""
        original_new_batch = service.new_batch_http_request

        def new_batch_side_effect(callback=None):
            batch = MagicMock()
            batch._callback = callback
            batch._added = []

            def add_side_effect(request, request_id=None):
                batch._added.append(request_id)

            batch.add.side_effect = add_side_effect

            def execute_side_effect():
                for i, req_id in enumerate(batch._added):
                    if i < len(expected_results):
                        batch._callback(req_id, expected_results[i], None)

            batch.execute.side_effect = execute_side_effect
            return batch

        service.new_batch_http_request.side_effect = new_batch_side_effect

    mock_batch_execute(service, [raw1, raw2])

    results, errors = fetch_messages_batch(service, ["m1", "m2"])

    assert len(results) == 2
    assert len(errors) == 0
    assert results[0]["id"] == "m1"
    assert results[1]["id"] == "m2"


# ---------------------------------------------------------------------------
# Tests: safety (FETCH-05)
# ---------------------------------------------------------------------------

def test_no_mutating_api_calls():
    """Inspect gmail.py source to verify no calls to .modify(, .trash(, .delete(."""
    gmail_path = Path(__file__).parent.parent / "src" / "email_triage" / "gmail.py"
    source = gmail_path.read_text()

    tree = ast.parse(source)

    forbidden = {"modify", "trash", "delete", "batchModify", "batchDelete"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            assert node.attr not in forbidden, (
                f"SAFETY VIOLATION: gmail.py contains reference to '{node.attr}' "
                f"at line {node.lineno}. FETCH-05 requires read-only operations."
            )
