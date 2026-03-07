"""Tests for config loading and validation."""

import pytest

from email_triage.config import load_config


class TestLoadValidConfig:
    """Test loading a well-formed config file."""

    def test_load_valid_config(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            """
categories:
  - name: Newsletter
    description: "Periodic newsletters"
    examples:
      - "Weekly digest"
  - name: Finance
    description: "Banking notifications"
    examples:
      - "Your statement is ready"
"""
        )
        config = load_config(str(config_file))
        assert len(config.categories) == 2
        assert config.categories[0].name == "Newsletter"
        assert config.categories[1].name == "Finance"
        assert config.categories[0].description == "Periodic newsletters"
        assert config.categories[0].examples == ["Weekly digest"]


class TestCategoryValidation:
    """Test that invalid category definitions are rejected."""

    def test_category_missing_description(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            """
categories:
  - name: Newsletter
    examples:
      - "Weekly digest"
"""
        )
        with pytest.raises(SystemExit):
            load_config(str(config_file))

    def test_category_no_examples(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            """
categories:
  - name: Newsletter
    description: "Periodic newsletters"
    examples: []
"""
        )
        with pytest.raises(SystemExit):
            load_config(str(config_file))


class TestConfigFileErrors:
    """Test error handling for file-level issues."""

    def test_missing_config_file(self):
        with pytest.raises(SystemExit):
            load_config("/nonexistent/path/config.yaml")

    def test_invalid_yaml_syntax(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            """
categories:
  - name: Newsletter
    description: "Periodic newsletters
    examples: [missing bracket
"""
        )
        with pytest.raises(SystemExit):
            load_config(str(config_file))


class TestFetchSettings:
    """Test fetch configuration defaults and overrides."""

    def test_default_fetch_settings(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            """
categories:
  - name: Newsletter
    description: "Periodic newsletters"
    examples:
      - "Weekly digest"
"""
        )
        config = load_config(str(config_file))
        assert config.fetch.processing_window_hours == 24
        assert config.fetch.max_emails == 100
        assert config.fetch.snippet_length == 500
        assert config.fetch.fields == ["subject", "sender", "snippet"]

    def test_custom_fetch_settings(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            """
categories:
  - name: Newsletter
    description: "Periodic newsletters"
    examples:
      - "Weekly digest"
fetch:
  processing_window_hours: 48
  max_emails: 50
  snippet_length: 300
  fields:
    - subject
    - sender
"""
        )
        config = load_config(str(config_file))
        assert config.fetch.processing_window_hours == 48
        assert config.fetch.max_emails == 50
        assert config.fetch.snippet_length == 300
        assert config.fetch.fields == ["subject", "sender"]
