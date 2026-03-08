# Phase 2: Classification - Research

**Researched:** 2026-03-08
**Domain:** LLM classification (Gemini Flash), Gmail label management, structured JSON output
**Confidence:** HIGH

## Summary

Phase 2 transforms the fetch-only pipeline into a full classification loop: each unread email is sent to Gemini Flash for classification, receives a structured JSON response with categories and confidence scores, and gets labeled in Gmail accordingly. The domain breaks into three technical areas: (1) Google GenAI SDK for structured LLM output, (2) Gmail API label management (create, list, apply), and (3) orchestration logic (idempotency, dry-run, fuzzy matching).

The Google GenAI SDK (`google-genai`) is the current official Python SDK, replacing the legacy `google-generativeai` package. It supports Pydantic-based response schemas natively, making structured JSON output straightforward. Gmail label management uses the existing `google-api-python-client` already in the project -- nested labels are created with `/` in the name (e.g., `AutoTriage/Newsletter`). The `gmail.modify` scope already configured in Phase 1 covers all label operations.

**Primary recommendation:** Use `google-genai` with Pydantic response schema for classification, reuse existing Gmail service for label operations, and add `rapidfuzz` for fuzzy category matching. Keep classification and labeling as separate, testable modules.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- Each message is classified individually -- no thread grouping before LLM call
- Every unread message goes to the LLM independently, regardless of thread membership
- LLM decides freely whether to return 1 or 2 labels per email based on content
- If LLM returns a category name not in `categories.yaml`, apply fuzzy match to existing categories; if no match, treat as "ambiguous"
- Default confidence threshold: 0.5 (50%) -- configurable in `categories.yaml`
- Labels below threshold are discarded (not kept as secondary)
- If both labels are below threshold, email receives "ambiguous" label
- Idempotency check at message level: if a message already has any `AutoTriage/*` label, skip it entirely
- New messages in an already-triaged thread are still classified independently
- Label prefix: `AutoTriage/` -- hardcoded, not configurable
- Ambiguous label: `AutoTriage/_Ambiguous` -- underscore prefix sorts it to top
- `--dry-run` performs real LLM classification but does not apply labels in Gmail
- Summary counts always shown at end of run: classified, ambiguous, skipped

### Claude's Discretion
- Thread context assembly strategy for the LLM prompt (how much of the thread to send per message)
- Dry-run output format and verbosity level
- Whether to offer a `--no-llm` mock mode for testing without API calls
- Fuzzy matching algorithm for category name mismatches
- Structured JSON output schema design for Gemini Flash

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| CLASS-01 | LLM-based classification using Gemini Flash with structured JSON output | Google GenAI SDK `response_schema` with Pydantic models; `gemini-2.5-flash` model |
| CLASS-02 | Fallback "ambiguous" label for unclassifiable emails | Schema design returns categories list; empty/low-confidence maps to `AutoTriage/_Ambiguous` |
| CLASS-03 | LLM confidence score threshold -- below threshold maps to ambiguous | Pydantic schema includes `confidence: float` per category; threshold from config |
| CLASS-04 | Multi-label support (email can receive 1-2 category labels) | Schema returns `list[Classification]` with max 2 items; Gmail API supports multiple `addLabelIds` |
| CLASS-05 | Thread-aware classification (classify by conversation thread) | CONTEXT.md overrides: per-message classification, not thread-based. Claude's discretion on thread context in prompt |
| LABL-01 | Apply Gmail labels based on classification result | `messages().modify(addLabelIds=[...])` -- 5 quota units per call |
| LABL-02 | Auto-create labels in Gmail if they don't exist | `labels().create(body={'name': 'AutoTriage/Category'})` -- parent must exist first |
| LABL-03 | Label namespacing with prefix `AutoTriage/` | Hardcoded prefix; Gmail renders `/` as nested folder hierarchy |
| LABL-04 | Idempotency -- skip emails already bearing any triage label | Check `label_ids` on EmailData against cached `AutoTriage/*` label IDs |
| OPS-06 | Dry-run mode -- process and classify without applying labels | `--dry-run` flag skips `messages().modify()` calls; prints classification results |

