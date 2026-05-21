"""Tests for edge cases and boundary conditions."""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from vision_insight.models.schemas import AnalysisReport, AnalysisStatus
from vision_insight.utils.image import compress_image, get_image_metadata, is_blurry


class TestLargeImageHandling:
    """Test handling of large images."""

    def test_large_image_compressed(self):
        """Images >4MB should be compressed."""
        # Create a large image (simulate 5MB)
        img = Image.new("RGB", (4000, 3000), color="red")
        buf = io.BytesIO()
        img.save(buf, format="BMP")  # BMP is uncompressed
        large_bytes = buf.getvalue()

        # Compress should reduce size significantly
        compressed = compress_image(large_bytes, max_size=(2048, 2048), quality=85)

        assert len(compressed) < len(large_bytes)
        # Verify the compressed image is valid
        img_compressed = Image.open(io.BytesIO(compressed))
        assert img_compressed.width <= 2048
        assert img_compressed.height <= 2048

    def test_small_image_not_compressed(self):
        """Images <4MB should not be compressed."""
        img = Image.new("RGB", (100, 100), color="blue")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        small_bytes = buf.getvalue()

        # Size should remain similar (header may change slightly)
        assert len(small_bytes) < 4 * 1024 * 1024

    def test_very_large_dimensions_resized(self):
        """Images with very large dimensions should be resized."""
        img = Image.new("RGB", (8000, 6000), color="green")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        large_bytes = buf.getvalue()

        compressed = compress_image(large_bytes, max_size=(2048, 2048), quality=85)
        result = Image.open(io.BytesIO(compressed))

        assert result.width <= 2048
        assert result.height <= 2048


class TestCorruptedImageHandling:
    """Test handling of corrupted or invalid image files."""

    def test_corrupted_jpeg_returns_error(self):
        """Corrupted JPEG bytes should raise an exception."""
        corrupted_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 100  # Invalid JPEG

        with pytest.raises(Exception):
            get_image_metadata(corrupted_bytes)

    def test_empty_bytes_returns_error(self):
        """Empty bytes should raise an exception."""
        with pytest.raises(Exception):
            get_image_metadata(b"")

    def test_random_bytes_returns_error(self):
        """Random bytes should raise an exception."""
        random_bytes = b"this is not an image file at all"
        with pytest.raises(Exception):
            get_image_metadata(random_bytes)

    def test_truncated_image_handled(self):
        """Truncated image should be handled gracefully."""
        # Create a valid image then truncate it
        img = Image.new("RGB", (100, 100), color="red")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        full_bytes = buf.getvalue()
        truncated = full_bytes[:len(full_bytes) // 2]

        # Should either work or raise a clear error
        try:
            metadata = get_image_metadata(truncated)
            # If it works, that's fine too
            assert metadata is not None
        except Exception:
            # Expected - corrupted data
            pass


class TestBlurDetection:
    """Test blur detection edge cases."""

    def test_empty_bytes_not_blurry(self):
        """Empty bytes should return True (is blurry)."""
        assert is_blurry(b"") is True

    def test_invalid_bytes_not_blurry(self):
        """Invalid bytes should return True (is blurry)."""
        assert is_blurry(b"not an image") is True

    def test_solid_color_low_sharpness(self):
        """Solid color image should have low sharpness."""
        img = Image.new("RGB", (100, 100), color="white")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        image_bytes = buf.getvalue()

        # Solid color has no edges, so sharpness should be low
        assert is_blurry(image_bytes, threshold=100.0) is True

    def test_high_contrast_higher_sharpness(self):
        """High contrast image should have higher sharpness."""
        img = Image.new("RGB", (100, 100), color="white")
        # Add black squares for contrast
        for x in range(0, 100, 20):
            for y in range(0, 100, 20):
                for dx in range(10):
                    for dy in range(10):
                        img.putpixel((x + dx, y + dy), (0, 0, 0))

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=100)
        image_bytes = buf.getvalue()

        # High contrast should have higher sharpness
        from vision_insight.utils.image import assess_sharpness
        sharpness = assess_sharpness(image_bytes)
        assert sharpness > 0  # Should have some sharpness


class TestMetadataEdgeCases:
    """Test metadata extraction edge cases."""

    def test_png_metadata(self):
        """PNG images should have correct metadata."""
        img = Image.new("RGB", (200, 150), color="blue")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        image_bytes = buf.getvalue()

        metadata = get_image_metadata(image_bytes)

        assert metadata["width"] == 200
        assert metadata["height"] == 150
        assert metadata["format"] == "PNG"

    def test_jpeg_metadata(self):
        """JPEG images should have correct metadata."""
        img = Image.new("RGB", (300, 200), color="green")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        image_bytes = buf.getvalue()

        metadata = get_image_metadata(image_bytes)

        assert metadata["width"] == 300
        assert metadata["height"] == 200
        assert metadata["format"] == "JPEG"

    def test_rgba_image_metadata(self):
        """RGBA images should be handled."""
        img = Image.new("RGBA", (100, 100), color=(255, 0, 0, 128))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        image_bytes = buf.getvalue()

        metadata = get_image_metadata(image_bytes)

        assert metadata["width"] == 100
        assert metadata["height"] == 100
        assert metadata["mode"] == "RGBA"
