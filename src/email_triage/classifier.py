"""Email classification engine using Gemini Flash structured output.

Classifies emails into 1-2 categories from the user's config,
with confidence scoring and fuzzy category matching.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from google import genai
from google.genai import types
from rapidfuzz import fuzz, process

from email_triage.config import CategoryConfig, ClassificationConfig
from email_triage.models import (
    ClassificationResponse,
    ClassificationResult,
    EmailData,
)

# System instruction for the Gemini Flash classifier
_SYSTEM_INSTRUCTION = (
    "You are an email classifier. Assign each email to 1-2 categories "
    "from the provided list. Be precise with confidence scores."
)


def create_genai_client() -> genai.Client:
    """Create Gemini client with API key from environment.

    Reads GEMINI_API_KEY (or GOOGLE_API_KEY as fallback) from environment.
    Loads .env file first via python-dotenv.

    Raises:
        SystemExit: If no API key is found in environment.
    """
    load_dotenv()
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise SystemExit(
            "GEMINI_API_KEY not set. Get one at https://aistudio.google.com/apikey "
            "and add it to your .env file."
        )
    return genai.Client(api_key=api_key)


def build_classification_prompt(
    email: EmailData,
    categories: list[CategoryConfig],
) -> str:
    """Build classification prompt with category context and email fields.

    Includes category names, descriptions, examples from config,
    and email sender, subject, snippet. Explicitly instructs
    "assign 1 or 2 categories maximum" (belt-and-suspenders with schema).
    """
    category_section = "\n".join(
        f"- **{cat.name}**: {cat.description}\n"
        f"  Examples: {', '.join(cat.examples)}"
        for cat in categories
    )
    return f"""Classify this email into 1 or 2 of the following categories.
Return confidence scores (0.0-1.0) for each assigned category.
Assign 1 or 2 categories maximum.

## Available Categories
{category_section}

## Email to Classify
From: {email.sender}
Subject: {email.subject}
Snippet: {email.snippet}

Classify this email. Assign only categories that genuinely apply.
If unsure, use lower confidence scores."""


def fuzzy_match_category(
    llm_category: str,
    valid_categories: list[str],
    threshold: int = 70,
) -> str | None:
    """Match an LLM-returned category name to valid categories.

    Uses rapidfuzz for fuzzy string matching. Handles typos and
    case-insensitive matching.

    Args:
        llm_category: Category name as returned by the LLM.
        valid_categories: List of valid category names from config.
        threshold: Minimum fuzzy match score (0-100). Default 70.

    Returns:
        Best matching category name if score >= threshold, else None.
    """
    result = process.extractOne(
        llm_category,
        valid_categories,
        scorer=fuzz.ratio,
        score_cutoff=threshold,
    )
    return result[0] if result else None


def classify_email(
    client: genai.Client,
    email: EmailData,
    categories: list[CategoryConfig],
    config: ClassificationConfig,
) -> ClassificationResult:
    """Classify a single email using Gemini Flash.

    Calls Gemini with structured JSON output (Pydantic response_schema),
    applies fuzzy matching to LLM-returned category names, and filters
    by confidence threshold.

    Args:
        client: Initialized Gemini client.
        email: Email to classify.
        categories: Category definitions from config.
        config: Classification settings (threshold, model).

    Returns:
        ClassificationResult with matched categories, reasoning,
        and is_ambiguous flag.
    """
    prompt = build_classification_prompt(email, categories)
    valid_names = [cat.name for cat in categories]

    response = client.models.generate_content(
        model=config.model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ClassificationResponse,
            temperature=0.1,
            system_instruction=_SYSTEM_INSTRUCTION,
        ),
    )

    parsed = ClassificationResponse.model_validate_json(response.text)

    # Apply fuzzy matching and confidence filtering
    matched_categories: list[tuple[str, float]] = []
    for cat_result in parsed.categories:
        matched_name = fuzzy_match_category(cat_result.category, valid_names)
        if matched_name is not None and cat_result.confidence >= config.confidence_threshold:
            matched_categories.append((matched_name, cat_result.confidence))

    return ClassificationResult(
        categories=matched_categories,
        reasoning=parsed.reasoning,
        is_ambiguous=len(matched_categories) == 0,
    )
