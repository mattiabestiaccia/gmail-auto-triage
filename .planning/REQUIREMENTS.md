# Requirements: Gmail Auto-Triage

**Defined:** 2026-03-07
**Core Value:** Aprire Gmail e trovare le email gia' organizzate per categoria, senza alcuno sforzo manuale.

## v1 Requirements

Requirements for initial release. Includes all table stakes + differentiators.

### Authentication

- [x] **AUTH-01**: OAuth2 authentication with token persistence across cron runs
- [x] **AUTH-02**: Automatic token refresh without user intervention
- [x] **AUTH-03**: One-time interactive setup for initial OAuth2 authorization

### Email Fetching

- [x] **FETCH-01**: Fetch unread emails via Gmail API with pagination support
- [x] **FETCH-02**: Processing window — only process emails from configurable time period (default: 24h)
- [x] **FETCH-03**: Configurable email fields sent to LLM (subject, sender, body snippet)
- [x] **FETCH-04**: Configurable body snippet length limit to control token usage
- [x] **FETCH-05**: Conservative behavior enforced — never mark as read, never archive, never delete

### Configuration

- [x] **CONF-01**: Categories defined in YAML file with name and description
- [x] **CONF-02**: Category examples in config for few-shot LLM prompting
- [x] **CONF-03**: Config validation on startup with clear error messages (fail fast)
- [x] **CONF-04**: Custom LLM prompt template override in config

### Classification

- [x] **CLASS-01**: LLM-based classification using Gemini Flash with structured JSON output
- [x] **CLASS-02**: Fallback "ambiguous" label for unclassifiable emails
- [x] **CLASS-03**: LLM confidence score threshold — below threshold maps to ambiguous
- [x] **CLASS-04**: Multi-label support (email can receive 1-2 category labels)
- [x] **CLASS-05**: Thread-aware classification (classify by conversation thread, not individual messages)

### Label Management

- [x] **LABL-01**: Apply Gmail labels based on classification result
- [x] **LABL-02**: Auto-create labels in Gmail if they don't exist
- [x] **LABL-03**: Label namespacing with configurable prefix (e.g., `AutoTriage/`)
- [x] **LABL-04**: Idempotency — skip emails already bearing any triage label

### Operability

- [x] **OPS-01**: Cron-compatible execution (clean exit codes, no interactive prompts, stdout/stderr logging)
- [x] **OPS-02**: Structured logging with configurable levels to file and console
- [x] **OPS-03**: Graceful per-email error handling — one failure does not crash the batch
- [x] **OPS-04**: Rate limiting with exponential backoff for Gmail API (429/503)
- [x] **OPS-05**: Retry logic for LLM API failures with exponential backoff
- [x] **OPS-06**: Dry-run mode — process and classify without applying labels

### Notification

- [x] **NOTF-01**: Summary email notification sent to self after each run
- [ ] **NOTF-02**: Statistics in summary email (per-category breakdown, error count, token usage estimate)

## v2 Requirements

Deferred to future release. Not in current roadmap.

### Classification Enhancements

- **CLASS-06**: Learning from user corrections (feedback loop for prompt tuning)
- **CLASS-07**: Attachment-aware classification (note attachment presence/type without parsing content)

### Operability Enhancements

- **OPS-07**: Systemd timer as alternative to cron
- **OPS-08**: Log rotation for long-running deployments

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Auto-archive or auto-delete | Destructive actions on email are irreversible — tool categorizes, user decides |
| Mark as read | Unread status is a personal signal — tool must not alter it |
| Web UI or dashboard | Out of scope — Gmail itself is the UI, email log for status |
| Multi-user support | Personal tool — single user, single Gmail account |
| Retroactive re-categorization | Category changes apply only to future emails — avoids confusion and quota waste |
| Custom actions per category (move, forward, reply) | Scope creep — labels only, user can set Gmail filters for actions |
| Training / feedback loop | Enormous complexity for personal use — tune YAML config manually (deferred to v2) |
| Attachment content analysis | Security risks, processing time, token cost — classify on text only |
| Priority scoring / ranking | Subjective and error-prone — categorize by type, user judges priority |
| Real-time push/webhook processing | Requires public endpoint, Pub/Sub — cron polling is sufficient |
| Local database for state | Gmail labels are the sole state mechanism — no sync complexity |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| AUTH-01 | Phase 1 | Complete |
| AUTH-02 | Phase 1 | Complete |
| AUTH-03 | Phase 1 | Complete |
| FETCH-01 | Phase 1 | Complete |
| FETCH-02 | Phase 1 | Complete |
| FETCH-03 | Phase 1 | Complete |
| FETCH-04 | Phase 1 | Complete |
| FETCH-05 | Phase 1 | Complete |
| CONF-01 | Phase 1 | Complete |
| CONF-02 | Phase 1 | Complete |
| CONF-03 | Phase 1 | Complete |
| CONF-04 | Phase 1 | Complete |
| CLASS-01 | Phase 2 | Complete |
| CLASS-02 | Phase 2 | Complete |
| CLASS-03 | Phase 2 | Complete |
| CLASS-04 | Phase 2 | Complete |
| CLASS-05 | Phase 2 | Complete |
| LABL-01 | Phase 2 | Complete |
| LABL-02 | Phase 2 | Complete |
| LABL-03 | Phase 2 | Complete |
| LABL-04 | Phase 2 | Complete |
| OPS-06 | Phase 2 | Complete |
| OPS-01 | Phase 3 | Complete |
| OPS-02 | Phase 3 | Complete |
| OPS-03 | Phase 3 | Complete |
| OPS-04 | Phase 3 | Complete |
| OPS-05 | Phase 3 | Complete |
| NOTF-01 | Phase 3 | Complete |
| NOTF-02 | Phase 4 | Pending |

**Coverage:**
- v1 requirements: 29 total
- Mapped to phases: 29
- Unmapped: 0

---
*Requirements defined: 2026-03-07*
*Last updated: 2026-03-09 after milestone audit gap closure planning*
