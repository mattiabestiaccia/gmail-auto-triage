"""Data models for email triage."""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, Field


@dataclass
class EmailData:
    """Parsed email data from Gmail API response.

    Simple dataclass (not pydantic) because it represents API response data,
    not validated configuration.
    """

    id: str
    thread_id: str
    sender: str
    subject: str
    date: str
    snippet: str
    label_ids: list[str]


# ---------------------------------------------------------------------------
# Pydantic models for Gemini Flash structured output (response_schema)
# ---------------------------------------------------------------------------


class CategoryClassification(BaseModel):
    """A single category assignment with confidence score."""

    category: str = Field(description="Category name from the provided list")
    confidence: float = Field(description="Confidence score between 0.0 and 1.0")


class ClassificationResponse(BaseModel):
    """LLM classification result schema for Gemini Flash.

    Used as response_schema in generate_content -- Pydantic model is converted
    to JSON Schema automatically by the GenAI SDK.
    """

    categories: list[CategoryClassification] = Field(
        description="1-2 category assignments, ordered by confidence",
        max_length=2,
    )
    reasoning: str = Field(description="Brief explanation of classification decision")


# ---------------------------------------------------------------------------
# Internal result dataclass (post fuzzy-match + threshold filtering)
# ---------------------------------------------------------------------------


@dataclass
class ClassificationResult:
    """Internal classification result after fuzzy matching and threshold filtering.

    Plain dataclass (not Pydantic) because it's internal state, not schema.
    Token fields populated from Gemini response.usage_metadata.
    """

    categories: list[tuple[str, float]]
    reasoning: str
    is_ambiguous: bool
    prompt_tokens: int = 0
    completion_tokens: int = 0


# ---------------------------------------------------------------------------
# Run statistics for accumulating pipeline metrics
# ---------------------------------------------------------------------------


@dataclass
class RunStats:
    """Accumulated statistics for a single pipeline run.

    All fields have defaults so RunStats() can be created at pipeline start
    and populated incrementally during execution.
    """

    total_fetched: int = 0
    skipped_triaged: int = 0
    classified: int = 0
    ambiguous: int = 0
    errors: int = 0
    error_details: list[str] = field(default_factory=list)
    categories: dict[str, int] = field(default_factory=dict)
    api_calls_gmail: int = 0
    api_calls_llm: int = 0
    token_usage_prompt: int = 0
    token_usage_completion: int = 0
    elapsed_seconds: float = 0.0
