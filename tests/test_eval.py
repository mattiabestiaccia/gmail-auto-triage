"""Tests for email classification eval pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from email_triage.eval import _cmd_create, _cmd_reset, _cmd_run


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_raw_message(
    msg_id: str = "msg1",
    sender: str = "alice@example.com",
    subject: str = "Test email",
    snippet: str = "Preview text",
    label_ids: list[str] | None = None,
) -> dict:
    """Build a raw Gmail API message dict."""
    return {
        "id": msg_id,
        "threadId": f"thread_{msg_id}",
        "snippet": snippet,
        "labelIds": label_ids or ["INBOX"],
        "payload": {
            "headers": [
                {"name": "From", "value": sender},
                {"name": "Subject", "value": subject},
                {"name": "Date", "value": "Sun, 8 Mar 2026 10:00:00 +0000"},
            ],
        },
    }


def _mock_gmail_service(message_ids: list[str], raw_messages: list[dict],
                         triage_labels: dict[str, str] | None = None):
    """Build a mock Gmail service for eval tests."""
    service = MagicMock()
    users = service.users.return_value
    messages = users.messages.return_value

    # messages().list() for fetch_message_ids
    list_response = {"messages": [{"id": mid} for mid in message_ids]}
    first_request = MagicMock()
    first_request.execute.return_value = list_response
    messages.list.return_value = first_request
    messages.list_next.return_value = None

    # Batch fetch: new_batch_http_request
    def new_batch_side_effect(callback=None):
        batch = MagicMock()
        batch._callback = callback
        batch._added = []

        def add_side_effect(request, request_id=None):
            batch._added.append(request_id)

        batch.add.side_effect = add_side_effect

        def execute_side_effect():
            for req_id in batch._added:
                raw = next((m for m in raw_messages if m["id"] == req_id), None)
                if raw:
                    batch._callback(req_id, raw, None)

        batch.execute.side_effect = execute_side_effect
        return batch

    service.new_batch_http_request.side_effect = new_batch_side_effect

    # labels().list() for list_triage_labels
    labels_list = []
    if triage_labels:
        labels_list = [{"id": v, "name": k} for k, v in triage_labels.items()]
    users.labels.return_value.list.return_value.execute.return_value = {
        "labels": labels_list,
    }

    return service


def _make_args(tmp_path: Path, **overrides):
    """Build a namespace mimicking argparse output."""
    defaults = {
        "credentials": "credentials/credentials.json",
        "token": "credentials/token.json",
        "config": "categories.yaml",
        "testset": str(tmp_path / "testset.json"),
        "dry_run": False,
        "count": 20,
        "query": None,
    }
    defaults.update(overrides)

    class Args:
        pass

    args = Args()
    for k, v in defaults.items():
        setattr(args, k, v)
    return args


# ---------------------------------------------------------------------------
# Tests: _cmd_create
# ---------------------------------------------------------------------------

class TestCmdCreate:
    """_cmd_create: select emails, strip labels, save testset.json."""

    @patch("email_triage.eval.remove_labels")
    @patch("email_triage.eval.get_gmail_service")
    @patch("email_triage.eval.authenticate")
    def test_saves_json_with_ids(self, mock_auth, mock_get_svc, mock_remove, tmp_path):
        """Creates testset.json with message IDs."""
        ids = ["m1", "m2", "m3"]
        raws = [_make_raw_message(mid) for mid in ids]
        service = _mock_gmail_service(ids, raws)
        mock_get_svc.return_value = service

        args = _make_args(tmp_path, count=3)
        _cmd_create(args)

        testset_path = Path(args.testset)
        assert testset_path.exists()
        data = json.loads(testset_path.read_text())
        assert data["message_ids"] == ids
        assert data["count"] == 3
        assert "created_at" in data
        assert "query" in data

    @patch("email_triage.eval.remove_labels")
    @patch("email_triage.eval.get_gmail_service")
    @patch("email_triage.eval.authenticate")
    def test_strips_existing_labels(self, mock_auth, mock_get_svc, mock_remove, tmp_path):
        """Calls remove_labels for emails that have AutoTriage labels."""
        triage_labels = {
            "AutoTriage/Newsletter": "Label_1",
            "AutoTriage/Receipt": "Label_2",
        }
        ids = ["m1", "m2"]
        raws = [
            _make_raw_message("m1", label_ids=["INBOX", "Label_1"]),
            _make_raw_message("m2", label_ids=["INBOX"]),
        ]
        service = _mock_gmail_service(ids, raws, triage_labels)
        mock_get_svc.return_value = service

        args = _make_args(tmp_path, count=2)
        _cmd_create(args)

        # Only m1 has a triage label, so remove_labels called once
        mock_remove.assert_called_once_with(service, "m1", ["Label_1"])


# ---------------------------------------------------------------------------
# Tests: _cmd_reset
# ---------------------------------------------------------------------------

class TestCmdReset:
    """_cmd_reset: remove AutoTriage labels from test set emails."""

    @patch("email_triage.eval.remove_labels")
    @patch("email_triage.eval.get_gmail_service")
    @patch("email_triage.eval.authenticate")
    def test_removes_triage_labels(self, mock_auth, mock_get_svc, mock_remove, tmp_path):
        """Removes AutoTriage labels from emails in testset."""
        triage_labels = {"AutoTriage/Newsletter": "Label_1"}
        ids = ["m1", "m2"]
        raws = [
            _make_raw_message("m1", label_ids=["INBOX", "Label_1"]),
            _make_raw_message("m2", label_ids=["INBOX", "Label_1"]),
        ]
        service = _mock_gmail_service(ids, raws, triage_labels)
        mock_get_svc.return_value = service

        # Write testset.json
        testset_path = tmp_path / "testset.json"
        testset_path.write_text(json.dumps({"message_ids": ids, "count": 2}))

        args = _make_args(tmp_path)
        _cmd_reset(args)

        assert mock_remove.call_count == 2
        mock_remove.assert_any_call(service, "m1", ["Label_1"])
        mock_remove.assert_any_call(service, "m2", ["Label_1"])

    @patch("email_triage.eval.remove_labels")
    @patch("email_triage.eval.get_gmail_service")
    @patch("email_triage.eval.authenticate")
    def test_skips_emails_without_labels(self, mock_auth, mock_get_svc, mock_remove, tmp_path):
        """No remove_labels call for emails without triage labels."""
        triage_labels = {"AutoTriage/Newsletter": "Label_1"}
        ids = ["m1"]
        raws = [_make_raw_message("m1", label_ids=["INBOX"])]
        service = _mock_gmail_service(ids, raws, triage_labels)
        mock_get_svc.return_value = service

        testset_path = tmp_path / "testset.json"
        testset_path.write_text(json.dumps({"message_ids": ids, "count": 1}))

        args = _make_args(tmp_path)
        _cmd_reset(args)

        mock_remove.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: _cmd_run
# ---------------------------------------------------------------------------

class TestCmdRun:
    """_cmd_run: classify test set emails."""

    @patch("email_triage.eval.time.sleep")
    @patch("email_triage.eval.classify_email")
    @patch("email_triage.eval.create_genai_client")
    @patch("email_triage.eval.load_config")
    @patch("email_triage.eval.get_gmail_service")
    @patch("email_triage.eval.authenticate")
    def test_classifies_all_emails(
        self, mock_auth, mock_get_svc, mock_load_config,
        mock_genai, mock_classify, mock_sleep, tmp_path,
    ):
        """classify_email called once per email in testset."""
        from email_triage.models import ClassificationResult

        ids = ["m1", "m2", "m3"]
        raws = [_make_raw_message(mid, subject=f"Email {mid}") for mid in ids]
        service = _mock_gmail_service(ids, raws)
        mock_get_svc.return_value = service

        mock_config = MagicMock()
        mock_config.categories = [MagicMock(name="Newsletter")]
        mock_config.classification = MagicMock()
        mock_config.fetch.snippet_length = 500
        mock_load_config.return_value = mock_config

        mock_classify.return_value = ClassificationResult(
            categories=[("Newsletter", 0.9)],
            reasoning="test",
            is_ambiguous=False,
        )

        testset_path = tmp_path / "testset.json"
        testset_path.write_text(json.dumps({"message_ids": ids, "count": 3}))

        args = _make_args(tmp_path, dry_run=False)
        _cmd_run(args)

        assert mock_classify.call_count == 3

    @patch("email_triage.eval.time.sleep")
    @patch("email_triage.eval.apply_labels")
    @patch("email_triage.eval.classify_email")
    @patch("email_triage.eval.create_genai_client")
    @patch("email_triage.eval.load_config")
    @patch("email_triage.eval.get_gmail_service")
    @patch("email_triage.eval.authenticate")
    def test_dry_run_no_labels(
        self, mock_auth, mock_get_svc, mock_load_config,
        mock_genai, mock_classify, mock_apply, mock_sleep, tmp_path,
    ):
        """--dry-run: classify but never call apply_labels."""
        from email_triage.models import ClassificationResult

        ids = ["m1"]
        raws = [_make_raw_message("m1")]
        service = _mock_gmail_service(ids, raws)
        mock_get_svc.return_value = service

        mock_config = MagicMock()
        mock_config.categories = [MagicMock(name="Newsletter")]
        mock_config.classification = MagicMock()
        mock_config.fetch.snippet_length = 500
        mock_load_config.return_value = mock_config

        mock_classify.return_value = ClassificationResult(
            categories=[("Newsletter", 0.9)],
            reasoning="test",
            is_ambiguous=False,
        )

        testset_path = tmp_path / "testset.json"
        testset_path.write_text(json.dumps({"message_ids": ids, "count": 1}))

        args = _make_args(tmp_path, dry_run=True)
        _cmd_run(args)

        mock_apply.assert_not_called()
