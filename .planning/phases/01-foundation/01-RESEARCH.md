# Phase 1: Foundation - Research

**Researched:** 2026-03-07
**Domain:** Gmail API OAuth2 authentication, email fetching, YAML config validation, Python project scaffolding
**Confidence:** HIGH

## Summary

Phase 1 delivers the complete input pipeline for email classification: OAuth2 authentication with Gmail, paginated email fetching, and YAML config loading with strict validation. The stack is well-established: Python 3.11+ with Google's official API client libraries (`google-api-python-client` 2.192.0, `google-auth-oauthlib` 1.3.0) for Gmail access, PyYAML 6.0.3 for config parsing, and pydantic 2.12.5 for validation. Package management with `uv`.

The Gmail API is stable, well-documented, and the Python client has mature pagination and batch support. OAuth2 token persistence uses the standard `InstalledAppFlow` -> `token.json` pattern with automatic refresh. The single most critical pitfall is OAuth2 consent screen in "Testing" mode, which causes refresh token expiry after 7 days -- the user must publish the consent screen before relying on cron automation.

The CONTEXT.md decisions constrain Phase 1 to: YAML config with strict validation (name + description + >= 1 example per category), browser-first OAuth2 with URL fallback, configurable fetch window (default 24h), progressive counter output with ANSI colors, and verbose first-run guidance. CONF-04 (custom LLM prompt template) is explicitly dropped.

**Primary recommendation:** Use `gmail.modify` as single OAuth2 scope (covers read + label + send), `InstalledAppFlow.run_local_server()` with `open_browser=True` for first-run setup, `format="metadata"` for message fetching, and pydantic BaseModel for YAML config validation with fail-fast on startup.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- YAML format, structure at Claude's discretion (flat list vs map-keyed)
- Config file path at Claude's discretion
- No custom prompt template override -- prompt is hardcoded (CONF-04 dropped from v1)
- Strict validation: every category must have name + description + at least 1 example, otherwise exit with clear error
- Credentials.json path at Claude's discretion
- First launch: attempt to open browser automatically for OAuth2 flow; if that fails, print the authorization URL as fallback
- Token storage location at Claude's discretion
- Verbose step-by-step guidance messages during first setup (user may return to the project after months)
- Default processing window: 24 hours
- Default email fields sent to LLM: subject + sender + body snippet
- Default body snippet length: 500 characters
- Batch fetching with configurable max emails per run (avoids infinite runs on large inboxes)
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

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| AUTH-01 | OAuth2 authentication with token persistence across cron runs | `InstalledAppFlow` + `token.json` pattern; `Credentials.from_authorized_user_file()` for loading; `creds.to_json()` for saving; verified in Gmail quickstart and google-auth-oauthlib docs |
| AUTH-02 | Automatic token refresh without user intervention | `creds.refresh(Request())` when `creds.expired and creds.refresh_token`; google-auth handles this automatically; refresh token survives if consent screen is Published |
| AUTH-03 | One-time interactive setup for initial OAuth2 authorization | `InstalledAppFlow.from_client_secrets_file().run_local_server(open_browser=True)` with fallback to URL print; `run_local_server(port=0)` for auto-port selection |
| FETCH-01 | Fetch unread emails via Gmail API with pagination support | `messages.list(userId="me", q="is:unread", maxResults=500)` + `list_next()` pagination pattern; batch `messages.get(format="metadata")` for efficiency |
| FETCH-02 | Processing window -- only process emails from configurable time period (default: 24h) | Gmail query `after:` date filter or `internalDate` comparison post-fetch; code-side filtering more reliable |
| FETCH-03 | Configurable email fields sent to LLM (subject, sender, body snippet) | `format="metadata"` with `metadataHeaders=["From", "Subject", "Date"]`; `snippet` always included in response (~200 chars) |
| FETCH-04 | Configurable body snippet length limit to control token usage | Snippet is ~200 chars from API; for longer snippets, fetch body parts; truncation logic in code |
| FETCH-05 | Conservative behavior enforced -- never mark as read, never archive, never delete | Only use `messages.list` and `messages.get`; never call `messages.modify`, `messages.trash`, `messages.delete` in fetch phase; enforced by code design |
| CONF-01 | Categories defined in YAML file with name and description | PyYAML `yaml.safe_load()` + pydantic BaseModel with `name: str` and `description: str` fields |
| CONF-02 | Category examples in config for few-shot LLM prompting | pydantic model: `examples: list[str]` with `min_length=1` validator; used later in prompt construction |
| CONF-03 | Config validation on startup with clear error messages (fail fast) | pydantic `ValidationError` caught at load time; formatted field-specific errors; `sys.exit(1)` on failure |
| CONF-04 | Custom LLM prompt template override in config | **DROPPED from v1** per user decision -- prompt is hardcoded |

