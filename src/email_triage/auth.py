"""OAuth2 authentication with Gmail, token persistence, and automatic refresh.

Handles three authentication paths:
1. Valid cached token -> use directly (no prompt)
2. Expired token with refresh token -> auto-refresh silently
3. No token -> interactive browser-based OAuth2 flow with URL fallback

Token is persisted as JSON at credentials/token.json with 600 permissions.
Uses gmail.modify scope to cover read + label + send (avoids re-authorization).
"""

from __future__ import annotations

import os
import sys

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from email_triage.output import print_error, print_info, print_step, print_success

# Single scope covers read + label management + send.
# Using gmail.modify from the start avoids scope mismatch re-authorization later.
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

DEFAULT_TOKEN_PATH = "credentials/token.json"
DEFAULT_CREDENTIALS_PATH = "credentials/credentials.json"


def authenticate(
    credentials_path: str = DEFAULT_CREDENTIALS_PATH,
    token_path: str = DEFAULT_TOKEN_PATH,
) -> Credentials:
    """Authenticate with Gmail via OAuth2.

    Loads persisted token if available, refreshes if expired, or runs
    interactive browser flow for first-time setup.

    Args:
        credentials_path: Path to OAuth2 client secrets JSON from Google Cloud.
        token_path: Path where the user token is persisted between runs.

    Returns:
        Valid Google OAuth2 credentials.
    """
    creds: Credentials | None = None

    # 1. Load existing token
    if os.path.exists(token_path):
        print_info("Loading saved credentials...")
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    # 2. Check validity — return immediately if valid
    if creds and creds.valid:
        print_success("Authenticated successfully.")
        return creds

    # 3. Auto-refresh expired token
    if creds and creds.expired and creds.refresh_token:
        print_info("Token expired, refreshing...")
        creds.refresh(Request())
        _save_token(creds, token_path)
        print_success("Token refreshed successfully.")
        return creds

    # 4. First-run interactive flow
    if not os.path.exists(credentials_path):
        print_error(
            f"credentials.json not found at {credentials_path}",
            suggestion=(
                "Download it from Google Cloud Console -> "
                "APIs & Services -> Credentials -> "
                "OAuth 2.0 Client IDs -> Download JSON"
            ),
        )
        sys.exit(1)

    print_step(1, 3, "Opening browser for Google authorization...")
    print_step(2, 3, "Sign in with your Google account and grant access to Gmail")
    print_step(3, 3, "Waiting for authorization callback...")

    flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
    creds = flow.run_local_server(port=0, open_browser=True)

    _save_token(creds, token_path)
    print_success(f"Authorization complete! Token saved to {token_path}")
    print_info(
        "Note: Your OAuth2 consent screen must be 'Published' (not 'Testing') "
        "for the token to persist beyond 7 days. "
        "See: https://console.cloud.google.com/apis/credentials/consent"
    )
    return creds


def _save_token(creds: Credentials, token_path: str) -> None:
    """Save credentials to file with restricted permissions (600)."""
    os.makedirs(os.path.dirname(token_path), exist_ok=True)
    with open(token_path, "w") as f:
        f.write(creds.to_json())
    os.chmod(token_path, 0o600)


def get_gmail_service(creds: Credentials):
    """Build an authenticated Gmail API v1 service object.

    Args:
        creds: Valid Google OAuth2 credentials.

    Returns:
        Gmail API service resource.
    """
    return build("gmail", "v1", credentials=creds)
