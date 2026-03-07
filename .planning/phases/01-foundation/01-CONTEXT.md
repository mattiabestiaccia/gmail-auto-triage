# Phase 1: Foundation - Context

**Gathered:** 2026-03-07
**Status:** Ready for planning

<domain>

## Phase Boundary

OAuth2 authentication with Gmail, email fetching via Gmail API, YAML config loading and validation, project scaffolding. This is the complete input pipeline for classification — no classification or labeling happens here.

</domain>

<decisions>

## Implementation Decisions

### Config file design
- YAML format, structure at Claude's discretion (flat list vs map-keyed)
- Config file path at Claude's discretion
- No custom prompt template override — prompt is hardcoded (CONF-04 dropped from v1)
- Strict validation: every category must have name + description + at least 1 example, otherwise exit with clear error

### First-run setup experience
- Credentials.json path at Claude's discretion
- First launch: attempt to open browser automatically for OAuth2 flow; if that fails, print the authorization URL as fallback
- Token storage location at Claude's discretion
- Verbose step-by-step guidance messages during first setup (user may return to the project after months)

### Fetch scope and defaults
- Default processing window: 24 hours
- Default email fields sent to LLM: subject + sender + body snippet
- Default body snippet length: 500 characters
- Batch fetching with configurable max emails per run (avoids infinite runs on large inboxes)

### Script output
- Progressive counter during fetch ("Fetched 15/42 emails...")
- Compact summary at end of run (total fetched, errors, elapsed time)
- ANSI colors for info/warning/error, with automatic fallback to plain text when no TTY (cron-safe)
- Error messages include actionable suggestions (e.g., "check credentials", "run with --verbose")

### Claude's Discretion
- YAML config structure (flat list vs map-keyed)
- Config file default path
- credentials.json location and lookup strategy
- OAuth2 token storage location
- Exact progress counter implementation
- Batch size default value

</decisions>

<specifics>

## Specific Ideas

- Step-by-step guidance at first run: the tool is personal and may be picked up again after months — clear instructions matter more than brevity
- Browser-first OAuth2 with link fallback covers both desktop and headless/server scenarios
- Strict config validation ensures fail-fast behavior — no silent misconfiguration

</specifics>

<deferred>

## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-foundation*
*Context gathered: 2026-03-07*
