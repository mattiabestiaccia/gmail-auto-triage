# Architecture Patterns

**Domain:** Email auto-triage CLI script (Gmail + LLM classification)
**Researched:** 2026-03-07

## Recommended Architecture

Single-process Python CLI script with a **pipeline architecture**: emails flow through discrete stages, each handled by a dedicated module. No web server, no database, no background workers. The pipeline runs to completion and exits.

```
                    +------------------+
                    |   main.py (CLI)  |
                    +--------+---------+
                             |
                    +--------v---------+
                    |  config_loader   |  <-- categories.yaml
                    +--------+---------+
                             |
                    +--------v---------+
                    |   gmail_client   |  <-- OAuth2 credentials
                    +--------+---------+
                             |
               +-------------+-------------+
               |                           |
      +--------v---------+       +--------v---------+
      |  fetch unread     |       |  check existing  |
      |  (list+get)       |       |  labels (cache)  |
      +--------+---------+       +--------+---------+
               |                           |
               +-------------+-------------+
                             |
                    +--------v---------+
                    |   classifier     |  <-- LLM API
                    +--------+---------+
                             |
                    +--------v---------+
                    |   label_applier  |  <-- Gmail modify
                    +--------+---------+
                             |
                    +--------v---------+
                    |   notifier       |  <-- Gmail send
                    +--------+---------+
                             |
                    +--------v---------+
                    |   exit (0 or 1)  |
                    +------------------+
```

### Component Boundaries

| Component | Responsibility | Communicates With | I/O |
|-----------|---------------|-------------------|-----|
| `main.py` | CLI entry point, orchestrates pipeline, exit codes | All modules | stdin args -> exit code |
| `config.py` | Load and validate YAML categories, settings | main | YAML file -> CategoryConfig dataclass |
| `auth.py` | OAuth2 token acquisition, refresh, storage | gmail_client | credentials.json + token.json -> Credentials object |
| `gmail_client.py` | All Gmail API interactions (fetch, label, send) | auth, main | Credentials -> Gmail service; API calls |
| `classifier.py` | LLM prompt construction and response parsing | config (categories), main | Email data + categories -> classification result |
| `notifier.py` | Build and send summary email | gmail_client | Classification results -> email sent |
| `models.py` | Shared data structures (dataclasses/TypedDict) | All modules | N/A (type definitions) |

### Data Flow

**Phase 1: Initialization**
```
CLI args -> load config (categories.yaml) -> authenticate (OAuth2) -> build Gmail service
```

**Phase 2: Fetch**
```
Gmail API list(q="is:unread") -> paginate all message IDs
-> batch get (format=METADATA, fields: From, Subject, Date, snippet)
-> filter out already-labeled emails (idempotency check)
-> list of EmailData objects
```

**Phase 3: Classify**
```
For each email (or batched):
  EmailData + categories -> build LLM prompt -> call LLM API
  -> parse response -> ClassificationResult (category + confidence)
```

**Phase 4: Apply**
```
For each classified email:
  Ensure label exists (create if needed, cache label IDs)
  -> Gmail modify (addLabelIds) -> record result
```

**Phase 5: Notify**
```
All results -> build summary text -> Gmail send to self
```

**Phase 6: Exit**
```
Log final stats -> exit 0 (success) or exit 1 (partial failure)
```

## Patterns to Follow

### Pattern 1: Idempotency via Label Check
**What:** Before classifying an email, check if it already has any of the triage labels. If yes, skip it.
**When:** Every run. This is the core idempotency mechanism.
**Why:** Gmail labels are the single source of truth. No local state needed. Re-running the script on the same emails produces no side effects.
**Implementation:**
```python
TRIAGE_PREFIX = "AutoTriage/"

def needs_classification(message: dict, triage_label_ids: set[str]) -> bool:
    """An email needs classification only if it has no triage labels."""
    current_labels = set(message.get("labelIds", []))
    return not current_labels.intersection(triage_label_ids)
```
**Note:** Triage labels should share a common prefix (e.g., `AutoTriage/`) to make identification unambiguous and to group them visually in Gmail's sidebar.

