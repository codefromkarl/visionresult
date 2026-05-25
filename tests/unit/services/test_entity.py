"""Tests for LLM-based entity extraction service."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from vision_insight.models.schemas import (
    EntityExtraction,
    LocationGuess,
    OCRResult,
    SceneAnalysis,
    TimeGuess,
)
from vision_insight.services.entity.llm_entity_service import LLMEntityService

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"

VALID_ENTITIES_JSON = {
    "location_keywords": ["Rome", "Trastevere"],
    "brands": ["Starbucks"],
    "landmarks": ["Colosseum"],
    "text_entities": ["OPEN 24H", "+39 06 1234567"],
}

SAMPLE_SCENE = SceneAnalysis(
    scene_type="restaurant",
    description="An Italian restaurant in Rome.",
    location_guess=LocationGuess(location="Rome, Italy", confidence=0.8, evidence=["Italian menu"]),
    time_guess=TimeGuess(time_of_day="evening", season="summer", year_estimate="2024"),
    key_evidence=["wine glasses"],
    uncertainties=[],
)

SAMPLE_OCR = [
    OCRResult(
        text="OPEN 24H",
        bbox=[[0, 0], [10, 0], [10, 10], [0, 10]],
        confidence=0.95,
    ),
    OCRResult(
        text="+39 06 1234567",
        bbox=[[20, 20], [30, 20], [30, 30], [20, 30]],
        confidence=0.88,
    ),
    OCRResult(
        text="noise",
        bbox=[[40, 40], [50, 40], [50, 50], [40, 50]],
        confidence=0.3,
    ),
]


def _openai_chat_response(content: str) -> dict:
    return {
        "choices": [
            {
                "message": {"content": content, "role": "assistant"},
                "finish_reason": "stop",
                "index": 0,
            }
        ],
        "model": "gpt-4o-mini",
        "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
    }


# ===================================================================
# LLMEntityService Tests
# ===================================================================


class TestLLMEntityService:
    """Tests for LLM-based entity extraction."""

    # --- construction ---

    def test_init_requires_api_key(self, monkeypatch):
        """Should raise ValueError when no API key is configured."""
        monkeypatch.setattr(
            "vision_insight.services.entity.llm_entity_service.settings.openai_api_key", ""
        )
        with pytest.raises(ValueError, match="OpenAI API key"):
            LLMEntityService(api_key=None)

    def test_init_with_explicit_key(self):
        """Should accept explicit API key."""
        svc = LLMEntityService(api_key="test-key")
        assert svc._client._api_key == "test-key"

    # --- extract (normal path) ---

    @respx.mock
    @pytest.mark.asyncio
    async def test_extract_returns_entity_extraction(self):
        """Should parse valid JSON into EntityExtraction."""
        respx.post(OPENAI_CHAT_URL).mock(
            return_value=httpx.Response(
                200, json=_openai_chat_response(json.dumps(VALID_ENTITIES_JSON))
            )
        )
        svc = LLMEntityService(api_key="test-key")
        result = await svc.extract(SAMPLE_SCENE, SAMPLE_OCR)

        assert isinstance(result, EntityExtraction)
        assert "Rome" in result.location_keywords
        assert "Trastevere" in result.location_keywords
        assert "Starbucks" in result.brands
        assert "Colosseum" in result.landmarks
        assert "OPEN 24H" in result.text_entities

    @respx.mock
    @pytest.mark.asyncio
    async def test_extract_empty_categories(self):
        """Should handle empty arrays for all categories."""
        empty = {"location_keywords": [], "brands": [], "landmarks": [], "text_entities": []}
        respx.post(OPENAI_CHAT_URL).mock(
            return_value=httpx.Response(200, json=_openai_chat_response(json.dumps(empty)))
        )
        svc = LLMEntityService(api_key="test-key")
        result = await svc.extract(SAMPLE_SCENE, SAMPLE_OCR)

        assert result.location_keywords == []
        assert result.brands == []
        assert result.landmarks == []
        assert result.text_entities == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_extract_prompt_includes_scene_and_ocr(self):
        """Should include scene analysis and OCR texts in the prompt."""
        captured_request = {}

        def _capture(request):
            captured_request["body"] = request.content
            return httpx.Response(200, json=_openai_chat_response(json.dumps(VALID_ENTITIES_JSON)))

        respx.post(OPENAI_CHAT_URL).mock(side_effect=_capture)

        svc = LLMEntityService(api_key="test-key")
        await svc.extract(SAMPLE_SCENE, SAMPLE_OCR)

        body = json.loads(captured_request["body"])
        user_content = body["messages"][0]["content"]
        assert "restaurant" in user_content
        assert "OPEN 24H" in user_content
        assert "+39 06 1234567" in user_content

    @respx.mock
    @pytest.mark.asyncio
    async def test_extract_handles_markdown_fenced_json(self):
        """Should strip ```json fences before parsing."""
        fenced = "```json\n" + json.dumps(VALID_ENTITIES_JSON) + "\n```"
        respx.post(OPENAI_CHAT_URL).mock(
            return_value=httpx.Response(200, json=_openai_chat_response(fenced))
        )
        svc = LLMEntityService(api_key="test-key")
        result = await svc.extract(SAMPLE_SCENE, SAMPLE_OCR)
        assert "Rome" in result.location_keywords

    # --- extract (error paths / fallback) ---

    @respx.mock
    @pytest.mark.asyncio
    async def test_extract_invalid_json_falls_back(self):
        """Should fall back to rule-based extraction on invalid JSON."""
        respx.post(OPENAI_CHAT_URL).mock(
            return_value=httpx.Response(200, json=_openai_chat_response("not json"))
        )
        svc = LLMEntityService(api_key="test-key")
        result = await svc.extract(SAMPLE_SCENE, SAMPLE_OCR)

        # Fallback should still return EntityExtraction
        assert isinstance(result, EntityExtraction)
        # Fallback uses scene location_guess
        assert "Rome, Italy" in result.location_keywords
        # Fallback includes high-confidence OCR texts
        assert "OPEN 24H" in result.text_entities
        assert "+39 06 1234567" in result.text_entities
        # Low-confidence OCR text should be excluded
        assert "noise" not in result.text_entities

    @respx.mock
    @pytest.mark.asyncio
    async def test_extract_http_error_propagates(self):
        """Should propagate HTTP errors (not caught by fallback)."""
        respx.post(OPENAI_CHAT_URL).mock(
            return_value=httpx.Response(503, text="Service Unavailable")
        )
        svc = LLMEntityService(api_key="test-key")
        with pytest.raises(httpx.HTTPStatusError):
            await svc.extract(SAMPLE_SCENE, SAMPLE_OCR)

    @respx.mock
    @pytest.mark.asyncio
    async def test_extract_empty_ocr_results(self):
        """Should handle empty OCR results."""
        empty = {"location_keywords": [], "brands": [], "landmarks": [], "text_entities": []}
        respx.post(OPENAI_CHAT_URL).mock(
            return_value=httpx.Response(200, json=_openai_chat_response(json.dumps(empty)))
        )
        svc = LLMEntityService(api_key="test-key")
        result = await svc.extract(SAMPLE_SCENE, [])
        assert isinstance(result, EntityExtraction)
        assert result.text_entities == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_extract_partial_json_fields(self):
        """Should handle JSON with missing fields gracefully."""
        partial = {"location_keywords": ["Rome"]}
        respx.post(OPENAI_CHAT_URL).mock(
            return_value=httpx.Response(200, json=_openai_chat_response(json.dumps(partial)))
        )
        svc = LLMEntityService(api_key="test-key")
        result = await svc.extract(SAMPLE_SCENE, SAMPLE_OCR)

        assert result.location_keywords == ["Rome"]
        assert result.brands == []
        assert result.landmarks == []
        assert result.text_entities == []


# ===================================================================
# Fallback extraction tests
# ===================================================================


class TestFallbackExtraction:
    """Tests for _fallback_extraction static method."""

    def test_fallback_with_location_guess(self):
        """Should extract location from scene.location_guess."""
        result = LLMEntityService._fallback_extraction(SAMPLE_OCR, SAMPLE_SCENE)
        assert "Rome, Italy" in result.location_keywords

    def test_fallback_with_high_confidence_ocr(self):
        """Should include OCR texts with confidence >= 0.8."""
        result = LLMEntityService._fallback_extraction(SAMPLE_OCR, SAMPLE_SCENE)
        assert "OPEN 24H" in result.text_entities
        assert "+39 06 1234567" in result.text_entities

    def test_fallback_excludes_low_confidence_ocr(self):
        """Should exclude OCR texts with confidence < 0.8."""
        result = LLMEntityService._fallback_extraction(SAMPLE_OCR, SAMPLE_SCENE)
        assert "noise" not in result.text_entities

    def test_fallback_no_location_guess(self):
        """Should handle scene without location_guess."""
        scene = SceneAnalysis(scene_type="unknown", description="unclear")
        result = LLMEntityService._fallback_extraction([], scene)
        assert result.location_keywords == []
        assert result.brands == []
        assert result.landmarks == []
        assert result.text_entities == []

    def test_fallback_empty_ocr(self):
        """Should handle empty OCR results."""
        result = LLMEntityService._fallback_extraction([], SAMPLE_SCENE)
        assert result.text_entities == []
        assert "Rome, Italy" in result.location_keywords
