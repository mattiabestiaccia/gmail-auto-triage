"""Gmail label management: list, create, apply labels under AutoTriage/ namespace.

Handles the full label lifecycle:
- Cache existing AutoTriage/* labels at startup
- Create missing labels (parent before child)
- Apply label IDs to messages
- Check idempotency (skip already-triaged emails)
"""

from __future__ import annotations

import logging

from googleapiclient.errors import HttpError

from email_triage.gmail import _execute_with_retry
from email_triage.models import EmailData

logger = logging.getLogger(__name__)

# Hardcoded per user decision -- NOT configurable
LABEL_PREFIX = "AutoTriage/"
AMBIGUOUS_CATEGORY = "_Ambiguous"
AMBIGUOUS_LABEL = f"{LABEL_PREFIX}{AMBIGUOUS_CATEGORY}"

# Label visibility defaults for created labels
_LABEL_VISIBILITY = {
    "labelListVisibility": "labelShow",
    "messageListVisibility": "show",
}


def list_triage_labels(service) -> dict[str, str]:
    """Fetch all AutoTriage/* labels, return {name: id} mapping.

    Only includes labels whose name starts with LABEL_PREFIX (i.e.,
    ``AutoTriage/Category``). The parent ``AutoTriage`` label itself
    is excluded from the mapping.

    Args:
        service: Authenticated Gmail API service resource.

    Returns:
        Dict mapping label name to label ID for all triage labels.
    """
    result = _execute_with_retry(service.users().labels().list(userId="me"))
    labels = result.get("labels", [])
    return {
        label["name"]: label["id"]
        for label in labels
        if label["name"].startswith(LABEL_PREFIX)
    }


def is_already_triaged(email: EmailData, triage_label_ids: set[str]) -> bool:
    """Check if email already has any AutoTriage label.

    Pure function -- no API call. Uses set intersection.

    Args:
        email: Parsed email data with label_ids.
        triage_label_ids: Set of known triage label IDs.

    Returns:
        True if the email already has at least one triage label.
    """
    return bool(set(email.label_ids) & triage_label_ids)


def ensure_label(service, name: str, cache: dict[str, str]) -> str:
    """Get or create a label under AutoTriage/, updating cache in place.

    Constructs the full label name (e.g., ``AutoTriage/Newsletter``),
    checks the cache, and creates the label if missing. Parent label
    ``AutoTriage`` is created first if it doesn't exist.

    On ``HttpError`` with status 409 (conflict -- label already exists),
    re-fetches the label list to populate cache and returns the existing ID.

    Args:
        service: Authenticated Gmail API service resource.
        name: Category name (e.g., "Newsletter"). Will be prefixed
            with ``AutoTriage/``.
        cache: Mutable dict {name: id} of known labels. Updated in place.

    Returns:
        Label ID for the requested label.
    """
    full_name = f"{LABEL_PREFIX}{name}"

    # Return from cache if already known
    if full_name in cache:
        return cache[full_name]

    try:
        # Ensure parent "AutoTriage" exists
        parent_name = LABEL_PREFIX.rstrip("/")
        if parent_name not in cache:
            parent = _execute_with_retry(
                service.users()
                .labels()
                .create(
                    userId="me",
                    body={"name": parent_name, **_LABEL_VISIBILITY},
                )
            )
            cache[parent["name"]] = parent["id"]

        # Create child label
        label = _execute_with_retry(
            service.users()
            .labels()
            .create(
                userId="me",
                body={"name": full_name, **_LABEL_VISIBILITY},
            )
        )
        cache[label["name"]] = label["id"]
        return label["id"]

    except HttpError as err:
        if err.resp.status == 409:
            # Label already exists -- re-fetch and return existing ID
            refreshed = list_triage_labels(service)
            cache.update(refreshed)
            # Also fetch parent if needed
            all_labels = _execute_with_retry(
                service.users().labels().list(userId="me")
            )
            for lbl in all_labels.get("labels", []):
                if lbl["name"] == LABEL_PREFIX.rstrip("/"):
                    cache[lbl["name"]] = lbl["id"]
            return cache[full_name]
        raise


def remove_labels(service, message_id: str, label_ids: list[str]) -> None:
    """Remove one or more labels from a Gmail message.

    Single API call per message using messages().modify().

    Args:
        service: Authenticated Gmail API service resource.
        message_id: Gmail message ID.
        label_ids: List of label IDs to remove.
    """
    _execute_with_retry(
        service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"removeLabelIds": label_ids},
        )
    )


def apply_labels(service, message_id: str, label_ids: list[str]) -> None:
    """Apply one or more labels to a Gmail message.

    Single API call per message using messages().modify().

    Args:
        service: Authenticated Gmail API service resource.
        message_id: Gmail message ID.
        label_ids: List of label IDs to apply.
    """
    _execute_with_retry(
        service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"addLabelIds": label_ids},
        )
    )
