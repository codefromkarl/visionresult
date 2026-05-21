"""LLM-based entity extraction service."""

from __future__ import annotations

import json
import logging

import httpx

from vision_insight.core.config import settings
from vision_insight.models.schemas import EntityExtraction, OCRResult, SceneAnalysis
from vision_insight.services import EntityService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt template for entity extraction
# ---------------------------------------------------------------------------

ENTITY_EXTRACTION_PROMPT = """\
You are an information extraction specialist. Given the scene analysis and OCR text \
from an image, extract structured entities and return a JSON object (no markdown, \
pure JSON only):

{{
  "location_keywords": ["<location-related keywords, e.g. city names, street names, venue names>"],
  "brands": ["<brand names detected, e.g. Starbucks, Nike>"],
  "landmarks": ["<landmark names, e.g. Eiffel Tower, Great Wall>"],
  "text_entities": ["<important text entities from OCR, e.g. phone numbers, addresses, dates>"]
}}

## Scene Analysis
{scene_json}

## OCR Texts
{ocr_texts}

Rules:
- Extract only entities that are clearly identifiable.
- Deduplicate entries.
- If nothing found for a category, return an empty array.
"""


class LLMEntityService(EntityService):
    """Entity extraction using an LLM (OpenAI-compatible chat API)."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key or settings.openai_api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        if not self._api_key:
            raise ValueError("OpenAI API key is required for entity extraction")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def extract(self, scene: SceneAnalysis, ocr_results: list[OCRResult]) -> EntityExtraction:
        """Extract structured entities from scene analysis and OCR results."""
        scene_json = scene.model_dump_json(indent=2)
        ocr_texts = [r.text for r in ocr_results]

        prompt = ENTITY_EXTRACTION_PROMPT.format(
            scene_json=scene_json,
            ocr_texts=json.dumps(ocr_texts, ensure_ascii=False),
        )

        try:
            response_text = await self._chat(prompt)
            data = self._parse_json_response(response_text)
            return self._build_entity_extraction(data)
        except (json.JSONDecodeError, ValueError, KeyError) as exc:
            logger.warning("Entity extraction failed, returning empty result: %s", exc)
            return self._fallback_extraction(ocr_results, scene)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _chat(self, prompt: str) -> str:
        """Make a chat completion request (no image)."""
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1024,
            "temperature": 0.1,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            body = resp.json()

        return body["choices"][0]["message"]["content"]

    @staticmethod
    def _parse_json_response(text: str) -> dict:
        """Extract JSON from model response, handling markdown fences."""
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [ln for ln in lines if not ln.strip().startswith("```")]
            text = "\n".join(lines)
        return json.loads(text)

    @staticmethod
    def _build_entity_extraction(data: dict) -> EntityExtraction:
        """Build EntityExtraction from parsed JSON dict."""
        return EntityExtraction(
            location_keywords=data.get("location_keywords", []),
            brands=data.get("brands", []),
            landmarks=data.get("landmarks", []),
            text_entities=data.get("text_entities", []),
        )

    @staticmethod
    def _fallback_extraction(
        ocr_results: list[OCRResult], scene: SceneAnalysis
    ) -> EntityExtraction:
        """Rule-based fallback when LLM parsing fails."""
        location_keywords: list[str] = []
        if scene.location_guess and scene.location_guess.location:
            location_keywords.append(scene.location_guess.location)

        # Extract text entities from OCR results with high confidence
        text_entities = [r.text for r in ocr_results if r.confidence >= 0.8]

        return EntityExtraction(
            location_keywords=location_keywords,
            brands=[],
            landmarks=[],
            text_entities=text_entities,
        )