</phase_requirements>

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | >= 3.11 | Runtime | Google SDKs are Python-first; typing, f-string, performance improvements. 3.11+ for 10-60% perf gain over 3.10 |
| google-api-python-client | 2.192.0 | Gmail API v1 client | Official Google SDK, maintenance mode (stable), covers all Gmail operations. Released 2026-03-05 |
| google-auth-oauthlib | 1.3.0 | OAuth2 consent flow | Official companion for OAuth2 installed app flow. `InstalledAppFlow` class. Released 2026-02-27 |
| google-auth-httplib2 | >= 0.2.0 | HTTP transport auth | Bridges google-auth credentials with httplib2 transport. Required dependency |
| PyYAML | 6.0.3 | YAML config parsing | Mature, stable, MIT license. `yaml.safe_load()` for secure parsing. Released 2025-09-25 |
| pydantic | 2.12.5 | Config + data validation | Validates YAML config at load time with clear error messages; typed data models for email data. Released 2025-11-26 |
| uv | latest | Package manager | Project convention (CLAUDE.md). Manages venv + deps + lockfile. `uv run` for cron execution |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| tenacity | 9.1.4 | Retry logic with backoff | Retry failed Gmail API calls (429/503). Requires Python >= 3.10. Released 2026-02-07 |
| python-dotenv | >= 1.0.0 | Environment variables | Load API keys from `.env`. Keeps secrets out of code |

### Dev

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | >= 8.0.0 | Testing | Unit tests for config validation, auth flow mocking |
| ruff | >= 0.4.0 | Linter + formatter | Code quality checks |
| mypy | >= 1.10.0 | Type checking | Static type verification |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| google-api-python-client | simplegmail | Thin wrapper; hides control needed for label management. Not worth the abstraction |
| PyYAML | toml (stdlib) | TOML awkward for nested category definitions with descriptions/examples |
| pydantic | dataclasses + manual validation | Pydantic provides automatic validation, clear error messages, and type coercion out of the box |
| tenacity | manual retry loops | Tenacity handles jitter, backoff strategies, per-exception retry -- not worth reimplementing |

**Installation:**
```bash
# Initialize project
uv init email-triage
cd email-triage

# Core dependencies
uv add google-api-python-client google-auth-oauthlib google-auth-httplib2
uv add pyyaml pydantic tenacity python-dotenv

# Dev dependencies
uv add --dev pytest ruff mypy
```

## Architecture Patterns

### Recommended Project Structure
```
email_fetch/
+-- pyproject.toml              # Project metadata, dependencies (uv)
+-- categories.yaml             # User-editable category definitions
+-- .env                        # API keys (gitignored)
+-- .gitignore                  # credentials/, token.json, .env, __pycache__
+-- src/
|   +-- email_triage/
|       +-- __init__.py
|       +-- __main__.py         # Entry point: python -m email_triage
|       +-- cli.py              # Argument parsing, orchestration
|       +-- config.py           # YAML loading, pydantic validation, defaults
|       +-- auth.py             # OAuth2 flow, token persistence, refresh
|       +-- gmail.py            # Gmail API wrapper (fetch messages, pagination)
|       +-- models.py           # Dataclasses: EmailData, Config schemas
+-- tests/
|   +-- test_config.py
|   +-- test_auth.py
|   +-- test_gmail.py
+-- credentials/                # NOT version-controlled (.gitignore)
    +-- credentials.json        # OAuth2 client secret (from Google Cloud Console)
    +-- token.json              # Auto-generated after first OAuth2 flow
```

