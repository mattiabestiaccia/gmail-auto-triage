"""YAML config loading with pydantic validation and fail-fast behavior."""

from __future__ import annotations

import sys

import yaml
from pydantic import BaseModel, field_validator


class CategoryConfig(BaseModel):
    """A single email category definition."""

    name: str
    description: str
    examples: list[str]

    @field_validator("examples")
    @classmethod
    def examples_must_not_be_empty(cls, v: list[str]) -> list[str]:
        if len(v) < 1:
            raise ValueError("must have at least 1 example")
        return v


class FetchConfig(BaseModel):
    """Email fetch settings with sensible defaults."""

    processing_window_hours: int = 24
    max_emails: int = 100
    snippet_length: int = 500
    fields: list[str] = ["subject", "sender", "snippet"]


class AppConfig(BaseModel):
    """Top-level application configuration."""

    categories: list[CategoryConfig]
    fetch: FetchConfig = FetchConfig()

    @field_validator("categories")
    @classmethod
    def must_have_at_least_one_category(
        cls, v: list[CategoryConfig],
    ) -> list[CategoryConfig]:
        if len(v) < 1:
            raise ValueError("must have at least 1 category")
        return v


def load_config(path: str) -> AppConfig:
    """Load and validate config from a YAML file.

    Exits with code 1 and a clear error message on any failure:
    - File not found
    - Invalid YAML syntax
    - Validation errors (missing fields, wrong types, etc.)
    """
    try:
        with open(path) as f:
            raw = yaml.safe_load(f)
    except FileNotFoundError:
        print(
            f"Config file not found: {path}. "
            "Create a categories.yaml file — see categories.yaml.example for format."
        )
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"Invalid YAML syntax in {path}: {e}")
        sys.exit(1)

    try:
        return AppConfig.model_validate(raw)
    except Exception as e:
        print(f"Config validation error in {path}:\n{e}")
        sys.exit(1)