</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| google-genai | >=1.66.0 | Gemini Flash API client | Official Google GenAI SDK; replaces legacy `google-generativeai`; native Pydantic schema support |
| google-api-python-client | >=2.192.0 | Gmail label management | Already in project from Phase 1; covers labels.create/list, messages.modify |
| rapidfuzz | >=3.12.0 | Fuzzy string matching for category names | MIT license, 5-100x faster than thefuzz, C++ backend, drop-in API |
| pydantic | >=2.12.5 | LLM response schema definition | Already in project; GenAI SDK accepts Pydantic models for `response_schema` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| python-dotenv | >=1.2.2 | Load GEMINI_API_KEY from .env | Already in project; use for API key management |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| google-genai | google-generativeai | Legacy SDK, no longer recommended by Google |
| rapidfuzz | thefuzz | GPL license, 5-100x slower, no C++ backend |
| rapidfuzz | difflib.SequenceMatcher | stdlib but much slower, less accurate for short strings |
| Pydantic response_schema | raw JSON mode + manual parsing | More error-prone, no type safety, no validation |

**Installation:**
```bash
uv add google-genai rapidfuzz
```

Note: `pydantic`, `google-api-python-client`, and `python-dotenv` are already in pyproject.toml.

## Architecture Patterns

### Recommended Project Structure
```
src/email_triage/
  __init__.py
  __main__.py
  auth.py            # [existing] OAuth2
  cli.py             # [modify] Add --dry-run flag, integrate classify+label pipeline
  config.py          # [modify] Add confidence_threshold to config model
  gmail.py           # [existing] Fetch operations (read-only)
  labels.py          # [NEW] Gmail label management (create, list, apply, idempotency check)
  classifier.py      # [NEW] Gemini Flash classification with structured output
  models.py          # [modify] Add ClassificationResult dataclass
  output.py          # [modify] Add classification summary formatting
```

### Pattern 1: Pydantic Response Schema for Gemini Flash
**What:** Define a Pydantic model that describes the expected LLM output; pass it directly to `generate_content` via `response_schema`.
**When to use:** Every classification call.
**Example:**
```python
# Source: https://googleapis.github.io/python-genai/
from pydantic import BaseModel, Field
from google.genai import types

class CategoryClassification(BaseModel):
    """A single category assignment with confidence."""
    category: str = Field(description="Category name from the provided list")
    confidence: float = Field(description="Confidence score between 0.0 and 1.0")

class ClassificationResponse(BaseModel):
    """LLM classification result for an email."""
    categories: list[CategoryClassification] = Field(
        description="1-2 category assignments, ordered by confidence",
        max_length=2,
    )
    reasoning: str = Field(description="Brief explanation of classification decision")

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=prompt,
    config=types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=ClassificationResponse,
        temperature=0.1,  # Low temperature for consistent classification
    ),
)
result = ClassificationResponse.model_validate_json(response.text)
```

### Pattern 2: Label Cache + Ensure Pattern
**What:** On startup, fetch all existing labels once; cache them by name. When applying a label, check cache first, create if missing, then apply.
**When to use:** Every label operation to avoid redundant API calls.
**Example:**
```python
# Source: https://developers.google.com/workspace/gmail/api/guides/labels
LABEL_PREFIX = "AutoTriage/"

def list_triage_labels(service) -> dict[str, str]:
    """Fetch all AutoTriage/* labels, return {name: id} mapping."""
    result = service.users().labels().list(userId="me").execute()
    labels = result.get("labels", [])
    return {
        label["name"]: label["id"]
        for label in labels
        if label["name"].startswith(LABEL_PREFIX)
    }

def ensure_label(service, name: str, cache: dict[str, str]) -> str:
    """Get or create a label, updating cache. Returns label ID."""
    full_name = f"{LABEL_PREFIX}{name}"
    if full_name in cache:
        return cache[full_name]

    # Ensure parent exists first
    if LABEL_PREFIX.rstrip("/") not in cache:
        parent = service.users().labels().create(
            userId="me",
            body={"name": LABEL_PREFIX.rstrip("/"),
                  "labelListVisibility": "labelShow",
                  "messageListVisibility": "show"},
        ).execute()
        cache[parent["name"]] = parent["id"]

    # Create child label
    label = service.users().labels().create(
        userId="me",
        body={"name": full_name,
              "labelListVisibility": "labelShow",
              "messageListVisibility": "show"},
    ).execute()
    cache[label["name"]] = label["id"]
    return label["id"]
```

### Pattern 3: Idempotency Check via Label IDs
**What:** Before classifying an email, check if it already has any `AutoTriage/*` label ID. Skip if so.
**When to use:** Every email in the pipeline.
**Example:**
```python
def is_already_triaged(email: EmailData, triage_label_ids: set[str]) -> bool:
    """Check if email already has any AutoTriage label."""
    return bool(set(email.label_ids) & triage_label_ids)
```
Note: `email.label_ids` already contains Gmail label IDs from Phase 1's `parse_message()`.

