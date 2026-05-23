"""Tests for API key authentication helpers."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from vision_insight.core import auth


def test_hash_api_key_is_deterministic_and_not_plaintext():
    hashed = auth._hash_api_key("secret-key")

    assert hashed == auth._hash_api_key("secret-key")
    assert hashed != "secret-key"
    assert len(hashed) == 64


@patch("vision_insight.core.auth.settings")
def test_verify_api_key_accepts_configured_header_key(mock_settings):
    mock_settings.api_keys = "alpha,beta"

    assert auth.verify_api_key(api_key_header="alpha", api_key_query=None) == "alpha"


@patch("vision_insight.core.auth.settings")
def test_verify_api_key_rejects_invalid_key(mock_settings):
    mock_settings.api_keys = "alpha"

    with pytest.raises(HTTPException) as exc:
        auth.verify_api_key(api_key_header="wrong", api_key_query=None)

    assert exc.value.status_code == 403
    assert exc.value.detail == "Invalid API key"


@patch("vision_insight.core.auth.settings")
def test_verify_api_key_allows_any_key_when_no_keys_configured(mock_settings):
    mock_settings.api_keys = ""

    assert auth.verify_api_key(api_key_header=None, api_key_query="dev-key") == "dev-key"


def test_generate_api_key_is_urlsafe_and_unique():
    key1 = auth.generate_api_key()
    key2 = auth.generate_api_key()

    assert key1 != key2
    assert len(key1) >= 32
