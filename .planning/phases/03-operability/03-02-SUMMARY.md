---
phase: 03-operability
plan: 02
subsystem: cli, notifications
tags: [runstats, summary-email, exit-codes, error-resilience, gmail-send, structured-logging]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: "Gmail API wrapper (gmail.py) and auth infrastructure"
  - phase: 02-classification
    provides: "Classifier module (classifier.py) and label management (labels.py)"
  - phase: 03-operability
    provides: "Structured logging (logging_setup.py) and retry wrappers"
provides:
  - "RunStats dataclass for accumulating pipeline statistics"
  - "Summary email notification via Gmail API (HTML + plain text)"
  - "Cron-compatible CLI with exit codes 0/1/130"
  - "Per-email error resilience — batch continues on individual failures"
  - "CLI flags: --log-level, --log-file, --no-notify"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns: [runstats-accumulation, summary-email-multipart, cron-exit-codes, best-effort-notification]

key-files:
  created:
    - src/email_triage/notify.py
    - tests/test_notify.py
    - tests/test_cli_ops.py
  modified:
    - src/email_triage/models.py
    - src/email_triage/cli.py

key-decisions:
  - "Summary email uses get_user_email() to fetch real address from Gmail profile, not 'me' (Pitfall #3)"
  - "Summary email failure is logged as warning, does not change exit code (Pitfall #6)"
  - "No summary email on zero-email runs or dry-run mode"
  - "print_info/print_error replaced by logger.info/logger.error; print_classification_result/summary kept for TTY output"
  - "RunStats fields all have defaults — instantiate at pipeline start, populate incrementally"

patterns-established:
  - "Best-effort notification: wrap send_summary_email in try/except, log warning on failure"
  - "Dual output channels: logger to stderr for machines, output.py to stdout for humans"

requirements-completed: [OPS-01, OPS-03, NOTF-01, NOTF-02]

# Metrics
duration: 4min
completed: 2026-03-09
---

# Phase 3 Plan 2: CLI Ops & Notifications Summary

**RunStats accumulation, HTML+text summary email via Gmail API, cron-compatible exit codes (0/1/130), and per-email error resilience in the CLI pipeline**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-09T09:13:09Z
- **Completed:** 2026-03-09T09:17:00Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- RunStats dataclass accumulates all pipeline metrics (classified, ambiguous, errors, categories, token usage, elapsed time)
- Summary email sent via Gmail API after each run with HTML+text multipart, per-category breakdown, error details, and token usage
- CLI exits cleanly with cron-compatible codes: 0 success, 1 fatal error, 130 keyboard interrupt
- Per-email errors accumulated and reported — individual failures don't crash the batch
- All print_info/print_error/print_success calls replaced with structured logger calls
- New CLI flags: --log-level, --log-file, --no-notify
- 29 new tests (19 notify + 10 cli_ops), 132/134 suite green (2 pre-existing env-related)

## Task Commits

Each task was committed atomically:

1. **Task 1: RunStats model and summary email notification module** - `37bc4d5` (feat)
2. **Task 2: Cron-compatible CLI with logging, stats, error resilience, and summary email** - `aa737f6` (feat)

## Files Created/Modified
- `src/email_triage/models.py` - Added RunStats dataclass with all pipeline statistics fields
- `src/email_triage/notify.py` - Summary email builder (HTML+text) and sender via Gmail API
- `src/email_triage/cli.py` - Refactored for logging, RunStats accumulation, exit codes, summary email
- `tests/test_notify.py` - 19 tests for email builders and sender
- `tests/test_cli_ops.py` - 10 tests for exit codes, error resilience, CLI flags

## Decisions Made
- Summary email uses get_user_email() to fetch real email from Gmail profile, not "me" (per Pitfall #3 in RESEARCH.md)
- Summary email failure is logged as warning, does not change exit code (per Pitfall #6)
- No summary email on zero-email runs or dry-run mode (dry-run should have no side effects beyond LLM calls)
- All print_info/print_error/print_success/print_warn calls in cli.py replaced by logger.info/logger.error/logger.warning
- print_classification_result() and print_classification_summary() kept for user-facing formatted console output
- RunStats fields all have defaults (field(default_factory=...) where needed) so it can be instantiated at pipeline start

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 3 complete: logging, retry, CLI ops, and notifications all wired
- Full pipeline: config -> auth -> fetch -> classify -> label -> notify -> exit
- Ready for milestone verification

## Self-Check: PASSED

All 5 key files verified present. Both task commits (37bc4d5, aa737f6) confirmed in git log.

---
*Phase: 03-operability*
*Completed: 2026-03-09*
