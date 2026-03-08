# Phase 3: Operability - Research

**Researched:** 2026-03-08
**Domain:** Production operability — structured logging, retry/backoff, error resilience, cron compatibility, email notifications
**Confidence:** HIGH

## Summary

Phase 3 transforms the email triage script from an interactive tool into a production-ready cron job. The work spans five domains: (1) structured logging replacing print-based output, (2) retry with exponential backoff for both Gmail API and Gemini LLM calls, (3) per-email error resilience so one failure doesn't crash the batch, (4) cron-compatible exit codes and non-interactive execution, and (5) summary email notification sent via Gmail API after each run.

The codebase already has several pieces in place: `tenacity` is in dependencies, `gmail.modify` scope covers email sending, per-email try/except exists in `cli.py`, and `output.py` has TTY detection for cron-safe output. The main work is replacing print-based output with stdlib `logging`, wrapping API calls in tenacity decorators, building the summary email sender, and refactoring the CLI to produce clean exit codes.

**Primary recommendation:** Use Python stdlib `logging` with `python-json-logger` for JSON file output. Use `tenacity` for Gmail API retries (wrapping `execute()` calls). Rely on google-genai SDK built-in retry for LLM calls, adding tenacity only as a fallback layer. Send summary email via Gmail API `messages.send()` using `email.message.EmailMessage` from stdlib.

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| OPS-01 | Cron-compatible execution (clean exit codes, no interactive prompts, stdout/stderr logging) | Exit code pattern (0/1), logging to stderr for errors, stdout for info. Auth module already has non-interactive path when token exists. See "Cron Compatibility" pattern. |
| OPS-02 | Structured logging with configurable levels to file and console | Python stdlib `logging` + `python-json-logger` for JSON file handler, console handler with human-readable format. See "Structured Logging" section. |
| OPS-03 | Graceful per-email error handling — one failure does not crash the batch | Already partially implemented in `cli.py` (try/except per email). Needs: error accumulation, structured logging of failures, inclusion in summary stats. See "Error Resilience" pattern. |
| OPS-04 | Rate limiting with exponential backoff for Gmail API (429/503) | `google-api-python-client` has `num_retries` on `execute()`. Wrap with tenacity for finer control. See "Gmail API Retry" pattern. |
| OPS-05 | Retry logic for LLM API failures with exponential backoff | `google-genai` SDK has built-in retry for 429/503. Add tenacity wrapper as defense-in-depth for other transient errors. See "LLM Retry" pattern. |
| NOTF-01 | Summary email notification sent to self after each run | Gmail API `messages.send()` with `email.message.EmailMessage`. Scope `gmail.modify` already covers sending. See "Summary Email" pattern. |
| NOTF-02 | Statistics in summary email (per-category breakdown, error count, token usage estimate) | Accumulate `RunStats` dataclass during pipeline, render as HTML email body. Token usage from Gemini response `usage_metadata`. See "Run Statistics" pattern. |

</phase_requirements>

## Standard Stack

### Core (already in dependencies)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `logging` (stdlib) | Python 3.11 | Logging framework | Built-in, zero deps, handlers/formatters/levels |
| `tenacity` | >=9.1.4 | Retry with backoff | Already in pyproject.toml, de facto Python retry standard |
| `email.message` (stdlib) | Python 3.11 | Build email messages | stdlib, modern API replaces MIMEText |
| `base64` (stdlib) | Python 3.11 | Encode email for Gmail API | Required for `messages.send()` raw format |
| `google-api-python-client` | >=2.192.0 | Gmail API (send email) | Already used for fetching/labeling |
| `google-genai` | >=1.66.0 | Gemini LLM (built-in retry) | Already used for classification |

