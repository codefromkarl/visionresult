"""Tests for fallback service implementations."""

from __future__ import annotations

import pytest

from vision_insight.models.schemas import LocationGuess, OCRResult, SceneAnalysis
from vision_insight.services import OCRService, VLMService
from vision_insight.services.fallback import (
    CompositeOCRService,
    CompositeVLMService,
    DegradedVLMService,
    RuleBasedEntityService,
)


class EmptyOCR(OCRService):
    async def extract(self, image_bytes: bytes) -> list[OCRResult]:
        return []


class GoodOCR(OCRService):
    async def extract(self, image_bytes: bytes) -> list[OCRResult]:
        return [OCRResult(text="Shibuya", bbox=[[0, 0], [1, 0], [1, 1], [0, 1]], confidence=0.9)]


class FailingVLM(VLMService):
    async def analyze(self, image_bytes, ocr_results=None, lang: str = "zh"):
        raise RuntimeError("provider down")

    async def detect_objects(self, image_bytes, lang: str = "zh"):
        raise RuntimeError("provider down")


class GoodVLM(VLMService):
    async def analyze(self, image_bytes, ocr_results=None, lang: str = "zh"):
        return SceneAnalysis(scene_type="street", description=f"lang={lang}")

    async def detect_objects(self, image_bytes, lang: str = "zh"):
        return []


@pytest.mark.asyncio
async def test_composite_ocr_returns_first_non_empty_result():
    service = CompositeOCRService([("empty", EmptyOCR()), ("good", GoodOCR())])

    results = await service.extract(b"image")

    assert len(results) == 1
    assert results[0].text == "Shibuya"


@pytest.mark.asyncio
async def test_degraded_vlm_is_explicit_about_unavailability():
    service = DegradedVLMService()
    ocr = [OCRResult(text="涩谷109", bbox=[[0, 0], [1, 0], [1, 1], [0, 1]], confidence=0.9)]

    scene = await service.analyze(b"image", ocr_results=ocr, lang="zh")

    assert scene.scene_type == "unknown"
    assert "不可用" in scene.description
    assert scene.key_evidence == ["OCR 文字：涩谷109"]


@pytest.mark.asyncio
async def test_composite_vlm_falls_back_to_second_provider():
    service = CompositeVLMService([("bad", FailingVLM()), ("good", GoodVLM())])

    scene = await service.analyze(b"image", lang="en")

    assert scene.scene_type == "street"
    assert scene.description == "lang=en"


@pytest.mark.asyncio
async def test_rule_based_entity_service_extracts_location_and_high_confidence_text():
    service = RuleBasedEntityService()
    scene = SceneAnalysis(
        scene_type="street",
        description="Tokyo street",
        location_guess=LocationGuess(location="Tokyo Shibuya", confidence=0.8),
    )
    ocr = [
        OCRResult(text="SHIBUYA", bbox=[[0, 0], [1, 0], [1, 1], [0, 1]], confidence=0.9),
        OCRResult(text="noise", bbox=[[0, 0], [1, 0], [1, 1], [0, 1]], confidence=0.3),
    ]

    entities = await service.extract(scene, ocr)

    assert entities.location_keywords == ["Tokyo Shibuya"]
    assert entities.text_entities == ["SHIBUYA"]
