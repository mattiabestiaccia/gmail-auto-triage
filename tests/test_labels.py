"""Tests for Gmail label management: list, create, apply, idempotency."""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from email_triage.labels import (
    AMBIGUOUS_LABEL,
    LABEL_PREFIX,
    apply_labels,
    ensure_label,
    is_already_triaged,
    list_triage_labels,
)
from email_triage.models import EmailData


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_email(
    label_ids: list[str] | None = None,
    msg_id: str = "msg1",
) -> EmailData:
    """Create a minimal EmailData for testing."""
    return EmailData(
        id=msg_id,
        thread_id="thread1",
        sender="alice@example.com",
        subject="Test",
        date="Mon, 7 Mar 2026 10:00:00 +0000",
        snippet="Preview",
        label_ids=label_ids or [],
    )


def _mock_label_service(existing_labels: list[dict] | None = None) -> MagicMock:
    """Create a mock Gmail service with label methods.

    Args:
        existing_labels: List of label dicts {"id": ..., "name": ...} returned
            by labels().list().
    """
    service = MagicMock()
    users = service.users.return_value
    labels = users.labels.return_value

    # labels().list() -> execute() returns labels
    list_result = {"labels": existing_labels or []}
    labels.list.return_value.execute.return_value = list_result

    return service


# ---------------------------------------------------------------------------
# Tests: constants
# ---------------------------------------------------------------------------

class TestConstants:
    """Verify module-level constants."""

    def test_label_prefix(self):
        assert LABEL_PREFIX == "AutoTriage/"

    def test_ambiguous_label(self):
        assert AMBIGUOUS_LABEL == "AutoTriage/_Ambiguous"


# ---------------------------------------------------------------------------
# Tests: is_already_triaged (pure logic, no mocking needed)
# ---------------------------------------------------------------------------

class TestIsAlreadyTriaged:
    """Pure function: check set intersection of email.label_ids with triage IDs."""

    def test_email_with_triage_label_returns_true(self):
        email = _make_email(label_ids=["Label_100", "UNREAD"])
        assert is_already_triaged(email, triage_label_ids={"Label_100"}) is True

    def test_email_without_triage_label_returns_false(self):
        email = _make_email(label_ids=["UNREAD", "INBOX"])
        assert is_already_triaged(email, triage_label_ids={"Label_100"}) is False

    def test_email_with_empty_labels_returns_false(self):
        email = _make_email(label_ids=[])
        assert is_already_triaged(email, triage_label_ids={"Label_100"}) is False

    def test_email_with_multiple_triage_labels(self):
        """Email has one of several triage labels -> True."""
        email = _make_email(label_ids=["UNREAD", "Label_200"])
        assert is_already_triaged(
            email, triage_label_ids={"Label_100", "Label_200"}
        ) is True

    def test_empty_triage_set_returns_false(self):
        """No triage labels cached yet -> nothing matches."""
        email = _make_email(label_ids=["Label_100", "UNREAD"])
        assert is_already_triaged(email, triage_label_ids=set()) is False


# ---------------------------------------------------------------------------
# Tests: list_triage_labels (mocked Gmail service)
# ---------------------------------------------------------------------------

class TestListTriageLabels:
    """list_triage_labels: fetch and filter to AutoTriage/* labels only."""

    def test_returns_filtered_mapping(self):
        """Only AutoTriage/* labels are returned in the mapping."""
        labels = [
            {"id": "Label_1", "name": "AutoTriage/Newsletter"},
            {"id": "Label_2", "name": "AutoTriage/Receipt"},
            {"id": "Label_3", "name": "INBOX"},
            {"id": "Label_4", "name": "UNREAD"},
            {"id": "Label_5", "name": "OtherLabel"},
        ]
        service = _mock_label_service(labels)

        result = list_triage_labels(service)

        assert result == {
            "AutoTriage/Newsletter": "Label_1",
            "AutoTriage/Receipt": "Label_2",
        }

    def test_ignores_non_autotriage_labels(self):
        """Labels without AutoTriage/ prefix are excluded."""
        labels = [
            {"id": "Label_1", "name": "Work"},
            {"id": "Label_2", "name": "Personal"},
        ]
        service = _mock_label_service(labels)

        result = list_triage_labels(service)

        assert result == {}

    def test_includes_parent_label(self):
        """The parent 'AutoTriage' label (without /) is NOT included —
        only labels starting with 'AutoTriage/' are included."""
        labels = [
            {"id": "Label_0", "name": "AutoTriage"},
            {"id": "Label_1", "name": "AutoTriage/Newsletter"},
        ]
        service = _mock_label_service(labels)

        result = list_triage_labels(service)

        # Parent "AutoTriage" does NOT start with "AutoTriage/" so it's excluded
        assert result == {"AutoTriage/Newsletter": "Label_1"}

    def test_calls_api_correctly(self):
        """Verify the API call is made with userId='me'."""
        service = _mock_label_service([])

        list_triage_labels(service)

        service.users().labels().list.assert_called_once_with(userId="me")