### New Dependencies
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `python-json-logger` | >=3.2 | JSON formatter for stdlib logging | File output handler — structured JSON logs for machine parsing |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| stdlib `logging` + `python-json-logger` | `structlog` | structlog is more powerful but overkill for a cron script with < 10 log points. stdlib is zero-dep, well-understood, sufficient. |
| `python-json-logger` | Custom `json.dumps` formatter | python-json-logger handles edge cases (extra fields, exception formatting, timestamps). Don't hand-roll. |
| `tenacity` for Gmail | `num_retries` param on `execute()` | `num_retries` is basic (random backoff, no logging, no exception filtering). Tenacity gives before_sleep_log, retry_if_exception_type, configurable backoff. |
| Custom email builder | Third-party mail library | Gmail API send is < 20 lines of code with stdlib `EmailMessage`. No external library needed. |

**Installation:**
```bash
uv add python-json-logger
```

## Architecture Patterns

### Recommended Changes to Existing Structure
```
src/email_triage/
├── __init__.py          # (exists)
├── __main__.py          # (exists)
├── auth.py              # (exists)
├── classifier.py        # (exists, add tenacity retry wrapper)
├── cli.py               # (exists, major refactor: logging + exit codes + summary)
├── config.py            # (exists, add logging config section)
├── gmail.py             # (exists, add tenacity retry wrapper)
├── labels.py            # (exists, add tenacity retry wrapper)
├── logging_setup.py     # NEW: configure logging handlers
├── models.py            # (exists, add RunStats dataclass)
├── notify.py            # NEW: summary email builder + sender
└── output.py            # (exists, migrate to logging, possibly deprecate)
```

### Pattern 1: Structured Logging Setup
**What:** Configure stdlib logging with two handlers — console (human-readable) and file (JSON)
**When to use:** At application startup, before any other code runs

```python
# Source: Python stdlib logging docs + python-json-logger docs
import logging
import sys
from pythonjsonlogger.json import JsonFormatter

def setup_logging(level: str = "INFO", log_file: str | None = None) -> None:
    """Configure logging with console and optional JSON file handlers."""
    root = logging.getLogger("email_triage")
    root.setLevel(getattr(logging, level.upper()))

    # Console handler — human-readable
    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    ))
    root.addHandler(console)

    # File handler — JSON structured
    if log_file:
        file_handler = logging.FileHandler(log_file)
        json_fmt = JsonFormatter(
            "%(asctime)s %(name)s %(levelname)s %(message)s",
            rename_fields={"asctime": "timestamp", "levelname": "level"},
        )
        file_handler.setFormatter(json_fmt)
        root.addHandler(file_handler)
```

### Pattern 2: Tenacity Retry for Gmail API
**What:** Wrap Gmail API `execute()` calls with tenacity for exponential backoff on 429/503
**When to use:** On all Gmail API calls (fetch, labels, send)

```python
# Source: tenacity docs + googleapiclient.errors.HttpError
from googleapiclient.errors import HttpError
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)
import logging

logger = logging.getLogger(__name__)

def _is_retryable_http_error(exc: BaseException) -> bool:
    """Check if HttpError is retryable (429 or 5xx)."""
    return isinstance(exc, HttpError) and exc.resp.status in (429, 500, 502, 503, 504)

gmail_retry = retry(
    retry=retry_if_exception(_is_retryable_http_error),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
```

### Pattern 3: Run Statistics Accumulation
**What:** Collect stats during pipeline for summary email
**When to use:** Throughout the classification loop

```python
from dataclasses import dataclass, field

@dataclass
class RunStats:
    """Accumulated statistics for a single pipeline run."""
    total_fetched: int = 0
    skipped_triaged: int = 0
    classified: int = 0
    ambiguous: int = 0
    errors: int = 0
    error_details: list[str] = field(default_factory=list)
    categories: dict[str, int] = field(default_factory=dict)  # name -> count
    api_calls_gmail: int = 0
    api_calls_llm: int = 0
    token_usage_prompt: int = 0
    token_usage_completion: int = 0
    elapsed_seconds: float = 0.0
```

### Pattern 4: Summary Email via Gmail API
**What:** Send HTML summary email to self after each run
**When to use:** At the end of the pipeline, after all processing

