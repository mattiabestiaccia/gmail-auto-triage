# Feature Landscape

**Domain:** Email auto-triage / LLM-based Gmail classification (personal tool)
**Researched:** 2026-03-07
**Confidence:** MEDIUM (based on training data, domain well-known; no live web verification available)

## Table Stakes

Features users expect. Missing = product feels broken.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Fetch unread emails via Gmail API | Core function -- nothing works without it | Low | Use `messages.list` with `q=is:unread` plus `messages.get` for content. Batch API recommended for efficiency. |
| LLM-based classification of each email | Core value proposition -- the whole point of the tool | Medium | Send subject + sender + body snippet to LLM, get category back. Structured output (JSON mode) preferred over free-text parsing. |
| YAML config for categories | Stated requirement, enables customization without code changes | Low | Each category: name, description, optional keywords/examples. Description feeds the LLM prompt. |
| Apply Gmail labels based on classification | The visible output -- user sees organized inbox | Low | Use `messages.modify` to add label IDs. Create labels automatically if they don't exist (`labels.create`). |
| Idempotency -- skip already-labeled emails | Without this, re-runs waste API calls and LLM tokens, may cause label conflicts | Medium | Check if email already has any triage label before processing. Gmail labels are the single source of truth (no local DB needed). |
| Fallback "ambiguous" label | Emails that don't fit any category must not be silently dropped | Low | Apply a dedicated label like `auto-triage/ambiguous` when LLM confidence is low or category is unclear. |
| Conservative behavior (read-only except labels) | Stated constraint -- never mark as read, never archive, never delete | Low | Enforce at code level: only call `messages.modify` with `addLabelIds`, never `removeLabelIds` for system labels like UNREAD/INBOX. |
| Email log notification | Stated requirement -- user needs to know what happened | Medium | Send summary email to self after each run: timestamp, emails processed, categories assigned, errors. Use Gmail API `messages.send` or SMTP. |
| Cron-compatible execution | Must run unattended on schedule | Low | Clean exit codes (0 = success, 1 = error), no interactive prompts, stdout/stderr logging, handle token refresh silently. |
| OAuth2 authentication with token persistence | Gmail API requires OAuth2; tokens must survive between cron runs | Medium | Store refresh token securely on disk. Handle token expiry gracefully -- auto-refresh without user intervention. Initial setup is interactive (one-time). |
| Rate limiting and API quota awareness | Gmail API has daily quotas (250 units/sec, 1B units/day for free tier). Hitting limits = broken tool. | Medium | Implement exponential backoff on 429/503 errors. Batch requests where possible. Track usage if processing large volumes. |
| Graceful error handling per email | One bad email (encoding issues, huge attachment) must not crash the entire run | Medium | Try/catch per email. Log the error, apply an "error" label or skip, continue with next. Never leave the run in an inconsistent state. |

## Differentiators

