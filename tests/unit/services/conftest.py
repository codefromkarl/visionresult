"""Shared fixtures for service unit tests."""

import pytest


@pytest.fixture(autouse=True)
def _clear_proxy_env(monkeypatch):
    """Remove proxy env vars so httpx.AsyncClient doesn't fail with missing socksio."""
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.delenv(var, raising=False)