```python
# Source: Google Gmail API official docs — Sending Email
import base64
from email.message import EmailMessage

def send_summary_email(service, stats: RunStats) -> None:
    """Send summary notification email to self via Gmail API."""
    msg = EmailMessage()
    msg["To"] = "me"  # Gmail API resolves "me" to authenticated user
    msg["From"] = "me"
    msg["Subject"] = f"AutoTriage Summary: {stats.classified} classified, {stats.errors} errors"
    msg.set_content(_build_summary_text(stats))
    msg.add_alternative(_build_summary_html(stats), subtype="html")

    encoded = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service.users().messages().send(
        userId="me",
        body={"raw": encoded},
    ).execute()
```

### Pattern 5: Cron-Compatible Exit Codes
**What:** Clean sys.exit(0) on success, sys.exit(1) on failure, no interactive prompts
**When to use:** Top-level CLI wrapper

```python
def main(args: list[str] | None = None) -> None:
    """Cron-compatible entry point."""
    try:
        stats = run_pipeline(args)
        if stats.errors > 0:
            logger.warning("Completed with %d errors", stats.errors)
        logger.info("Run complete: %d classified, %d errors", stats.classified, stats.errors)
        sys.exit(0)
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception:
        logger.exception("Fatal error")
        sys.exit(1)
```

### Anti-Patterns to Avoid
- **Logging secrets:** Never log API keys, OAuth tokens, or email content beyond subject/sender. Sanitize before logging.
- **Catching too broadly in retry:** Don't retry on authentication errors (401/403) or validation errors (400). Only retry transient failures (429, 5xx, connection errors).
- **print() in production code:** Replace all `print_info()`, `print_error()` etc. with `logger.info()`, `logger.error()`. Keep output.py for backwards-compatible console formatting if needed, but logging is the primary output channel.
- **Sending email on empty runs:** Don't send summary if zero emails processed — it's noise for cron.
- **Blocking on email send failure:** Summary email failure should be logged, not raise. The triage work is already done.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON log formatting | Custom `json.dumps` in a formatter | `python-json-logger` | Handles exception serialization, extra fields, timestamp formatting, log record attrs |
| Retry with backoff | Manual `while/sleep` loop | `tenacity` decorators | Jitter, configurable stop/wait, logging hooks, exception filtering, already in deps |
| Email MIME encoding | Manual multipart MIME construction | `email.message.EmailMessage` | stdlib, handles encoding, multipart, content-type automatically |
| Gmail API retry | Custom wrapper around `execute()` | tenacity + `retry_if_exception` | Clean separation, testable, composable with other retry strategies |
| LLM retry | Custom retry loop around `generate_content` | google-genai built-in + tenacity fallback | SDK already retries 429/503 with exponential backoff internally |

**Key insight:** The retry domain is deceptively complex (jitter, max backoff, exception filtering, logging, idempotency). Tenacity handles all of this and is already a dependency. The email domain is deceptively simple — stdlib `EmailMessage` + `base64` is all you need.

## Common Pitfalls

### Pitfall 1: Double Retry (LLM)
**What goes wrong:** Wrapping google-genai `generate_content()` in tenacity when the SDK already retries internally. Result: a single 429 triggers up to 5 SDK retries x 5 tenacity retries = 25 attempts, potentially exhausting quota harder.
**Why it happens:** Not knowing the SDK has built-in retry.
**How to avoid:** For LLM calls, use tenacity only for non-429 transient errors (e.g., connection resets, timeouts), or use it as a coarse outer layer with very few attempts (2-3) and longer waits. Do NOT retry on the same error codes the SDK already handles.
**Warning signs:** Extremely long retry sequences in logs; hitting quota ceiling repeatedly.

### Pitfall 2: Logging to stdout Breaks cron
**What goes wrong:** Logging to stdout means cron captures it as email output (if MAILTO is set) or mixed with actual program output.
**Why it happens:** Python's default `StreamHandler` goes to stderr, but `print()` goes to stdout.
**How to avoid:** Log all structured output to stderr via logging. Use stdout only for intentional user-facing output (e.g., the final "done" message in interactive mode). In cron, redirect stdout to /dev/null and capture stderr: `script 2>> /var/log/email-triage.log`.
**Warning signs:** Cron sends emails on every run; log files contain ANSI escape codes.

