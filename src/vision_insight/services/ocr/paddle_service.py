"""PaddleOCR-based OCR service implementation."""

from __future__ import annotations

import logging
from typing import Any

from vision_insight.models.schemas import OCRResult
from vision_insight.services import OCRService

logger = logging.getLogger(__name__)

# Supported language codes for PaddleOCR
SUPPORTED_LANGUAGES = {
    "ch": "chinese",
    "en": "english",
    "japan": "japanese",
    "ko": "korean",
}


class PaddleOCRService(OCRService):
    """OCR service using PaddleOCR.

    Supports Chinese, English, Japanese, and Korean text recognition.
    Returns OCRResult list with text, bounding box, and confidence.
    """

    def __init__(
        self,
        lang: str = "ch",
        use_gpu: bool = False,
        enable_mkldnn: bool = True,
    ) -> None:
        """Initialize PaddleOCR engine.

        Args:
            lang: Language code ('ch', 'en', 'japan', 'ko').
            use_gpu: Whether to use GPU inference.
            enable_mkldnn: Enable MKL-DNN acceleration for CPU.
        """
        self._lang = lang
        self._use_gpu = use_gpu
        self._enable_mkldnn = enable_mkldnn
        self._engine: Any = None
        self._initialized = False

    def _ensure_engine(self):
        """Lazy initialization of PaddleOCR engine."""
        if self._initialized:
            return

        try:
            from paddleocr import PaddleOCR

            # Try with minimal parameters for compatibility
            try:
                self._engine = PaddleOCR(
                    use_angle_cls=True,
                    lang=self._lang,
                )
            except Exception as e:
                logger.warning("PaddleOCR initialization failed: %s", e)
                raise
            self._initialized = True
            logger.info("PaddleOCR engine initialized (lang=%s)", self._lang)
        except ImportError:
            logger.error("paddleocr package not installed. Install with: pip install paddleocr")
            raise
        except Exception:
            logger.exception("Failed to initialize PaddleOCR engine")
            raise

    async def extract(self, image_bytes: bytes) -> list[OCRResult]:
        """Extract text from image bytes using PaddleOCR.

        Args:
            image_bytes: Raw image file bytes.

        Returns:
            List of OCRResult with detected text, bbox, and confidence.
            Returns empty list if no text detected or image is invalid.
        """
        if not image_bytes:
            logger.warning("Empty image bytes provided")
            return []

        self._ensure_engine()

        try:
            # PaddleOCR expects file path or numpy array, not bytes
            import os
            import tempfile

            # Save bytes to temporary file
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                tmp.write(image_bytes)
                tmp_path = tmp.name

            try:
                # Try with cls parameter first, fallback without it
                try:
                    results = self._engine.ocr(tmp_path, cls=True)
                except TypeError:
                    results = self._engine.ocr(tmp_path)
            finally:
                # Clean up temporary file
                os.unlink(tmp_path)
        except Exception:
            logger.exception("PaddleOCR inference failed")
            return []

        return self._parse_results(results)

    def _parse_results(self, results) -> list[OCRResult]:
        """Parse raw PaddleOCR output into OCRResult list.

        PaddleOCR returns:
            [
                [
                    [bbox, (text, confidence)],
                    ...
                ]
            ]
        or [None] if no text detected.
        """
        if not results or results == [None]:
            return []

        parsed: list[OCRResult] = []
        for line_group in results:
            if not line_group:
                continue
            for item in line_group:
                try:
                    bbox_raw, (text, confidence) = item
                    # Convert bbox to list[list[int]] format
                    bbox = [[int(x), int(y)] for x, y in bbox_raw]
                    parsed.append(
                        OCRResult(
                            text=text.strip(),
                            bbox=bbox,
                            confidence=round(float(confidence), 4),
                        )
                    )
                except (ValueError, TypeError, IndexError):
                    logger.warning("Failed to parse OCR item: %s", item)
                    continue

        return parsed

    @classmethod
    def create_for_language(cls, lang: str = "ch", **kwargs) -> PaddleOCRService:
        """Factory method to create service for a specific language.

        Args:
            lang: One of 'ch', 'en', 'japan', 'ko'.
            **kwargs: Additional arguments passed to __init__.

        Returns:
            Configured PaddleOCRService instance.

        Raises:
            ValueError: If language is not supported.
        """
        if lang not in SUPPORTED_LANGUAGES:
            raise ValueError(
                f"Unsupported language '{lang}'. Supported: {list(SUPPORTED_LANGUAGES.keys())}"
            )
        return cls(lang=lang, **kwargs)