### Pattern 2: Label ID Caching
**What:** Fetch the full label list once at startup, build a name-to-ID map, create missing labels, then use IDs throughout.
**When:** At initialization, before processing emails.
**Why:** Gmail API operations use label IDs (not names). Creating labels is idempotent (create-if-not-exists pattern). Caching avoids redundant API calls.
```python
def ensure_labels_exist(
    service, categories: list[str], prefix: str = "AutoTriage/"
) -> dict[str, str]:
    """Return {category_name: label_id}, creating labels as needed."""
    existing = {l["name"]: l["id"] for l in service.users().labels().list(userId="me").execute()["labels"]}
    label_map = {}
    for cat in categories:
        full_name = f"{prefix}{cat}"
        if full_name in existing:
            label_map[cat] = existing[full_name]
        else:
            created = service.users().labels().create(
                userId="me", body={"name": full_name, "labelListVisibility": "labelShow", "messageListVisibility": "show"}
            ).execute()
            label_map[cat] = created["id"]
    return label_map
```

### Pattern 3: Structured LLM Output
**What:** Ask the LLM for JSON output with a strict schema, not free-text.
**When:** Every classification call.
**Why:** Eliminates parsing ambiguity. JSON mode (available in Gemini, OpenAI, etc.) ensures parseable responses. Fallback to regex extraction if JSON mode unavailable.
```python
CLASSIFICATION_PROMPT = """You are an email classifier. Classify the following email into exactly one category.

Categories:
{categories_with_descriptions}

Email:
From: {sender}
Subject: {subject}
Snippet: {snippet}

Respond with ONLY a JSON object:
{{"category": "<category_name>", "confidence": "<high|medium|low>"}}
"""
```
**Important:** Include category descriptions (not just names) so the LLM understands what each category means. These descriptions come from the YAML config.

### Pattern 4: Batching LLM Calls
**What:** Classify multiple emails in a single LLM prompt when possible.
**When:** When processing more than ~5 emails.
**Why:** Reduces API calls, latency, and cost. Most LLMs handle batch classification well within context windows.
**Tradeoff:** Batch classification is slightly less accurate than one-by-one. Start with individual calls, optimize to batching later if volume warrants it.
```python
# Single-email first (simpler, more reliable), batch later as optimization
BATCH_PROMPT = """Classify each email into exactly one category.
Categories: {categories_with_descriptions}

Emails:
{numbered_emails}

Respond with a JSON array:
[{{"id": 1, "category": "...", "confidence": "..."}}, ...]
"""
```

### Pattern 5: Conservative Gmail API Usage
**What:** Use minimal scopes, metadata-only fetches, and read+label operations only.
**When:** All Gmail interactions.
**Why:** Security (minimal permissions), performance (metadata is much smaller than full body), and safety (no destructive actions).
```python
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",  # read + label + send
]
# Note: gmail.modify is needed for both labeling AND sending the notification email.
# gmail.labels is not a separate scope — it's included in gmail.modify.
# Do NOT use gmail.full — it's unnecessary and grants delete access.
```

### Pattern 6: Gmail API Pagination
**What:** The messages.list endpoint returns pages of message IDs. Paginate until all unread messages are collected.
**When:** Fetching unread emails.
**Why:** Gmail returns max 100 message IDs per page (configurable up to 500). A busy inbox may have more unread emails.
```python
def fetch_all_unread_ids(service) -> list[str]:
    """Paginate through all unread message IDs."""
    ids = []
    request = service.users().messages().list(userId="me", q="is:unread", maxResults=500)
    while request:
        response = request.execute()
        ids.extend(m["id"] for m in response.get("messages", []))
        request = service.users().messages().list_next(request, response)
    return ids
```