### Pitfall 3: Gmail "To: me" Doesn't Work
**What goes wrong:** Setting `To: me` in the email headers doesn't resolve to the user's email. The Gmail API `userId="me"` is a special keyword for the API, but the email `To` header needs an actual email address.
**Why it happens:** Confusing API parameter `userId="me"` with email addressing.
**How to avoid:** Fetch the user's email address via `service.users().getProfile(userId="me").execute()["emailAddress"]` and use that in the `To` header.
**Warning signs:** Email delivery fails silently or goes to wrong address.

### Pitfall 4: Token Usage Not Available in Gemini Response
**What goes wrong:** Assuming `response.usage_metadata` always has token counts.
**Why it happens:** The `usage_metadata` field may be None or have different attribute names across SDK versions.
**How to avoid:** Access `usage_metadata` defensively: `getattr(response, 'usage_metadata', None)`. Track prompt/completion tokens when available, use "N/A" when not.
**Warning signs:** AttributeError on response object; zero token counts in summary.

### Pitfall 5: Retry on Auth Errors (401/403)
**What goes wrong:** Retrying on 401 (unauthenticated) or 403 (forbidden) wastes time — these are permanent failures.
**Why it happens:** Overly broad retry condition that catches all HttpErrors.
**How to avoid:** Use `retry_if_exception` with a predicate that checks `exc.resp.status in (429, 500, 502, 503, 504)`.
**Warning signs:** 5 retries followed by the same auth error; long delays before failure.

### Pitfall 6: Summary Email Failure Crashes the Run
**What goes wrong:** If `messages.send()` fails (quota, auth, network), the entire run is reported as failed even though all emails were classified and labeled successfully.
**Why it happens:** No try/except around the notification step.
**How to avoid:** Wrap `send_summary_email()` in try/except; log the error but exit 0 if triage work completed. The notification is best-effort.
**Warning signs:** Exit code 1 when classification succeeded but email failed.

## Code Examples

Verified patterns from official sources:

### Sending Email via Gmail API
```python
# Source: https://developers.google.com/workspace/gmail/api/guides/sending
import base64
from email.message import EmailMessage

def send_summary(service, to_email: str, subject: str, body_html: str) -> str:
    """Send an HTML email via Gmail API. Returns message ID."""
    msg = EmailMessage()
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content("Plain text fallback")
    msg.add_alternative(body_html, subtype="html")

    encoded = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    result = service.users().messages().send(
        userId="me",
        body={"raw": encoded},
    ).execute()
    return result["id"]
```

### Tenacity Retry with Logging
```python
# Source: https://tenacity.readthedocs.io/
from tenacity import (
    retry, retry_if_exception, stop_after_attempt,
    wait_exponential, before_sleep_log,
)
from googleapiclient.errors import HttpError
import logging

logger = logging.getLogger(__name__)

def _is_retryable(exc: BaseException) -> bool:
    return isinstance(exc, HttpError) and exc.resp.status in (429, 500, 502, 503, 504)

@retry(
    retry=retry_if_exception(_is_retryable),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def execute_with_retry(request):
    """Execute a Gmail API request with retry on transient errors."""
    return request.execute()
```

### Fetching Authenticated User Email
```python
# Source: Gmail API Users.getProfile
def get_user_email(service) -> str:
    """Get the authenticated user's email address."""
    profile = service.users().getProfile(userId="me").execute()
    return profile["emailAddress"]
```

### Gemini Response Token Usage
```python
# Source: google-genai SDK response object
def extract_token_usage(response) -> tuple[int, int]:
    """Extract prompt and completion token counts from Gemini response."""
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return (0, 0)
    return (
        getattr(usage, "prompt_token_count", 0) or 0,
        getattr(usage, "candidates_token_count", 0) or 0,
    )
```

