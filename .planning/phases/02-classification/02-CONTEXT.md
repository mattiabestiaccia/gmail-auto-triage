# Phase 2: Classification - Context

**Gathered:** 2026-03-07
**Status:** Ready for planning

<domain>

## Phase Boundary

Unread emails are classified by Gemini Flash and labeled in Gmail. Covers: LLM classification with structured JSON output, confidence scoring, multi-label support, Gmail label application with auto-creation, idempotency (skip already-triaged), and dry-run mode. Does NOT include: error resilience, retry logic, logging, cron support, or notifications (Phase 3).

</domain>

<decisions>

## Implementation Decisions

### Classification granularity
- Each message is classified individually — no thread grouping before LLM call
- Every unread message goes to the LLM independently, regardless of thread membership
- Claude's discretion on how much thread context (if any) to include in the prompt for a single message

### Multi-label behavior
- LLM decides freely whether to return 1 or 2 labels per email based on content
- Threads that evolve across topics naturally get multi-label through per-message classification
- If LLM returns a category name not in `categories.yaml`, apply fuzzy match to existing categories; if no match, treat as "ambiguous"

### Confidence threshold
- Default threshold: 0.5 (50%) — configurable in `categories.yaml`
- Labels below threshold are discarded (not kept as secondary)
- If both labels are below threshold, email receives "ambiguous" label
- Conservative default: better to flag as ambiguous than misclassify

### Idempotency
- Check at message level, not thread level
- If a message already has any `AutoTriage/*` label, skip it entirely
- New messages in an already-triaged thread are still classified independently

### Label namespace
- Prefix: `AutoTriage/` — hardcoded, not configurable
- Gmail renders this as a nested folder in the sidebar
- Ambiguous label: `AutoTriage/_Ambiguous` — underscore prefix sorts it to the top alphabetically
- If a label already exists in Gmail (e.g., manually created), reuse it without error

### Dry-run output
- `--dry-run` performs real LLM classification but does not apply labels in Gmail
- Summary counts always shown at end of run (both dry-run and real): classified, ambiguous, skipped
- Claude's discretion: output format (table/JSON/text), whether to show skipped emails, mock LLM option

### Claude's Discretion
- Thread context assembly strategy for the LLM prompt (how much of the thread to send per message)
- Dry-run output format and verbosity level
- Whether to offer a `--no-llm` mock mode for testing without API calls
- Fuzzy matching algorithm for category name mismatches
- Structured JSON output schema design for Gemini Flash

</decisions>

<specifics>

## Specific Ideas

- Confidence threshold 0.5 chosen deliberately as "safe start" — user expects to tune it down after seeing real results
- `AutoTriage/_Ambiguous` naming convention mirrors how Gmail power users organize labels (underscore for pinning)
- Per-message classification keeps the system simple and granular — avoids complex thread aggregation logic

</specifics>

<deferred>

## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 02-classification*
*Context gathered: 2026-03-07*