### Pattern 7: Gmail Batch API for Message Retrieval
**What:** Use the Python client's `BatchHttpRequest` to fetch multiple messages in a single HTTP call.
**When:** After collecting message IDs, when fetching metadata for each message.
**Why:** Fetching 50 messages individually = 50 HTTP requests. Batching = 1 HTTP request. Gmail supports up to 100 requests per batch.
```python
def fetch_messages_batch(service, message_ids: list[str]) -> list[dict]:
    """Fetch message metadata in batches of 100."""
    results = []

    def callback(request_id, response, exception):
        if exception:
            logger.error(f"Failed to fetch {request_id}: {exception}")
        else:
            results.append(response)

    for chunk in chunked(message_ids, 100):
        batch = service.new_batch_http_request(callback=callback)
        for msg_id in chunk:
            batch.add(
                service.users().messages().get(
                    userId="me", id=msg_id,
                    format="metadata",
                    metadataHeaders=["From", "Subject", "Date"]
                ),
                request_id=msg_id
            )
        batch.execute()
    return results
```

## Anti-Patterns to Avoid

### Anti-Pattern 1: Fetching Full Email Bodies
**What:** Using `format="full"` or `format="raw"` when fetching messages.
**Why bad:** Full bodies are 10-100x larger than metadata. For classification, subject + sender + snippet is almost always sufficient. Full bodies also contain HTML, attachments (base64), and multipart MIME — all noise for classification.
**Instead:** Use `format="metadata"` with `metadataHeaders=["From", "Subject", "Date"]`. The `snippet` field (first ~200 chars of body text) is always included and provides enough context. Only fetch full body if classification confidence is low and a retry with more context is warranted.

### Anti-Pattern 2: Global Try/Except Swallowing Errors
**What:** Wrapping the entire script in a try/except that catches Exception and logs it.
**Why bad:** Hides individual email failures. A single malformed email kills the entire batch. Auth failures look like classification failures.
**Instead:** Error handling at each stage with per-email error isolation:
```python
for email in emails:
    try:
        result = classify(email)
        apply_label(email, result)
        successes.append(result)
    except ClassificationError as e:
        logger.warning(f"Failed to classify {email.id}: {e}")
        failures.append((email, e))
    except GmailApiError as e:
        logger.error(f"Failed to label {email.id}: {e}")
        failures.append((email, e))
# Continue processing remaining emails even if some fail
```

### Anti-Pattern 3: Storing OAuth Tokens in the Config File
**What:** Mixing OAuth2 tokens/credentials with the categories YAML or embedding them in the script.
**Why bad:** Tokens rotate. Config is version-controlled. Mixing concerns.
**Instead:** `token.json` in a separate location (e.g., `~/.config/email-triage/token.json`). `credentials.json` (the OAuth client secret) also separate. Config YAML contains only categories and settings.

### Anti-Pattern 4: LLM Prompt Without Examples
**What:** Giving the LLM category names without descriptions or examples.
**Why bad:** Category names alone are ambiguous. "Finance" could mean personal banking, invoices, investment newsletters, or salary notifications. The LLM will interpret differently than the user intends.
**Instead:** Each category in YAML should have a description and optionally example senders/subjects:
```yaml
categories:
  - name: "Finance"
    description: "Banking notifications, credit card alerts, investment updates, invoices"
    examples:
      - "from:noreply@bank.com"
      - "subject:Your statement is ready"
```