### Pattern 4: Prompt Assembly with Category Context
**What:** Build the classification prompt with category names, descriptions, and few-shot examples from `categories.yaml`.
**When to use:** Each LLM call.
**Example:**
```python
def build_classification_prompt(
    email: EmailData,
    categories: list[CategoryConfig],
) -> str:
    """Build prompt for Gemini Flash classification."""
    category_section = "\n".join(
        f"- **{cat.name}**: {cat.description}\n"
        f"  Examples: {', '.join(cat.examples)}"
        for cat in categories
    )
    return f"""Classify this email into 1-2 of the following categories.
Return confidence scores (0.0-1.0) for each assigned category.

## Available Categories
{category_section}

## Email to Classify
From: {email.sender}
Subject: {email.subject}
Snippet: {email.snippet}

Classify this email. Assign only categories that genuinely apply.
If unsure, use lower confidence scores."""
```

### Anti-Patterns to Avoid
- **Calling labels.list() per email:** Fetch once at startup, cache the mapping. labels.list costs 1 quota unit but is still unnecessary per-message overhead.
- **Creating parent+child in one call:** Gmail requires the parent label to exist before creating `AutoTriage/Newsletter`. Always create `AutoTriage` first, then `AutoTriage/Newsletter`.
- **Hardcoding model name deep in code:** Use a constant or config value for `gemini-2.5-flash` -- model names change across versions.
- **High temperature for classification:** Use `temperature=0.1` or lower. High temperature causes inconsistent classifications.
- **Parsing LLM text output manually:** Always use `response_schema` with Pydantic -- never parse free-text JSON from LLM.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Fuzzy string matching | Custom Levenshtein/edit distance | `rapidfuzz.fuzz.ratio()` or `rapidfuzz.process.extractOne()` | Edge cases in Unicode, performance, threshold tuning |
| JSON schema for LLM | Manual JSON schema dict | Pydantic `BaseModel` + `response_schema` param | GenAI SDK converts Pydantic to schema automatically |
| LLM response parsing | `json.loads()` + manual validation | `ClassificationResponse.model_validate_json()` | Type safety, validation errors, nested objects |
| Label existence check | Scan label list with string comparison | Dict cache with `ensure_label()` pattern | O(1) lookup, avoids repeated API calls |

**Key insight:** The GenAI SDK's native Pydantic integration eliminates the entire "parse LLM output" problem space. Define the schema, get validated objects back. No regex, no JSON parsing, no retry-on-malformed-output.

## Common Pitfalls

### Pitfall 1: Parent Label Must Exist Before Child
**What goes wrong:** Creating `AutoTriage/Newsletter` when `AutoTriage` doesn't exist returns a 400 error from Gmail API.
**Why it happens:** Gmail API requires parent labels to exist before creating nested children.
**How to avoid:** Always check/create the parent `AutoTriage` label first in the `ensure_label()` function.
**Warning signs:** `HttpError 400 "Invalid label name"` on first run.

### Pitfall 2: Label IDs vs Label Names
**What goes wrong:** Using label names (e.g., `"AutoTriage/Newsletter"`) in `addLabelIds` -- API expects label IDs (e.g., `"Label_123"`).
**Why it happens:** Confusion between display name and internal ID.
**How to avoid:** Always resolve name to ID via the label cache before calling `messages.modify()`.
**Warning signs:** `HttpError 400 "Invalid label"` when applying labels.

### Pitfall 3: Gemini Free Tier Rate Limits
**What goes wrong:** 429 errors when classifying many emails in rapid succession.
**Why it happens:** Free tier allows ~15 RPM for Gemini 2.5 Flash. 100 emails at 1 request each = ~7 minutes minimum.
**How to avoid:** Add simple delay between calls (e.g., `time.sleep(4)` for ~15 RPM). Phase 3 will add proper exponential backoff -- for now, a fixed delay is sufficient.
**Warning signs:** `google.genai.errors.APIError` with code 429.

### Pitfall 4: API Key Not Set
**What goes wrong:** Client initialization fails silently or with cryptic error.
**Why it happens:** User forgets to add `GEMINI_API_KEY` to `.env` file.
**How to avoid:** Validate API key presence at startup (fail-fast), print clear error message with setup instructions.
**Warning signs:** `APIError` with authentication-related message on first `generate_content` call.

