"""Summary email notification: build and send run report via Gmail API.

Sends a multipart (HTML + plain text) summary email to the authenticated user
after each pipeline run with at least one processed email. Uses Gmail API
messages.send (requires gmail.modify scope).
"""

from __future__ import annotations

import base64
import logging
from datetime import datetime, timezone
from email.message import EmailMessage

from email_triage.models import RunStats

logger = logging.getLogger(__name__)


def get_user_email(service) -> str:
    """Fetch the authenticated user's email address from Gmail profile.

    Uses users().getProfile() instead of hardcoding "me" as the To address
    (Pitfall #3 — "me" is only valid as userId, not as email).

    Args:
        service: Authenticated Gmail API service resource.

    Returns:
        The user's email address string.
    """
    profile = service.users().getProfile(userId="me").execute()
    return profile["emailAddress"]


def _build_summary_html(stats: RunStats) -> str:
    """Build an HTML email body with run statistics.

    Includes summary table, per-category breakdown, error details,
    token usage, and elapsed time. Uses inline CSS for compatibility.

    Args:
        stats: Accumulated run statistics.

    Returns:
        HTML string for the email body.
    """
    run_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Summary table rows
    summary_rows = f"""\
<tr><td>Classified</td><td><strong>{stats.classified}</strong></td></tr>
<tr><td>Ambiguous</td><td>{stats.ambiguous}</td></tr>
<tr><td>Skipped (already triaged)</td><td>{stats.skipped_triaged}</td></tr>
<tr><td>Errors</td><td style="color:#c00;">{stats.errors}</td></tr>"""

    # Category breakdown
    category_section = ""
    if stats.categories:
        sorted_cats = sorted(stats.categories.items(), key=lambda x: x[1], reverse=True)
        cat_rows = "\n".join(
            f'<tr><td>{name}</td><td>{count}</td></tr>'
            for name, count in sorted_cats
        )
        category_section = f"""\
<h3>Categories</h3>
<table border="1" cellpadding="4" cellspacing="0" style="border-collapse:collapse;">
<tr style="background:#f0f0f0;"><th>Category</th><th>Count</th></tr>
{cat_rows}
</table>"""

    # Error details
    error_section = ""
    if stats.error_details:
        shown = stats.error_details[:10]
        items = "\n".join(f"<li>{_html_escape(detail)}</li>" for detail in shown)
        more = ""
        if len(stats.error_details) > 10:
            more = f"<p>... and {len(stats.error_details) - 10} more errors</p>"
        error_section = f"""\
<h3>Errors ({stats.errors})</h3>
<ul>{items}</ul>
{more}"""

    # Token usage
    if stats.token_usage_prompt == 0 and stats.token_usage_completion == 0:
        token_section = "<p>Token usage: N/A</p>"
    else:
        total_tokens = stats.token_usage_prompt + stats.token_usage_completion
        token_section = f"""\
<h3>Token Usage</h3>
<table border="1" cellpadding="4" cellspacing="0" style="border-collapse:collapse;">
<tr><td>Prompt tokens</td><td>{stats.token_usage_prompt:,}</td></tr>
<tr><td>Completion tokens</td><td>{stats.token_usage_completion:,}</td></tr>
<tr><td><strong>Total</strong></td><td><strong>{total_tokens:,}</strong></td></tr>
</table>"""

    return f"""\
<html>
<body style="font-family:sans-serif; max-width:600px; margin:0 auto;">
<h2>AutoTriage Run Summary</h2>
<p style="color:#666;">{run_time}</p>

<table border="1" cellpadding="4" cellspacing="0" style="border-collapse:collapse;">
<tr style="background:#f0f0f0;"><th>Metric</th><th>Value</th></tr>
{summary_rows}
</table>

{category_section}
{error_section}
{token_section}

<p>Elapsed: {stats.elapsed_seconds:.1f}s | LLM calls: {stats.api_calls_llm}</p>
</body>
</html>"""


def _build_summary_text(stats: RunStats) -> str:
    """Build a plain text email body with run statistics.

    Same information as HTML version, formatted for plain text display.

    Args:
        stats: Accumulated run statistics.

    Returns:
        Plain text string for the email body.
    """
    run_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        "AutoTriage Run Summary",
        f"Run: {run_time}",
        "",
        f"Classified: {stats.classified}",
        f"Ambiguous:  {stats.ambiguous}",
        f"Skipped:    {stats.skipped_triaged}",
        f"Errors:     {stats.errors}",
    ]

    if stats.categories:
        lines.append("")
        lines.append("Categories:")
        sorted_cats = sorted(stats.categories.items(), key=lambda x: x[1], reverse=True)
        for name, count in sorted_cats:
            lines.append(f"  {name}: {count}")

    if stats.error_details:
        lines.append("")
        lines.append(f"Errors ({stats.errors}):")
        for detail in stats.error_details[:10]:
            lines.append(f"  - {detail}")
        if len(stats.error_details) > 10:
            lines.append(f"  ... and {len(stats.error_details) - 10} more")

    lines.append("")
    if stats.token_usage_prompt == 0 and stats.token_usage_completion == 0:
        lines.append("Token usage: N/A")
    else:
        total_tokens = stats.token_usage_prompt + stats.token_usage_completion
        lines.append(f"Prompt tokens:     {stats.token_usage_prompt:,}")
        lines.append(f"Completion tokens: {stats.token_usage_completion:,}")
        lines.append(f"Total tokens:      {total_tokens:,}")

    lines.append(f"Elapsed: {stats.elapsed_seconds:.1f}s | LLM calls: {stats.api_calls_llm}")

    return "\n".join(lines)


def send_summary_email(service, stats: RunStats) -> str | None:
    """Build and send a summary email to the authenticated user.

    Creates a multipart email (text/plain + text/html) with run statistics
    and sends it via Gmail API. The caller (cli.py) wraps this in try/except
    to handle API errors gracefully.

    Args:
        service: Authenticated Gmail API service resource.
        stats: Accumulated run statistics.

    Returns:
        Gmail message ID on success, or None if no email was sent.

    Raises:
        HttpError: On Gmail API send failure (caller handles).
    """
    user_email = get_user_email(service)

    msg = EmailMessage()
    msg["To"] = user_email
    msg["From"] = user_email
    msg["Subject"] = (
        f"AutoTriage Summary: {stats.classified} classified, {stats.errors} errors"
    )

    # Set plain text content and add HTML alternative
    text_content = _build_summary_text(stats)
    html_content = _build_summary_html(stats)

    msg.set_content(text_content)
    msg.add_alternative(html_content, subtype="html")

    # Base64url encode for Gmail API
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")

    result = (
        service.users()
        .messages()
        .send(userId="me", body={"raw": raw})
        .execute()
    )

    message_id = result.get("id", "unknown")
    logger.info("Summary email sent (ID: %s) to %s", message_id, user_email)
    return message_id


def _html_escape(text: str) -> str:
    """Minimal HTML escape for user-generated error messages."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