### Pattern 1: OAuth2 Token Persistence and Refresh
**What:** Load stored credentials, refresh if expired, run interactive flow if no token exists.
**When to use:** Every script invocation.
**Example:**
```python
# Source: https://developers.google.com/workspace/gmail/api/quickstart/python
# + https://google-auth-oauthlib.readthedocs.io/en/latest/reference/google_auth_oauthlib.flow.html
import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
TOKEN_PATH = "credentials/token.json"
CREDENTIALS_PATH = "credentials/credentials.json"

def authenticate() -> Credentials:
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            # open_browser=True attempts browser; prints URL as fallback
            # port=0 selects random available port
            creds = flow.run_local_server(port=0, open_browser=True)
        # Persist for next run
        with open(TOKEN_PATH, "w") as token_file:
            token_file.write(creds.to_json())

    return creds
```

### Pattern 2: Gmail API Pagination with list_next
**What:** Paginate through all unread message IDs using the built-in `list_next()` pattern.
**When to use:** Fetching unread emails.
**Example:**
```python
# Source: https://googleapis.github.io/google-api-python-client/docs/pagination.html
from googleapiclient.discovery import build

def fetch_unread_ids(service, max_results: int = 100) -> list[str]:
    """Paginate through unread message IDs, up to max_results."""
    ids: list[str] = []
    request = service.users().messages().list(
        userId="me",
        q="is:unread",
        maxResults=min(max_results, 500),  # API max per page is 500
    )
    while request and len(ids) < max_results:
        response = request.execute()
        for msg in response.get("messages", []):
            if len(ids) >= max_results:
                break
            ids.append(msg["id"])
        request = service.users().messages().list_next(request, response)
    return ids
```

### Pattern 3: Batch Message Retrieval with Metadata Format
**What:** Fetch multiple messages in a single HTTP call using `BatchHttpRequest`, requesting only metadata.
**When to use:** After collecting message IDs, to get headers and snippet efficiently.
**Example:**
```python
# Source: https://googleapis.github.io/google-api-python-client/docs/batch.html
# Limit: 1000 requests per batch (Google docs), but 100 is practical for Gmail

def fetch_messages_batch(service, message_ids: list[str]) -> list[dict]:
    """Fetch message metadata in batches of 100."""
    results: list[dict] = []
    errors: list[tuple[str, Exception]] = []

    def callback(request_id: str, response: dict, exception: Exception | None):
        if exception:
            errors.append((request_id, exception))
        else:
            results.append(response)

    for i in range(0, len(message_ids), 100):
        chunk = message_ids[i:i + 100]
        batch = service.new_batch_http_request(callback=callback)
        for msg_id in chunk:
            batch.add(
                service.users().messages().get(
                    userId="me",
                    id=msg_id,
                    format="metadata",
                    metadataHeaders=["From", "Subject", "Date"],
                ),
                request_id=msg_id,
            )
        batch.execute()

    return results
```

### Pattern 4: Pydantic YAML Config Validation
**What:** Load YAML, validate with pydantic models, fail fast with clear errors.
**When to use:** At script startup, before any API calls.
**Example:**
```python
# Source: https://docs.pydantic.dev/latest/api/config/
# + https://www.sarahglasmacher.com/how-to-validate-config-yaml-pydantic/
import sys
import yaml
from pydantic import BaseModel, field_validator, ValidationError

class CategoryConfig(BaseModel):
    name: str
    description: str
    examples: list[str]

    @field_validator("examples")
    @classmethod
    def at_least_one_example(cls, v: list[str]) -> list[str]:
        if len(v) < 0:
            raise ValueError("each category must have at least 1 example")
        return v

class FetchConfig(BaseModel):
    processing_window_hours: int = 24
    max_emails: int = 100
    snippet_length: int = 500

class AppConfig(BaseModel):
    categories: list[CategoryConfig]
    fetch: FetchConfig = FetchConfig()

def load_config(path: str) -> AppConfig:
    try:
        with open(path) as f:
            raw = yaml.safe_load(f)
        return AppConfig.model_validate(raw)
    except FileNotFoundError:
        print(f"ERROR: Config file not found: {path}")
        print("  Create a categories.yaml file. See README for format.")
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"ERROR: Invalid YAML syntax in {path}: {e}")
        sys.exit(1)
    except ValidationError as e:
        print(f"ERROR: Invalid configuration in {path}:")
        for error in e.errors():
            loc = " -> ".join(str(l) for l in error["loc"])
            print(f"  {loc}: {error['msg']}")
        sys.exit(1)
```

