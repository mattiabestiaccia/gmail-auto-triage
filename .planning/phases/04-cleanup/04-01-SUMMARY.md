---
phase: 04-cleanup
plan: 01
subsystem: classification
tags: [gemini, token-usage, tech-debt, test-isolation]

# Dependency graph
requires:
  - phase: 02-classification
    provides: "classify_email pipeline, ClassificationResult dataclass, labels module"
  - phase: 03-operability
    provides: "RunStats with token_usage fields, send_summary_email"
provides:
  - "Token usage flowing from Gemini response.usage_metadata through ClassificationResult to RunStats and summary email"
  - "AMBIGUOUS_CATEGORY constant in labels.py replacing hardcoded string"
  - "Properly isolated tests for create_genai_client with load_dotenv mock"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "None-safe usage_metadata extraction with fallback to 0"
    - "load_dotenv mock pattern for test isolation"

key-files:
  created: []
  modified:
    - src/email_triage/models.py
    - src/email_triage/classifier.py
    - src/email_triage/cli.py
    - src/email_triage/labels.py
    - src/email_triage/output.py
    - tests/test_classifier.py
    - .planning/REQUIREMENTS.md

key-decisions:
  - "Token fields added as defaults (=0) on ClassificationResult dataclass -- no breaking changes to existing callers"
  - "usage_metadata extraction uses None guards for both the metadata object and individual fields"

patterns-established:
  - "load_dotenv mock: always patch 'email_triage.classifier.load_dotenv' (where imported) not 'dotenv.load_dotenv'"

requirements-completed: [NOTF-02]

# Metrics
duration: 3min
completed: 2026-03-09
---

# Phase 4 Plan 1: Tech Debt Closure Summary

**Token usage extraction from Gemini usage_metadata into summary email, test isolation fixes, and dead code removal**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-09T10:14:47Z
- **Completed:** 2026-03-09T10:17:56Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- Token usage (prompt + completion tokens) now flows from Gemini API response through ClassificationResult to RunStats, enabling real numbers in summary email instead of N/A
- All 136 tests pass including previously failing test_missing_api_key_exits and test_google_api_key_fallback (fixed with load_dotenv mock)
- Hardcoded "_Ambiguous" string in cli.py replaced with AMBIGUOUS_CATEGORY constant from labels.py
- Dead print_warn function removed from output.py
- NOTF-02 (token usage in summary email) marked Complete -- all 29 v1 requirements now satisfied

## Task Commits

Each task was committed atomically:

1. **Task 1: Token usage extraction, AMBIGUOUS_CATEGORY constant, dead code removal** - `0ea2a66` (feat)
2. **Task 2: Fix test isolation and update test mocks** - `724d5b6` (test)

**Plan metadata:** `bdbad30` (docs: complete plan)

## Files Created/Modified
- `src/email_triage/models.py` - Added prompt_tokens and completion_tokens fields to ClassificationResult
- `src/email_triage/classifier.py` - Extract token usage from response.usage_metadata in classify_email()
- `src/email_triage/cli.py` - Accumulate tokens into RunStats + use AMBIGUOUS_CATEGORY constant
- `src/email_triage/labels.py` - Added AMBIGUOUS_CATEGORY constant, derived AMBIGUOUS_LABEL from it
- `src/email_triage/output.py` - Removed unused print_warn function
- `tests/test_classifier.py` - Fixed 3 tests with load_dotenv mock, added 2 token usage tests
- `.planning/REQUIREMENTS.md` - NOTF-02 marked [x] Complete in checkbox and traceability table

## Decisions Made
- Token fields added as defaults (=0) on ClassificationResult dataclass -- no breaking changes, no tuple unpacking needed
- usage_metadata extraction uses None guards for both the metadata object and individual token count fields (or 0 fallback)
- All three create_genai_client tests now mock load_dotenv, including test_gemini_api_key_used which passed by accident before

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All 29 v1 requirements complete (29/29)
- All 136 tests green
- No remaining tech debt items from milestone audit
- Codebase ready for v2 planning if desired

## Self-Check: PASSED

All 8 files verified present. Both commit hashes (0ea2a66, 724d5b6) confirmed in git log.

---
*Phase: 04-cleanup*
*Completed: 2026-03-09*
