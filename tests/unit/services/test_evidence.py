"""Tests for FusionService."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from vision_insight.models.schemas import (
    EntityExtraction,
    EvidenceItem,
    ImageMetadata,
    LocationGuess,
    OCRResult,
    SceneAnalysis,
    SearchResult,
    TimeGuess,
)
from vision_insight.services.evidence.fusion_service import FusionService, LLMPort


def _make_scene(**kwargs) -> SceneAnalysis:
    defaults = {
        "scene_type": "commercial_street",
        "description": "A busy commercial street at night",
        "location_guess": LocationGuess(
            location="Tokyo Shibuya", confidence=0.7, evidence=["Japanese signs"]
        ),
        "time_guess": TimeGuess(time_of_day="night", season="winter"),
        "people": [],
        "key_evidence": ["Japanese text"],
        "uncertainties": [],
    }
    defaults.update(kwargs)
    return SceneAnalysis(**defaults)


def _make_ocr(text: str = "Shibuya 109", confidence: float = 0.95) -> OCRResult:
    return OCRResult(text=text, bbox=[[0, 0], [100, 0], [100, 30], [0, 30]], confidence=confidence)


def _make_entities(**kwargs) -> EntityExtraction:
    defaults = {
        "location_keywords": ["Shibuya"],
        "brands": ["109"],
        "landmarks": ["Shibuya 109"],
        "text_entities": [],
    }
    defaults.update(kwargs)
    return EntityExtraction(**defaults)


def _make_search(title: str = "涩谷109", relevance: float = 0.8) -> SearchResult:
    return SearchResult(
        query="Shibuya 109",
        source="wikipedia",
        title=title,
        snippet="Shopping mall in Shibuya, Tokyo",
        url="https://zh.wikipedia.org/wiki/109",
        relevance=relevance,
    )


# --- High Confidence Rule-Based Tests ---


@pytest.mark.asyncio
async def test_high_confidence_ocr_match():
    """High-confidence OCR should use rule-based verdict."""
    service = FusionService()
    scene = _make_scene()
    ocr = [_make_ocr(confidence=0.95)]
    entities = _make_entities()
    search = [_make_search()]

    results = await service.fuse(scene, ocr, entities, search, None)
    assert len(results) >= 1
    location = [c for c in results if c.category == "location"][0]
    assert location.probability >= 0.8


@pytest.mark.asyncio
async def test_low_confidence_mark_uncertain():
    """Low confidence without LLM should mark uncertain."""
    service = FusionService(llm=None)
    scene = _make_scene(
        location_guess=LocationGuess(location="Unknown", confidence=0.3, evidence=[])
    )
    ocr = [_make_ocr(confidence=0.2)]
    entities = _make_entities(location_keywords=[], landmarks=[])

    results = await service.fuse(scene, ocr, entities, [], None)
    location = [c for c in results if c.category == "location"][0]
    assert "不确定" in location.statement or "证据不足" in location.statement


# --- LLM-Assisted Tests ---


@pytest.mark.asyncio
async def test_medium_confidence_llm_assist():
    """Medium confidence with LLM should use LLM reasoning."""
    mock_llm = AsyncMock(spec=LLMPort)
    mock_llm.infer.return_value = "东京涩谷"
    mock_llm.infer_with_reasoning.return_value = ("东京涩谷", "Based on signs and landmarks")

    service = FusionService(llm=mock_llm)
    scene = _make_scene(
        location_guess=LocationGuess(location="Tokyo", confidence=0.6, evidence=["signs"])
    )
    ocr = [_make_ocr(confidence=0.5)]
    entities = _make_entities(location_keywords=["Tokyo"], landmarks=[])

    results = await service.fuse(scene, ocr, entities, [], None)
    location = [c for c in results if c.category == "location"][0]
    assert "LLM辅助" in location.statement
    assert location.probability <= 0.75  # Capped


@pytest.mark.asyncio
async def test_llm_failure_falls_back():
    """LLM failure should fall back to uncertain."""
    mock_llm = AsyncMock(spec=LLMPort)
    mock_llm.infer.side_effect = Exception("API error")
    mock_llm.infer_with_reasoning.side_effect = Exception("API error")

    service = FusionService(llm=mock_llm)
    scene = _make_scene(location_guess=LocationGuess(location="Tokyo", confidence=0.6, evidence=[]))

    results = await service.fuse(scene, [], _make_entities(), [], None)
    location = [c for c in results if c.category == "location"][0]
    assert "不确定" in location.statement or "证据不足" in location.statement


# --- Time Fusion Tests ---


@pytest.mark.asyncio
async def test_exif_time_high_confidence():
    """EXIF time should have high confidence."""
    service = FusionService()
    service.set_verbose(True)
    from datetime import datetime

    metadata = ImageMetadata(
        width=1920,
        height=1080,
        format="JPEG",
        file_size=100000,
        capture_time=datetime(2024, 1, 15, 20, 30),
    )
    scene = _make_scene()

    results = await service.fuse(scene, [], _make_entities(), [], metadata)
    time_conclusions = [c for c in results if c.category == "time"]
    assert len(time_conclusions) == 1
    assert time_conclusions[0].probability >= 0.9

    # Verify reasoning trace was recorded
    traces = service.get_reasoning_traces()
    time_traces = [t for t in traces if t["conclusion_category"] == "time"]
    assert len(time_traces) == 1
    assert time_traces[0]["strategy_used"] == "rule"  # High confidence


@pytest.mark.asyncio
async def test_vlm_time_medium_confidence():
    """VLM time guess should have medium confidence."""
    service = FusionService()
    service.set_verbose(True)
    scene = _make_scene()

    results = await service.fuse(scene, [], _make_entities(), [], None)
    time_conclusions = [c for c in results if c.category == "time"]
    assert len(time_conclusions) == 1
    assert time_conclusions[0].probability == 0.5

    # Verify reasoning trace was recorded
    traces = service.get_reasoning_traces()
    time_traces = [t for t in traces if t["conclusion_category"] == "time"]
    assert len(time_traces) == 1
    assert time_traces[0]["strategy_used"] == "uncertain"  # Low confidence


# --- Weighted Probability Tests ---


def test_weighted_probability_empty():
    assert FusionService._weighted_probability([]) == 0.0


def test_weighted_probability_single():
    evidence = [EvidenceItem(source="test", content="test", confidence=0.8)]
    prob = FusionService._weighted_probability(evidence)
    assert abs(prob - 0.8) < 0.01


def test_weighted_probability_multiple():
    evidence = [
        EvidenceItem(source="test", content="test", confidence=0.7),
        EvidenceItem(source="test", content="test", confidence=0.6),
    ]
    prob = FusionService._weighted_probability(evidence)
    # 1 - (1-0.7)*(1-0.6) = 1 - 0.12 = 0.88
    assert abs(prob - 0.88) < 0.01


# --- No Evidence Tests ---


@pytest.mark.asyncio
async def test_no_evidence_returns_uncertain():
    service = FusionService()
    scene = _make_scene(location_guess=None)
    results = await service.fuse(scene, [], EntityExtraction(), [], None)
    location = [c for c in results if c.category == "location"][0]
    assert "无法确定" in location.statement
