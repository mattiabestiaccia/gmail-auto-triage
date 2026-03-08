# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-07)

**Core value:** Aprire Gmail e trovare le email gia' organizzate per categoria, senza alcuno sforzo manuale.
**Current focus:** Phase 2 - Classification

## Current Position

Phase: 2 of 3 (Classification) — IN PROGRESS
Plan: 3 of 3 in current phase
Status: All Plans Complete — Awaiting Verification
Last activity: 2026-03-08 — Completed 02-03-PLAN.md (CLI pipeline with --dry-run)

Progress: [████████░░] 75%

## Performance Metrics

**Velocity:**
- Total plans completed: 6
- Average duration: 3 min
- Total execution time: 0.32 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1. Foundation | 3/3 | 11 min | 4 min |
| 2. Classification | 3/3 | 8 min | 3 min |
| 3. Operability | 0/2 | - | - |

**Recent Trend:**
- Last 5 plans: 5min, 3min, 3min, 2min, 3min
- Trend: improving

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap]: 3-phase structure derived from requirement dependencies (auth -> fetch -> classify -> label -> notify -> automate)
- [Roadmap]: OPS-06 (dry-run) assigned to Phase 2 (Classification) because it validates classification without labels — a Phase 2 testing need
- [01-01]: Python 3.11 pinned (requires-python >= 3.11) for broad compatibility
- [01-01]: EmailData as plain dataclass (not pydantic) since it represents API response data, not validated config
- [01-01]: CONF-04 not implemented (no prompt template override) per user decision
- [01-02]: gmail.modify single scope from the start (avoids re-authorization when labeling is added in Phase 2)
- [01-02]: Token saved with 0o600 permissions for security (Pitfall #6)
- [01-02]: Errors/warnings to stderr, info/success to stdout (keeps stdout clean for piping)
- [01-03]: Batch size 100 per BatchHttpRequest (practical Gmail limit)
- [01-03]: Belt-and-suspenders time filtering: after: query pre-filter + internalDate code-side precision
- [01-03]: gmail.py is provably read-only (AST-verified test enforces FETCH-05)
- [02-02]: list_triage_labels excludes parent 'AutoTriage' label — only 'AutoTriage/*' children in mapping
- [02-02]: ensure_label re-fetches full label list on 409 Conflict to recover gracefully
- [02-02]: Cache dict mutated in place — caller keeps reference without reassignment
- [02-01]: rapidfuzz with fuzz.ratio scorer and threshold=70 for fuzzy category matching
- [02-01]: Pydantic models for GenAI response_schema, plain dataclass for internal ClassificationResult
- [02-01]: Belt-and-suspenders: max_length=2 in Pydantic schema + explicit prompt instruction for 1-2 categories
- [02-01]: GEMINI_API_KEY with GOOGLE_API_KEY fallback, loaded via python-dotenv
- [02-03]: --dry-run performs real LLM classification but skips apply_labels() calls
- [02-03]: 4-second delay between LLM calls for Gemini Flash free tier rate limiting
- [02-03]: Per-email error handling — one failure doesn't crash the batch

### Pending Todos

None yet.

### Blockers/Concerns

- [Phase 1]: OAuth2 consent screen must be published (not "Testing") before cron deployment — refresh token expires after 7 days in Testing mode (Pitfall #1)
- [Phase 1]: MIME parsing complexity — use subject + sender + snippet only, avoid full body parsing (Pitfall #4)
- [Phase 2]: Gemini Flash SDK version and free tier limits need live verification before implementation

## Session Continuity

Last session: 2026-03-08
Stopped at: Completed 02-03-PLAN.md (CLI pipeline with --dry-run)
Resume file: .planning/phases/02-classification/02-03-SUMMARY.md
