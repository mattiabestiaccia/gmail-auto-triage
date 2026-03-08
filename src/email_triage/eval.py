"""Classification quality eval pipeline.

Provides create/run/reset commands for a reproducible test set workflow:
  - create: select N read emails, strip AutoTriage labels, save testset.json
  - run: classify test set, show detailed results
  - reset: remove AutoTriage labels from test set (ready for re-run)

Usage:
  uv run email-triage-eval create
  uv run email-triage-eval run [--dry-run]
  uv run email-triage-eval reset
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from email_triage.auth import authenticate, get_gmail_service
from email_triage.classifier import classify_email, create_genai_client
from email_triage.config import load_config
from email_triage.gmail import fetch_message_ids, fetch_messages_batch, parse_message
from email_triage.labels import (
    LABEL_PREFIX,
    apply_labels,
    ensure_label,
    list_triage_labels,
    remove_labels,
)
from email_triage.output import (
    Colors,
    print_error,
    print_info,
    print_success,
)


# ---------------------------------------------------------------------------
# CLI parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="email-triage-eval",
        description="Classification quality eval pipeline.",
    )
    # Shared arguments
    parser.add_argument("--credentials", default="credentials/credentials.json")
    parser.add_argument("--token", default="credentials/token.json")
    parser.add_argument("--config", "-c", default="categories.yaml")
    parser.add_argument("--testset", default="testset.json",
                        help="Path to test set JSON (default: testset.json)")

    sub = parser.add_subparsers(dest="command")

    # create
    create_p = sub.add_parser("create", help="Select emails and save test set")
    create_p.add_argument("--count", type=int, default=20,
                          help="Number of emails to select (default: 20)")
    create_p.add_argument("--query", default=None,
                          help="Custom Gmail query (default: in:inbox -is:unread after:2026/01/01)")

    # run
    run_p = sub.add_parser("run", help="Classify test set emails")
    run_p.add_argument("--dry-run", action="store_true",
                       help="Classify but do not apply labels")

    # reset
    sub.add_parser("reset", help="Remove AutoTriage labels from test set")

    return parser


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def _cmd_create(args) -> None:
    """Select N read emails, strip existing AutoTriage labels, save testset.json."""
    creds = authenticate(args.credentials, args.token)
    service = get_gmail_service(creds)

    # Query: read emails from inbox
    query = args.query or "in:inbox -is:unread after:2026/01/01"
    print_info(f"Fetching up to {args.count} read emails ({query})...")
    message_ids = fetch_message_ids(service, query, max_results=args.count)

    if not message_ids:
        print_info("No matching emails found.")
        return

    # Fetch metadata for preview and label stripping
    raw_messages, errors = fetch_messages_batch(service, message_ids)
    emails = [parse_message(msg) for msg in raw_messages]

    # Strip existing AutoTriage labels
    label_cache = list_triage_labels(service)
    triage_label_ids = set(label_cache.values())
    stripped = 0

    for email in emails:
        matching_ids = [lid for lid in email.label_ids if lid in triage_label_ids]
        if matching_ids:
            remove_labels(service, email.id, matching_ids)
            stripped += 1

    # Save testset.json
    testset = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "query": query,
        "count": len(message_ids),
        "message_ids": message_ids,
    }
    Path(args.testset).write_text(json.dumps(testset, indent=2))

    # Print preview
    print_success(f"Selected {len(message_ids)} emails, stripped {stripped} existing labels.")
    print()
    for i, email in enumerate(emails, 1):
        sender = email.sender[:40]
        subject = email.subject[:50]
        print(f"  {i:2d}. {sender} — {subject}")

    print()
    print_success(f"Test set saved to {args.testset}")


def _cmd_run(args) -> None:
    """Classify all emails in test set, show detailed results."""
    # Load testset
    testset_path = Path(args.testset)
    if not testset_path.exists():
        print_error(f"Test set not found: {args.testset}",
                    suggestion="Run 'email-triage-eval create' first.")
        sys.exit(1)

    testset = json.loads(testset_path.read_text())
    message_ids = testset["message_ids"]

    # Auth & setup
    creds = authenticate(args.credentials, args.token)
    service = get_gmail_service(creds)
    config = load_config(args.config)
    client = create_genai_client()

    # Fetch metadata
    print_info(f"Fetching {len(message_ids)} emails...")
    raw_messages, errors = fetch_messages_batch(service, message_ids)
    emails = [parse_message(msg, config.fetch.snippet_length) for msg in raw_messages]

    # Label cache for apply
    label_cache = list_triage_labels(service)

    # Classify
    start = time.monotonic()
    classified = 0
    ambiguous = 0
    errors_count = 0
    category_dist: dict[str, int] = {}
    total = len(emails)

    print_info(f"Classifying {total} emails...\n")

    for i, email in enumerate(emails):
        print(f"  [{i + 1}/{total}] {email.sender[:30]} — {email.subject[:50]}")
        if email.snippet:
            print(f"         {Colors.info(email.snippet[:80])}")

        try:
            result = classify_email(client, email, config.categories, config.classification)

            if result.is_ambiguous:
                ambiguous += 1
                print(f"         -> {Colors.warn('_Ambiguous')}")
            else:
                classified += 1
                for cat_name, conf in result.categories:
                    category_dist[cat_name] = category_dist.get(cat_name, 0) + 1
                    print(f"         -> {Colors.success(f'{cat_name} ({conf:.2f})')}")

            print(f"         Reasoning: {result.reasoning}")

            # Apply labels unless dry-run
            if not args.dry_run:
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
            print(f"         -> {Colors.error(f'ERROR: {exc}')}")

        print()

        # Rate-limiting delay (skip after last email)
        if i < total - 1:
            time.sleep(4)

    # Summary
    elapsed = time.monotonic() - start
    mode = "(dry-run)" if args.dry_run else "(labeled)"

    print(Colors.bold("--- Eval Summary ---"))
    print(f"  Total:      {total}")
    print(f"  Classified: {classified} {mode}")
    print(f"  Ambiguous:  {ambiguous}")
    if errors_count:
        print(f"  Errors:     {errors_count}")
    print(f"  Elapsed:    {elapsed:.1f}s")

    if category_dist:
        print()
        print(Colors.bold("  Category distribution:"))
        for cat, count in sorted(category_dist.items(), key=lambda x: -x[1]):
            print(f"    {cat}: {count}")


def _cmd_reset(args) -> None:
    """Remove all AutoTriage labels from test set emails."""
    testset_path = Path(args.testset)
    if not testset_path.exists():
        print_error(f"Test set not found: {args.testset}",
                    suggestion="Run 'email-triage-eval create' first.")
        sys.exit(1)

    testset = json.loads(testset_path.read_text())
    message_ids = testset["message_ids"]

    creds = authenticate(args.credentials, args.token)
    service = get_gmail_service(creds)

    # Fetch label cache and message metadata
    label_cache = list_triage_labels(service)
    triage_label_ids = set(label_cache.values())

    raw_messages, errors = fetch_messages_batch(service, message_ids)
    emails = [parse_message(msg) for msg in raw_messages]

    removed = 0
    for email in emails:
        matching_ids = [lid for lid in email.label_ids if lid in triage_label_ids]
        if matching_ids:
            remove_labels(service, email.id, matching_ids)
            removed += 1

    print_success(f"Reset complete: removed labels from {removed}/{len(emails)} emails.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(args: list[str] | None = None) -> None:
    """Parse args and dispatch to the appropriate command."""
    parser = _build_parser()
    parsed = parser.parse_args(args)

    if parsed.command is None:
        parser.print_help()
        sys.exit(1)

    commands = {
        "create": _cmd_create,
        "run": _cmd_run,
        "reset": _cmd_reset,
    }
    commands[parsed.command](parsed)
