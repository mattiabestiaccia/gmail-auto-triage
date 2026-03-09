---
phase: 03-operability
plan: 01
subsystem: logging, resilience
tags: [tenacity, python-json-logger, retry, backoff, structured-logging]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: "Gmail API wrapper (gmail.py) and auth infrastructure"
  - phase: 02-classification
    provides: "Classifier module (classifier.py) and label management (labels.py)"
provides:
  - "setup_logging() with dual handlers (console stderr + JSON file)"
  - "gmail_retry decorator for Gmail API calls (429/5xx, 5 attempts, exponential backoff)"
  - "llm_retry decorator for LLM calls (connection errors, 3 attempts)"
  - "_execute_with_retry helper for wrapping .execute() calls"
  - "_is_retryable_http_error predicate for Gmail error classification"
affects: [03-operability]

# Tech tracking
tech-stack:
  added: [python-json-logger, tenacity]
  patterns: [dual-handler-logging, retry-with-predicate, retry-wrapper-function]

key-files:
  created:
    - src/email_triage/logging_setup.py
    - tests/test_logging_setup.py
    - tests/test_retry.py
  modified:
    - src/email_triage/gmail.py
    - src/email_triage/classifier.py
    - src/email_triage/labels.py
    - pyproject.toml
    - uv.lock

key-decisions:
  - "gmail_retry and _execute_with_retry defined in gmail.py, imported by labels.py — avoids duplication without circular imports"
  - "llm_retry only retries ConnectionError/TimeoutError/OSError — google-genai SDK already retries 429/503 internally"
  - "Auth errors (401/403) and validation errors (400) are explicitly excluded from retry via predicate"
  - "Console handler on stderr for cron compatibility (OPS-01)"

patterns-established:
  - "Retry wrapper pattern: define predicate + decorator at module level, wrap execute calls via helper function"
  - "Dual-handler logging: setup_logging() returns configured logger, call once at startup"

requirements-completed: [OPS-02, OPS-04, OPS-05]

# Metrics
duration: 9min
completed: 2026-03-09
---

# Phase 3 Plan 1: Logging & Retry Summary

**Structured logging with dual handlers (stderr + JSON file) and tenacity retry wrappers for all external API calls (Gmail 429/5xx, LLM connection errors)**

## Performance

- **Duration:** 9 min
- **Started:** 2026-03-09T09:00:02Z
- **Completed:** 2026-03-09T09:10:01Z
- **Tasks:** 2
- **Files modified:** 9

## Accomplishments
- Structured logging module with configurable level, stderr console output, and optional JSON file handler
- Gmail API calls (fetch, batch, labels) retry on 429/500/502/503/504 with exponential backoff (5 attempts, 2-60s)
- LLM generate_content calls have outer retry for connection/timeout errors (3 attempts, 4-30s) — avoids double retry with SDK
- Auth errors (401/403) and validation errors (400) are never retried — verified by predicate tests
- 20 new tests (6 logging + 14 retry), 103/105 total suite green (2 pre-existing env-related failures)

## Task Commits

Each task was committed atomically:

1. **Task 1: Structured logging module with dual handlers** - `cc9642f` (feat)
2. **Task 2: Tenacity retry wrappers for Gmail API and LLM calls** - `abcab06` (feat)

## Files Created/Modified
- `src/email_triage/logging_setup.py` - setup_logging() with console stderr + optional JSON file handler
- `tests/test_logging_setup.py` - 6 tests for logging configuration
- `tests/test_retry.py` - 14 tests for retry predicate and decorator behavior
- `src/email_triage/gmail.py` - Added gmail_retry decorator, _is_retryable_http_error predicate, _execute_with_retry helper
- `src/email_triage/classifier.py` - Added llm_retry decorator and _generate_content_with_retry wrapper
- `src/email_triage/labels.py` - All .execute() calls wrapped with _execute_with_retry from gmail.py
- `pyproject.toml` - Added python-json-logger dependency
- `uv.lock` - Updated lockfile

## Decisions Made
- gmail_retry and _execute_with_retry defined in gmail.py and imported by labels.py to avoid duplication without circular imports
- llm_retry only retries ConnectionError/TimeoutError/OSError (3 attempts) since google-genai SDK already handles 429/503 internally
- Auth errors (401/403) and validation errors (400) explicitly excluded from retry via _is_retryable_http_error predicate
- Console handler outputs to stderr (not stdout) for cron compatibility per OPS-01

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Logging infrastructure ready for integration into CLI pipeline (__main__.py)
- Retry wrappers active on all external API calls
- Ready for Plan 02 (CLI operations and notifications)

## Self-Check: PASSED

All 7 key files verified present. Both task commits (cc9642f, abcab06) confirmed in git log.

---
*Phase: 03-operability*
*Completed: 2026-03-09*
