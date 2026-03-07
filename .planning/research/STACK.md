# Technology Stack

**Project:** Gmail Auto-Triage
**Researched:** 2026-03-07
**Overall confidence:** MEDIUM (all recommendations based on training data — no web search or Context7 available during research; versions need validation)

## Recommended Stack

### Runtime

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Python | >= 3.11 | Runtime | De facto for scripting/automation; Google SDKs are Python-first; f-strings, tomllib, typing improvements. 3.11+ for performance (10-60% faster than 3.10). | HIGH |
| uv | latest | Package manager | Project convention (see CLAUDE.md). Manages venv + deps + lockfile in one tool. `uv run` for cron execution without manual venv activation. | HIGH |

### Gmail API Access

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| google-api-python-client | ~2.x | Gmail API v1 client | Official Google SDK. Covers all Gmail operations (list, get, modify labels). Well-maintained, huge community. No viable alternative for Gmail API. | HIGH |
| google-auth-oauthlib | ~1.x | OAuth2 flow | Official companion for OAuth2 consent flow. Handles token refresh, credential persistence. Required for Gmail API with user data scopes. | HIGH |
| google-auth-httplib2 | ~0.2.x | HTTP transport auth | Bridges google-auth credentials with httplib2 transport used by google-api-python-client. Required dependency. | HIGH |

**Why not alternatives:**
- `simplegmail`: Thin wrapper around the same Google SDK. Adds abstraction but hides control we need (label management, batch operations). Not worth the dependency for a focused script.
- `imaplib` (stdlib): Gmail IMAP is being deprecated/restricted. OAuth2 with IMAP is painful. No label management — only folders. Wrong abstraction.
- `nylas`, `mailgun`: Third-party email APIs. Add cost, latency, and a middleman. Overkill for single-user Gmail access.

### LLM for Classification

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| google-generativeai | ~0.8.x | Gemini API client | Official Python SDK for Gemini models. Direct access to Gemini 2.0 Flash. | MEDIUM |
| Model: Gemini 2.0 Flash | — | Email classification | See detailed rationale below. | MEDIUM |

**Gemini 2.0 Flash rationale:**

1. **Free tier**: As of early 2025, Gemini API offers a generous free tier (15 RPM, 1M tokens/day on Flash). For a personal cron job processing ~50-200 emails/day, this is effectively free forever. This is the single most important factor given the budget constraint.

2. **Speed**: Flash models are optimized for low latency. Email classification is a simple structured-output task — Flash handles it in <1s per email.

3. **Quality**: For a classification task with well-defined categories (not open-ended generation), Flash-tier models are more than sufficient. This is pattern matching, not creative writing.

4. **Structured output**: Gemini API supports JSON mode / response schemas, which simplifies parsing the classification result.

**LLM alternatives considered:**

| Model | Free Tier | Speed | Quality for Classification | Why Not |
|-------|-----------|-------|---------------------------|---------|
| Gemini 2.0 Flash | Very generous (1M tokens/day free) | Very fast | Excellent | **RECOMMENDED** |
| GPT-4o-mini | Limited free credits, then ~$0.15/1M input | Fast | Excellent | No sustainable free tier; requires OpenAI account + billing |
| Claude 3.5 Haiku | No free API tier | Fast | Excellent | Costs money; no free tier for API usage |
| Llama 3 (local) | Free (local) | Depends on hardware | Good | Requires GPU or slow on CPU; complex setup; overkill |
| Mistral Small | Limited free tier | Fast | Good | Smaller free tier than Gemini |

**Verdict**: Gemini 2.0 Flash wins on the constraint that matters most: **free or near-free operation for a personal tool**. The free tier is generous enough that a cron job will never hit limits.

> **VALIDATION NEEDED**: Verify current Gemini free tier limits at https://ai.google.dev/pricing — these may have changed since training cutoff. The `google-generativeai` package version should be checked on PyPI.

### Configuration

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| PyYAML | ~6.x | YAML config parsing | Mature, stable, widely used. Categories config is a natural fit for YAML (readable, hierarchical). | HIGH |

**Why YAML over alternatives:**
- **TOML**: Good for flat config but awkward for nested category definitions with descriptions/examples. YAML handles hierarchical data more naturally.
- **JSON**: No comments. Users need to edit this file — comments are essential for documenting categories.
- **Python dict**: Mixing config with code. Harder to edit for non-developers (even though this is a personal tool, separation is cleaner).

### Logging and Reporting

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| logging (stdlib) | — | Script logging | Python stdlib. Sufficient for cron job logging. File + console handlers. | HIGH |
| email.mime (stdlib) | — | Summary email composition | Stdlib. The script sends a log/summary email via Gmail API — no need for external email libraries. | HIGH |

### Scheduling

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| cron (system) | — | Periodic execution | System cron is the right tool for "run this script every N hours". Zero overhead, zero dependencies, battle-tested. | HIGH |

