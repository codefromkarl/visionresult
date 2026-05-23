"""Tesseract-based OCR service implementation."""

import io
import logging

from PIL import Image

from vision_insight.models.schemas import OCRResult
from vision_insight.services import OCRService

logger = logging.getLogger(__name__)

# Supported language codes for Tesseract
SUPPORTED_LANGUAGES = {
    "ch": "chi_sim+eng",
    "en": "eng",
    "japan": "jpn",
    "ko": "kor",
}


class TesseractOCRService(OCRService):
    """OCR service using Tesseract.

    Supports Chinese, English, Japanese, and Korean text recognition.
    Returns OCRResult list with text, bounding box, and confidence.
    """

    def __init__(
        self,
        lang: str = "ch",
    ) -> None:
        """Initialize Tesseract OCR engine.

        Args:
            lang: Language code ('ch', 'en', 'japan', 'ko').
        """
        self._lang = lang
        self._tesseract_lang = SUPPORTED_LANGUAGES.get(lang, "chi_sim+eng")
        self._initialized = False

    def _ensure_engine(self):
        """Lazy initialization of Tesseract engine."""
        if self._initialized:
            return

        try:
            import pytesseract
            self._pytesseract = pytesseract
            self._initialized = True
            logger.info("Tesseract OCR engine initialized (lang=%s)", self._tesseract_lang)
        except ImportError:
            logger.error("pytesseract package not installed. Install with: pip install pytesseract")
            raise

    async def extract(self, image_bytes: bytes) -> list[OCRResult]:
        """Extract text from image bytes using Tesseract.

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
            # Convert bytes to PIL Image
            image = Image.open(io.BytesIO(image_bytes))

            # Get detailed data with bounding boxes
            data = self._pytesseract.image_to_data(
                image,
                lang=self._tesseract_lang,
                output_type=self._pytesseract.Output.DICT,
            )

            return self._parse_results(data)
        except Exception:
            logger.exception("Tesseract OCR inference failed")
            return []

    def _parse_results(self, data: dict) -> list[OCRResult]:
        """Parse raw Tesseract output into OCRResult list."""
        results = []
        n_boxes = len(data['text'])

        for i in range(n_boxes):
            text = data['text'][i].strip()
            conf = int(data['conf'][i])

            # Skip empty text or low confidence
            if not text or conf < 0:
                continue

            # Get bounding box
            x = data['left'][i]
            y = data['top'][i]
            w = data['width'][i]
            h = data['height'][i]

            # Convert to polygon format [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
            bbox = [
                [x, y],
                [x + w, y],
                [x + w, y + h],
                [x, y + h],
            ]

            # Normalize confidence to 0-1 range
            confidence = conf / 100.0

            results.append(
                OCRResult(
                    text=text,
                    bbox=bbox,
                    confidence=confidence,
                )
            )

        logger.info("Tesseract OCR done: %d text regions found", len(results))
        return results
