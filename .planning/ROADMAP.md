# Roadmap: Gmail Auto-Triage

## Overview

Gmail Auto-Triage evolves from a bare project into a fully automated email classification script in 3 phases. Phase 1 establishes the foundation: OAuth2 authentication, Gmail API access, YAML configuration loading and validation. Phase 2 delivers the core value: LLM-based classification and Gmail label application, including idempotency and dry-run mode. Phase 3 makes the pipeline production-ready: summary email notifications, cron-compatible execution, structured logging, rate limiting, and robust error handling. Each phase produces a testable, runnable artifact that builds on the previous one.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Foundation** - OAuth2 auth, Gmail API fetch, YAML config loading and validation, project scaffolding
- [x] **Phase 2: Classification** - LLM-based email classification, Gmail label application, idempotency, dry-run mode
- [ ] **Phase 3: Operability** - Summary notifications, cron wrapper, structured logging, rate limiting, error resilience

## Phase Details

### Phase 1: Foundation
**Goal**: User can authenticate with Gmail, load a validated YAML config, and fetch unread emails — the complete input pipeline for classification
**Depends on**: Nothing (first phase)
**Requirements**: AUTH-01, AUTH-02, AUTH-03, FETCH-01, FETCH-02, FETCH-03, FETCH-04, FETCH-05, CONF-01, CONF-02, CONF-03, CONF-04
**Success Criteria** (what must be TRUE):
  1. Running the script with valid credentials authenticates via OAuth2, and the token persists across subsequent runs without requiring re-authentication
  2. Running the script with an expired token automatically refreshes it without user intervention
  3. Running the script for the first time launches an interactive browser-based OAuth2 authorization flow
  4. The script fetches unread emails from Gmail with pagination, respecting a configurable time window (default 24h), and never marks emails as read, archives, or deletes them
  5. A `categories.yaml` file with categories (name, description, examples) is loaded and validated at startup; malformed config causes an immediate exit with a clear error message
**Plans**: 3 plans

Plans:
- [x] 01-01-PLAN.md — Project scaffolding, data models, and YAML config loading with strict validation
- [x] 01-02-PLAN.md — OAuth2 authentication, token persistence, automatic refresh, and output utilities
- [x] 01-03-PLAN.md — Gmail email fetching with pagination, time window filtering, and CLI integration

### Phase 2: Classification
**Goal**: User's unread emails are classified by an LLM and labeled in Gmail — the core value loop works end-to-end
**Depends on**: Phase 1
**Requirements**: CLASS-01, CLASS-02, CLASS-03, CLASS-04, CLASS-05, LABL-01, LABL-02, LABL-03, LABL-04, OPS-06
**Success Criteria** (what must be TRUE):
  1. Each fetched email is classified into one or more categories by Gemini Flash, using structured JSON output with a confidence score
  2. Emails with LLM confidence below a configurable threshold receive the "ambiguous" fallback label instead of a category label
  3. Gmail labels matching the classification are applied automatically, with auto-creation of missing labels under a configurable namespace prefix (e.g., `AutoTriage/`)
  4. Emails that already bear any triage label are skipped entirely (idempotency) — re-running the script produces no duplicate labels or re-classifications
  5. Running with `--dry-run` classifies emails and prints results without applying any labels in Gmail
**Plans**: 3 plans

Plans:
- [x] 02-01-PLAN.md — Classification engine: Gemini Flash structured output, confidence scoring, fuzzy category matching
- [x] 02-02-PLAN.md — Gmail label management: list, create, apply labels under AutoTriage/ namespace with idempotency
- [ ] 02-03-PLAN.md — CLI pipeline integration: --dry-run flag, classification loop, summary output

### Phase 3: Operability
**Goal**: The script runs unattended via cron with robust error handling, rate limiting, structured logging, and sends a summary email after each run
**Depends on**: Phase 2
**Requirements**: OPS-01, OPS-02, OPS-03, OPS-04, OPS-05, NOTF-01, NOTF-02
**Success Criteria** (what must be TRUE):
  1. The script exits cleanly with code 0 (success) or 1 (failure), produces no interactive prompts, and logs to stdout/stderr — fully cron-compatible
  2. Structured logging with configurable levels outputs to both console and file, including per-email classification results and API call counts
  3. A single email failing to classify or label does not crash the batch — the script continues processing remaining emails and reports failures in the summary
  4. Gmail API 429/503 errors trigger exponential backoff retries; LLM API failures trigger separate retry logic with backoff — both respect configurable limits
  5. After each run, a summary email is sent to the user's inbox containing per-category breakdown, error count, and estimated token usage
**Plans**: TBD

Plans:
- [ ] 03-01: TBD
- [ ] 03-02: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 3/3 | Complete | 2026-03-07 |
| 2. Classification | 3/3 | Complete | 2026-03-08 |
| 3. Operability | 0/2 | Not started | - |