Features that set product apart. Not expected, but valued.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| LLM confidence score threshold | Avoid miscategorization -- only label when confident | Low | Ask LLM to return confidence (0-1). Below threshold -> "ambiguous" label. Prevents noisy wrong labels that erode trust. |
| Multi-label support | Some emails genuinely fit multiple categories (e.g., "receipt" + "work") | Low | Allow LLM to return 1-2 categories. Apply all matching labels. Config option to enable/disable. |
| Dry-run mode | Debug and tune categories without touching Gmail | Low | Process emails, print what would be labeled, but don't call `messages.modify`. Essential for initial setup and category tuning. |
| Category examples in config | Improve LLM accuracy with few-shot examples per category | Low | In YAML: each category can have 2-3 example subject/sender pairs. Fed into prompt as examples. Significant accuracy improvement for edge cases. |
| Configurable email fields for classification | Control what the LLM sees (subject only, subject+sender, subject+sender+body snippet) | Low | Privacy-conscious users may want to send only subject+sender. Also reduces token usage. Config option for which fields to include. |
| Body snippet length limit | Control token usage and cost | Low | Configurable max characters of body to send to LLM (e.g., first 500 chars). Prevents huge emails from consuming excessive tokens. |
| Processing window (time-based filter) | Don't re-scan the entire inbox history on first run | Low | Config option: only process emails from last N hours/days. Prevents first run from processing thousands of old emails. Default: 24h. |
| Structured logging with levels | Debuggability for cron jobs where you can't see stdout | Medium | Log to file with timestamps, log levels (DEBUG/INFO/WARNING/ERROR). Configurable verbosity. Rotation for long-running deployments. |
| Label hierarchy / namespacing | Keep triage labels organized, separate from manual labels | Low | Prefix all auto-triage labels: `auto-triage/work`, `auto-triage/receipts`. Avoids conflicts with user's existing labels. |
| Statistics in log email | Know how the tool is performing over time | Low | Include in notification: total processed, per-category breakdown, error count, LLM token usage estimate. |
| Config validation on startup | Fail fast with clear message if YAML is malformed or categories are missing | Low | Validate YAML schema, check required fields, verify category names are valid Gmail label names. Better than cryptic runtime errors. |
| Custom LLM prompt template | Power users can tune the classification prompt | Medium | Default prompt works out of the box, but config allows overriding the system prompt or classification prompt template. |
| Retry logic for LLM API failures | LLM APIs have transient failures; don't lose progress | Medium | Exponential backoff for LLM calls. Configurable max retries (default: 3). After max retries, label as "error" and continue. |
| Thread-aware classification | Classify by conversation thread, not individual messages | Medium | Gmail threads group related messages. Classifying the thread (using first message or latest) avoids re-classifying every reply differently. Uses `threads.list` instead of `messages.list`. |

## Anti-Features

