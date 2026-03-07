"""Data models for email triage."""

from dataclasses import dataclass


@dataclass
class EmailData:
    """Parsed email data from Gmail API response.

    Simple dataclass (not pydantic) because it represents API response data,
    not validated configuration.
    """

    id: str
    thread_id: str
    sender: str
    subject: str
    date: str
    snippet: str
    label_ids: list[str]
