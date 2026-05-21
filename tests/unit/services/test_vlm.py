"""Tests for VLM API service (OpenAI GPT-4V and Gemini Pro Vision)."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from vision_insight.models.schemas import (
    DetectedObject,
    OCRResult,
    SceneAnalysis,
)
from vision_insight.services.vlm.api_service import (
    GeminiVLMService,
    OpenAIVLMService,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_IMAGE = b"\xff\xd8\xff\xe0" + b"\x00" * 100  # minimal JPEG-like bytes

VALID_SCENE_JSON = {
    "scene_type": "restaurant",
    "description": "A cozy Italian restaurant with dim lighting and wooden tables.",
    "location_guess": {
        "location": "Rome, Italy",
        "confidence": 0.75,
        "evidence": ["Italian menu text", "Mediterranean decor"],
    },
    "time_guess": {
        "time_of_day": "evening",
        "season": "summer",
        "year_estimate": "2020s",
        "evidence": ["warm lighting"],
    },
    "people": [
        {"count": 2, "age_group": "young", "activity": "dining"},
    ],
    "key_evidence": ["Italian menu", "wine glasses", "candle light"],
    "uncertainties": ["exact city uncertain"],
}

VALID_OBJECTS_JSON = [
    {
        "label": "wine glass",
        "confidence": 0.92,
        "bbox": [100, 200, 150, 300],
        "category": "food",
    },
    {
        "label": "menu",
        "confidence": 0.85,
        "bbox": [50, 50, 200, 250],
        "category": "text",
    },
]

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
GEMINI_URL_PATTERN = "https://generativelanguage.googleapis.com/v1beta/models/*"


def _openai_chat_response(content: str) -> dict:
    """Build a mock OpenAI chat completion response."""
    return {
        "choices": [
            {
                "message": {"content": content, "role": "assistant"},
                "finish_reason": "stop",
                "index": 0,
            }
        ],
        "model": "gpt-4o",
        "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
    }


def _gemini_response(content: str) -> dict:
    """Build a mock Gemini generateContent response."""
    return {
        "candidates": [
            {
                "content": {"parts": [{"text": content}]},
                "finishReason": "STOP",
            }
        ],
    }


# ===================================================================
# OpenAIVLMService Tests
# ===================================================================


class TestOpenAIVLMService:
    """Tests for OpenAI GPT-4V implementation."""

    # --- construction ---

    def test_init_requires_api_key(self, monkeypatch):
        """Should raise ValueError when no API key is configured."""
        monkeypatch.delenv("VIA_OPENAI_API_KEY", raising=False)
        # Also patch the settings object to ensure it's empty
        monkeypatch.setattr(
            "vision_insight.services.vlm.api_service.settings.openai_api_key", ""
        )
        with pytest.raises(ValueError, match="OpenAI API key"):
            OpenAIVLMService(api_key=None)

    def test_init_with_explicit_key(self):
        """Should accept explicit API key."""
        svc = OpenAIVLMService(api_key="test-key-123")
        assert svc._api_key == "test-key-123"

    # --- analyze (normal path) ---

    @respx.mock
    @pytest.mark.asyncio
    async def test_analyze_returns_scene_analysis(self):
        """Should parse valid JSON response into SceneAnalysis."""
        respx.post(OPENAI_CHAT_URL).mock(
            return_value=httpx.Response(
                200, json=_openai_chat_response(json.dumps(VALID_SCENE_JSON))
            )
        )
        svc = OpenAIVLMService(api_key="test-key")
        result = await svc.analyze(SAMPLE_IMAGE)

        assert isinstance(result, SceneAnalysis)
        assert result.scene_type == "restaurant"
        expected = "A cozy Italian restaurant with dim lighting and wooden tables."
        assert result.description == expected
        assert result.location_guess is not None
        assert result.location_guess.location == "Rome, Italy"
        assert result.location_guess.confidence == 0.75
        assert result.time_guess is not None
        assert result.time_guess.time_of_day == "evening"
        assert len(result.people) == 1
        assert result.people[0].count == 2
        assert len(result.key_evidence) == 3
        assert len(result.uncertainties) == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_analyze_with_ocr_context(self):
        """Should include OCR texts in the prompt."""
        captured_request = {}

        def _capture(request):
            captured_request["body"] = request.content
            return httpx.Response(200, json=_openai_chat_response(json.dumps(VALID_SCENE_JSON)))

        respx.post(OPENAI_CHAT_URL).mock(side_effect=_capture)

        svc = OpenAIVLMService(api_key="test-key")
        ocr = [
            OCRResult(
                text="OPEN 24H",
                bbox=[[0, 0], [10, 0], [10, 10], [0, 10]],
                confidence=0.95,
            ),
            OCRResult(
                text="Free WiFi",
                bbox=[[20, 20], [30, 20], [30, 30], [20, 30]],
                confidence=0.88,
            ),
        ]
        await svc.analyze(SAMPLE_IMAGE, ocr_results=ocr)

        body = json.loads(captured_request["body"])
        user_content = body["messages"][0]["content"]
        assert isinstance(user_content, list)
        text_parts = [p["text"] for p in user_content if p.get("type") == "text"]
        combined = "\n".join(text_parts)
        assert "OPEN 24H" in combined
        assert "Free WiFi" in combined

    # --- analyze (error paths) ---

    @respx.mock
    @pytest.mark.asyncio
    async def test_analyze_handles_markdown_fenced_json(self):
        """Should strip ```json fences before parsing."""
        fenced = "```json\n" + json.dumps(VALID_SCENE_JSON) + "\n```"
        respx.post(OPENAI_CHAT_URL).mock(
            return_value=httpx.Response(200, json=_openai_chat_response(fenced))
        )
        svc = OpenAIVLMService(api_key="test-key")
        result = await svc.analyze(SAMPLE_IMAGE)
        assert result.scene_type == "restaurant"

    @respx.mock
    @pytest.mark.asyncio
    async def test_analyze_http_error_raises(self):
        """Should propagate HTTP errors."""
        respx.post(OPENAI_CHAT_URL).mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )
        svc = OpenAIVLMService(api_key="test-key")
        with pytest.raises(httpx.HTTPStatusError):
            await svc.analyze(SAMPLE_IMAGE)

    @respx.mock
    @pytest.mark.asyncio
    async def test_analyze_invalid_json_raises(self):
        """Should raise JSONDecodeError when model returns non-JSON."""
        respx.post(OPENAI_CHAT_URL).mock(
            return_value=httpx.Response(200, json=_openai_chat_response("not valid json"))
        )
        svc = OpenAIVLMService(api_key="test-key")
        with pytest.raises(json.JSONDecodeError):
            await svc.analyze(SAMPLE_IMAGE)

    # --- analyze (boundary cases) ---

    @respx.mock
    @pytest.mark.asyncio
    async def test_analyze_minimal_scene_json(self):
        """Should handle minimal JSON with only required fields."""
        minimal = {"scene_type": "unknown", "description": "unclear"}
        respx.post(OPENAI_CHAT_URL).mock(
            return_value=httpx.Response(200, json=_openai_chat_response(json.dumps(minimal)))
        )
        svc = OpenAIVLMService(api_key="test-key")
        result = await svc.analyze(SAMPLE_IMAGE)
        assert result.scene_type == "unknown"
        assert result.location_guess is None
        assert result.time_guess is None
        assert result.people == []
        assert result.key_evidence == []

    # --- detect_objects (normal path) ---

    @respx.mock
    @pytest.mark.asyncio
    async def test_detect_objects_returns_list(self):
        """Should parse valid object detection response."""
        respx.post(OPENAI_CHAT_URL).mock(
            return_value=httpx.Response(
                200, json=_openai_chat_response(json.dumps(VALID_OBJECTS_JSON))
            )
        )
        svc = OpenAIVLMService(api_key="test-key")
        result = await svc.detect_objects(SAMPLE_IMAGE)

        assert len(result) == 2
        assert all(isinstance(o, DetectedObject) for o in result)
        assert result[0].label == "wine glass"
        assert result[0].confidence == 0.92
        assert result[0].bbox == [100, 200, 150, 300]

    @respx.mock
    @pytest.mark.asyncio
    async def test_detect_objects_empty_array(self):
        """Should return empty list for empty array response."""
        respx.post(OPENAI_CHAT_URL).mock(
            return_value=httpx.Response(200, json=_openai_chat_response("[]"))
        )
        svc = OpenAIVLMService(api_key="test-key")
        result = await svc.detect_objects(SAMPLE_IMAGE)
        assert result == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_detect_objects_non_array_returns_empty(self):
        """Should return empty list when model returns non-array."""
        respx.post(OPENAI_CHAT_URL).mock(
            return_value=httpx.Response(
                200, json=_openai_chat_response(json.dumps({"objects": []}))
            )
        )
        svc = OpenAIVLMService(api_key="test-key")
        result = await svc.detect_objects(SAMPLE_IMAGE)
        assert result == []


# ===================================================================
# GeminiVLMService Tests
# ===================================================================


class TestGeminiVLMService:
    """Tests for Gemini Pro Vision implementation."""

    def test_init_requires_api_key(self, monkeypatch):
        """Should raise ValueError when no API key is configured."""
        monkeypatch.setattr(
            "vision_insight.services.vlm.api_service.settings.gemini_api_key", ""
        )
        with pytest.raises(ValueError, match="Gemini API key"):
            GeminiVLMService(api_key=None)

    @respx.mock
    @pytest.mark.asyncio
    async def test_analyze_returns_scene_analysis(self):
        """Should parse valid Gemini response into SceneAnalysis."""
        respx.post(url__regex=GEMINI_URL_PATTERN).mock(
            return_value=httpx.Response(
                200, json=_gemini_response(json.dumps(VALID_SCENE_JSON))
            )
        )
        svc = GeminiVLMService(api_key="test-key")
        result = await svc.analyze(SAMPLE_IMAGE)

        assert isinstance(result, SceneAnalysis)
        assert result.scene_type == "restaurant"
        assert result.location_guess.location == "Rome, Italy"

    @respx.mock
    @pytest.mark.asyncio
    async def test_analyze_with_ocr_context(self):
        """Should include OCR texts in prompt for Gemini."""
        captured_request = {}

        def _capture(request):
            captured_request["body"] = request.content
            return httpx.Response(
                200, json=_gemini_response(json.dumps(VALID_SCENE_JSON))
            )

        respx.post(url__regex=GEMINI_URL_PATTERN).mock(side_effect=_capture)

        svc = GeminiVLMService(api_key="test-key")
        ocr = [OCRResult(text="EXIT", bbox=[[0, 0], [10, 0], [10, 10], [0, 10]], confidence=0.9)]
        await svc.analyze(SAMPLE_IMAGE, ocr_results=ocr)

        body = json.loads(captured_request["body"])
        parts = body["contents"][0]["parts"]
        text_parts = [p["text"] for p in parts if "text" in p]
        combined = "\n".join(text_parts)
        assert "EXIT" in combined

    @respx.mock
    @pytest.mark.asyncio
    async def test_analyze_http_error_raises(self):
        """Should propagate HTTP errors from Gemini."""
        respx.post(url__regex=GEMINI_URL_PATTERN).mock(
            return_value=httpx.Response(429, text="Rate limited")
        )
        svc = GeminiVLMService(api_key="test-key")
        with pytest.raises(httpx.HTTPStatusError):
            await svc.analyze(SAMPLE_IMAGE)

    @respx.mock
    @pytest.mark.asyncio
    async def test_analyze_no_candidates_raises(self):
        """Should raise ValueError when Gemini returns no candidates."""
        respx.post(url__regex=GEMINI_URL_PATTERN).mock(
            return_value=httpx.Response(200, json={"candidates": []})
        )
        svc = GeminiVLMService(api_key="test-key")
        with pytest.raises(ValueError, match="no candidates"):
            await svc.analyze(SAMPLE_IMAGE)

    @respx.mock
    @pytest.mark.asyncio
    async def test_analyze_no_text_content_raises(self):
        """Should raise ValueError when Gemini returns no text parts."""
        respx.post(url__regex=GEMINI_URL_PATTERN).mock(
            return_value=httpx.Response(
                200,
                json={
                    "candidates": [
                        {"content": {"parts": [{"functionCall": {"name": "foo"}}]}}
                    ]
                },
            )
        )
        svc = GeminiVLMService(api_key="test-key")
        with pytest.raises(ValueError, match="no text content"):
            await svc.analyze(SAMPLE_IMAGE)

    @respx.mock
    @pytest.mark.asyncio
    async def test_detect_objects_returns_list(self):
        """Should parse Gemini object detection response."""
        respx.post(url__regex=GEMINI_URL_PATTERN).mock(
            return_value=httpx.Response(
                200, json=_gemini_response(json.dumps(VALID_OBJECTS_JSON))
            )
        )
        svc = GeminiVLMService(api_key="test-key")
        result = await svc.detect_objects(SAMPLE_IMAGE)
        assert len(result) == 2
        assert result[0].label == "wine glass"


# ===================================================================
# Shared parsing / builder tests
# ===================================================================


class TestParseJsonResponse:
    """Tests for _parse_json_response static method."""

    def test_plain_json(self):
        assert OpenAIVLMService._parse_json_response('{"a": 1}') == {"a": 1}

    def test_json_with_fences(self):
        result = OpenAIVLMService._parse_json_response('```json\n{"a": 1}\n```')
        assert result == {"a": 1}

    def test_json_with_leading_whitespace(self):
        assert OpenAIVLMService._parse_json_response('  \n{"a": 1}\n  ') == {"a": 1}

    def test_invalid_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            OpenAIVLMService._parse_json_response("not json at all")


class TestBuildSceneAnalysis:
    """Tests for _build_scene_analysis static method."""

    def test_full_data(self):
        result = OpenAIVLMService._build_scene_analysis(VALID_SCENE_JSON)
        assert result.scene_type == "restaurant"
        assert result.location_guess.location == "Rome, Italy"
        assert len(result.people) == 1

    def test_empty_data(self):
        result = OpenAIVLMService._build_scene_analysis({})
        assert result.scene_type == "unknown"
        assert result.location_guess is None
        assert result.people == []
