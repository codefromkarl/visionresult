"""Shared retry logic with exponential backoff for async HTTP calls."""

import asyncio
import logging
import random

import httpx

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0  # seconds
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


async def retry_with_backoff(coro_factory, max_retries: int = MAX_RETRIES):
    """Retry an async operation with exponential backoff."""
    last_exc: BaseException | None = None
    for attempt in range(max_retries):
        try:
            return await coro_factory()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in RETRYABLE_STATUS_CODES and attempt < max_retries - 1:
                delay = RETRY_BASE_DELAY * (2**attempt) * (0.5 + random.random())
                logger.warning(
                    "Retryable HTTP %d, attempt %d/%d, waiting %.1fs",
                    exc.response.status_code,
                    attempt + 1,
                    max_retries,
                    delay,
                )
                await asyncio.sleep(delay)
                last_exc = exc
            else:
                raise
        except (httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
            if attempt < max_retries - 1:
                delay = RETRY_BASE_DELAY * (2**attempt) * (0.5 + random.random())
                logger.warning(
                    "Timeout, attempt %d/%d, waiting %.1fs", attempt + 1, max_retries, delay
                )
                await asyncio.sleep(delay)
                last_exc = exc
            else:
                raise
    assert last_exc is not None
    raise last_exc
