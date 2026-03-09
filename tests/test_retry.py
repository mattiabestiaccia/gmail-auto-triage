"""Tests for retry predicates and decorator behavior."""

from __future__ import annotations

from unittest.mock import MagicMock

import httplib2
import pytest
from googleapiclient.errors import HttpError

from email_triage.gmail import _execute_with_retry, _is_retryable_http_error


class TestIsRetryableHttpError:
    """Tests for the Gmail API retry predicate."""

    @pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
    def test_retryable_status_codes(self, status: int):
        err = HttpError(
            httplib2.Response({"status": str(status)}),
            b"Transient error",
        )
        assert _is_retryable_http_error(err) is True

    @pytest.mark.parametrize("status", [400, 401, 403])
    def test_non_retryable_status_codes(self, status: int):
        err = HttpError(
            httplib2.Response({"status": str(status)}),
            b"Non-retryable error",
        )
        assert _is_retryable_http_error(err) is False

    def test_non_http_error_not_retryable(self):
        assert _is_retryable_http_error(ValueError("not an http error")) is False

    def test_generic_exception_not_retryable(self):
        assert _is_retryable_http_error(RuntimeError("generic")) is False


class TestExecuteWithRetry:
    """Tests for the retry-wrapped execute helper."""

    def test_retries_on_503_then_succeeds(self):
        mock_request = MagicMock()
        err_503 = HttpError(
            httplib2.Response({"status": "503"}),
            b"Service Unavailable",
        )
        mock_request.execute.side_effect = [err_503, {"result": "ok"}]

        result = _execute_with_retry(mock_request)

        assert result == {"result": "ok"}
        assert mock_request.execute.call_count == 2

    def test_does_not_retry_on_401(self):
        mock_request = MagicMock()
        err_401 = HttpError(
            httplib2.Response({"status": "401"}),
            b"Unauthorized",
        )
        mock_request.execute.side_effect = err_401

        with pytest.raises(HttpError) as exc_info:
            _execute_with_retry(mock_request)

        assert exc_info.value.resp.status == 401
        assert mock_request.execute.call_count == 1

    def test_does_not_retry_on_403(self):
        mock_request = MagicMock()
        err_403 = HttpError(
            httplib2.Response({"status": "403"}),
            b"Forbidden",
        )
        mock_request.execute.side_effect = err_403

        with pytest.raises(HttpError) as exc_info:
            _execute_with_retry(mock_request)

        assert exc_info.value.resp.status == 403
        assert mock_request.execute.call_count == 1

    def test_retries_on_429_then_succeeds(self):
        mock_request = MagicMock()
        err_429 = HttpError(
            httplib2.Response({"status": "429"}),
            b"Rate limited",
        )
        mock_request.execute.side_effect = [err_429, {"result": "ok"}]

        result = _execute_with_retry(mock_request)

        assert result == {"result": "ok"}
        assert mock_request.execute.call_count == 2
