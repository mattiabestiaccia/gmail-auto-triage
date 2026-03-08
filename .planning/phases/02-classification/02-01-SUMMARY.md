---
phase: 02-classification
plan: 01
subsystem: classification
tags: [gemini-flash, google-genai, rapidfuzz, pydantic, structured-output, fuzzy-matching]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: "EmailData model, CategoryConfig, AppConfig, FetchConfig"
provides:
  - "classify_email() -- Gemini Flash classification with structured JSON output"
  - "fuzzy_match_category() -- rapidfuzz-based category name matching"
  - "build_classification_prompt() -- prompt assembly with categories and email fields"
  - "create_genai_client() -- Gemini client with API key from env"
  - "ClassificationResult dataclass -- internal result after filtering"
  - "ClassificationResponse/CategoryClassification Pydantic models -- GenAI response schema"
  - "ClassificationConfig -- confidence_threshold and model settings"
affects: [02-02, 02-03, 03-operability]

# Tech tracking
tech-stack:
  added: [google-genai >=1.66.0, rapidfuzz >=3.14.3]
  patterns: [pydantic-response-schema, fuzzy-category-matching, confidence-threshold-filtering]

key-files:
  created:
    - src/email_triage/classifier.py
    - tests/test_classifier.py
  modified:
    - src/email_triage/models.py
    - src/email_triage/config.py
    - pyproject.toml
    - uv.lock

key-decisions:
  - "rapidfuzz with fuzz.ratio scorer and threshold=70 for fuzzy matching"
  - "Pydantic response_schema for structured JSON output (not manual JSON parsing)"
  - "ClassificationResult as plain dataclass (internal state), ClassificationResponse as Pydantic (GenAI schema)"
  - "Belt-and-suspenders: max_length=2 in schema + explicit prompt instruction for 1-2 categories"
  - "GEMINI_API_KEY with GOOGLE_API_KEY fallback, loaded via python-dotenv"

patterns-established:
  - "Pydantic models for LLM response schema, dataclasses for internal state"
  - "Fuzzy match + confidence filter pipeline: LLM response -> fuzzy_match -> threshold -> ClassificationResult"
  - "Fail-fast client initialization with clear error message for missing API key"

requirements-completed: [CLASS-01, CLASS-02, CLASS-03, CLASS-04, CLASS-05]

# Metrics
duration: 3min
completed: 2026-03-08
---

# Phase 2 Plan 1: Classification Engine Summary

**Gemini Flash classification engine with Pydantic structured output, rapidfuzz category matching, confidence filtering, and ambiguous fallback**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-08T09:10:15Z
- **Completed:** 2026-03-08T09:12:45Z
- **Tasks:** 2 (TDD RED + GREEN)
- **Files modified:** 6

## Accomplishments
- Classification engine with Gemini Flash structured JSON output via Pydantic response_schema
- Fuzzy category matching with rapidfuzz (handles typos, case-insensitive)
- Confidence threshold filtering with ambiguous fallback when all categories below threshold
- 33 new tests covering fuzzy matching, confidence filtering, prompt assembly, config, and mocked API calls

## Task Commits

Each task was committed atomically:

1. **TDD RED: Failing tests** - `179f7b8` (test)
2. **TDD GREEN: Implementation** - `7204b70` (feat)

_Note: No refactor commit needed -- implementation was clean from the start._

## Files Created/Modified
- `src/email_triage/classifier.py` - Classification engine: classify_email, create_genai_client, build_classification_prompt, fuzzy_match_category
- `src/email_triage/models.py` - Added CategoryClassification, ClassificationResponse (Pydantic), ClassificationResult (dataclass)
- `src/email_triage/config.py` - Added ClassificationConfig with confidence_threshold=0.5 and model=gemini-2.5-flash; AppConfig.classification field
- `tests/test_classifier.py` - 33 tests for all classification behaviors
- `pyproject.toml` - Added google-genai and rapidfuzz dependencies
- `uv.lock` - Updated lockfile

## Decisions Made
- Used rapidfuzz with `fuzz.ratio` scorer and score_cutoff=70 for fuzzy matching (per RESEARCH.md recommendation)
- Pydantic models for GenAI response_schema, plain dataclass for internal ClassificationResult (separation of concerns)
- Belt-and-suspenders: `max_length=2` in Pydantic schema AND explicit "1 or 2 categories maximum" in prompt text
- GEMINI_API_KEY as primary env var with GOOGLE_API_KEY fallback, loaded via python-dotenv
- System instruction for classifier: "You are an email classifier. Assign each email to 1-2 categories from the provided list. Be precise with confidence scores."

## Deviations from Plan

None - plan executed exactly as written.

## User Setup Required

**External services require manual configuration.** The Gemini API key is needed for live classification:
- Set `GEMINI_API_KEY` in `.env` file
- Get key at https://aistudio.google.com/apikey

## Next Phase Readiness
- Classification engine complete, ready for integration with Gmail labels (Plan 02-02)
- classify_email returns ClassificationResult that label operations will consume
- All 75 tests pass (33 classifier + 42 existing)

## Self-Check: PASSED

All 5 key files verified present on disk. Both commits (179f7b8, 7204b70) verified in git log.

---
*Phase: 02-classification*
*Completed: 2026-03-08*