Features to explicitly NOT build.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Auto-archive or auto-delete | Violates core safety constraint. Destructive actions on email are irreversible and dangerous for a personal tool. User explicitly scoped this out. | Only apply labels. User decides what to do with categorized email. |
| Mark as read | Changes user's workflow -- unread status is a personal signal. The tool categorizes, it doesn't manage attention. | Leave read/unread status entirely untouched. |
| Web UI or dashboard | Out of scope. Adds massive complexity (auth, hosting, frontend) for a personal script. | Use email log notification for status. Gmail itself is the UI. |
| Multi-user support | Personal tool. Multi-user adds auth complexity, data isolation, quota management. | Single-user, single Gmail account, single config. |
| Retroactive re-categorization | When categories change, re-processing old emails causes confusion (labels shift under user's feet), wastes API/LLM quota, and the user has likely already triaged old email. | New categories apply only to future emails. Already-labeled emails are skipped (idempotency). |
| Custom actions per category (move, forward, reply) | Scope creep. Each action type needs its own error handling, undo mechanism, and safety considerations. Turns a simple classifier into a complex automation engine. | Labels only. User can set up Gmail filters for actions on specific labels if desired. |
| Training / feedback loop | Learning from user corrections sounds great but adds enormous complexity: data storage, model fine-tuning or prompt evolution, regression handling. Overkill for personal use. | Tune categories and examples in YAML config manually. User knows their own email. |
| Attachment analysis | Parsing attachments (PDFs, images) adds dependencies, security risks, processing time, and token cost. Subject + sender + body snippet is sufficient for triage. | Classify based on text content only. Attachment presence can be noted as a field but content is not analyzed. |
| Priority scoring / ranking | Subjective and error-prone. What's "urgent" varies by context the LLM can't fully understand. Creates false sense of reliability. | Categorize by type (work, personal, receipts, newsletters). Priority is the user's judgment call. |
| Real-time processing (push/webhook) | Gmail push notifications require a public endpoint, domain verification, Pub/Sub setup. Massive infrastructure overhead for a cron script. | Cron-based polling at configurable intervals (e.g., every 30 min). Good enough for triage that doesn't need sub-minute latency. |
| Local database for state | Adds sync complexity, migration burden, backup concerns. Gmail labels already provide persistent state. | Use Gmail labels as the sole state mechanism. "Has triage label?" = "Already processed." |

## Feature Dependencies

```
OAuth2 Auth Setup ─────────────────────────────────────┐
                                                        v
YAML Config Loading ──> Config Validation ──> LLM Prompt Construction
                                                        │
                                                        v
Gmail API: Fetch Unread ──> Idempotency Check ──> LLM Classification
                            (skip if labeled)          │
                                                        v
                                              Apply Gmail Labels
                                                        │
                                                        v
                                              Email Log Notification
                                                        │
                                                        v
                                              Exit with status code
```

Key dependency chains:

1. **Auth must come first**: Nothing works without OAuth2 tokens. Initial interactive setup is a prerequisite for all cron runs.
2. **Config before classification**: Categories must be loaded and validated before emails can be classified.
3. **Fetch before classify**: Emails must be retrieved and filtered (idempotency) before sending to LLM.
4. **Classify before label**: LLM response must be parsed and validated before applying labels.
5. **Everything before notification**: Log email summarizes the entire run, so it's the last step.
6. **Dry-run mode**: Cuts the chain after classification -- skips label application and (optionally) notification.

## MVP Recommendation

**Prioritize (Phase 1 - Core Loop):**

1. **OAuth2 auth with token persistence** -- gate for everything else
2. **Fetch unread emails via Gmail API** -- core input
3. **YAML config for categories** -- core configuration
4. **LLM classification** with structured output -- core logic
5. **Apply Gmail labels** with auto-creation -- core output
6. **Idempotency via label check** -- prevents re-processing
7. **Fallback "ambiguous" label** -- handles edge cases
8. **Per-email error handling** -- resilience
9. **Conservative behavior enforcement** -- safety constraint

**Prioritize (Phase 2 - Operability):**

1. **Email log notification** -- stated requirement, important for unattended operation
2. **Structured logging** -- debuggability for cron
3. **Config validation** -- fail-fast on bad config
4. **Dry-run mode** -- essential for tuning categories
5. **Processing window** -- prevents first-run explosion
6. **Rate limiting / backoff** -- prevents quota exhaustion
7. **Label namespacing** -- organization

**Defer:**

- **Multi-label support**: Add after single-label works well. Low complexity but adds classification ambiguity.
- **Confidence thresholds**: Add after observing real-world "ambiguous" rate. Needs empirical tuning.
- **Thread-aware classification**: Add after per-message works. Medium complexity, may not be needed if subject+sender is sufficient.
- **Custom LLM prompt template**: Add only if default prompt proves insufficient. Power-user feature.
- **Category examples in config**: Add when accuracy needs improvement. Low effort, high impact, but not needed for initial validation.

## Notes on Confidence

| Area | Confidence | Notes |
|------|------------|-------|
| Table stakes features | HIGH | Well-established patterns from Gmail API, email automation, and LLM classification domains |
| Anti-features | HIGH | Clearly defined in PROJECT.md constraints + standard safety practices for email tools |
| Differentiators | MEDIUM | Based on common patterns in email tools and LLM application best practices. No live competitor analysis performed. |
| Feature dependencies | HIGH | Follows from logical data flow -- minimal ambiguity |
| Complexity estimates | MEDIUM | Based on general development experience. Actual complexity depends on chosen stack (e.g., Gmail API client library quality). |

## Sources

- PROJECT.md constraints and requirements (primary source for scope)
- Gmail API documentation patterns (training data, well-established API -- HIGH confidence)
- LLM structured output patterns for classification tasks (training data -- HIGH confidence)
- Email automation tool patterns (SaneBox, Gmail filters, Mailstrom, Clean Email feature sets -- training data, MEDIUM confidence)
- OAuth2 for Google APIs patterns (training data, well-documented -- HIGH confidence)
