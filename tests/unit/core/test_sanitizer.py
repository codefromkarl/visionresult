"""Tests for log sanitization utilities."""

from __future__ import annotations

import logging

from vision_insight.core.sanitizer import (
    SanitizedLogger,
    sanitize_dict,
    sanitize_log_message,
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

    assert sanitized["token"] == "ab***yz"
    assert sanitized["nested"]["password"] == "se***et"
    assert sanitized["items"][0]["api_key"] == "ab***yz"


def test_sanitize_log_message_formats_and_redacts_args():
    message = sanitize_log_message("Bearer %s", "abcdefghijklmnopqrstuvwxyz")

    assert "abcdefghijklmnopqrstuvwxyz" not in message
    assert "***REDACTED***" in message


def test_sanitized_logger_redacts_string_args(caplog):
    logger = logging.getLogger("test-sanitized")
    wrapper = SanitizedLogger(logger)

    with caplog.at_level(logging.INFO, logger="test-sanitized"):
        wrapper.info("api_key=%s", "abcdefghijklmnopqrstuvwxyz")

    assert "abcdefghijklmnopqrstuvwxyz" not in caplog.text
    assert "***REDACTED***" in caplog.text
