"""Tests for vision_insight.utils.retry."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from vision_insight.utils.retry import retry_with_backoff


def _make_response(status_code: int) -> httpx.Response:
    return httpx.Response(status_code=status_code, request=httpx.Request("GET", "http://test"))


class TestRetryWithBackoff:
    """retry_with_backoff 应正确处理成功、重试和最终失败。"""

    @pytest.mark.asyncio
    async def test_success_on_first_try(self):
        call_count = 0

        async def factory():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await retry_with_backoff(factory)
        assert result == "ok"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_retryable_status_then_succeeds(self):
        attempts = []

        async def factory():
            attempts.append(1)
            if len(attempts) < 3:
                raise httpx.HTTPStatusError(
                    "retryable", request=httpx.Request("GET", "http://x"), response=_make_response(503)
                )
            return "recovered"

        result = await retry_with_backoff(factory, max_retries=5)
        assert result == "recovered"
        assert len(attempts) == 3

    @pytest.mark.asyncio
    async def test_raises_non_retryable_status(self):
        async def factory():
            raise httpx.HTTPStatusError(
                "bad", request=httpx.Request("GET", "http://x"), response=_make_response(400)
            )

        with pytest.raises(httpx.HTTPStatusError):
            await retry_with_backoff(factory, max_retries=3)

    @pytest.mark.asyncio
    async def test_raises_after_max_retries_exhausted(self):
        async def factory():
            raise httpx.HTTPStatusError(
                "server", request=httpx.Request("GET", "http://x"), response=_make_response(500)
            )

        with pytest.raises(httpx.HTTPStatusError):
            await retry_with_backoff(factory, max_retries=2)

    @pytest.mark.asyncio
    async def test_retries_on_connect_timeout(self):
        attempts = []

        async def factory():
            attempts.append(1)
            if len(attempts) < 2:
                raise httpx.ConnectTimeout("timeout")
            return "ok"

        result = await retry_with_backoff(factory, max_retries=3)
        assert result == "ok"
        assert len(attempts) == 2
