"""Tests for OAuth2 authentication with mocked Google APIs."""

from __future__ import annotations

import json
import os
import stat
from unittest.mock import MagicMock, patch

import pytest

from email_triage.auth import (
    DEFAULT_CREDENTIALS_PATH,
    SCOPES,
    authenticate,
    get_gmail_service,
)


def _make_creds(*, valid: bool = True, expired: bool = False, refresh_token: str | None = "refresh") -> MagicMock:
    """Create a mock Credentials object with given state."""
    creds = MagicMock()
    creds.valid = valid
    creds.expired = expired
    creds.refresh_token = refresh_token
    creds.to_json.return_value = json.dumps({"token": "mock", "refresh_token": refresh_token})
    return creds


class TestAuthenticateWithValidToken:
    """When a valid cached token exists, use it directly."""

    @patch("email_triage.auth.os.path.exists", return_value=True)
    @patch("email_triage.auth.Credentials.from_authorized_user_file")
    def test_returns_valid_creds_without_refresh_or_flow(self, mock_load, mock_exists):
        valid_creds = _make_creds(valid=True, expired=False)
        mock_load.return_value = valid_creds

        result = authenticate(token_path="credentials/token.json")

        assert result is valid_creds
        mock_load.assert_called_once_with("credentials/token.json", SCOPES)
        # No refresh should be called
        valid_creds.refresh.assert_not_called()


class TestAuthenticateRefreshesExpiredToken:
    """When token is expired but has refresh_token, auto-refresh it."""

    @patch("email_triage.auth._save_token")
    @patch("email_triage.auth.Request")
    @patch("email_triage.auth.os.path.exists", return_value=True)
    @patch("email_triage.auth.Credentials.from_authorized_user_file")
    def test_refreshes_and_saves(self, mock_load, mock_exists, mock_request, mock_save):
        expired_creds = _make_creds(valid=False, expired=True, refresh_token="token")
        mock_load.return_value = expired_creds

        result = authenticate(token_path="credentials/token.json")

        assert result is expired_creds
        expired_creds.refresh.assert_called_once_with(mock_request.return_value)
        mock_save.assert_called_once_with(expired_creds, "credentials/token.json")


class TestAuthenticateFirstRunFlow:
    """When no token file exists, run interactive OAuth2 flow."""

    @patch("email_triage.auth._save_token")
    @patch("email_triage.auth.InstalledAppFlow")
    @patch("email_triage.auth.os.path.exists")
    def test_runs_local_server_flow(self, mock_exists, mock_flow_cls, mock_save):
        # token_path doesn't exist, but credentials_path does
        mock_exists.side_effect = lambda p: p != "credentials/token.json"

        mock_flow = MagicMock()
        new_creds = _make_creds(valid=True)
        mock_flow.run_local_server.return_value = new_creds
        mock_flow_cls.from_client_secrets_file.return_value = mock_flow

        result = authenticate(
            credentials_path="credentials/credentials.json",
            token_path="credentials/token.json",
        )

        assert result is new_creds
        mock_flow_cls.from_client_secrets_file.assert_called_once_with(
            "credentials/credentials.json", SCOPES,
        )
        mock_flow.run_local_server.assert_called_once_with(port=0, open_browser=True)
        mock_save.assert_called_once_with(new_creds, "credentials/token.json")


class TestAuthenticateMissingCredentialsFile:
    """When neither credentials.json nor token.json exist, exit with error."""

    @patch("email_triage.auth.os.path.exists", return_value=False)
    def test_exits_with_code_1(self, mock_exists):
        with pytest.raises(SystemExit) as exc_info:
            authenticate(
                credentials_path="credentials/credentials.json",
                token_path="credentials/token.json",
            )
        assert exc_info.value.code == 1


class TestTokenFilePermissions:
    """Token file must be saved with 600 permissions."""

    def test_token_saved_with_restricted_permissions(self, tmp_path):
        from email_triage.auth import _save_token

        token_path = str(tmp_path / "token.json")
        creds = _make_creds(valid=True)

        _save_token(creds, token_path)

        file_stat = os.stat(token_path)
        # Check only owner read+write bits
        permission_bits = stat.S_IMODE(file_stat.st_mode)
        assert permission_bits == 0o600, f"Expected 0o600, got {oct(permission_bits)}"


class TestGetGmailService:
    """get_gmail_service builds a Gmail API v1 service."""

    @patch("email_triage.auth.build")
    def test_builds_gmail_v1_service(self, mock_build):
        creds = _make_creds(valid=True)
        result = get_gmail_service(creds)

        mock_build.assert_called_once_with("gmail", "v1", credentials=creds)
        assert result is mock_build.return_value
