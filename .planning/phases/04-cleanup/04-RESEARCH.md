# Phase 4: Cleanup & Tech Debt - Research

**Researched:** 2026-03-09
**Domain:** Python codebase maintenance, google-genai SDK token usage, pytest test isolation
**Confidence:** HIGH

## Summary

Phase 4 is a focused tech debt closure phase with 5 well-defined success criteria, all derived from the v1.0 milestone audit. The work is entirely internal refactoring and bug fixes -- no new features, no new dependencies, no architectural changes. Every change target has been inspected in the source code and the root causes are fully understood.

The primary technical challenge is extracting token usage from the google-genai SDK response. The `GenerateContentResponse.usage_metadata` attribute is well-documented and contains `prompt_token_count` and `candidates_token_count` (completion tokens). The data flow needs to be extended: `classify_email()` must return token counts alongside the classification result, and `cli.py` must accumulate them into `RunStats`.

The test isolation fix is straightforward: `load_dotenv()` in `create_genai_client()` re-reads `.env` after `patch.dict` clears `os.environ`, leaking real API keys. The fix is to also mock `load_dotenv` or patch it as a no-op in the affected tests.

**Primary recommendation:** All 5 items are independent, low-risk changes. A single plan with 5 tasks (one per success criterion) is sufficient. Total effort: ~15-20 minutes.

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| NOTF-02 | Statistics in summary email (per-category breakdown, error count, token usage estimate) | Token usage extraction pattern from google-genai SDK `response.usage_metadata` documented in detail. Fields: `prompt_token_count`, `candidates_token_count`. Data flow: classifier.py -> cli.py -> RunStats -> notify.py already wired for rendering, only extraction missing. |

</phase_requirements>

## Standard Stack

### Core (already installed -- no new dependencies)

| Library | Version | Purpose | Relevant to Phase 4 |
|---------|---------|---------|---------------------|
| google-genai | 1.66.0 | Gemini API client | `response.usage_metadata` for token counts |
| pytest | (installed) | Test framework | Fixing test isolation |
| python-dotenv | (installed) | .env loading | Root cause of test isolation bug |

### No New Dependencies

This phase requires zero new libraries. All changes are to existing code using existing APIs.

## Architecture Patterns

### Pattern 1: Token Usage Data Flow

**What:** Extract token usage from Gemini API response and propagate through the pipeline.

**Current flow (broken):**
```
classifier.py: _generate_content_with_retry() -> response (usage_metadata ignored)
                                                 -> ClassificationResult (no token data)
cli.py:        classify_email() result -> stats (token fields stay 0)
notify.py:     stats.token_usage_prompt == 0 -> "N/A"
```

**Target flow (fixed):**
```
classifier.py: _generate_content_with_retry() -> response.usage_metadata extracted
                                                 -> return token counts alongside ClassificationResult
cli.py:        classify_email() -> accumulate token counts into RunStats
notify.py:     stats.token_usage_prompt > 0 -> renders real numbers
```

**Implementation approach:** `classify_email()` returns a tuple `(ClassificationResult, prompt_tokens, completion_tokens)` or a richer result object. The simplest approach is returning a tuple since `ClassificationResult` is a plain dataclass and adding fields to it is also clean.

**Key code reference (google-genai SDK v1.66.0, types.py):**
```python
# GenerateContentResponse has:
response.usage_metadata.prompt_token_count      # int | None
response.usage_metadata.candidates_token_count   # int | None (= completion tokens)
response.usage_metadata.total_token_count        # int | None
```

### Pattern 2: Test Isolation for load_dotenv

**What:** `create_genai_client()` calls `load_dotenv()` which reads `.env` file from disk, bypassing `os.environ` mocks.

**Root cause:** `patch.dict("os.environ", {}, clear=True)` clears runtime env vars, but `load_dotenv()` inside the function re-reads `.env` and re-populates them.

**Fix:** Mock `load_dotenv` as no-op in the affected tests:
```python
# Option A: patch load_dotenv to do nothing
with patch("email_triage.classifier.load_dotenv"):
    with patch.dict("os.environ", {}, clear=True):
        # load_dotenv won't re-populate from .env
        create_genai_client()

# Option B: Use monkeypatch.delenv + mock load_dotenv
```

### Pattern 3: Constant Substitution

