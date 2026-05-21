"""Tests for PaddleOCR service."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from vision_insight.models.schemas import OCRResult
from vision_insight.services.ocr.paddle_service import (
    SUPPORTED_LANGUAGES,
    PaddleOCRService,
)

# === Mock PaddleOCR fixtures ===


def _make_paddle_result(texts: list[tuple[str, float, list]]) -> list:
    """Build a fake PaddleOCR result structure.

    Args:
        texts: List of (text, confidence, bbox_points).
               bbox_points is [[x1,y1],[x2,y2],[x3,y3],[x4,y4]].

    Returns:
        Nested list matching PaddleOCR output format.
    """
    lines = []
    for text, conf, bbox in texts:
        lines.append([bbox, (text, conf)])
    return [lines]


@pytest.fixture
def mock_paddle_ocr():
    """Patch PaddleOCR class so no real model loads."""
    mock_paddle_module = MagicMock()
    mock_instance = MagicMock()
    mock_paddle_module.PaddleOCR.return_value = mock_instance
    with patch.dict("sys.modules", {"paddleocr": mock_paddle_module}):
        yield mock_instance


# === Initialization tests ===


class TestPaddleOCRServiceInit:
    def test_default_init(self):
        svc = PaddleOCRService()
        assert svc._lang == "ch"
        assert svc._use_gpu is False
        assert svc._initialized is False

    def test_custom_lang(self):
        svc = PaddleOCRService(lang="japan")
        assert svc._lang == "japan"

    def test_create_for_language_valid(self):
        svc = PaddleOCRService.create_for_language("en")
        assert svc._lang == "en"

    def test_create_for_language_invalid(self):
        with pytest.raises(ValueError, match="Unsupported language"):
            PaddleOCRService.create_for_language("xx")

    def test_all_supported_languages_creatable(self):
        for lang in SUPPORTED_LANGUAGES:
            svc = PaddleOCRService.create_for_language(lang)
            assert svc._lang == lang


# === Extract tests ===


class TestPaddleOCRExtract:
    @pytest.mark.asyncio
    async def test_extract_normal(self, mock_paddle_ocr, sample_png_bytes):
        fake_result = _make_paddle_result(
            [
                ("你好世界", 0.98, [[10, 10], [100, 10], [100, 40], [10, 40]]),
                ("Hello", 0.95, [[10, 50], [80, 50], [80, 80], [10, 80]]),
            ]
        )
        mock_paddle_ocr.ocr.return_value = fake_result

        svc = PaddleOCRService()
        results = await svc.extract(sample_png_bytes)

        assert len(results) == 2
        assert isinstance(results[0], OCRResult)
        assert results[0].text == "你好世界"
        assert results[0].confidence == pytest.approx(0.98, abs=0.01)
        assert results[0].bbox == [[10, 10], [100, 10], [100, 40], [10, 40]]
        assert results[1].text == "Hello"

    @pytest.mark.asyncio
    async def test_extract_empty_bytes(self, mock_paddle_ocr):
        svc = PaddleOCRService()
        results = await svc.extract(b"")

        assert results == []
        mock_paddle_ocr.ocr.assert_not_called()

    @pytest.mark.asyncio
    async def test_extract_no_text_detected(self, mock_paddle_ocr, blank_image_bytes):
        mock_paddle_ocr.ocr.return_value = [None]

        svc = PaddleOCRService()
        results = await svc.extract(blank_image_bytes)

        assert results == []

    @pytest.mark.asyncio
    async def test_extract_empty_result_list(self, mock_paddle_ocr, sample_png_bytes):
        mock_paddle_ocr.ocr.return_value = [[]]

        svc = PaddleOCRService()
        results = await svc.extract(sample_png_bytes)

        assert results == []

    @pytest.mark.asyncio
    async def test_extract_japanese_text(self, mock_paddle_ocr, sample_png_bytes):
        fake_result = _make_paddle_result(
            [
                ("東京タワー", 0.92, [[5, 5], [120, 5], [120, 35], [5, 35]]),
            ]
        )
        mock_paddle_ocr.ocr.return_value = fake_result

        svc = PaddleOCRService(lang="japan")
        results = await svc.extract(sample_png_bytes)

        assert len(results) == 1
        assert results[0].text == "東京タワー"

    @pytest.mark.asyncio
    async def test_extract_inference_error(self, mock_paddle_ocr, sample_png_bytes):
        mock_paddle_ocr.ocr.side_effect = RuntimeError("CUDA out of memory")

        svc = PaddleOCRService()
        results = await svc.extract(sample_png_bytes)

        assert results == []

    @pytest.mark.asyncio
    async def test_extract_malformed_item_skipped(self, mock_paddle_ocr, sample_png_bytes):
        """Items with unexpected format should be skipped, not crash."""
        mock_paddle_ocr.ocr.return_value = [
            [
                [[10, 10], [100, 10], [100, 40], [10, 40], ("valid", 0.9)],
                "totally_broken_item",
            ]
        ]

        svc = PaddleOCRService()
        results = await svc.extract(sample_png_bytes)

        # Both items are malformed; service should return empty without crashing
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_extract_confidence_clamped(self, mock_paddle_ocr, sample_png_bytes):
        """Confidence should be rounded to 4 decimal places."""
        fake_result = _make_paddle_result(
            [
                ("test", 0.123456789, [[0, 0], [10, 0], [10, 10], [0, 10]]),
            ]
        )
        mock_paddle_ocr.ocr.return_value = fake_result

        svc = PaddleOCRService()
        results = await svc.extract(sample_png_bytes)

        assert results[0].confidence == pytest.approx(0.1235, abs=0.0001)

    @pytest.mark.asyncio
    async def test_lazy_initialization(self, mock_paddle_ocr, sample_png_bytes):
        """Engine should be created on first extract, not at __init__."""
        svc = PaddleOCRService()
        assert svc._initialized is False

        mock_paddle_ocr.ocr.return_value = [None]
        await svc.extract(sample_png_bytes)

        assert svc._initialized is True

    @pytest.mark.asyncio
    async def test_extract_bbox_as_int(self, mock_paddle_ocr, sample_png_bytes):
        """Bbox coordinates should be converted to int."""
        fake_result = _make_paddle_result(
            [
                ("test", 0.9, [[10.5, 20.7], [100.1, 20.7], [100.1, 50.3], [10.5, 50.3]]),
            ]
        )
        mock_paddle_ocr.ocr.return_value = fake_result

        svc = PaddleOCRService()
        results = await svc.extract(sample_png_bytes)

        for point in results[0].bbox:
            assert isinstance(point[0], int)
            assert isinstance(point[1], int)
