"""LLM-based entity extraction service."""

import json
import logging

from vision_insight.core.config import settings
from vision_insight.models.schemas import EntityExtraction, OCRResult, SceneAnalysis
from vision_insight.services import EntityService
from vision_insight.utils import extract_entities_rule_based
from vision_insight.utils.chat_client import ChatCompletionClient
from vision_insight.utils.json_helpers import parse_llm_json

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
        resolved_key = api_key or settings.openai_api_key
        if not resolved_key:
            raise ValueError("OpenAI API key is required for entity extraction")
        self._client = ChatCompletionClient(
            api_key=resolved_key,
            base_url=base_url,
            model=model,
            timeout=timeout,
            max_tokens=1024,
            temperature=0.1,
        )

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
            response_text = await self._client.chat(prompt)
            data = parse_llm_json(response_text)
            return self._build_entity_extraction(data)
        except (json.JSONDecodeError, ValueError, KeyError) as exc:
            logger.warning("Entity extraction failed, returning empty result: %s", exc)
            return self._fallback_extraction(ocr_results, scene)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

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
        return extract_entities_rule_based(scene, ocr_results)