**What:** Replace hardcoded `"_Ambiguous"` string in `cli.py` with `AMBIGUOUS_LABEL` constant from `labels.py`.

**Current code (cli.py L241):**
```python
label_id = ensure_label(service, "_Ambiguous", label_cache)
```

**Note:** `AMBIGUOUS_LABEL = "AutoTriage/_Ambiguous"` in labels.py, but `ensure_label()` prepends `LABEL_PREFIX` automatically. So the fix is not to use `AMBIGUOUS_LABEL` directly (which includes the prefix). Instead, extract just the suffix part, or define a new constant like `AMBIGUOUS_SUFFIX = "_Ambiguous"` in labels.py and use it in cli.py.

**Important subtlety:** `ensure_label(service, name, cache)` builds `full_name = f"{LABEL_PREFIX}{name}"`. So passing `"_Ambiguous"` produces `"AutoTriage/_Ambiguous"` which matches `AMBIGUOUS_LABEL`. The fix should define a constant for the suffix (e.g., `AMBIGUOUS_CATEGORY = "_Ambiguous"`) and use it, OR restructure `ensure_label` to accept full names. The simplest approach: add `AMBIGUOUS_CATEGORY = "_Ambiguous"` to labels.py and import it in cli.py.

### Anti-Patterns to Avoid

- **Changing `classify_email()` return type in a breaking way:** Existing tests mock the return value. If changing the return type, all existing tests and mocks must be updated.
- **Over-engineering the token usage:** Don't create a new `TokenUsage` dataclass just for two int fields. Add fields to `ClassificationResult` or return a simple tuple.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Token counting | Manual token estimation | `response.usage_metadata` from API | Actual usage is more accurate than estimation |
| Test env isolation | Complex fixture setup | `patch("email_triage.classifier.load_dotenv")` | One-line fix, addresses root cause |

## Common Pitfalls

### Pitfall 1: usage_metadata May Be None
**What goes wrong:** `response.usage_metadata` is `Optional`. Accessing `.prompt_token_count` on `None` raises `AttributeError`.
**Why it happens:** Edge cases in API responses, especially on errors or empty responses.
**How to avoid:** Always guard with `if response.usage_metadata:` before accessing fields. Also, individual fields are `Optional[int]`, so use `or 0` fallback.
**Warning signs:** `AttributeError: 'NoneType' has no attribute 'prompt_token_count'`

### Pitfall 2: candidates_token_count vs completion tokens
**What goes wrong:** Using the wrong field name. The SDK calls output tokens `candidates_token_count`, not `completion_token_count`.
**How to avoid:** Map `candidates_token_count` -> `token_usage_completion` in RunStats explicitly.

### Pitfall 3: Test Mock Must Match New Return Type
**What goes wrong:** If `classify_email()` return type changes (e.g., adds token fields to result), existing test mocks return the old shape, causing test failures.
**How to avoid:** Update all mocks in `test_classifier.py::TestClassifyEmail` to match the new return shape. Also update `test_cli_ops.py` if it mocks `classify_email`.

### Pitfall 4: load_dotenv Mock Scope
**What goes wrong:** Patching `dotenv.load_dotenv` instead of `email_triage.classifier.load_dotenv`. The mock must target the name as imported in the module under test.
**How to avoid:** Always patch `email_triage.classifier.load_dotenv` since that's where it's imported.

### Pitfall 5: ensure_label Name Construction
**What goes wrong:** Using `AMBIGUOUS_LABEL` ("AutoTriage/_Ambiguous") directly with `ensure_label()`, which would produce "AutoTriage/AutoTriage/_Ambiguous".
**How to avoid:** Define a separate constant for the suffix portion only (e.g., `AMBIGUOUS_CATEGORY = "_Ambiguous"`), or extract it from `AMBIGUOUS_LABEL` by stripping the prefix.

## Code Examples

### Token Usage Extraction from Gemini Response
```python
# Source: google-genai SDK v1.66.0 types.py + official docs
# https://ai.google.dev/gemini-api/docs/tokens

response = client.models.generate_content(model=model, contents=prompt, config=config)

# Safe extraction with None guards
prompt_tokens = 0
completion_tokens = 0
if response.usage_metadata:
    prompt_tokens = response.usage_metadata.prompt_token_count or 0
    completion_tokens = response.usage_metadata.candidates_token_count or 0
```

