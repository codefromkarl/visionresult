"""Tests for rate limiting middleware."""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.responses import Response

from vision_insight.core.rate_limiter import RateLimitMiddleware


def test_get_client_ip_prefers_forwarded_for_header():
    middleware = RateLimitMiddleware(app=None)
    request = SimpleNamespace(
        headers={"X-Forwarded-For": "203.0.113.1, 10.0.0.1"},
        client=SimpleNamespace(host="127.0.0.1"),
    )

    assert middleware._get_client_ip(request) == "203.0.113.1"


def test_check_rate_limit_raises_after_minute_limit():
    middleware = RateLimitMiddleware(app=None, requests_per_minute=1, requests_per_hour=10)
    middleware._check_rate_limit("127.0.0.1", "/api/v1/analyze")

    with pytest.raises(HTTPException) as exc:
        middleware._check_rate_limit("127.0.0.1", "/api/v1/analyze")

    assert exc.value.status_code == 429
    assert "per minute" in exc.value.detail


def test_cleanup_old_entries_removes_expired_ips():
    middleware = RateLimitMiddleware(app=None, cleanup_interval=0)
    middleware._requests["old"] = [(time.time() - 7200, "/api")]

    middleware._cleanup_old_entries()

    assert "old" not in middleware._requests


@pytest.mark.asyncio
async def test_dispatch_adds_rate_limit_headers():
    middleware = RateLimitMiddleware(app=None, requests_per_minute=5, requests_per_hour=10)
    request = SimpleNamespace(
        url=SimpleNamespace(path="/api/v1/stats"),
        headers={},
        client=SimpleNamespace(host="127.0.0.1"),
    )

    async def call_next(req):
        return Response("ok")

    response = await middleware.dispatch(request, call_next)

    assert response.headers["X-RateLimit-Limit"] == "5"
    assert response.headers["X-RateLimit-Remaining"] == "4"
