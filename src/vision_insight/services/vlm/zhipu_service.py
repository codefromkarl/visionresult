"""Zhipu GLM-4V implementation of VLMService."""

import logging

import httpx

from vision_insight.core.config import settings
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
from vision_insight.utils.image import detect_image_format, encode_image_base64
from vision_insight.utils.json_helpers import parse_llm_json
from vision_insight.utils.retry import retry_with_backoff
from vision_insight.utils.scene_builders import (
    build_detected_object,
    build_scene_analysis,
)

logger = logging.getLogger(__name__)


class ZhipuVLMService(VLMService):
    """VLM service using Zhipu GLM-4V API."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "glm-4v-flash",
        base_url: str = "https://open.bigmodel.cn/api/coding/paas/v4",
        timeout: float = 60.0,
    ) -> None:
        self._api_key = api_key or settings.zhipu_api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        if not self._api_key:
            raise ValueError("Zhipu API key is required (set VIA_ZHIPU_API_KEY)")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def analyze(
        self, image_bytes: bytes, ocr_results: list[OCRResult] | None = None, lang: str = "zh"
    ) -> SceneAnalysis:
        """Send image to GLM-4V and parse structured SceneAnalysis."""
        ocr_context = build_ocr_context(ocr_results, lang)
        prompt = (SCENE_ANALYSIS_PROMPT_EN if lang == "en" else SCENE_ANALYSIS_PROMPT_ZH).format(
            ocr_context=ocr_context
        )
        response_text = await self._vision_chat(prompt, image_bytes)
        data = parse_llm_json(response_text)
        return build_scene_analysis(data)

    async def detect_objects(self, image_bytes: bytes, lang: str = "zh") -> list[DetectedObject]:
        """Send image to GLM-4V for object detection."""
        prompt = OBJECT_DETECTION_PROMPT_EN if lang == "en" else OBJECT_DETECTION_PROMPT_ZH
        response_text = await self._vision_chat(prompt, image_bytes)
        items = parse_llm_json(response_text)
        if not isinstance(items, list):
            items = []
        return [build_detected_object(item) for item in items]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _vision_chat(self, prompt: str, image_bytes: bytes) -> str:
        """Make a vision chat completion request with retry."""
        b64_image = encode_image_base64(image_bytes)

        # Detect image format
        image_format = detect_image_format(image_bytes)

        # Zhipu GLM-4V API format (OpenAI compatible)
        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/{image_format};base64,{b64_image}",
                            },
                        },
                    ],
                }
            ],
            "max_tokens": 1024,
            "temperature": 0.2,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        async def _do_request():
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                resp.raise_for_status()
                return resp.json()

        body = await retry_with_backoff(_do_request)
        return body["choices"][0]["message"]["content"]
