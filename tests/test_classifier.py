"""Tests for email classification engine.

Tests cover:
- fuzzy_match_category: match, no-match, case-insensitive
- Confidence threshold filtering: filter, all-below=ambiguous, multi-label
- Prompt assembly: includes categories and email fields
- Config extension: ClassificationConfig defaults
- classify_email (mocked): API call, fuzzy matching, threshold, ambiguous
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from email_triage.classifier import (
    build_classification_prompt,
    classify_email,
    create_genai_client,
    fuzzy_match_category,
)
from email_triage.config import AppConfig, CategoryConfig, ClassificationConfig
from email_triage.models import (
    CategoryClassification,
    ClassificationResponse,
    ClassificationResult,
    EmailData,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def valid_categories() -> list[str]:
    return ["Newsletter", "Finance", "Social", "Shopping"]


@pytest.fixture
def category_configs() -> list[CategoryConfig]:
    return [
        CategoryConfig(
            name="Newsletter",
            description="Periodic newsletters and digests",
            examples=["Your weekly Python digest"],
        ),
        CategoryConfig(
            name="Finance",
            description="Banking notifications and invoices",
            examples=["Your credit card statement is ready"],
        ),
    ]


@pytest.fixture
def sample_email() -> EmailData:
    return EmailData(
        id="msg_001",
        thread_id="thread_001",
        sender="digest@python.org",
        subject="Your weekly Python digest",
        date="2026-03-08",
        snippet="This week in Python: new PEP accepted...",
        label_ids=["INBOX", "UNREAD"],
    )


@pytest.fixture
def default_config() -> ClassificationConfig:
    return ClassificationConfig()


# ---------------------------------------------------------------------------
# fuzzy_match_category tests
# ---------------------------------------------------------------------------


class TestFuzzyMatchCategory:
    """Test fuzzy matching of LLM-returned category names."""

    def test_exact_match(self, valid_categories: list[str]) -> None:
        result = fuzzy_match_category("Newsletter", valid_categories)
        assert result == "Newsletter"

    def test_typo_match(self, valid_categories: list[str]) -> None:
        result = fuzzy_match_category("Newsleter", valid_categories)
        assert result == "Newsletter"

    def test_case_insensitive(self, valid_categories: list[str]) -> None:
        result = fuzzy_match_category("newsletter", valid_categories)
        assert result == "Newsletter"

    def test_no_match_unknown(self, valid_categories: list[str]) -> None:
        result = fuzzy_match_category("totally_unknown", valid_categories)
        assert result is None

    def test_close_typo(self, valid_categories: list[str]) -> None:
        result = fuzzy_match_category("Newsltter", valid_categories, threshold=70)
        assert result == "Newsletter"

    def test_garbage_returns_none(self, valid_categories: list[str]) -> None:
        result = fuzzy_match_category("xyz", valid_categories, threshold=70)
        assert result is None


# ---------------------------------------------------------------------------
# Confidence threshold filtering tests
# ---------------------------------------------------------------------------


class TestConfidenceFiltering:
    """Test confidence threshold logic on ClassificationResult."""

    def test_one_above_one_below(self) -> None:
        """Only category above threshold survives."""
        categories = [("Newsletter", 0.8), ("Finance", 0.3)]
        result = _apply_threshold(categories, threshold=0.5)
        assert result.categories == [("Newsletter", 0.8)]
        assert result.is_ambiguous is False

    def test_both_below_is_ambiguous(self) -> None:
        """Both below threshold -> ambiguous."""
        categories = [("Newsletter", 0.2), ("Finance", 0.3)]
        result = _apply_threshold(categories, threshold=0.5)
        assert result.categories == []
        assert result.is_ambiguous is True

    def test_both_above_multi_label(self) -> None:
        """Both above threshold -> multi-label."""
        categories = [("Newsletter", 0.9), ("Finance", 0.7)]
        result = _apply_threshold(categories, threshold=0.5)
        assert result.categories == [("Newsletter", 0.9), ("Finance", 0.7)]
        assert result.is_ambiguous is False

    def test_exact_threshold_survives(self) -> None:
        """Category at exact threshold value survives."""
        categories = [("Newsletter", 0.5)]
        result = _apply_threshold(categories, threshold=0.5)
        assert result.categories == [("Newsletter", 0.5)]
        assert result.is_ambiguous is False


def _apply_threshold(
    categories: list[tuple[str, float]],
    threshold: float,
) -> ClassificationResult:
    """Helper: apply confidence threshold filtering."""
    filtered = [(cat, conf) for cat, conf in categories if conf >= threshold]
    return ClassificationResult(
        categories=filtered,
        reasoning="test",
        is_ambiguous=len(filtered) == 0,
    )


# ---------------------------------------------------------------------------
# build_classification_prompt tests
# ---------------------------------------------------------------------------


class TestBuildClassificationPrompt:
    """Test prompt assembly includes all required information."""

    def test_includes_category_names(
        self,
        sample_email: EmailData,
        category_configs: list[CategoryConfig],
    ) -> None:
        prompt = build_classification_prompt(sample_email, category_configs)
        assert "Newsletter" in prompt
        assert "Finance" in prompt

    def test_includes_category_descriptions(
        self,
        sample_email: EmailData,
        category_configs: list[CategoryConfig],
    ) -> None:
        prompt = build_classification_prompt(sample_email, category_configs)
        assert "Periodic newsletters" in prompt
        assert "Banking notifications" in prompt

    def test_includes_category_examples(
        self,
        sample_email: EmailData,
        category_configs: list[CategoryConfig],
    ) -> None:
        prompt = build_classification_prompt(sample_email, category_configs)
        assert "Your weekly Python digest" in prompt
        assert "Your credit card statement is ready" in prompt

    def test_includes_email_sender(
        self,
        sample_email: EmailData,
        category_configs: list[CategoryConfig],
    ) -> None:
        prompt = build_classification_prompt(sample_email, category_configs)
        assert "digest@python.org" in prompt

    def test_includes_email_subject(
        self,
        sample_email: EmailData,
        category_configs: list[CategoryConfig],
    ) -> None:
        prompt = build_classification_prompt(sample_email, category_configs)
        assert "Your weekly Python digest" in prompt

    def test_includes_email_snippet(
        self,
        sample_email: EmailData,
        category_configs: list[CategoryConfig],
    ) -> None:
        prompt = build_classification_prompt(sample_email, category_configs)
        assert "This week in Python" in prompt

    def test_includes_max_categories_instruction(
        self,
        sample_email: EmailData,
        category_configs: list[CategoryConfig],
    ) -> None:
        prompt = build_classification_prompt(sample_email, category_configs)
        # Belt-and-suspenders: prompt must mention 1-2 category limit
        assert "1" in prompt and "2" in prompt

    def test_fields_subset_excludes_other_fields(
        self,
        sample_email: EmailData,
        category_configs: list[CategoryConfig],
    ) -> None:
        """fields parameter controls which email fields appear in the prompt."""
        prompt = build_classification_prompt(
            sample_email, category_configs, fields=["sender"],
        )
        assert "digest@python.org" in prompt  # sender included
        assert "This week in Python" not in prompt  # snippet excluded


# ---------------------------------------------------------------------------
# ClassificationConfig tests
# ---------------------------------------------------------------------------


class TestClassificationConfig:
    """Test config extension for classification settings."""

    def test_default_confidence_threshold(self) -> None:
        config = ClassificationConfig()
        assert config.confidence_threshold == 0.5

    def test_default_model(self) -> None:
        config = ClassificationConfig()
        assert config.model == "gemini-2.5-flash"

    def test_custom_values(self) -> None:
        config = ClassificationConfig(confidence_threshold=0.7, model="gemini-2.0-flash")
        assert config.confidence_threshold == 0.7
        assert config.model == "gemini-2.0-flash"

    def test_app_config_includes_classification(self) -> None:
        """AppConfig has classification field with defaults."""
        app = AppConfig(
            categories=[
                CategoryConfig(
                    name="Test",
                    description="Test cat",
                    examples=["example"],
                ),
            ],
        )
        assert isinstance(app.classification, ClassificationConfig)
        assert app.classification.confidence_threshold == 0.5


# ---------------------------------------------------------------------------
# Models tests
# ---------------------------------------------------------------------------


class TestModels:
    """Test new classification models."""

    def test_classification_result_dataclass(self) -> None:
        result = ClassificationResult(
            categories=[("Newsletter", 0.9)],
            reasoning="Looks like a newsletter",
            is_ambiguous=False,
        )
        assert result.categories == [("Newsletter", 0.9)]
        assert result.reasoning == "Looks like a newsletter"
        assert result.is_ambiguous is False

    def test_classification_response_pydantic(self) -> None:
        resp = ClassificationResponse(
            categories=[
                CategoryClassification(category="Newsletter", confidence=0.9),
            ],
            reasoning="Newsletter content detected",
        )
        assert len(resp.categories) == 1
        assert resp.categories[0].category == "Newsletter"
        assert resp.categories[0].confidence == 0.9

    def test_classification_response_max_two_categories(self) -> None:
        """Schema enforces max 2 categories."""
        with pytest.raises(Exception):
            ClassificationResponse(
                categories=[
                    CategoryClassification(category="A", confidence=0.9),
                    CategoryClassification(category="B", confidence=0.8),
                    CategoryClassification(category="C", confidence=0.7),
                ],
                reasoning="Too many",
            )


# ---------------------------------------------------------------------------
# create_genai_client tests
# ---------------------------------------------------------------------------


class TestCreateGenaiClient:
    """Test client creation with API key from environment."""

    def test_missing_api_key_exits(self) -> None:
        with patch("email_triage.classifier.load_dotenv"):
            with patch.dict("os.environ", {}, clear=True):
                with pytest.raises(SystemExit) as exc_info:
                    create_genai_client()
                assert "GEMINI_API_KEY" in str(exc_info.value)

    def test_gemini_api_key_used(self) -> None:
        with patch("email_triage.classifier.load_dotenv"):
            with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}, clear=True):
                with patch("email_triage.classifier.genai.Client") as mock_client:
                    create_genai_client()
                    mock_client.assert_called_once_with(api_key="test-key")

    def test_google_api_key_fallback(self) -> None:
        with patch("email_triage.classifier.load_dotenv"):
            with patch.dict("os.environ", {"GOOGLE_API_KEY": "fallback-key"}, clear=True):
                with patch("email_triage.classifier.genai.Client") as mock_client:
                    create_genai_client()
                    mock_client.assert_called_once_with(api_key="fallback-key")


# ---------------------------------------------------------------------------
# classify_email (mocked) tests
# ---------------------------------------------------------------------------


class TestClassifyEmail:
    """Test classify_email with mocked Gemini API."""

    def _make_mock_response(self, categories_json: str) -> MagicMock:
        """Create a mock Gemini API response."""
        mock_response = MagicMock()
        mock_response.text = categories_json
        return mock_response

    def test_calls_gemini_with_correct_params(
        self,
        sample_email: EmailData,
        category_configs: list[CategoryConfig],
        default_config: ClassificationConfig,
    ) -> None:
        """classify_email calls generate_content with response_schema and temperature."""
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = self._make_mock_response(
            '{"categories": [{"category": "Newsletter", "confidence": 0.9}], "reasoning": "test"}',
        )

        classify_email(mock_client, sample_email, category_configs, default_config)

        call_kwargs = mock_client.models.generate_content.call_args
        config = call_kwargs.kwargs.get("config") or call_kwargs[1].get("config")
        assert config.temperature == 0.1
        assert config.response_mime_type == "application/json"

    def test_returns_classification_result(
        self,
        sample_email: EmailData,
        category_configs: list[CategoryConfig],
        default_config: ClassificationConfig,
    ) -> None:
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = self._make_mock_response(
            '{"categories": [{"category": "Newsletter", "confidence": 0.9}], "reasoning": "Newsletter content"}',
        )

        result = classify_email(mock_client, sample_email, category_configs, default_config)

        assert isinstance(result, ClassificationResult)
        assert result.categories == [("Newsletter", 0.9)]
        assert result.is_ambiguous is False

    def test_applies_fuzzy_matching(
        self,
        sample_email: EmailData,
        category_configs: list[CategoryConfig],
        default_config: ClassificationConfig,
    ) -> None:
        """LLM returns typo in category name -> fuzzy matched."""
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = self._make_mock_response(
            '{"categories": [{"category": "Newsleter", "confidence": 0.9}], "reasoning": "typo"}',
        )

        result = classify_email(mock_client, sample_email, category_configs, default_config)
        assert result.categories == [("Newsletter", 0.9)]

    def test_filters_by_confidence_threshold(
        self,
        sample_email: EmailData,
        category_configs: list[CategoryConfig],
    ) -> None:
        """Categories below threshold are removed."""
        config = ClassificationConfig(confidence_threshold=0.5)
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = self._make_mock_response(
            '{"categories": [{"category": "Newsletter", "confidence": 0.9}, {"category": "Finance", "confidence": 0.3}], "reasoning": "mixed"}',
        )

        result = classify_email(mock_client, sample_email, category_configs, config)
        assert result.categories == [("Newsletter", 0.9)]
        assert result.is_ambiguous is False

    def test_ambiguous_when_all_below_threshold(
        self,
        sample_email: EmailData,
        category_configs: list[CategoryConfig],
    ) -> None:
        """All categories below threshold -> ambiguous."""
        config = ClassificationConfig(confidence_threshold=0.5)
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = self._make_mock_response(
            '{"categories": [{"category": "Newsletter", "confidence": 0.2}, {"category": "Finance", "confidence": 0.3}], "reasoning": "unsure"}',
        )

        result = classify_email(mock_client, sample_email, category_configs, config)
        assert result.categories == []
        assert result.is_ambiguous is True

    def test_unmatched_category_dropped(
        self,
        sample_email: EmailData,
        category_configs: list[CategoryConfig],
        default_config: ClassificationConfig,
    ) -> None:
        """LLM returns category not in config -> fuzzy match fails -> dropped."""
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = self._make_mock_response(
            '{"categories": [{"category": "TotallyUnknown", "confidence": 0.9}], "reasoning": "bad category"}',
        )

        result = classify_email(mock_client, sample_email, category_configs, default_config)
        assert result.categories == []
        assert result.is_ambiguous is True

    def test_returns_token_usage(
        self,
        sample_email: EmailData,
        category_configs: list[CategoryConfig],
        default_config: ClassificationConfig,
    ) -> None:
        """classify_email extracts token usage from response.usage_metadata."""
        mock_client = MagicMock()
        mock_response = self._make_mock_response(
            '{"categories": [{"category": "Newsletter", "confidence": 0.9}], "reasoning": "test"}',
        )
        # Set up usage_metadata
        mock_response.usage_metadata.prompt_token_count = 150
        mock_response.usage_metadata.candidates_token_count = 42
        mock_client.models.generate_content.return_value = mock_response

        result = classify_email(mock_client, sample_email, category_configs, default_config)
        assert result.prompt_tokens == 150
        assert result.completion_tokens == 42

    def test_handles_missing_usage_metadata(
        self,
        sample_email: EmailData,
        category_configs: list[CategoryConfig],
        default_config: ClassificationConfig,
    ) -> None:
        """Token counts default to 0 when usage_metadata is None."""
        mock_client = MagicMock()
        mock_response = self._make_mock_response(
            '{"categories": [{"category": "Newsletter", "confidence": 0.9}], "reasoning": "test"}',
        )
        mock_response.usage_metadata = None
        mock_client.models.generate_content.return_value = mock_response

        result = classify_email(mock_client, sample_email, category_configs, default_config)
        assert result.prompt_tokens == 0
        assert result.completion_tokens == 0