### Test Isolation Fix for load_dotenv
```python
# Source: unittest.mock standard library + python-dotenv behavior

class TestCreateGenaiClient:
    def test_missing_api_key_exits(self) -> None:
        with patch("email_triage.classifier.load_dotenv"):  # prevent .env loading
            with patch.dict("os.environ", {}, clear=True):
                with pytest.raises(SystemExit) as exc_info:
                    create_genai_client()
                assert "GEMINI_API_KEY" in str(exc_info.value)

    def test_google_api_key_fallback(self) -> None:
        with patch("email_triage.classifier.load_dotenv"):
            with patch.dict("os.environ", {"GOOGLE_API_KEY": "fallback-key"}, clear=True):
                with patch("email_triage.classifier.genai.Client") as mock_client:
                    create_genai_client()
                    mock_client.assert_called_once_with(api_key="fallback-key")
```

### AMBIGUOUS_CATEGORY Constant Pattern
```python
# In labels.py - add constant for the suffix
AMBIGUOUS_CATEGORY = "_Ambiguous"
AMBIGUOUS_LABEL = f"{LABEL_PREFIX}{AMBIGUOUS_CATEGORY}"

# In cli.py - import and use
from email_triage.labels import AMBIGUOUS_CATEGORY
# ...
label_id = ensure_label(service, AMBIGUOUS_CATEGORY, label_cache)
```

### Dead Code Removal (print_warn)
```python
# In output.py - simply remove lines 60-62:
# def print_warn(msg: str) -> None:
#     """Print a warning message to stderr with WARN color."""
#     print(Colors.warn(f"WARNING: {msg}"), file=sys.stderr)
```

## State of the Art

No changes in approach needed. This phase uses only established patterns from earlier phases.

| Item | Current State | Action |
|------|--------------|--------|
| google-genai SDK | v1.66.0 installed, usage_metadata available | Extract, don't estimate |
| RunStats model | Fields exist, initialized to 0 | Populate in cli.py loop |
| notify.py rendering | Already handles non-zero token counts | No changes needed |
| OPS-06 traceability | Already marked Complete in REQUIREMENTS.md | Verify, no action needed |

## File Impact Analysis

| File | Change | Risk |
|------|--------|------|
| `src/email_triage/classifier.py` | Return token usage from `classify_email()` | LOW - additive change |
| `src/email_triage/cli.py` | Accumulate token counts into RunStats, use AMBIGUOUS_CATEGORY constant | LOW - 3-line change |
| `src/email_triage/labels.py` | Add `AMBIGUOUS_CATEGORY` constant | LOW - additive, no behavior change |
| `src/email_triage/output.py` | Remove `print_warn` function | LOW - dead code, no callers |
| `tests/test_classifier.py` | Fix test isolation (mock load_dotenv), update mocks for new return shape | LOW - test-only |
| `.planning/REQUIREMENTS.md` | Update NOTF-02 traceability to Complete | LOW - docs only |

**No new files created. No files deleted (only function removal within output.py).**

## Open Questions

None. All success criteria have clear implementation paths with no ambiguity.

## Sources

### Primary (HIGH confidence)
- google-genai SDK v1.66.0 source code (`types.py` L7284-7414): `GenerateContentResponseUsageMetadata` class with `prompt_token_count`, `candidates_token_count` fields
- Project source code: all target files read and analyzed directly
- Milestone audit: `.planning/v1.0-MILESTONE-AUDIT.md` -- gap analysis and tech debt inventory

### Secondary (MEDIUM-HIGH confidence)
- [Google AI for Developers - Token docs](https://ai.google.dev/gemini-api/docs/tokens) -- confirms `response.usage_metadata` pattern with Python examples

## Metadata

**Confidence breakdown:**
- Token usage extraction: HIGH -- verified in installed SDK source AND official docs
- Test isolation fix: HIGH -- root cause confirmed by running failing tests, fix verified against Python mock documentation
- AMBIGUOUS_CATEGORY constant: HIGH -- code inspection confirms `ensure_label` prefixing behavior
- Dead code removal: HIGH -- grep confirms zero callers of `print_warn`
- OPS-06 traceability: HIGH -- already marked Complete in current REQUIREMENTS.md

**Research date:** 2026-03-09
**Valid until:** indefinite (stable patterns, no version-sensitive findings)