### Pitfall 5: Pydantic Schema Constraints Ignored by LLM
**What goes wrong:** LLM returns 3+ categories despite `max_length=2` in schema.
**Why it happens:** `max_length` in Pydantic is a Python-side validation constraint; Gemini's structured output respects JSON Schema `maxItems` but behavior can vary.
**How to avoid:** Include the constraint explicitly in the prompt text ("assign 1 or 2 categories maximum") AND in the schema. Validate response and truncate if needed.
**Warning signs:** `ValidationError` from Pydantic on response parsing.

### Pitfall 6: Gmail Label Quota Accumulation
**What goes wrong:** Hitting 15,000 quota units/min on large mailboxes.
**Why it happens:** `messages.modify` = 5 units, `labels.create` = 5 units. 100 emails = 500 quota units for modify alone -- well within limits. But combined with list/fetch operations from Phase 1, monitor total.
**How to avoid:** With 100 emails max and ~10 label operations, quota is not a concern for this use case. No special handling needed.
**Warning signs:** Only relevant if max_emails increases significantly beyond 100.

### Pitfall 7: Duplicate Label Creation Race Condition
**What goes wrong:** Two runs create the same label simultaneously, one fails.
**Why it happens:** Not applicable for single-user CLI tool, but worth noting for future.
**How to avoid:** The `ensure_label()` pattern with cache handles this. On `HttpError 409 Conflict`, re-fetch label list.
**Warning signs:** `HttpError 409` on `labels.create`.

## Code Examples

### Complete Classification Flow
```python
# Source: https://googleapis.github.io/python-genai/ + https://ai.google.dev/gemini-api/docs/structured-output
from google import genai
from google.genai import types, errors

def classify_email(
    client: genai.Client,
    email: EmailData,
    categories: list[CategoryConfig],
    model: str = "gemini-2.5-flash",
) -> ClassificationResponse:
    """Classify a single email using Gemini Flash."""
    prompt = build_classification_prompt(email, categories)

    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ClassificationResponse,
            temperature=0.1,
            system_instruction=(
                "You are an email classifier. Assign each email to 1-2 categories "
                "from the provided list. Be precise with confidence scores."
            ),
        ),
    )
    return ClassificationResponse.model_validate_json(response.text)
```

### Apply Labels to Message
```python
# Source: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/modify
def apply_labels(service, message_id: str, label_ids: list[str]) -> None:
    """Apply one or more labels to a Gmail message."""
    service.users().messages().modify(
        userId="me",
        id=message_id,
        body={"addLabelIds": label_ids},
    ).execute()
```

### Fuzzy Match Category Name
```python
# Source: https://github.com/rapidfuzz/RapidFuzz
from rapidfuzz import process, fuzz

def fuzzy_match_category(
    llm_category: str,
    valid_categories: list[str],
    threshold: int = 70,
) -> str | None:
    """Match an LLM-returned category name to valid categories.

    Returns the best match if score >= threshold, else None (-> ambiguous).
    """
    result = process.extractOne(
        llm_category,
        valid_categories,
        scorer=fuzz.ratio,
        score_cutoff=threshold,
    )
    return result[0] if result else None
```

### Config Extension for Confidence Threshold
```python
# Extend existing AppConfig in config.py
class ClassificationConfig(BaseModel):
    """Classification settings."""
    confidence_threshold: float = 0.5
    model: str = "gemini-2.5-flash"

class AppConfig(BaseModel):
    """Top-level application configuration."""
    categories: list[CategoryConfig]
    fetch: FetchConfig = FetchConfig()
    classification: ClassificationConfig = ClassificationConfig()
```

