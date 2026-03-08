"""CLI entry point orchestrating config -> auth -> fetch pipeline.

Usage: uv run python -m email_triage [options]
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timedelta, timezone

from email_triage.auth import authenticate, get_gmail_service
from email_triage.config import load_config
from email_triage.gmail import (
    fetch_messages_batch,
    fetch_unread_ids,
    filter_by_window,
    parse_message,
)
from email_triage.classifier import classify_email, create_genai_client
from email_triage.labels import (
    AMBIGUOUS_LABEL,
    apply_labels,
    ensure_label,
    is_already_triaged,
    list_triage_labels,
)
from email_triage.output import (
    Colors,
    print_classification_result,
    print_classification_summary,
    print_error,
    print_info,
    print_progress,
    print_success,
)


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="email-triage",
        description="Fetch and classify Gmail emails by category.",
    )
    parser.add_argument(
        "--config", "-c",
        default="categories.yaml",
        help="Path to categories YAML config (default: categories.yaml)",
    )
    parser.add_argument(
        "--credentials",
        default="credentials/credentials.json",
        help="Path to OAuth2 credentials JSON (default: credentials/credentials.json)",
    )
    parser.add_argument(
        "--token",
        default="credentials/token.json",
        help="Path to stored OAuth2 token (default: credentials/token.json)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output (show email previews)",
    )
    parser.add_argument(
        "--max-emails",
        type=int,
        default=None,
        help="Override max emails per run from config",
    )
    parser.add_argument(
        "--window-hours",
        type=int,
        default=None,
        help="Override processing window hours from config",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Classify emails but do not apply labels in Gmail",
    )
    return parser


def main(args: list[str] | None = None) -> None:
    """Run the full email triage fetch pipeline.

    Pipeline: load config -> authenticate -> fetch IDs -> batch fetch ->
    parse -> filter by time window -> print summary.
    """
    parser = _build_parser()
    parsed = parser.parse_args(args)

    start = time.monotonic()

    try:
        # 1. Load config
        print_info(f"Loading config from {parsed.config}...")
        config = load_config(parsed.config)
        category_names = ", ".join(c.name for c in config.categories)
        print_success(f"Loaded {len(config.categories)} categories: {category_names}")

        # 2. Authenticate
        creds = authenticate(parsed.credentials, parsed.token)
        service = get_gmail_service(creds)
        print_success("Connected to Gmail.")

        # 3. Calculate time window
        hours = parsed.window_hours or config.fetch.processing_window_hours
        after_dt = datetime.now(timezone.utc) - timedelta(hours=hours)
        after_date = after_dt.strftime("%Y/%m/%d")

        # 4. Effective max emails
        max_emails = parsed.max_emails or config.fetch.max_emails

        # 5. Fetch unread IDs
        print_info(f"Fetching unread emails (window: {hours}h, max: {max_emails})...")
        message_ids = fetch_unread_ids(service, max_results=max_emails, after_date=after_date)

        # 6. Handle empty result
        if not message_ids:
            print_success(f"No unread emails found in the last {hours} hours.")
            return

        print_info(f"Found {len(message_ids)} unread email(s). Fetching metadata...")

        # 7. Fetch message metadata with progress
        raw_messages, errors = fetch_messages_batch(
            service,
            message_ids,
            on_progress=lambda cur, tot: print_progress(cur, tot),
        )

        # 8. Parse and filter
        emails = [parse_message(msg, config.fetch.snippet_length) for msg in raw_messages]
        filtered = filter_by_window(emails, raw_messages, hours)

        if not filtered:
            print_success("No emails to classify after time filter.")
            return

        # 9. Initialize GenAI client
        client = create_genai_client()
        print_success("Gemini client ready.")

        # 10. Load label cache and filter already-triaged emails
        label_cache = list_triage_labels(service)
        triage_label_ids = set(label_cache.values())
        to_classify = []
        skipped = 0
        for email in filtered:
            if is_already_triaged(email, triage_label_ids):
                skipped += 1
            else:
                to_classify.append(email)

        if not to_classify:
            print_success(f"All {skipped} emails already triaged. Nothing to do.")
            return

        print_info(
            f"{len(to_classify)} emails to classify "
            f"({skipped} already triaged, skipped)."
        )

        # 11. Classify each email with delay between calls
        classified = 0
        ambiguous = 0
        errors_count = 0
        total = len(to_classify)

        for i, email in enumerate(to_classify):
            print_info(f"Classifying {i + 1}/{total}...")
            try:
                result = classify_email(
                    client, email, config.categories, config.classification,
                )
                if result.is_ambiguous:
                    ambiguous += 1
                else:
                    classified += 1

                # Per-email output in verbose or dry-run mode
                if parsed.verbose or parsed.dry_run:
                    print_classification_result(
                        email.subject, result.categories,
                        result.is_ambiguous, parsed.dry_run,
                    )

                # 12. Apply labels (skip if dry-run)
                if not parsed.dry_run:
                    if result.is_ambiguous:
                        label_id = ensure_label(service, "_Ambiguous", label_cache)
                        apply_labels(service, email.id, [label_id])
                    else:
                        label_ids = [
                            ensure_label(service, cat_name, label_cache)
                            for cat_name, _conf in result.categories
                        ]
                        apply_labels(service, email.id, label_ids)

            except Exception as exc:
                errors_count += 1
                print_error(
                    f"Failed to classify '{email.subject[:50]}': {exc}",
                )

            # Rate-limiting delay (skip after last email)
            if i < total - 1:
                time.sleep(4)

        # 13. Classification summary
        elapsed = time.monotonic() - start
        print_classification_summary(
            classified, ambiguous, skipped, parsed.dry_run, elapsed,
        )

    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)
    except Exception as e:
        # Check for Google auth refresh errors
        err_type = type(e).__name__
        if "RefreshError" in err_type:
            print_error(
                "Token refresh failed",
                suggestion=f"Delete {parsed.token} and re-run to re-authenticate",
            )
        else:
            print_error(
                str(e),
                suggestion="Run with --verbose for details" if not parsed.verbose else None,
            )
        sys.exit(1)