**Why not alternatives:**
- `schedule` (Python lib): Requires a long-running Python process. Wastes memory, can crash silently, needs process supervision (systemd). Cron is simpler for periodic batch jobs.
- `APScheduler`: Same issue — long-running process. Good for app-embedded scheduling, overkill for a standalone script.
- `systemd timer`: Viable alternative to cron with better logging. Slightly more complex to configure. Fine if user prefers it, but cron is the simpler default.
- `celery` / `dramatiq`: Task queues for distributed systems. Absurdly overkill for a single-user script.

### Supporting Libraries

| Library | Version | Purpose | When to Use | Confidence |
|---------|---------|---------|-------------|------------|
| pydantic | ~2.x | Config validation + LLM response parsing | Validate YAML config at load time; parse/validate LLM JSON responses into typed models. Catches malformed config and hallucinated LLM output. | HIGH |
| tenacity | ~9.x | Retry logic | Retry failed Gmail API calls and LLM requests with exponential backoff. Network calls fail — retries are essential for unattended cron jobs. | HIGH |
| python-dotenv | ~1.x | Environment variables | Load API keys from `.env` file. Keeps secrets out of code and config. | MEDIUM |

**Why pydantic is worth the dependency:**
- The script has two critical data boundaries: (1) YAML config input, (2) LLM JSON output. Both can be malformed. Pydantic validates both with minimal code.
- Structured output from Gemini can be constrained via response schema, but pydantic gives a second layer of validation and typed access.

**Libraries explicitly NOT recommended:**

| Library | Why Not |
|---------|---------|
| `langchain` | Massive dependency for a single LLM call. The script makes one type of API call — direct SDK usage is clearer, lighter, and more debuggable. |
| `litellm` | Multi-provider abstraction. We're using one provider (Gemini). Adds complexity without value. |
| `pandas` | No data analysis needed. Email data is processed one-at-a-time, not in dataframes. |
| `requests` | Not needed. Google SDK handles HTTP. Gemini SDK handles HTTP. |
| `beautifulsoup4` / `lxml` | Email body parsing is tempting but dangerous. HTML emails are messy. Better to send raw text/HTML to the LLM and let it extract what matters. If HTML stripping is needed, stdlib `html.parser` or a simple regex suffices for removing tags. |

## Dependency Summary

### Core (required)

```
google-api-python-client>=2.100.0
google-auth-oauthlib>=1.0.0
google-auth-httplib2>=0.2.0
google-generativeai>=0.8.0
pyyaml>=6.0.1
pydantic>=2.5.0
tenacity>=9.0.0
python-dotenv>=1.0.0
```

### Dev (development/testing)

```
pytest>=8.0.0
pytest-cov>=5.0.0
ruff>=0.4.0
mypy>=1.10.0
```

## Installation

```bash
# Initialize project
uv init email-triage
cd email-triage

# Core dependencies
uv add google-api-python-client google-auth-oauthlib google-auth-httplib2
uv add google-generativeai
uv add pyyaml pydantic tenacity python-dotenv

# Dev dependencies
uv add --dev pytest pytest-cov ruff mypy
```

## Environment Variables

```bash
# .env (never commit this)
GEMINI_API_KEY=your-api-key-here
```

OAuth2 credentials (`credentials.json` from Google Cloud Console) are a file, not an env var. Store in project root but add to `.gitignore`. The token file (`token.json`) generated after first auth should also be in `.gitignore`.

## Version Validation Checklist

> **IMPORTANT**: All versions below are from training data (cutoff May 2025). Before implementation, validate:

- [ ] `google-api-python-client` latest version on PyPI
- [ ] `google-generativeai` latest version on PyPI (this SDK evolves rapidly)
- [ ] Gemini 2.0 Flash free tier limits at https://ai.google.dev/pricing
- [ ] `pydantic` v2 latest minor version
- [ ] `tenacity` latest version on PyPI
- [ ] Gemini API model name string (e.g., `gemini-2.0-flash` vs `gemini-2.0-flash-001`)

## Architecture Fit

This stack is intentionally minimal for a single-file-ish script:

- **No web framework** — it's a CLI/cron script, not a server
- **No database** — Gmail labels ARE the state store (idempotency via label check)
- **No async** — sequential processing is fine for ~200 emails; simpler to debug
- **No containerization** — runs directly on the host where cron lives

The total dependency footprint is ~8 packages (plus their transitive deps), which is appropriate for a personal automation tool.

## Sources

- Google API Python Client: https://github.com/googleapis/google-api-python-client (HIGH confidence — official repo)
- Gmail API documentation: https://developers.google.com/gmail/api (HIGH confidence — official docs)
- Gemini API: https://ai.google.dev/ (MEDIUM confidence — pricing/limits may have changed)
- google-generativeai SDK: https://github.com/google-gemini/generative-ai-python (MEDIUM confidence — SDK evolving rapidly)
- PyYAML: https://github.com/yaml/pyyaml (HIGH confidence — stable project)
- Pydantic: https://docs.pydantic.dev/ (HIGH confidence — well-documented)
- Tenacity: https://github.com/jd/tenacity (HIGH confidence — stable project)

**Note**: All research was conducted from training data only. WebSearch, WebFetch, and Context7 were unavailable during this research session. Versions and pricing should be validated before implementation begins.