### Pattern 5: ANSI Color Output with TTY Detection
**What:** Colored terminal output for info/warning/error with automatic plain text fallback when stdout is not a TTY (cron, pipes).
**When to use:** All user-facing output.
**Example:**
```python
import sys

class Colors:
    """ANSI colors with automatic TTY detection."""
    _enabled: bool = sys.stdout.isatty()

    RESET = "\033[0m"
    INFO = "\033[36m"     # cyan
    WARN = "\033[33m"     # yellow
    ERROR = "\033[31m"    # red
    SUCCESS = "\033[32m"  # green
    BOLD = "\033[1m"

    @classmethod
    def info(cls, msg: str) -> str:
        return f"{cls.INFO}{msg}{cls.RESET}" if cls._enabled else msg

    @classmethod
    def error(cls, msg: str) -> str:
        return f"{cls.ERROR}{msg}{cls.RESET}" if cls._enabled else msg
```

### Anti-Patterns to Avoid

- **Fetching full email bodies (`format="full"` or `format="raw"`):** 10-100x larger than metadata. For classification, subject + sender + snippet is sufficient. Only fetch body parts if snippet is inadequate.
- **Using `gmail.readonly` scope:** Insufficient for later phases (labeling, sending notification). Use `gmail.modify` from the start to avoid re-authorization.
- **Storing OAuth tokens in YAML config:** Tokens rotate. Config is version-controlled. Keep `token.json` separate in `credentials/` directory, gitignored.
- **Silent error swallowing:** Never `except Exception: pass`. Every error must be logged or surfaced with actionable suggestions.
- **Using `q="label:UNREAD"` instead of `q="is:unread"`:** Different behavior. `is:unread` is the standard Gmail search syntax.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| OAuth2 flow + token refresh | Custom HTTP requests to Google OAuth endpoints | `google-auth-oauthlib` InstalledAppFlow | Token rotation, PKCE, redirect handling, refresh logic -- all handled correctly |
| Gmail API pagination | Manual nextPageToken tracking | `list_next()` built into google-api-python-client | Library handles token extraction, None detection, request reconstruction |
| Config validation | Manual dict key checking with if/elif chains | pydantic BaseModel + `model_validate()` | Type coercion, nested validation, field-specific error messages, default values |
| Retry with exponential backoff | `time.sleep()` in while loops | tenacity `@retry` decorator | Jitter, max attempts, per-exception filtering, stop conditions |
| YAML parsing | Manual string parsing or regex | PyYAML `yaml.safe_load()` | Handles all YAML types, anchors, multiline strings safely |
| Batch HTTP requests | Sequential `messages.get()` in a for loop | `service.new_batch_http_request()` | 100 requests in 1 HTTP call; callback-based error handling |

**Key insight:** Google's Python SDK ecosystem is mature and handles all the edge cases (token rotation, API pagination, batch requests, error codes). Custom implementations will miss edge cases that Google's libraries handle correctly.

## Common Pitfalls

### Pitfall 1: OAuth2 Refresh Token Expires After 7 Days in Testing Mode
**What goes wrong:** Script works perfectly during development, then dies silently after 7 days when running via cron because the refresh token expired.
**Why it happens:** Google OAuth2 consent screens in "External + Testing" status issue refresh tokens that expire after 7 days. This is confirmed in Google's official documentation and multiple community reports.
**How to avoid:** Publish the OAuth2 consent screen in Google Cloud Console before deploying to cron. For personal use (single Google account), set the consent screen to "External", add your own email as a test user, then click "Publish App". No verification is needed for apps with < 100 users.
**Warning signs:** `google.auth.exceptions.RefreshError` in logs; script works manually but fails in cron after ~7 days.

