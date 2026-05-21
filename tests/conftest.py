"""Shared test fixtures for vision-insight tests."""

from __future__ import annotations

import io

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
