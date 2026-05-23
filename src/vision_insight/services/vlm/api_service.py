"""OpenAI GPT-4V and Gemini Pro Vision implementation of VLMService."""

from __future__ import annotations

import asyncio
import base64
import contextvars
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

# Context variable for task_id. Pipeline nodes set this before calling VLM
# providers so lower-level request/retry logging can correlate events.
current_task_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_task_id", default="unknown"
)

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
你是一个视觉场景分析师。请仔细分析这张图片。

重要规则：
1. 只返回有效的JSON对象，不要markdown，不要额外文本。
2. "scene_type" 必须是以下之一：indoor, outdoor, street, restaurant, office, home, transport,
   event, nature, unknown
3. "description" 用中文写2-4个不重复的句子描述场景。
4. "location_guess.location" 用中文写具体地点（如"东京涩谷"、"北京故宫"），不要写大洲或地区。
5. "time_guess.time_of_day" 必须是以下之一：morning, afternoon, evening, night
6. "time_guess.season" 必须是以下之一：spring, summer, autumn, winter
7. 所有文字描述（description, evidence, key_evidence, uncertainties）都用中文。

返回这个JSON结构：
{{
  "scene_type": "<indoor|outdoor|street|restaurant|office|home|transport|event|nature|unknown>",
  "description": "<用中文描述场景>"
  "location_guess": {{
    "location": "<用中文写具体地点>",
    "confidence": <0.0-1.0>,
    "evidence": ["<视觉线索1>", "<视觉线索2>"]
  }},
  "time_guess": {{
    "time_of_day": "<morning|afternoon|evening|night>",
    "season": "<spring|summer|autumn|winter>",
    "year_estimate": "<如 2020s, 2024>",
    "evidence": ["<时间线索1>"]
  }},
  "people": [
    {{
      "count": <int>,
      "age_group": "<young|middle-aged|elderly>",
      "activity": "<用中文描述活动>"
    }}
  ],
  "key_evidence": ["<重要的视觉细节1>", "<重要的视觉细节2>"],
  "uncertainties": ["<不确定的地方>"]
}}

{ocr_context}"""

SCENE_ANALYSIS_PROMPT_EN = """\
You are a visual scene analyst. Carefully analyze this image.

Important rules:
1. Return ONLY a valid JSON object. No markdown, no extra text.
2. "scene_type" must be one of: indoor, outdoor, street, restaurant, office, home, transport,
   event, nature, unknown
3. "description" must be 2-4 sentences in English.
4. "location_guess.location" must be a specific place in English.
5. "time_guess.time_of_day" must be one of: morning, afternoon, evening, night
6. "time_guess.season" must be one of: spring, summer, autumn, winter
7. All text fields must be in English.

Return this JSON structure:
{{
  "scene_type": "<indoor|outdoor|street|restaurant|office|home|transport|event|nature|unknown>",
  "description": "<describe scene in English>"
  "location_guess": {{
    "location": "<specific location in English>",
    "confidence": <0.0-1.0>,
    "evidence": ["<visual clue 1>", "<visual clue 2>"]
  }},
  "time_guess": {{
    "time_of_day": "<morning|afternoon|evening|night>",
    "season": "<spring|summer|autumn|winter>",
    "year_estimate": "<e.g. 2020s, 2024>",
    "evidence": ["<time clue 1>"]
  }},
  "people": [
    {{
      "count": <int>,
      "age_group": "<young|middle-aged|elderly>",
      "activity": "<describe activity in English>"
    }}
  ],
  "key_evidence": ["<important detail 1>", "<important detail 2>"],
  "uncertainties": ["<uncertain aspects>"]
}}

{ocr_context}"""

# Default (backward-compatible) alias
SCENE_ANALYSIS_PROMPT = SCENE_ANALYSIS_PROMPT_EN

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

# Default (backward-compatible) alias
OBJECT_DETECTION_PROMPT = OBJECT_DETECTION_PROMPT_EN


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
        ocr_context = ""
        if ocr_results:
            texts = [r.text for r in ocr_results]
            if lang == "en":
                ocr_context = f"\nOCR detected these texts: {texts}\n"
            else:
                ocr_context = f"\n图片中检测到的文字：{texts}\n"

        prompt_tpl = (
            SCENE_ANALYSIS_PROMPT_EN if lang == "en" else SCENE_ANALYSIS_PROMPT_ZH
        )
        prompt = prompt_tpl.format(ocr_context=ocr_context)
        response_text = await self._vision_chat(prompt, image_bytes)
        data = self._parse_json_response(response_text)
        return self._build_scene_analysis(data)

    async def detect_objects(
        self, image_bytes: bytes, lang: str = "en"
    ) -> list[DetectedObject]:
        """Send image to GPT-4V for object detection."""
        prompt = (
            OBJECT_DETECTION_PROMPT_EN if lang == "en" else OBJECT_DETECTION_PROMPT_ZH
        )
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
        ocr_context = ""
        if ocr_results:
            texts = [r.text for r in ocr_results]
            if lang == "en":
                ocr_context = f"\nOCR detected these texts: {texts}\n"
            else:
                ocr_context = f"\n图片中检测到的文字：{texts}\n"

        prompt_tpl = (
            SCENE_ANALYSIS_PROMPT_EN if lang == "en" else SCENE_ANALYSIS_PROMPT_ZH
        )
        prompt = prompt_tpl.format(ocr_context=ocr_context)
        response_text = await self._generate(prompt, image_bytes)
        data = OpenAIVLMService._parse_json_response(response_text)
        return OpenAIVLMService._build_scene_analysis(data)

    async def detect_objects(
        self, image_bytes: bytes, lang: str = "en"
    ) -> list[DetectedObject]:
        """Send image to Gemini for object detection."""
        prompt = (
            OBJECT_DETECTION_PROMPT_EN if lang == "en" else OBJECT_DETECTION_PROMPT_ZH
        )
        response_text = await self._generate(prompt, image_bytes)
        items = OpenAIVLMService._parse_json_response(response_text)
        if not isinstance(items, list):
            items = []
        return [OpenAIVLMService._build_detected_object(item) for item in items]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _generate(self, prompt: str, image_bytes: bytes) -> str:
        """Make a Gemini generateContent request with retry."""
        b64_image = base64.b64encode(image_bytes).decode("utf-8")
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

        body = await _retry_with_backoff(_do_request)

        # Extract text from Gemini response structure
        candidates = body.get("candidates", [])
        if not candidates:
            raise ValueError("Gemini returned no candidates")
        parts = candidates[0].get("content", {}).get("parts", [])
        for part in parts:
            if "text" in part:
                return part["text"]
        raise ValueError("Gemini returned no text content")
