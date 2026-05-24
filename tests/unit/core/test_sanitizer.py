"""Tests for log sanitization utilities."""

from __future__ import annotations

from vision_insight.core.sanitizer import (
    sanitize_dict,
    sanitize_string,
)


def test_sanitize_string_redacts_api_key_password_and_email():
    text = "api_key=abcdefghijklmnopqrstuvwxyz password=hunter2 user=alice@example.com"

    sanitized = sanitize_string(text)

    assert "abcdefghijklmnopqrstuvwxyz" not in sanitized
    assert "hunter2" not in sanitized
    assert "al***@example.com" in sanitized
    assert "***REDACTED***" in sanitized


def test_sanitize_dict_redacts_sensitive_keys_and_nested_values():
    data = {
        "token": "abcdefghijklmnopqrstuvwxyz",
        "nested": {"password": "secret"},
        "items": [{"api_key": "abcdefghijklmnopqrstuvwxyz"}],
    }

    sanitized = sanitize_dict(data)

    assert sanitized["token"] == "***"
    assert sanitized["nested"]["password"] == "***"
    assert sanitized["items"][0]["api_key"] == "***"
