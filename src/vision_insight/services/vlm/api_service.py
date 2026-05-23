"""OpenAI GPT-4V and Gemini Pro Vision implementation of VLMService."""

import contextvars
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
from vision_insight.utils.image import encode_image_base64
from vision_insight.utils.json_helpers import parse_llm_json
from vision_insight.utils.retry import retry_with_backoff
from vision_insight.utils.scene_builders import (
    build_detected_object,
    build_scene_analysis,
)

logger = logging.getLogger(__name__)

# Context variable for task_id. Pipeline nodes set this before calling VLM
# providers so lower-level request/retry logging can correlate events.
current_task_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_task_id", default="unknown"
)

class OpenAIVLMService(VLMService):
    """VLM service using OpenAI GPT-4 Vision API via httpx."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o",
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 60.0,
    ) -> None:
        self._api_key = api_key or settings.openai_api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        if not self._api_key:
            raise ValueError("OpenAI API key is required (set VIA_OPENAI_API_KEY)")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def analyze(
        self,
        image_bytes: bytes,
        ocr_results: list[OCRResult] | None = None,
        lang: str = "zh",
    ) -> SceneAnalysis:
        """Send image to GPT-4V and parse structured SceneAnalysis."""
        ocr_context = build_ocr_context(ocr_results, lang)
        prompt_tpl = SCENE_ANALYSIS_PROMPT_EN if lang == "en" else SCENE_ANALYSIS_PROMPT_ZH
        prompt = prompt_tpl.format(ocr_context=ocr_context)
        response_text = await self._vision_chat(prompt, image_bytes)
        data = parse_llm_json(response_text)
        return build_scene_analysis(data)

    async def detect_objects(self, image_bytes: bytes, lang: str = "en") -> list[DetectedObject]:
        """Send image to GPT-4V for object detection."""
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
                                "url": f"data:image/jpeg;base64,{b64_image}",
                            },
                        },
                    ],
                }
            ],
            "max_tokens": 2048,
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

    # parse_json_response and build_scene_analysis are now free functions
    # imported from vision_insight.utils.json_helpers and vision_insight.utils.scene_builders


class GeminiVLMService(VLMService):
    """VLM service using Google Gemini Pro Vision API via httpx."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gemini-2.0-flash",
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        timeout: float = 60.0,
    ) -> None:
        self._api_key = api_key or settings.gemini_api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        if not self._api_key:
            raise ValueError("Gemini API key is required (set VIA_GEMINI_API_KEY)")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def analyze(
        self,
        image_bytes: bytes,
        ocr_results: list[OCRResult] | None = None,
        lang: str = "zh",
    ) -> SceneAnalysis:
        """Send image to Gemini and parse structured SceneAnalysis."""
        ocr_context = build_ocr_context(ocr_results, lang)
        prompt_tpl = SCENE_ANALYSIS_PROMPT_EN if lang == "en" else SCENE_ANALYSIS_PROMPT_ZH
        prompt = prompt_tpl.format(ocr_context=ocr_context)
        response_text = await self._generate(prompt, image_bytes)
        data = parse_llm_json(response_text)
        return build_scene_analysis(data)

    async def detect_objects(self, image_bytes: bytes, lang: str = "en") -> list[DetectedObject]:
        """Send image to Gemini for object detection."""
        prompt = OBJECT_DETECTION_PROMPT_EN if lang == "en" else OBJECT_DETECTION_PROMPT_ZH
        response_text = await self._generate(prompt, image_bytes)
        items = parse_llm_json(response_text)
        if not isinstance(items, list):
            items = []
        return [build_detected_object(item) for item in items]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _generate(self, prompt: str, image_bytes: bytes) -> str:
        """Make a Gemini generateContent request with retry."""
        b64_image = encode_image_base64(image_bytes)
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": b64_image,
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 2048,
            },
        }
        url = f"{self._base_url}/models/{self._model}:generateContent?key={self._api_key}"

        async def _do_request():
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                return resp.json()

        body = await retry_with_backoff(_do_request)

        # Extract text from Gemini response structure
        candidates = body.get("candidates", [])
        if not candidates:
            raise ValueError("Gemini returned no candidates")
        parts = candidates[0].get("content", {}).get("parts", [])
        for part in parts:
            if "text" in part:
                return part["text"]
        raise ValueError("Gemini returned no text content")
