"""Tests for MarkdownReportService."""

from __future__ import annotations

import pytest

from vision_insight.models.schemas import (
    AnalysisReport,
    AnalysisStatus,
    FusedConclusion,
    ImageMetadata,
    LocationGuess,
    OCRResult,
    PeopleInfo,
    SceneAnalysis,
    TimeGuess,
)
from vision_insight.services.report.markdown_report_service import MarkdownReportService


@pytest.fixture
def service() -> MarkdownReportService:
    return MarkdownReportService()


def _make_report(**kwargs) -> AnalysisReport:
    defaults = {
        "id": "test-001",
        "status": AnalysisStatus.COMPLETED,
        "image_metadata": ImageMetadata(
            width=1920, height=1080, format="JPEG", file_size=204800
        ),
        "scene_analysis": SceneAnalysis(
            scene_type="commercial_street",
            description="日本商业街夜景",
            location_guess=LocationGuess(
                location="东京涩谷", confidence=0.82,
                evidence=["日文招牌", "涩谷109", "JR标识"]
            ),
            time_guess=TimeGuess(time_of_day="夜晚", season="冬季"),
            people=[PeopleInfo(count=3, age_group="年轻成年人", activity="聚餐")],
            key_evidence=["日文招牌", "涩谷109建筑"],
            uncertainties=["具体街道不确定"],
        ),
        "ocr_results": [
            OCRResult(text="Shibuya", bbox=[[0,0],[100,0],[100,30],[0,30]], confidence=0.98),
            OCRResult(text="109", bbox=[[0,40],[50,40],[50,70],[0,70]], confidence=0.95),
        ],
        "conclusions": [
            FusedConclusion(
                statement="拍摄地点: 东京涩谷",
                probability=0.82,
                category="location",
            ),
        ],
    }
    defaults.update(kwargs)
    return AnalysisReport(**defaults)


# --- User Report Tests ---


@pytest.mark.asyncio
async def test_user_report_contains_all_sections(service: MarkdownReportService):
    report = _make_report()
    md = await service.generate_user_report(report)

    assert "# 图片分析报告" in md
    assert "## 场景" in md
    assert "日本商业街夜景" in md
    assert "## 地点推测" in md
    assert "东京涩谷" in md
    assert "82%" in md
    assert "## 时间推测" in md
    assert "夜晚" in md
    assert "## 人物" in md
    assert "3人" in md
    assert "## OCR 文字" in md
    assert "Shibuya" in md
    assert "## 结论" in md
    assert "## ⚠️ 不确定因素" in md
    assert "## 图片信息" in md
    assert "1920×1080" in md


@pytest.mark.asyncio
async def test_user_report_minimal(service: MarkdownReportService):
    report = AnalysisReport(id="min", status=AnalysisStatus.COMPLETED)
    md = await service.generate_user_report(report)
    assert "# 图片分析报告" in md
    assert "由 Visual Insight Agent 生成" in md


@pytest.mark.asyncio
async def test_user_report_evidence_detail(service: MarkdownReportService):
    report = _make_report()
    md = await service.generate_user_report(report)
    # Should include evidence for conclusions
    assert "日文招牌" in md or "涩谷109" in md


# --- Structured Report Tests ---


@pytest.mark.asyncio
async def test_structured_report_full(service: MarkdownReportService):
    report = _make_report()
    data = await service.generate_structured_report(report)

    assert data["id"] == "test-001"
    assert data["status"] == "completed"
    assert data["image"]["width"] == 1920
    assert data["scene"]["type"] == "commercial_street"
    assert data["location"]["confidence"] == 0.82
    assert data["time"]["time_of_day"] == "夜晚"
    assert len(data["people"]) == 1
    assert data["people"][0]["count"] == 3
    assert len(data["ocr"]) == 2
    assert len(data["conclusions"]) == 1


@pytest.mark.asyncio
async def test_structured_report_minimal(service: MarkdownReportService):
    report = AnalysisReport(id="min", status=AnalysisStatus.COMPLETED)
    data = await service.generate_structured_report(report)
    assert data["id"] == "min"
    assert "image" not in data
    assert "scene" not in data