### Pitfall 2: MIME Parsing Complexity for Email Body
**What goes wrong:** Treating email body extraction as trivial. Gmail API returns emails in complex MIME multipart structures. HTML-only emails, nested multipart, Base64 encoding, varied charsets.
**Why it happens:** Email (RFC 2822 / MIME) is one of the oldest and most inconsistent internet standards.
**How to avoid:** For Phase 1, use `format="metadata"` which returns only headers + snippet (~200 chars of body text). Snippet is always included, requires no MIME parsing, and is sufficient for classification context. Full body parsing is NOT needed for this phase.
**Warning signs:** `KeyError`, `IndexError` when accessing payload parts; encoding errors.

### Pitfall 3: Scope Mismatch Requiring Re-Authorization
**What goes wrong:** Starting with `gmail.readonly` scope, then needing to add `gmail.modify` later for labeling/sending, which forces the user through the OAuth2 consent flow again (deleting the token and re-authenticating).
**Why it happens:** OAuth2 tokens are scoped. Changing scopes requires new consent.
**How to avoid:** Use `gmail.modify` from the start. It covers read, label management, label creation, and message sending. It does NOT allow permanent deletion (that requires `mail.google.com`). Verified against official Gmail API scope docs.
**Warning signs:** `HttpError 403` when trying label operations with readonly token.

### Pitfall 4: Gmail API Rate Limit on First Run with Large Inbox
**What goes wrong:** First run processes the entire unread inbox (potentially thousands of emails), exhausting API quota or taking too long.
**Why it happens:** No limit on how many emails to process per run.
**How to avoid:** Implement `max_emails` config parameter (default: 100). Cap fetching at this limit. Use `maxResults` parameter in `messages.list` and batch `messages.get` calls (100 per batch).
**Warning signs:** `HttpError 429 Too Many Requests`; script running for minutes instead of seconds.

### Pitfall 5: `run_local_server()` Fails in Headless/WSL Environments
**What goes wrong:** `InstalledAppFlow.run_local_server()` tries to open a browser, which fails in headless servers, Docker, or WSL without a display server.
**Why it happens:** `webbrowser.open()` requires a display. WSL2 may or may not have browser integration configured.
**How to avoid:** Use `run_local_server(port=0, open_browser=True)` which prints the authorization URL to console as a fallback. The user can copy-paste the URL into any browser. Print a clear instruction message. The local server still listens for the redirect callback even if the browser didn't open.
**Warning signs:** `webbrowser.Error` exception; script hanging waiting for browser callback.

### Pitfall 6: Token File Permissions in Shared Environments
**What goes wrong:** `token.json` is created with default permissions (644), readable by other users on the system.
**Why it happens:** Python `open()` creates files with default umask permissions.
**How to avoid:** After writing `token.json`, set permissions to 600: `os.chmod(TOKEN_PATH, 0o600)`. Add `credentials/` directory to `.gitignore`.
**Warning signs:** Other users on the system can read the OAuth2 refresh token.

## Code Examples

Verified patterns from official sources:

### Building Gmail Service Object
```python
# Source: https://developers.google.com/workspace/gmail/api/quickstart/python
from googleapiclient.discovery import build

def get_gmail_service(creds):
    """Build authenticated Gmail API service."""
    return build("gmail", "v1", credentials=creds)
```

### Extracting Email Data from Metadata Response
```python
# Source: https://developers.google.com/gmail/api/reference/rest/v1/users.messages#Message
from dataclasses import dataclass
from datetime import datetime

@dataclass
class EmailData:
    id: str
    thread_id: str
    sender: str
    subject: str
    date: str
    snippet: str
    label_ids: list[str]

def parse_message(msg: dict) -> EmailData:
    """Parse Gmail API message response into EmailData."""
    headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
    return EmailData(
        id=msg["id"],
        thread_id=msg["threadId"],
        sender=headers.get("From", ""),
        subject=headers.get("Subject", ""),
        date=headers.get("Date", ""),
        snippet=msg.get("snippet", ""),
        label_ids=msg.get("labelIds", []),
    )
```

