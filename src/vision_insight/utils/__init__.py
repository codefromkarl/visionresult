"""Utility modules."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vision_insight.models.schemas import EntityExtraction, OCRResult, SceneAnalysis


def generate_task_id() -> str:
    """Generate a short unique task ID (8 chars from UUID4)."""
    return str(uuid.uuid4())[:8]


def generate_request_id() -> str:
    """Generate a short unique request ID (16 chars from UUID4)."""
    return str(uuid.uuid4())[:16]


def dedupe_strings(values: list[str]) -> list[str]:
    """Deduplicate strings while preserving order and ignoring case."""
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        normalized = value.strip()
        key = normalized.lower()
        if normalized and key not in seen:
            seen.add(key)
            deduped.append(normalized)
    return deduped


def extract_entities_rule_based(
    scene: SceneAnalysis, ocr_results: list[OCRResult], min_confidence: float = 0.8
) -> EntityExtraction:
    """Extract entities using simple rules (no LLM).

    Used as fallback when LLM-based entity extraction is unavailable or fails.

    Args:
        scene: Scene analysis result.
        ocr_results: OCR results from the image.
        min_confidence: Minimum OCR confidence threshold for text entities.

    Returns:
        EntityExtraction with location keywords and high-confidence OCR texts.
    """
    from vision_insight.models.schemas import EntityExtraction

    location_keywords: list[str] = []
    if scene.location_guess and scene.location_guess.location:
        location_keywords.append(scene.location_guess.location)

    text_entities = [r.text for r in ocr_results if r.confidence >= min_confidence]

    return EntityExtraction(
        location_keywords=dedupe_strings(location_keywords),
        brands=[],
        landmarks=[],
        text_entities=dedupe_strings(text_entities),
    )
