"""Tests for vision_insight.utils.scene_builders."""

from __future__ import annotations

import pytest

from vision_insight.utils.scene_builders import build_detected_object, build_scene_analysis


class TestBuildSceneAnalysis:
    """build_scene_analysis 应从 LLM JSON dict 构建有效的 SceneAnalysis。"""

    def test_minimal_data(self):
        result = build_scene_analysis({})
        assert result.scene_type == "unknown"
        assert result.description == ""
        assert result.location_guess is None
        assert result.time_guess is None
        assert result.people == []
        assert result.key_evidence == []
        assert result.uncertainties == []

    def test_full_data(self):
        data = {
            "scene_type": "urban",
            "description": "A busy street",
            "location_guess": {
                "location": "Tokyo",
                "confidence": 0.9,
                "evidence": ["signs"],
            },
            "time_guess": {
                "time_of_day": "night",
                "season": "winter",
                "year_estimate": "2024",
                "evidence": ["lights"],
            },
            "people": [
                {"count": 5, "age_group": "adult", "activity": "walking"},
            ],
            "key_evidence": ["neon sign"],
            "uncertainties": ["exact location"],
        }
        result = build_scene_analysis(data)
        assert result.scene_type == "urban"
        assert result.location_guess.location == "Tokyo"
        assert result.location_guess.confidence == 0.9
        assert result.time_guess.time_of_day == "night"
        assert len(result.people) == 1
        assert result.people[0].count == 5

    def test_location_guess_partial(self):
        data = {"location_guess": {"location": "Paris"}}
        result = build_scene_analysis(data)
        assert result.location_guess is not None
        assert result.location_guess.location == "Paris"
        assert result.location_guess.confidence == 0.0


class TestBuildDetectedObject:
    """build_detected_object 应从 dict 构建 DetectedObject。"""

    def test_minimal(self):
        result = build_detected_object({})
        assert result.label == ""
        assert result.confidence == 0.0
        assert result.bbox is None
        assert result.category == ""

    def test_full(self):
        result = build_detected_object({
            "label": "cat",
            "confidence": 0.95,
            "bbox": [10, 20, 100, 200],
            "category": "animal",
        })
        assert result.label == "cat"
        assert result.confidence == 0.95
        assert result.bbox == [10, 20, 100, 200]
        assert result.category == "animal"