# ---------------------------------------------------------------------------
# Tests: ensure_label (mocked Gmail service)
# ---------------------------------------------------------------------------

class TestEnsureLabel:
    """ensure_label: get or create labels, managing cache and parent creation."""

    def test_returns_cached_label_without_api_call(self):
        """If label already in cache, return ID without any create call."""
        service = _mock_label_service()
        cache = {"AutoTriage/Newsletter": "Label_1"}

        result = ensure_label(service, "Newsletter", cache)

        assert result == "Label_1"
        # No create call should have been made
        service.users().labels().create.assert_not_called()

    def test_creates_parent_then_child(self):
        """When cache is empty, creates parent 'AutoTriage' first, then child."""
        service = _mock_label_service()

        # First create call (parent) returns parent label
        # Second create call (child) returns child label
        create_mock = service.users().labels().create
        create_mock.return_value.execute.side_effect = [
            {"id": "Label_P", "name": "AutoTriage"},
            {"id": "Label_C", "name": "AutoTriage/Newsletter"},
        ]

        cache: dict[str, str] = {}
        result = ensure_label(service, "Newsletter", cache)

        assert result == "Label_C"
        # Parent should be in cache now
        assert cache["AutoTriage"] == "Label_P"
        assert cache["AutoTriage/Newsletter"] == "Label_C"
        # Two create calls: parent + child
        assert create_mock.call_count == 2

    def test_creates_child_when_parent_exists_in_cache(self):
        """When parent is in cache, only creates child label."""
        service = _mock_label_service()

        create_mock = service.users().labels().create
        create_mock.return_value.execute.return_value = {
            "id": "Label_C",
            "name": "AutoTriage/Receipt",
        }

        cache = {"AutoTriage": "Label_P"}
        result = ensure_label(service, "Receipt", cache)

        assert result == "Label_C"
        assert cache["AutoTriage/Receipt"] == "Label_C"
        # Only one create call (child only)
        assert create_mock.call_count == 1

    def test_updates_cache_in_place(self):
        """Cache dict is mutated in place (caller keeps reference)."""
        service = _mock_label_service()

        create_mock = service.users().labels().create
        create_mock.return_value.execute.side_effect = [
            {"id": "Label_P", "name": "AutoTriage"},
            {"id": "Label_C", "name": "AutoTriage/Alert"},
        ]

        cache: dict[str, str] = {}
        original_cache = cache  # same reference
        ensure_label(service, "Alert", cache)

        # Verify mutation, not replacement
        assert original_cache is cache
        assert "AutoTriage/Alert" in original_cache

    def test_handles_409_conflict(self):
        """On 409 Conflict, re-fetch labels and return existing ID."""
        from googleapiclient.errors import HttpError

        service = _mock_label_service()

        # First create call raises 409
        resp = MagicMock()
        resp.status = 409
        conflict_error = HttpError(resp, b"Label already exists")

        create_mock = service.users().labels().create
        create_mock.return_value.execute.side_effect = conflict_error

        # Re-fetch returns the existing label
        service.users().labels().list.return_value.execute.return_value = {
            "labels": [
                {"id": "Label_P", "name": "AutoTriage"},
                {"id": "Label_E", "name": "AutoTriage/Newsletter"},
            ]
        }

        cache: dict[str, str] = {"AutoTriage": "Label_P"}
        result = ensure_label(service, "Newsletter", cache)

        assert result == "Label_E"
        assert cache["AutoTriage/Newsletter"] == "Label_E"

    def test_label_visibility_settings(self):
        """Created labels have correct visibility settings."""
        service = _mock_label_service()

        create_mock = service.users().labels().create
        create_mock.return_value.execute.side_effect = [
            {"id": "Label_P", "name": "AutoTriage"},
            {"id": "Label_C", "name": "AutoTriage/News"},
        ]

        cache: dict[str, str] = {}
        ensure_label(service, "News", cache)

        # Check the body of the child label create call
        calls = create_mock.call_args_list
        for c in calls:
            body = c.kwargs.get("body", c[1].get("body", {}))
            assert body["labelListVisibility"] == "labelShow"
            assert body["messageListVisibility"] == "show"


# ---------------------------------------------------------------------------
# Tests: apply_labels (mocked Gmail service)
# ---------------------------------------------------------------------------

class TestApplyLabels:
    """apply_labels: calls messages().modify with addLabelIds."""

    def test_calls_modify_with_label_ids(self):
        """Single label ID sent via modify."""
        service = MagicMock()

        apply_labels(service, "msg123", ["Label_1"])

        service.users().messages().modify.assert_called_once_with(
            userId="me",
            id="msg123",
            body={"addLabelIds": ["Label_1"]},
        )
        service.users().messages().modify().execute.assert_called_once()

    def test_multiple_labels_in_single_call(self):
        """Multiple label IDs sent in one modify call."""
        service = MagicMock()

        apply_labels(service, "msg456", ["Label_1", "Label_2"])

        service.users().messages().modify.assert_called_once_with(
            userId="me",
            id="msg456",
            body={"addLabelIds": ["Label_1", "Label_2"]},
        )
