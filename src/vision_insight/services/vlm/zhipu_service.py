"""Zhipu GLM-4V implementation of VLMService."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any

import httpx

from vision_insight.core.config import settings
from vision_insight.models.schemas import (
    DetectedObject,
    LocationGuess,
    OCRResult,
    PeopleInfo,
    SceneAnalysis,
    TimeGuess,
)
from vision_insight.services import VLMService

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0  # seconds
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


async def _retry_with_backoff(coro_factory, max_retries: int = MAX_RETRIES):
    """Retry an async operation with exponential backoff."""
    last_exc = None
    for attempt in range(max_retries):
        try:
            return await coro_factory()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in RETRYABLE_STATUS_CODES and attempt < max_retries - 1:
                delay = RETRY_BASE_DELAY * (2**attempt)
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
                delay = RETRY_BASE_DELAY * (2**attempt)
                logger.warning(
                    "Timeout, attempt %d/%d, waiting %.1fs", attempt + 1, max_retries, delay
                )
                await asyncio.sleep(delay)
                last_exc = exc
            else:
                raise
    raise last_exc


# ---------------------------------------------------------------------------
# Structured prompt template for scene analysis
# ---------------------------------------------------------------------------

SCENE_ANALYSIS_PROMPT_ZH = """\
分析图片，用JSON回答：
{{"scene_type":"场景类型","description":"描述","location_guess":{{"location":"地点","confidence":0.5}},"time_guess":{{"time_of_day":"时段"}}}}
{ocr_context}"""

SCENE_ANALYSIS_PROMPT_EN = """\
Analyze this image and respond with JSON:
{{"scene_type":"scene type","description":"description",
"location_guess":{{"location":"location","confidence":0.5}},
"time_guess":{{"time_of_day":"time of day"}}}}
{ocr_context}"""

# Default alias
SCENE_ANALYSIS_PROMPT = SCENE_ANALYSIS_PROMPT_ZH

OBJECT_DETECTION_PROMPT_ZH = """\
检测这张图片中的所有显著对象。返回一个 JSON 数组（纯 JSON，不要 markdown）：

[
  {{
    "label": "<对象名称>",
    "confidence": <0.0-1.0>,
    "bbox": [x1, y1, x2, y2],
    "category": "<person|building|food|logo|vehicle|text|sign|other>"
  }}
]

如果没有可检测的对象，返回空数组 []。"""

OBJECT_DETECTION_PROMPT_EN = """\
Detect all notable objects in this image. Return a JSON array (no markdown, pure JSON):

[
  {{
    "label": "<object name>",
    "confidence": <0.0-1.0>,
    "bbox": [x1, y1, x2, y2],
    "category": "<person|building|food|logo|vehicle|text|sign|other>"
  }}
]

If no objects are detectable, return an empty array []."""

# Default alias
OBJECT_DETECTION_PROMPT = OBJECT_DETECTION_PROMPT_ZH


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
        ocr_context = ""
        if ocr_results:
            texts = [r.text for r in ocr_results]
            if lang == "en":
                ocr_context = f"\nTexts detected in image: {texts}\n"
            else:
                ocr_context = f"\n图片中检测到的文字：{texts}\n"

        prompt = (SCENE_ANALYSIS_PROMPT_EN if lang == "en" else SCENE_ANALYSIS_PROMPT_ZH).format(
            ocr_context=ocr_context
        )
        response_text = await self._vision_chat(prompt, image_bytes)
        data = self._parse_json_response(response_text)
        return self._build_scene_analysis(data)

    async def detect_objects(self, image_bytes: bytes, lang: str = "zh") -> list[DetectedObject]:
        """Send image to GLM-4V for object detection."""
        prompt = OBJECT_DETECTION_PROMPT_EN if lang == "en" else OBJECT_DETECTION_PROMPT_ZH
        response_text = await self._vision_chat(prompt, image_bytes)
        items = self._parse_json_response(response_text)
        if not isinstance(items, list):
            items = []
        return [self._build_detected_object(item) for item in items]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _vision_chat(self, prompt: str, image_bytes: bytes) -> str:
        """Make a vision chat completion request with retry."""
        b64_image = base64.b64encode(image_bytes).decode("utf-8")

        # Detect image format
        image_format = "jpeg"
        if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
            image_format = "png"
        elif image_bytes[:4] == b"GIF8":
            image_format = "gif"
        elif image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
            image_format = "webp"

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

        body = await _retry_with_backoff(_do_request)
        return body["choices"][0]["message"]["content"]

    @staticmethod
    def _parse_json_response(text: str) -> Any:
        """Extract JSON from model response, handling markdown fences."""
        text = text.strip()
        # Strip ```json ... ``` wrappers
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first and last lines (the fences)
            lines = [ln for ln in lines if not ln.strip().startswith("```")]
            text = "\n".join(lines)
        return json.loads(text)

    @staticmethod
    def _build_scene_analysis(data: dict) -> SceneAnalysis:
        """Build SceneAnalysis from parsed JSON dict."""
        location = None
        if lg := data.get("location_guess"):
            location = LocationGuess(
                location=lg.get("location", ""),
                confidence=float(lg.get("confidence", 0.0)),
                evidence=lg.get("evidence", []),
            )

        time = None
        if tg := data.get("time_guess"):
            time = TimeGuess(
                time_of_day=tg.get("time_of_day", ""),
                season=tg.get("season", ""),
                year_estimate=tg.get("year_estimate", ""),
                evidence=tg.get("evidence", []),
            )

        people = []
        for p in data.get("people", []):
            people.append(
                PeopleInfo(
                    count=int(p.get("count", 0)),
                    age_group=p.get("age_group", ""),
                    activity=p.get("activity", ""),
                )
            )

        return SceneAnalysis(
            scene_type=data.get("scene_type", "unknown"),
            description=data.get("description", ""),
            location_guess=location,
            time_guess=time,
            people=people,
            key_evidence=data.get("key_evidence", []),
            uncertainties=data.get("uncertainties", []),
        )

    @staticmethod
    def _build_detected_object(item: dict) -> DetectedObject:
        """Build DetectedObject from parsed JSON dict."""
        return DetectedObject(
            label=item.get("label", ""),
            confidence=float(item.get("confidence", 0.0)),
            bbox=item.get("bbox"),
            category=item.get("category", ""),
        )
