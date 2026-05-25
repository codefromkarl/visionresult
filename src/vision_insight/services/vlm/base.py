"""Base VLM service with shared logic for all providers.

This module provides a deep interface for VLM services:
- Single abstract method: `_call_vlm(prompt, image_bytes) -> str`
- Shared `analyze()` and `detect_objects()` implementations
- Easy to add new providers by implementing only the HTTP call
"""

import logging
from abc import abstractmethod

from vision_insight.models.schemas import (
    DetectedObject,
    OCRResult,
    SceneAnalysis,
)
from vision_insight.services import VLMService
from vision_insight.services.vlm.prompts import (
    OBJECT_DETECTION_PROMPT_EN,
    OBJECT_DETECTION_PROMPT_ZH,
    SCENE_ANALYSIS_PROMPT_EN,
    SCENE_ANALYSIS_PROMPT_ZH,
    build_ocr_context,
)
from vision_insight.utils.json_helpers import parse_llm_json
from vision_insight.utils.scene_builders import (
    build_detected_object,
    build_scene_analysis,
)

logger = logging.getLogger(__name__)


class BaseVLMService(VLMService):
    """Base class for VLM services with shared orchestration logic.

    Subclasses only need to implement `_call_vlm(prompt, image_bytes) -> str`
    to handle provider-specific HTTP request formatting.

    This provides:
    - Shared `analyze()` implementation (OCR context → prompt → call → parse → build)
    - Shared `detect_objects()` implementation (prompt → call → parse → build)
    - Consistent error handling and logging
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        timeout: float = 60.0,
    ) -> None:
        """Initialize base VLM service.

        Args:
            api_key: API key for the provider.
            model: Model identifier.
            base_url: Base URL for API calls.
            timeout: Request timeout in seconds.
        """
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Public API (shared implementation)
    # ------------------------------------------------------------------

    async def analyze(
        self,
        image_bytes: bytes,
        ocr_results: list[OCRResult] | None = None,
        lang: str = "zh",
    ) -> SceneAnalysis:
        """Send image to VLM and parse structured SceneAnalysis.

        Args:
            image_bytes: Raw image bytes.
            ocr_results: Optional OCR results for context.
            lang: Output language - 'zh' for Chinese, 'en' for English.

        Returns:
            Parsed SceneAnalysis from the VLM response.
        """
        ocr_context = build_ocr_context(ocr_results, lang)
        prompt_tpl = SCENE_ANALYSIS_PROMPT_EN if lang == "en" else SCENE_ANALYSIS_PROMPT_ZH
        prompt = prompt_tpl.format(ocr_context=ocr_context)
        response_text = await self._call_vlm(prompt, image_bytes)
        data = parse_llm_json(response_text)
        return build_scene_analysis(data)

    async def detect_objects(self, image_bytes: bytes, lang: str = "zh") -> list[DetectedObject]:
        """Send image to VLM for object detection.

        Args:
            image_bytes: Raw image bytes.
            lang: Output language - 'zh' for Chinese, 'en' for English.

        Returns:
            List of detected objects.
        """
        prompt = OBJECT_DETECTION_PROMPT_EN if lang == "en" else OBJECT_DETECTION_PROMPT_ZH
        response_text = await self._call_vlm(prompt, image_bytes)
        items = parse_llm_json(response_text)
        if not isinstance(items, list):
            items = []
        return [build_detected_object(item) for item in items]

    # ------------------------------------------------------------------
    # Abstract method (provider-specific)
    # ------------------------------------------------------------------

    @abstractmethod
    async def _call_vlm(self, prompt: str, image_bytes: bytes) -> str:
        """Make a VLM API call and return the response text.

        This is the only method subclasses need to implement.
        It should handle:
        - Image encoding (base64, etc.)
        - Request formatting (provider-specific payload structure)
        - HTTP client management
        - Retry logic
        - Response extraction (provider-specific response parsing)

        Args:
            prompt: The text prompt to send.
            image_bytes: Raw image bytes.

        Returns:
            The text response from the VLM.

        Raises:
            ValueError: If the response cannot be parsed.
            httpx.HTTPStatusError: If the API returns an error.
        """
        ...