### GenAI Client Initialization with Fail-Fast
```python
import os
from google import genai

def create_genai_client() -> genai.Client:
    """Create Gemini client with API key from environment."""
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise SystemExit(
            "GEMINI_API_KEY not set. Get one at https://aistudio.google.com/apikey "
            "and add it to your .env file."
        )
    return genai.Client(api_key=api_key)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `google-generativeai` SDK | `google-genai` SDK | 2025 | Unified SDK for AI Studio + Vertex AI; legacy SDK no longer recommended |
| Manual JSON parsing of LLM output | `response_schema` with Pydantic | 2025 | Eliminates parsing errors; SDK handles JSON Schema conversion |
| `gemini-1.5-flash` | `gemini-2.5-flash` | 2025 | Better structured output support, faster, cheaper |
| `thefuzz` (GPL) | `rapidfuzz` (MIT) | 2020+ | 5-100x faster, MIT license, more string metrics |
| `response_json_schema` (dict) | `response_schema` (Pydantic model) | 2025 | Direct Pydantic model support, no manual schema conversion needed |

**Deprecated/outdated:**
- `google-generativeai`: Legacy package, use `google-genai` instead
- `fuzzywuzzy`: Deprecated predecessor of `thefuzz`, which itself is superseded by `rapidfuzz`
- `gemini-pro` / `gemini-1.0-pro`: Older models, use `gemini-2.5-flash` for classification tasks

## Discretion Recommendations

### Thread Context in Prompt
**Recommendation:** Don't include thread context. Each email already has subject, sender, and snippet -- sufficient for classification. Thread context would require additional API calls (fetching other messages in the thread) and add complexity without proportional benefit for categorization. The user's decision to classify per-message already simplifies this.

### Dry-Run Output Format
**Recommendation:** Use a simple text table format with columns: `Subject (truncated) | Categories | Confidence | Action`. Print summary counts at the end. JSON output adds complexity without user benefit for a CLI tool.

### Mock LLM Mode (--no-llm)
**Recommendation:** Yes, implement `--no-llm` flag. Assign a deterministic mock category (e.g., round-robin from configured categories with confidence 0.8). Essential for testing label operations without burning Gemini API quota. Keep it simple -- not a full mock LLM, just deterministic category assignment.

### Fuzzy Matching Algorithm
**Recommendation:** Use `rapidfuzz.process.extractOne()` with `fuzz.ratio` scorer and a cutoff of 70. This handles common LLM mistakes (case differences, plurals, minor typos). If no match at 70+, treat as ambiguous.

### Structured JSON Schema Design
**Recommendation:** Use the `ClassificationResponse` schema shown in Code Examples above. Two-level structure: top-level response with `categories` list (max 2) and `reasoning` string. Each category has `category` name and `confidence` float. The `reasoning` field helps with debugging but is not stored or displayed by default.

## Open Questions

1. **Gemini 2.5 Flash free tier exact RPM for current date**
   - What we know: Web sources cite ~15 RPM free tier, but Google notes "rate limits depend on a variety of factors"
   - What's unclear: Exact current limits may have changed since December 2025 quota adjustments
   - Recommendation: Handle 429 with a simple retry/delay. Start with 4-second delay between calls. Verify in practice.

2. **Gmail API error on duplicate label creation**
   - What we know: Creating a label that already exists likely returns 409 Conflict
   - What's unclear: Exact error code and message not verified in official docs
   - Recommendation: Wrap `labels.create()` in try/except, on conflict re-fetch label list and return existing ID.

## Sources

### Primary (HIGH confidence)
- [Google GenAI SDK docs](https://googleapis.github.io/python-genai/) - structured output, client config, error handling
- [Gemini API structured output](https://ai.google.dev/gemini-api/docs/structured-output) - response_schema, Pydantic support, model list
- [Gmail API labels guide](https://developers.google.com/workspace/gmail/api/guides/labels) - label types, management
- [Gmail API quota reference](https://developers.google.com/workspace/gmail/api/reference/quota) - per-method quota units
- [Gmail API messages.modify](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/modify) - addLabelIds, scopes
- [google-genai PyPI](https://pypi.org/project/google-genai/) - v1.66.0, Python >=3.10

### Secondary (MEDIUM confidence)
- [python-genai GitHub](https://github.com/googleapis/python-genai) - client initialization, environment variables
- [RapidFuzz GitHub](https://github.com/rapidfuzz/RapidFuzz) - API, performance comparison
- [Nested label creation gist](https://gist.github.com/SyedaMahamFahim/71959d5697aabf42c216f1223d6b30c8) - parent-before-child pattern

### Tertiary (LOW confidence)
- [Gemini free tier blog posts](https://www.aifreeapi.com/en/posts/google-gemini-api-free-tier) - rate limits may vary; verify in practice

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - official SDK docs, PyPI verified, well-documented APIs
- Architecture: HIGH - patterns derived from official docs and existing codebase
- Pitfalls: HIGH - Gmail label quirks well-documented; Gemini rate limits MEDIUM (may vary)

**Research date:** 2026-03-08
**Valid until:** 2026-04-08 (stable APIs, 30-day validity)
