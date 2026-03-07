# Requirements: Gmail Auto-Triage

**Defined:** 2026-03-07
**Core Value:** Aprire Gmail e trovare le email gia' organizzate per categoria, senza alcuno sforzo manuale.

## v1 Requirements

Requirements for initial release. Includes all table stakes + differentiators.

### Authentication

- [ ] **AUTH-01**: OAuth2 authentication with token persistence across cron runs
- [ ] **AUTH-02**: Automatic token refresh without user intervention
- [ ] **AUTH-03**: One-time interactive setup for initial OAuth2 authorization

### Email Fetching

- [ ] **FETCH-01**: Fetch unread emails via Gmail API with pagination support
- [ ] **FETCH-02**: Processing window — only process emails from configurable time period (default: 24h)
- [ ] **FETCH-03**: Configurable email fields sent to LLM (subject, sender, body snippet)
- [ ] **FETCH-04**: Configurable body snippet length limit to control token usage
- [ ] **FETCH-05**: Conservative behavior enforced — never mark as read, never archive, never delete

### Configuration

- [x] **CONF-01**: Categories defined in YAML file with name and description
- [x] **CONF-02**: Category examples in config for few-shot LLM prompting
- [x] **CONF-03**: Config validation on startup with clear error messages (fail fast)
- [x] **CONF-04**: Custom LLM prompt template override in config

### Classification

- [ ] **CLASS-01**: LLM-based classification using Gemini Flash with structured JSON output
- [ ] **CLASS-02**: Fallback "ambiguous" label for unclassifiable emails
- [ ] **CLASS-03**: LLM confidence score threshold — below threshold maps to ambiguous
- [ ] **CLASS-04**: Multi-label support (email can receive 1-2 category labels)
- [ ] **CLASS-05**: Thread-aware classification (classify by conversation thread, not individual messages)

### Label Management

- [ ] **LABL-01**: Apply Gmail labels based on classification result
- [ ] **LABL-02**: Auto-create labels in Gmail if they don't exist
- [ ] **LABL-03**: Label namespacing with configurable prefix (e.g., `AutoTriage/`)
- [ ] **LABL-04**: Idempotency — skip emails already bearing any triage label

### Operability

- [ ] **OPS-01**: Cron-compatible execution (clean exit codes, no interactive prompts, stdout/stderr logging)
- [ ] **OPS-02**: Structured logging with configurable levels to file and console
- [ ] **OPS-03**: Graceful per-email error handling — one failure does not crash the batch
- [ ] **OPS-04**: Rate limiting with exponential backoff for Gmail API (429/503)
- [ ] **OPS-05**: Retry logic for LLM API failures with exponential backoff
- [ ] **OPS-06**: Dry-run mode — process and classify without applying labels

### Notification

- [ ] **NOTF-01**: Summary email notification sent to self after each run
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
| AUTH-01 | Phase 1 | Pending |
| AUTH-02 | Phase 1 | Pending |
| AUTH-03 | Phase 1 | Pending |
| FETCH-01 | Phase 1 | Pending |
| FETCH-02 | Phase 1 | Pending |
| FETCH-03 | Phase 1 | Pending |
| FETCH-04 | Phase 1 | Pending |
| FETCH-05 | Phase 1 | Pending |
| CONF-01 | Phase 1 | Complete |
| CONF-02 | Phase 1 | Complete |
| CONF-03 | Phase 1 | Complete |
| CONF-04 | Phase 1 | Complete |
| CLASS-01 | Phase 2 | Pending |
| CLASS-02 | Phase 2 | Pending |
| CLASS-03 | Phase 2 | Pending |
| CLASS-04 | Phase 2 | Pending |
| CLASS-05 | Phase 2 | Pending |
| LABL-01 | Phase 2 | Pending |
| LABL-02 | Phase 2 | Pending |
| LABL-03 | Phase 2 | Pending |
| LABL-04 | Phase 2 | Pending |
| OPS-06 | Phase 2 | Pending |
| OPS-01 | Phase 3 | Pending |
| OPS-02 | Phase 3 | Pending |
| OPS-03 | Phase 3 | Pending |
| OPS-04 | Phase 3 | Pending |
| OPS-05 | Phase 3 | Pending |
| NOTF-01 | Phase 3 | Pending |
| NOTF-02 | Phase 3 | Pending |

**Coverage:**
- v1 requirements: 29 total
- Mapped to phases: 29
- Unmapped: 0

---
*Requirements defined: 2026-03-07*
*Last updated: 2026-03-07 after roadmap creation*