### Anti-Pattern 5: Creating a Local Database for State
**What:** Adding SQLite or a JSON file to track which emails have been processed.
**Why bad:** Introduces sync problems (DB says processed, but label wasn't applied due to API failure). Gmail labels already provide this state. Adds backup/corruption concerns.
**Instead:** Gmail labels are the single source of truth. Idempotency check = "does this email have a triage label?" If yes, skip.

## Module Structure

Recommended project layout:

```
email_fetch/
+-- pyproject.toml              # Project metadata, dependencies
+-- categories.yaml             # User-editable category definitions
+-- src/
|   +-- email_triage/
|       +-- __init__.py
|       +-- __main__.py         # Entry point: python -m email_triage
|       +-- cli.py              # Argument parsing, orchestration
|       +-- config.py           # YAML loading, validation, defaults
|       +-- auth.py             # OAuth2 flow, token refresh
|       +-- gmail_client.py     # Gmail API wrapper (fetch, label, send)
|       +-- classifier.py       # LLM prompt building, API call, response parsing
|       +-- notifier.py         # Summary email construction
|       +-- models.py           # Dataclasses: EmailData, ClassificationResult, etc.
+-- tests/
|   +-- test_config.py
|   +-- test_classifier.py
|   +-- test_gmail_client.py
|   +-- test_notifier.py
+-- credentials/                # NOT version-controlled (.gitignore)
    +-- credentials.json        # OAuth2 client secret (from Google Cloud Console)
    +-- token.json              # Auto-generated refresh token
```

**Why `src/` layout:** Prevents accidental imports from the project root. Standard Python packaging practice. Makes `python -m email_triage` work cleanly.

## Gmail API Specifics

### Rate Limits (MEDIUM confidence - from training data)
- **Per-user rate limit:** 250 quota units per second per user
- **Daily limit:** 1 billion quota units per day (effectively unlimited for personal use)
- **Quota costs:** messages.list = 5 units, messages.get = 5 units, messages.modify = 5 units, labels.create = 5 units, messages.send = 100 units
- **Batch limit:** 100 requests per batch call
- **For context:** Processing 100 emails = ~100 list + 100 get + 100 modify = ~1500 quota units. Well within limits.

### Key API Design Decisions
1. **messages.list returns only IDs** — always need a second call (messages.get) for metadata
2. **Labels are global to the mailbox** — use a naming prefix to namespace triage labels
3. **messages.modify is additive** — can add labels without affecting existing ones
4. **Snippet is always returned** — no need to request it separately, present in both list and get responses

## OAuth2 Token Management

### Flow
```
First run:
  credentials.json -> InstalledAppFlow -> browser auth -> token.json (with refresh_token)

Subsequent runs:
  token.json -> Credentials.from_authorized_user_file()
  -> if expired: auto-refresh using refresh_token
  -> if refresh fails: re-run browser auth
```

### Critical Details
- **Offline access:** Request `access_type='offline'` to get a refresh token
- **Token storage:** `token.json` contains access_token, refresh_token, expiry. Auto-refreshed by the google-auth library.
- **Consent screen:** For personal use, app can stay in "Testing" mode in Google Cloud Console (no verification needed, but token expires every 7 days). For permanent use, publish the app or use a service account.
- **Token expiry in Testing mode:** This is a significant gotcha. Access tokens expire after 1 hour (auto-refreshed). But in Testing mode, the refresh token itself expires after 7 days, requiring manual re-authentication. To avoid this, publish the OAuth consent screen (it can still be "Internal" if using Google Workspace, or "External" with just your own account added as a test user and the app published).

## LLM Integration Architecture

### Prompt Design Principles
1. **System prompt:** Define role ("You are an email classifier")
2. **Categories with descriptions:** Not just names
3. **Input format:** Structured (From/Subject/Snippet), not raw email
4. **Output format:** Strict JSON schema
5. **Ambiguity handling:** Explicit "ambiguous" category as fallback
6. **Confidence signal:** Ask the LLM to self-report confidence

### Classifier Module Responsibilities
- Build prompt from template + config categories + email data
- Call LLM API with appropriate parameters (low temperature for consistency)
- Parse JSON response, validate category is in allowed list
- Handle parse failures gracefully (default to "ambiguous")
- Log token usage for cost monitoring

### LLM API Abstraction
The classifier should abstract the LLM provider behind a simple interface:
```python
class Classifier(Protocol):
    def classify(self, email: EmailData, categories: list[Category]) -> ClassificationResult: ...
```
This allows swapping Gemini for another provider without touching the rest of the codebase. However, do NOT over-engineer this with a full plugin system. A simple if/elif on a config value ("gemini", "openai") is sufficient for a personal tool.

## Configuration Schema (YAML)

```yaml
# categories.yaml
gmail:
  query: "is:unread"              # Gmail search query for target emails
  label_prefix: "AutoTriage/"     # Prefix for created labels
  max_emails: 100                 # Max emails to process per run

llm:
  provider: "gemini"              # gemini | openai
  model: "gemini-2.0-flash"      # Model identifier
  temperature: 0.1                # Low for consistency
  max_tokens: 100                 # Classification responses are short

notification:
  enabled: true
  send_to: "me"                   # "me" = same authenticated account

categories:
  - name: "Newsletter"
    description: "Recurring newsletters, digests, content roundups"
    examples:
      - "from:substack.com"
      - "subject:Weekly digest"

  - name: "Finance"
    description: "Bank alerts, credit card notifications, invoices, receipts"

  - name: "Social"
    description: "Social media notifications from LinkedIn, Twitter, etc."

  - name: "Shopping"
    description: "Order confirmations, shipping updates, promotional offers"

  - name: "Ambiguous"
    description: "Emails that don't clearly fit any other category. This is the fallback."
```

## Logging Architecture

### Approach: Python `logging` Module
- **Console handler:** INFO level for cron (captured in cron's mail or syslog)
- **No file handler:** Keep it simple. Cron already captures stdout/stderr.
- **Structured log format:** Include timestamp, level, email_id where applicable

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("email_triage")
```

### What to Log
- Start/end of run with email count
- Each classification result (email_id, category, confidence)
- API errors with context
- Summary stats (processed, classified, failed, skipped)
- Token usage / cost (if available from LLM API)

### Notification Email vs Logging
The notification email (sent to self) is NOT a replacement for logging. It is a user-facing summary. Logging is for debugging. They serve different purposes:
- **Notification email:** "12 emails classified: 5 Newsletter, 3 Finance, 2 Social, 1 Shopping, 1 Ambiguous"
- **Logs:** "2026-03-07 08:00:01 [INFO] Classified msg_id=18e3f2a: Newsletter (high confidence)"

## Error Handling Flow

```
Pipeline Stage         Error Type              Handling
----------------------------------------------------------------------
Config loading         FileNotFoundError       EXIT 1 with clear message
                       ValidationError         EXIT 1 with clear message

Authentication         Token refresh fail      Prompt re-auth (if interactive)
                       No credentials.json     EXIT 1 with setup instructions

Fetch emails           API quota exceeded      EXIT 1, suggest retry later
                       Network error           Retry 3x with backoff, then EXIT 1

Classify               LLM API error           Retry 2x, then mark "ambiguous"
                       Parse error             Mark "ambiguous", log warning
                       Rate limit              Backoff and retry

Apply labels           API error               Log, continue with next email
                       Label creation fail     EXIT 1 (label setup is prerequisite)

Send notification      API error               Log warning, don't fail the run
                       (notification is best-effort)
```

**Key principle:** Per-email errors should not abort the entire run. Infrastructure errors (auth, config, label setup) should abort immediately.

## Scalability Considerations

| Concern | At 10 emails/run | At 100 emails/run | At 500 emails/run |
|---------|-------------------|--------------------|--------------------|
| Gmail API | Negligible | 1 batch fetch, well within quota | 5 batch fetches, still fine |
| LLM cost | ~0.001 USD (Gemini Flash) | ~0.01 USD | Consider batch prompts |
| Runtime | ~5 seconds | ~30 seconds | ~2 minutes, consider async |
| Memory | Negligible | Negligible | Still negligible (metadata only) |

**Realistic volume:** For a personal inbox with cron running 3-4x/day, expect 10-50 emails per run. The architecture handles this trivially. No need to optimize for scale beyond this.

## Build Order (Dependencies)

The components should be built in this order based on dependencies:

```
1. models.py          (no dependencies — pure data structures)
2. config.py          (depends on: models)
3. auth.py            (depends on: nothing — standalone OAuth2)
4. gmail_client.py    (depends on: auth, models)
5. classifier.py      (depends on: config, models)
6. notifier.py        (depends on: gmail_client, models)
7. cli.py / main      (depends on: everything — orchestration)
```

**Implication for phases:**
- Phase 1 should cover models + config + auth + basic gmail_client (fetch). This gives a working "read emails" pipeline.
- Phase 2 should cover classifier + label application. This gives classification.
- Phase 3 should cover notifier + cli polish + cron setup. This gives the full loop.

Each phase produces a testable, runnable artifact.

## Sources

- Gmail API documentation (developers.google.com/gmail/api) — MEDIUM confidence (from training data, not live-verified)
- Google Auth Library for Python patterns — MEDIUM confidence (from training data)
- LLM classification prompt design — MEDIUM confidence (from training data + community patterns)
- Python project structure best practices — HIGH confidence (well-established conventions)