### Time Window Filtering
```python
# Source: Gmail API internalDate field (epoch ms)
from datetime import datetime, timedelta, timezone

def filter_by_window(emails: list[EmailData], messages_raw: list[dict], hours: int = 24) -> list[EmailData]:
    """Filter emails to only those within the processing window."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    cutoff_ms = int(cutoff.timestamp() * 1000)
    filtered = []
    for email, raw in zip(emails, messages_raw):
        internal_date = int(raw.get("internalDate", "0"))
        if internal_date >= cutoff_ms:
            filtered.append(email)
    return filtered
```

### YAML Config File Format
```yaml
# categories.yaml -- example configuration
categories:
  - name: "Newsletter"
    description: "Recurring newsletters, digests, content roundups from media and tech companies"
    examples:
      - "from:substack.com"
      - "subject:Weekly digest"
      - "subject:Your daily briefing"

  - name: "Finance"
    description: "Bank alerts, credit card notifications, invoices, receipts, payment confirmations"
    examples:
      - "from:noreply@bank.com"
      - "subject:Your statement is ready"

  - name: "Social"
    description: "Social media notifications from LinkedIn, Twitter/X, GitHub, etc."
    examples:
      - "from:notifications@linkedin.com"
      - "from:noreply@github.com"

  - name: "Shopping"
    description: "Order confirmations, shipping updates, delivery notifications, promotional offers"
    examples:
      - "subject:Your order has shipped"
      - "subject:Delivery confirmation"

fetch:
  processing_window_hours: 24
  max_emails: 100
  snippet_length: 500
  fields:
    - subject
    - sender
    - snippet
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `run_console()` (copy-paste code) | `run_local_server(port=0)` | google-auth-oauthlib 0.5+ | Better UX -- browser auto-opens, redirect captures code automatically |
| Manual `nextPageToken` tracking | `list_next()` method | google-api-python-client built-in | Eliminates pagination boilerplate |
| `token.pickle` (pickle format) | `creds.to_json()` / `Credentials.from_authorized_user_file()` | google-auth 2.x | JSON is human-readable, debuggable, and avoids pickle security concerns |
| `pydantic.validator` | `pydantic.field_validator` | pydantic v2 (2023) | New decorator-based validation API in v2 |
| `gmail.readonly` + `gmail.send` (two scopes) | `gmail.modify` (single scope) | Always available | Single scope covers read + label + send; simpler consent screen |

**Deprecated/outdated:**
- `run_console()`: Still available but provides worse UX than `run_local_server()`. Only use if local server cannot bind to a port.
- `token.pickle`: Legacy format. Use JSON-based token persistence instead.
- pydantic v1 `@validator`: Replaced by `@field_validator` in v2. v1 compatibility mode exists but should not be used for new code.

## Open Questions

1. **Body snippet vs full body for FETCH-04**
   - What we know: Gmail API `snippet` field is ~200 characters (first part of body text, always included in metadata format). CONTEXT.md says "default body snippet length: 500 characters".
   - What's unclear: 500 chars exceeds what `snippet` provides. Getting more requires fetching body parts (MIME parsing complexity).
   - Recommendation: Start with the API-provided snippet (~200 chars). If the user later needs more context for classification accuracy, add optional body part fetching in a future iteration. Document this limitation clearly.

2. **Processing window implementation: query vs code-side filtering**
   - What we know: Gmail `after:` query parameter uses midnight UTC boundaries (not exact hours). Code-side filtering using `internalDate` field is more precise.
   - What's unclear: Whether `after:` is accurate enough for 24h windows or if off-by-hours matters.
   - Recommendation: Use `after:` in the query for rough pre-filtering (reduces API calls), then apply exact `internalDate` comparison in code for precision. Belt-and-suspenders approach.

3. **Batch size default value (Claude's discretion)**
   - What we know: Gmail API `maxResults` caps at 500 per page. Batch `messages.get` supports up to 1000 per batch (100 recommended for Gmail). Personal inbox typically has 10-50 unread per cron run.
   - Recommendation: Default `max_emails` to 100. This covers normal personal inbox volume with a comfortable margin. Users with busier inboxes can increase via config.

## Sources

### Primary (HIGH confidence)
- [Gmail API Python Quickstart](https://developers.google.com/workspace/gmail/api/quickstart/python) -- OAuth2 flow, token persistence pattern
- [Gmail API messages.list reference](https://developers.google.com/gmail/api/reference/rest/v1/users.messages/list) -- maxResults=500, pagination, labelIds parameter
- [Gmail API messages.get reference](https://developers.google.com/gmail/api/reference/rest/v1/users.messages/get) -- format options (METADATA, FULL, RAW, MINIMAL), metadataHeaders
- [Gmail API messages.modify reference](https://developers.google.com/gmail/api/reference/rest/v1/users.messages/modify) -- addLabelIds, removeLabelIds
- [Gmail API messages.batchModify reference](https://developers.google.com/gmail/api/reference/rest/v1/users.messages/batchModify) -- batch label modification, 1000 IDs limit
- [Gmail API labels.create reference](https://developers.google.com/gmail/api/reference/rest/v1/users.labels/create) -- scopes: gmail.modify, gmail.labels
- [Gmail API messages.send reference](https://developers.google.com/gmail/api/reference/rest/v1/users.messages/send) -- scopes include gmail.modify
- [Gmail API scopes documentation](https://developers.google.com/workspace/gmail/api/auth/scopes) -- scope hierarchy and permissions
- [google-api-python-client pagination docs](https://googleapis.github.io/google-api-python-client/docs/pagination.html) -- list_next() pattern
- [google-api-python-client batch docs](https://googleapis.github.io/google-api-python-client/docs/batch.html) -- BatchHttpRequest, 1000 limit
- [google-auth-oauthlib InstalledAppFlow docs](https://google-auth-oauthlib.readthedocs.io/en/latest/reference/google_auth_oauthlib.flow.html) -- run_local_server(), open_browser parameter
- [PyPI: google-api-python-client 2.192.0](https://pypi.org/project/google-api-python-client/) -- released 2026-03-05, Python >= 3.7
- [PyPI: google-auth-oauthlib 1.3.0](https://pypi.org/project/google-auth-oauthlib/) -- released 2026-02-27
- [PyPI: PyYAML 6.0.3](https://pypi.org/project/PyYAML/) -- released 2025-09-25
- [PyPI: pydantic 2.12.5](https://pypi.org/project/pydantic/) -- released 2025-11-26
- [PyPI: tenacity 9.1.4](https://pypi.org/project/tenacity/) -- released 2026-02-07, requires Python >= 3.10

### Secondary (MEDIUM confidence)
- [Google OAuth2 Testing mode token expiry](https://developers.google.com/identity/protocols/oauth2) -- refresh token 7-day expiry for Testing status confirmed by multiple sources
- [Pydantic YAML config validation patterns](https://www.sarahglasmacher.com/how-to-validate-config-yaml-pydantic/) -- BaseModel + yaml.safe_load pattern
- [Gmail Message resource reference](https://developers.google.com/gmail/api/reference/rest/v1/users.messages#Message) -- snippet field, payload structure, headers

### Tertiary (LOW confidence)
- Gmail API quota numbers (250 units/sec, message costs) -- from training data, specific numbers should be verified against current [quota documentation](https://developers.google.com/gmail/api/reference/quota)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all library versions verified on PyPI with release dates; Gmail API is stable and well-documented
- Architecture: HIGH -- standard pipeline pattern for CLI tools; module structure follows Python best practices; Gmail API patterns verified against official docs
- Pitfalls: HIGH -- OAuth2 token expiry in Testing mode confirmed by multiple sources including Google's official docs; MIME complexity is well-established; scope requirements verified against official API reference

**Research date:** 2026-03-07
**Valid until:** 2026-04-07 (30 days -- stack is stable, Gmail API is in maintenance mode)
