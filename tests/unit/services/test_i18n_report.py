"""Tests for bilingual (zh/en) report generation.

验证 MarkdownReportService 的中英文双语支持。
"""

from __future__ import annotations

import pytest

from vision_insight.models.schemas import (
    AnalysisReport,
    AnalysisStatus,
    EvidenceItem,
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


def _make_full_report() -> AnalysisReport:
    """Create a report with all fields populated."""
    return AnalysisReport(
        id="i18n-001",
        status=AnalysisStatus.COMPLETED,
        processing_time_ms=3500,
        image_metadata=ImageMetadata(width=1920, height=1080, format="JPEG", file_size=204800),
        scene_analysis=SceneAnalysis(
            scene_type="street",
            description="A busy commercial street at night with neon signs.",
            location_guess=LocationGuess(
                location="Shibuya, Tokyo",
                confidence=0.85,
                evidence=["Japanese signage", "Shibuya 109 building"],
            ),
            time_guess=TimeGuess(time_of_day="night", season="winter", year_estimate="2024"),
            people=[PeopleInfo(count=5, age_group="young", activity="walking")],
            key_evidence=["Neon signs", "Shibuya 109"],
            uncertainties=["Exact street unclear"],
        ),
        ocr_results=[
            OCRResult(
                text="Shibuya 109",
                bbox=[[0, 0], [200, 0], [200, 30], [0, 30]],
                confidence=0.97,
            ),
        ],
        conclusions=[
            FusedConclusion(
                statement="Location: Shibuya, Tokyo",
                probability=0.85,
                category="location",
                evidence=[
                    EvidenceItem(
                        source="vlm",
                        content="Japanese signage and Shibuya 109 building",
                        confidence=0.85,
                    )
                ],
            ),
        ],
    )


# ─── Chinese Report Tests ────────────────────────────────────────


class TestChineseReport:
    """Test Chinese (zh) report generation."""

    @pytest.mark.asyncio
    async def test_title_in_chinese(self, service: MarkdownReportService):
        report = _make_full_report()
        md = await service.generate_user_report(report, lang="zh")
        assert "# 图片分析报告" in md

    @pytest.mark.asyncio
    async def test_scene_section_in_chinese(self, service: MarkdownReportService):
        report = _make_full_report()
        md = await service.generate_user_report(report, lang="zh")
        assert "## 场景" in md
        assert "A busy commercial street" in md  # Content stays as-is from VLM

    @pytest.mark.asyncio
    async def test_location_section_in_chinese(self, service: MarkdownReportService):
        report = _make_full_report()
        md = await service.generate_user_report(report, lang="zh")
        assert "## 地点推测" in md
        assert "Shibuya, Tokyo" in md

    @pytest.mark.asyncio
    async def test_time_section_in_chinese(self, service: MarkdownReportService):
        report = _make_full_report()
        md = await service.generate_user_report(report, lang="zh")
        assert "## 时间推测" in md

    @pytest.mark.asyncio
    async def test_people_section_in_chinese(self, service: MarkdownReportService):
        report = _make_full_report()
        md = await service.generate_user_report(report, lang="zh")
        assert "## 人物" in md
        assert "5人" in md

    @pytest.mark.asyncio
    async def test_key_evidence_in_chinese(self, service: MarkdownReportService):
        report = _make_full_report()
        md = await service.generate_user_report(report, lang="zh")
        assert "## 关键证据" in md

    @pytest.mark.asyncio
    async def test_uncertainties_in_chinese(self, service: MarkdownReportService):
        report = _make_full_report()
        md = await service.generate_user_report(report, lang="zh")
        assert "## ⚠️ 不确定因素" in md

    @pytest.mark.asyncio
    async def test_ocr_section_in_chinese(self, service: MarkdownReportService):
        report = _make_full_report()
        md = await service.generate_user_report(report, lang="zh")
        assert "## OCR 文字" in md

    @pytest.mark.asyncio
    async def test_conclusions_in_chinese(self, service: MarkdownReportService):
        report = _make_full_report()
        md = await service.generate_user_report(report, lang="zh")
        assert "## 结论与证据链" in md
        assert "证据来源:" in md

    @pytest.mark.asyncio
    async def test_metadata_in_chinese(self, service: MarkdownReportService):
        report = _make_full_report()
        md = await service.generate_user_report(report, lang="zh")
        assert "## 图片信息" in md
        assert "尺寸:" in md
        assert "格式:" in md
        assert "大小:" in md

    @pytest.mark.asyncio
    async def test_footer_in_chinese(self, service: MarkdownReportService):
        report = _make_full_report()
        md = await service.generate_user_report(report, lang="zh")
        assert "由 Visual Insight Agent 生成" in md
        assert "耗时:" in md


# ─── English Report Tests ────────────────────────────────────────


class TestEnglishReport:
    """Test English (en) report generation."""

    @pytest.mark.asyncio
    async def test_title_in_english(self, service: MarkdownReportService):
        report = _make_full_report()
        md = await service.generate_user_report(report, lang="en")
        assert "# Image Analysis Report" in md

    @pytest.mark.asyncio
    async def test_scene_section_in_english(self, service: MarkdownReportService):
        report = _make_full_report()
        md = await service.generate_user_report(report, lang="en")
        assert "## Scene" in md
        assert "A busy commercial street" in md

    @pytest.mark.asyncio
    async def test_location_section_in_english(self, service: MarkdownReportService):
        report = _make_full_report()
        md = await service.generate_user_report(report, lang="en")
        assert "## Location Guess" in md
        assert "Shibuya, Tokyo" in md

    @pytest.mark.asyncio
    async def test_time_section_in_english(self, service: MarkdownReportService):
        report = _make_full_report()
        md = await service.generate_user_report(report, lang="en")
        assert "## Time Guess" in md

    @pytest.mark.asyncio
    async def test_people_section_in_english(self, service: MarkdownReportService):
        report = _make_full_report()
        md = await service.generate_user_report(report, lang="en")
        assert "## People" in md
        assert "5" in md  # No "人" suffix in English

    @pytest.mark.asyncio
    async def test_key_evidence_in_english(self, service: MarkdownReportService):
        report = _make_full_report()
        md = await service.generate_user_report(report, lang="en")
        assert "## Key Evidence" in md

    @pytest.mark.asyncio
    async def test_uncertainties_in_english(self, service: MarkdownReportService):
        report = _make_full_report()
        md = await service.generate_user_report(report, lang="en")
        assert "## ⚠️ Uncertainties" in md

    @pytest.mark.asyncio
    async def test_ocr_section_in_english(self, service: MarkdownReportService):
        report = _make_full_report()
        md = await service.generate_user_report(report, lang="en")
        assert "## OCR Text" in md

    @pytest.mark.asyncio
    async def test_conclusions_in_english(self, service: MarkdownReportService):
        report = _make_full_report()
        md = await service.generate_user_report(report, lang="en")
        assert "## Conclusions & Evidence Chain" in md
        assert "Evidence Sources:" in md

    @pytest.mark.asyncio
    async def test_metadata_in_english(self, service: MarkdownReportService):
        report = _make_full_report()
        md = await service.generate_user_report(report, lang="en")
        assert "## Image Info" in md
        assert "Size:" in md
        assert "Format:" in md
        assert "File Size:" in md

    @pytest.mark.asyncio
    async def test_footer_in_english(self, service: MarkdownReportService):
        report = _make_full_report()
        md = await service.generate_user_report(report, lang="en")
        assert "Generated by Visual Insight Agent" in md
        assert "Time:" in md


# ─── Language Consistency Tests ──────────────────────────────────


class TestLanguageConsistency:
    """Verify zh and en produce different output for same input."""

    @pytest.mark.asyncio
    async def test_zh_and_en_differ(self, service: MarkdownReportService):
        report = _make_full_report()
        md_zh = await service.generate_user_report(report, lang="zh")
        md_en = await service.generate_user_report(report, lang="en")
        # Titles must differ
        assert md_zh != md_en
        assert "图片分析报告" in md_zh
        assert "Image Analysis Report" in md_en

    @pytest.mark.asyncio
    async def test_default_is_chinese(self, service: MarkdownReportService):
        report = _make_full_report()
        md_default = await service.generate_user_report(report)
        md_zh = await service.generate_user_report(report, lang="zh")
        assert md_default == md_zh

    @pytest.mark.asyncio
    async def test_unknown_lang_falls_back_to_zh(self, service: MarkdownReportService):
        report = _make_full_report()
        md_unknown = await service.generate_user_report(report, lang="fr")
        md_zh = await service.generate_user_report(report, lang="zh")
        assert md_unknown == md_zh

    @pytest.mark.asyncio
    async def test_content_preserved_across_languages(self, service: MarkdownReportService):
        """VLM-generated content (description, location) must be preserved."""
        report = _make_full_report()
        md_zh = await service.generate_user_report(report, lang="zh")
        md_en = await service.generate_user_report(report, lang="en")
        # Content from VLM should appear in both
        for content in ["A busy commercial street", "Shibuya, Tokyo", "Shibuya 109"]:
            assert content in md_zh
            assert content in md_en


# ─── HTML Report Tests ───────────────────────────────────────────


class TestHTMLReport:
    """Test HTML report generation with lang support."""

    @pytest.mark.asyncio
    async def test_html_zh_lang_attribute(self, service: MarkdownReportService):
        report = _make_full_report()
        html = await service.generate_html_report(report, lang="zh")
        assert '<html lang="zh">' in html

    @pytest.mark.asyncio
    async def test_html_en_lang_attribute(self, service: MarkdownReportService):
        report = _make_full_report()
        html = await service.generate_html_report(report, lang="en")
        assert '<html lang="en">' in html

    @pytest.mark.asyncio
    async def test_html_zh_title(self, service: MarkdownReportService):
        report = _make_full_report()
        html = await service.generate_html_report(report, lang="zh")
        assert "<title>图片分析报告</title>" in html

    @pytest.mark.asyncio
    async def test_html_en_title(self, service: MarkdownReportService):
        report = _make_full_report()
        html = await service.generate_html_report(report, lang="en")
        assert "<title>Image Analysis Report</title>" in html

    @pytest.mark.asyncio
    async def test_html_contains_content(self, service: MarkdownReportService):
        report = _make_full_report()
        html = await service.generate_html_report(report, lang="en")
        assert "Shibuya" in html
        assert "Image Analysis Report" in html


# ─── Minimal Report Tests ────────────────────────────────────────


class TestMinimalReport:
    """Test reports with minimal data in both languages."""

    @pytest.mark.asyncio
    async def test_minimal_zh(self, service: MarkdownReportService):
        report = AnalysisReport(id="min", status=AnalysisStatus.COMPLETED)
        md = await service.generate_user_report(report, lang="zh")
        assert "# 图片分析报告" in md
        assert "由 Visual Insight Agent 生成" in md

    @pytest.mark.asyncio
    async def test_minimal_en(self, service: MarkdownReportService):
        report = AnalysisReport(id="min", status=AnalysisStatus.COMPLETED)
        md = await service.generate_user_report(report, lang="en")
        assert "# Image Analysis Report" in md
        assert "Generated by Visual Insight Agent" in md

    @pytest.mark.asyncio
    async def test_minimal_no_crash(self, service: MarkdownReportService):
        """Empty report should not crash in any language."""
        report = AnalysisReport(id="empty", status=AnalysisStatus.PENDING)
        for lang in ["zh", "en", "unknown"]:
            md = await service.generate_user_report(report, lang=lang)
            assert len(md) > 0