### Logging Configuration with Dual Handlers
```python
# Source: Python logging docs + python-json-logger docs
import logging
import sys
from pythonjsonlogger.json import JsonFormatter

def setup_logging(level: str = "INFO", log_file: str | None = None) -> logging.Logger:
    """Set up dual-output logging: human console + JSON file."""
    logger = logging.getLogger("email_triage")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.handlers.clear()

    # Console: human-readable to stderr
    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    ))
    logger.addHandler(console)

    # File: structured JSON
    if log_file:
        fh = logging.FileHandler(log_file)
        fh.setFormatter(JsonFormatter(
            "%(asctime)s %(name)s %(levelname)s %(message)s",
            rename_fields={"asctime": "timestamp", "levelname": "level"},
        ))
        logger.addHandler(fh)

    return logger
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `print()` with ANSI colors | stdlib `logging` with JSON formatter | Python best practice 2020+ | Machine-parseable logs, configurable levels, file output |
| `email.mime.text.MIMEText` | `email.message.EmailMessage` | Python 3.6+ | Cleaner API, built-in content-type handling, multipart support |
| Manual retry loops | `tenacity` decorators | tenacity 4.0+ (2017) | Composable, testable, configurable, jitter support |
| `google.generativeai` SDK | `google.genai` SDK | 2024-2025 | New unified SDK, built-in retry, HttpOptions config |

**Deprecated/outdated:**
- `email.mime.text.MIMEText`: Still works but `EmailMessage` is the modern replacement recommended in Python docs
- Manual `time.sleep()` between API calls: Replace with tenacity for retry, keep fixed delay for Gemini free tier rate limiting (separate concern from retry)

## Open Questions

1. **Token usage field stability in google-genai SDK**
   - What we know: `response.usage_metadata` exists with `prompt_token_count` and `candidates_token_count` based on documentation
   - What's unclear: Whether attribute names are stable across SDK versions; the project uses `google-genai>=1.66.0`
   - Recommendation: Access defensively with `getattr()`, handle None, don't crash on missing fields. Test with actual API response.

2. **Logging config in YAML vs CLI args**
   - What we know: Config currently uses `categories.yaml` for categories/fetch/classification
   - What's unclear: Whether log level and log file path should go in YAML config or stay as CLI flags
   - Recommendation: Add `--log-level` and `--log-file` CLI flags (cron-friendly). Optionally allow config.yaml to set defaults. CLI flags override config.

3. **Summary email on zero-email runs**
   - What we know: Current code returns early when no emails found
   - What's unclear: Whether user wants summary email for "0 emails processed" runs
   - Recommendation: Skip summary email when zero emails processed. Only send when at least one email was classified or an error occurred.

## Sources

### Primary (HIGH confidence)
- [Gmail API Sending Guide](https://developers.google.com/workspace/gmail/api/guides/sending) — email sending pattern with base64 encoding
- [Gmail API Scopes](https://developers.google.com/workspace/gmail/api/auth/scopes) — confirmed `gmail.modify` covers sending
- [Tenacity docs](https://tenacity.readthedocs.io/) — retry decorators API, wait_exponential, before_sleep_log
- [Python logging docs](https://docs.python.org/3/howto/logging-cookbook.html) — handler configuration, formatters
- [python-json-logger](https://nhairs.github.io/python-json-logger/latest/) — JSON formatter for stdlib logging

### Secondary (MEDIUM confidence)
- [google-genai SDK built-in retry](https://deepwiki.com/googleapis/python-genai/1.1-installation-and-setup) — automatic retry for 429/503 with exponential backoff
- [google-api-python-client num_retries](https://github.com/googleapis/google-api-python-client/issues/1049) — `execute()` supports `num_retries` parameter
- [python-genai retry issue #1875](https://github.com/googleapis/python-genai/issues/1875) — SDK ignores server retryDelay, uses fixed backoff

### Tertiary (LOW confidence)
- Token usage metadata attribute names — based on SDK docs but may vary with version; needs live verification

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries verified in official docs, tenacity already in project deps
- Architecture: HIGH — patterns follow stdlib conventions and existing project structure
- Pitfalls: HIGH — verified through official docs, issue trackers, and project code inspection
- Gmail send: HIGH — official Google docs example, scope confirmed
- Token usage: MEDIUM — field existence confirmed but attribute stability not guaranteed across SDK versions

**Research date:** 2026-03-08
**Valid until:** 2026-04-08 (stable domain, stdlib-heavy, low churn risk)
