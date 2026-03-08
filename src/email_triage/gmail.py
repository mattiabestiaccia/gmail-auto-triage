# SAFETY: This module ONLY reads. No modify/trash/delete calls.
# All functions use messages.list and messages.get exclusively.
"""Gmail API wrapper: fetch unread IDs with pagination, batch message retrieval,
time window filtering, and message parsing into EmailData."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from email_triage.models import EmailData


def fetch_message_ids(
    service,
    query: str,
    max_results: int = 100,
) -> list[str]:
    """Fetch message IDs matching a Gmail query, with pagination.

    Args:
        service: Authenticated Gmail API service resource.
        query: Gmail search query string (e.g. "is:unread", "in:inbox").
        max_results: Maximum number of message IDs to return.

    Returns:
        List of Gmail message IDs.
    """
    ids: list[str] = []
    request = service.users().messages().list(
        userId="me",
        q=query,
        maxResults=min(max_results, 500),
    )

    while request and len(ids) < max_results:
        response = request.execute()
        for msg in response.get("messages", []):
            if len(ids) >= max_results:
                break
            ids.append(msg["id"])
        request = service.users().messages().list_next(request, response)

    return ids


def fetch_unread_ids(
    service,
    max_results: int = 100,
    after_date: str | None = None,
) -> list[str]:
    """Fetch unread message IDs with pagination, up to max_results.

    Thin wrapper around fetch_message_ids with "is:unread" query.

    Args:
        service: Authenticated Gmail API service resource.
        max_results: Maximum number of message IDs to return.
        after_date: Optional date string (YYYY/MM/DD) for rough pre-filtering
            via Gmail query. Belt-and-suspenders with code-side internalDate filtering.

    Returns:
        List of Gmail message IDs.
    """
    query = "is:unread"
    if after_date:
        query += f" after:{after_date}"
    return fetch_message_ids(service, query, max_results)


def fetch_messages_batch(
    service,
    message_ids: list[str],
    on_progress: Callable[[int, int], None] | None = None,
) -> tuple[list[dict], list[tuple[str, Exception]]]:
    """Fetch message metadata in batches of 100 using BatchHttpRequest.

    Args:
        service: Authenticated Gmail API service resource.
        message_ids: List of message IDs to fetch.
        on_progress: Optional callback(current, total) called after each batch.

    Returns:
        Tuple of (results list, errors list). Each error is (message_id, exception).
    """
    results: list[dict] = []
    errors: list[tuple[str, Exception]] = []

    def callback(request_id: str, response: dict, exception: Exception | None):
        if exception:
            errors.append((request_id, exception))
        else:
            results.append(response)

    batch_size = 100
    for i in range(0, len(message_ids), batch_size):
        chunk = message_ids[i : i + batch_size]
        batch = service.new_batch_http_request(callback=callback)
        for msg_id in chunk:
            batch.add(
                service.users().messages().get(
                    userId="me",
                    id=msg_id,
                    format="metadata",
                    metadataHeaders=["From", "Subject", "Date"],
                ),
                request_id=msg_id,
            )
        batch.execute()

        if on_progress:
            on_progress(len(results) + len(errors), len(message_ids))

    return results, errors


def parse_message(msg: dict, snippet_length: int = 500) -> EmailData:
    """Parse a Gmail API message response into an EmailData instance.

    Args:
        msg: Raw Gmail API message dict (format="metadata").
        snippet_length: Maximum length for the snippet field.

    Returns:
        EmailData with extracted fields.
    """
    headers = {
        h["name"]: h["value"]
        for h in msg.get("payload", {}).get("headers", [])
    }
    snippet = msg.get("snippet", "")[:snippet_length]

    return EmailData(
        id=msg["id"],
        thread_id=msg["threadId"],
        sender=headers.get("From", ""),
        subject=headers.get("Subject", ""),
        date=headers.get("Date", ""),
        snippet=snippet,
        label_ids=msg.get("labelIds", []),
    )


def filter_by_window(
    emails: list[EmailData],
    messages_raw: list[dict],
    hours: int = 24,
) -> list[EmailData]:
    """Filter emails to only those within the processing time window.

    Uses internalDate field from raw messages for precise filtering
    (more accurate than Gmail query after: which uses midnight UTC boundaries).

    Args:
        emails: Parsed EmailData instances.
        messages_raw: Corresponding raw Gmail API message dicts.
        hours: Time window in hours (default 24).

    Returns:
        Filtered list of EmailData within the time window.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    cutoff_ms = int(cutoff.timestamp() * 1000)

    filtered: list[EmailData] = []
    for email, raw in zip(emails, messages_raw):
        internal_date = int(raw.get("internalDate", "0"))
        if internal_date >= cutoff_ms:
            filtered.append(email)

    return filtered
