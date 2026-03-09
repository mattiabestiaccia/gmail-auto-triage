"""CLI entry point orchestrating config -> auth -> fetch -> classify -> notify pipeline.

Usage: uv run python -m email_triage [options]

Cron-compatible: exits 0 on success, 1 on fatal error, 130 on interrupt.
Logging to stderr (console) and optional JSON file. Per-email errors do not
crash the batch -- they are accumulated and reported in the summary email.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timedelta, timezone

from email_triage.auth import authenticate, get_gmail_service
from email_triage.classifier import classify_email, create_genai_client
from email_triage.config import load_config
from email_triage.gmail import (
    fetch_messages_batch,
    fetch_unread_ids,
    filter_by_window,
    parse_message,
)
from email_triage.labels import (
    AMBIGUOUS_CATEGORY,
    AMBIGUOUS_LABEL,
    apply_labels,
    ensure_label,
    is_already_triaged,
    list_triage_labels,
)
from email_triage.logging_setup import setup_logging
from email_triage.models import RunStats
from email_triage.notify import send_summary_email
from email_triage.output import (
    print_classification_result,
    print_classification_summary,
    print_progress,
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
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)",
    )
    parser.add_argument(
        "--log-file",
        default=None,
        help="Path to JSON log file",
    )
    parser.add_argument(
        "--no-notify",
        action="store_true",
        help="Skip summary email notification",
    )
    return parser


def main(args: list[str] | None = None) -> None:
    """Run the full email triage pipeline.

    Pipeline: load config -> authenticate -> fetch IDs -> batch fetch ->
    parse -> filter by time window -> classify -> label -> notify.

    Exit codes: 0 = success, 1 = fatal error, 130 = keyboard interrupt.
    """
    parser = _build_parser()
    parsed = parser.parse_args(args)

    # Initialize logging
    setup_logging(parsed.log_level, parsed.log_file)
    logger = logging.getLogger("email_triage")

    start = time.monotonic()
    stats = RunStats()

    try:
        # 1. Load config
        logger.info("Loading config from %s...", parsed.config)
        config = load_config(parsed.config)
        category_names = ", ".join(c.name for c in config.categories)
        logger.info(
            "Loaded %d categories: %s", len(config.categories), category_names,
        )

        # 2. Authenticate
        creds = authenticate(parsed.credentials, parsed.token)
        service = get_gmail_service(creds)
        logger.info("Connected to Gmail.")

        # 3. Calculate time window
        hours = parsed.window_hours or config.fetch.processing_window_hours
        after_dt = datetime.now(timezone.utc) - timedelta(hours=hours)
        after_date = after_dt.strftime("%Y/%m/%d")

        # 4. Effective max emails
        max_emails = parsed.max_emails or config.fetch.max_emails

        # 5. Fetch unread IDs
        logger.info(
            "Fetching unread emails (window: %dh, max: %d)...", hours, max_emails,
        )
        message_ids = fetch_unread_ids(
            service, max_results=max_emails, after_date=after_date,
        )

        # 6. Handle empty result
        if not message_ids:
            logger.info("No unread emails found in the last %d hours.", hours)
            sys.exit(0)

        stats.total_fetched = len(message_ids)
        logger.info(
            "Found %d unread email(s). Fetching metadata...", len(message_ids),
        )

        # 7. Fetch message metadata with progress
        raw_messages, fetch_errors = fetch_messages_batch(
            service,
            message_ids,
            on_progress=lambda cur, tot: print_progress(cur, tot),
        )
        stats.api_calls_gmail += 1  # batch fetch counts as 1 API call

        # 8. Parse and filter
        emails = [
            parse_message(msg, config.fetch.snippet_length) for msg in raw_messages
        ]
        filtered = filter_by_window(emails, raw_messages, hours)

        if not filtered:
            logger.info("No emails to classify after time filter.")
            sys.exit(0)

        # 9. Initialize GenAI client
        client = create_genai_client()
        logger.info("Gemini client ready.")

        # 10. Load label cache and filter already-triaged emails
        label_cache = list_triage_labels(service)
        stats.api_calls_gmail += 1
        triage_label_ids = set(label_cache.values())
        to_classify = []
        skipped = 0
        for email in filtered:
            if is_already_triaged(email, triage_label_ids):
                skipped += 1
            else:
                to_classify.append(email)

        stats.skipped_triaged = skipped

        if not to_classify:
            logger.info(
                "All %d emails already triaged. Nothing to do.", skipped,
            )
            sys.exit(0)

        logger.info(
            "%d emails to classify (%d already triaged, skipped).",
            len(to_classify), skipped,
        )

        # 11. Classify each email with delay between calls
        total = len(to_classify)

        for i, email in enumerate(to_classify):
            logger.info("Classifying %d/%d...", i + 1, total)
            try:
                result = classify_email(
                    client, email, config.categories, config.classification,
                    config.fetch.fields,
                )
                stats.api_calls_llm += 1
                stats.token_usage_prompt += result.prompt_tokens
                stats.token_usage_completion += result.completion_tokens

                if result.is_ambiguous:
                    stats.ambiguous += 1
                else:
                    stats.classified += 1
                    for cat_name, _conf in result.categories:
                        stats.categories[cat_name] = (
                            stats.categories.get(cat_name, 0) + 1
                        )

                # Per-email output in verbose or dry-run mode
                if parsed.verbose or parsed.dry_run:
                    print_classification_result(
                        email.subject, result.categories,
                        result.is_ambiguous, parsed.dry_run,
                    )

                # 12. Apply labels (skip if dry-run)
                if not parsed.dry_run:
                    if result.is_ambiguous:
                        label_id = ensure_label(
                            service, AMBIGUOUS_CATEGORY, label_cache,
                        )
                        apply_labels(service, email.id, [label_id])
                        logger.debug(
                            "Labeled '%s' as %s", email.subject[:50], AMBIGUOUS_LABEL,
                        )
                    else:
                        label_ids = [
                            ensure_label(service, cat_name, label_cache)
                            for cat_name, _conf in result.categories
                        ]
                        apply_labels(service, email.id, label_ids)
                    stats.api_calls_gmail += 1

            except Exception as exc:
                stats.errors += 1
                detail = f"Failed to process '{email.subject[:50]}': {exc}"
                stats.error_details.append(detail[:200])
                logger.error(
                    "Failed to process '%s': %s", email.subject[:50], exc,
                )

            # Rate-limiting delay (skip after last email)
            if i < total - 1:
                time.sleep(4)

        # 13. Record elapsed time
        elapsed = time.monotonic() - start
        stats.elapsed_seconds = elapsed

        # 14. Classification summary (console output for TTY users)
        print_classification_summary(
            stats.classified, stats.ambiguous, stats.skipped_triaged,
            parsed.dry_run, elapsed,
        )

        # 15. Log warnings for errors
        if stats.errors > 0:
            logger.warning(
                "%d email(s) failed to process during this run.", stats.errors,
            )

        # 16. Send summary email (best-effort)
        should_notify = (
            not parsed.no_notify
            and not parsed.dry_run
            and (stats.classified + stats.ambiguous + stats.errors > 0)
        )
        if should_notify:
            try:
                msg_id = send_summary_email(service, stats)
                logger.info("Summary email sent (ID: %s)", msg_id)
            except Exception as exc:
                logger.warning("Failed to send summary email: %s", exc)

        sys.exit(0)

    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
        sys.exit(130)
    except SystemExit:
        # Re-raise SystemExit so it propagates (e.g., from create_genai_client)
        raise
    except Exception as exc:
        logger.exception("Fatal error: %s", exc)
        sys.exit(1)
