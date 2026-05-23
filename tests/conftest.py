"""Shared test fixtures for vision-insight tests."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image


@pytest.fixture
def sample_png_bytes() -> bytes:
    """Create a minimal valid PNG image as bytes."""
    img = Image.new("RGB", (100, 100), color="red")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def sample_jpeg_bytes() -> bytes:
    """Create a minimal valid JPEG image as bytes."""
    img = Image.new("RGB", (200, 150), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


@pytest.fixture
def blank_image_bytes() -> bytes:
    """Create a blank white image (no text)."""
    img = Image.new("RGB", (640, 480), color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Run Playwright E2E tests after async unit/integration tests.

    pytest-playwright uses synchronous browser fixtures. In this project that can
    leave an event-loop interaction that breaks later pytest-asyncio tests when
    E2E is collected first. Sorting E2E last keeps the full suite deterministic.
    """

    def sort_key(item: pytest.Item) -> tuple[int, str]:
        path = Path(str(item.fspath))
        is_e2e = "e2e" in path.parts
        return (1 if is_e2e else 0, item.nodeid)

    items.sort(key=sort_key)
