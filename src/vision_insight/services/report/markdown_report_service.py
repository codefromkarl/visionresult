"""Markdown report generation service."""

from __future__ import annotations

import logging

from vision_insight.models.schemas import AnalysisReport, AnalysisStatus
from vision_insight.services import ReportService

logger = logging.getLogger(__name__)


class MarkdownReportService(ReportService):
    """Generate structured Markdown reports from analysis results."""

    async def generate_user_report(self, report: AnalysisReport) -> str:
        """Generate a user-friendly Markdown report."""
        sections = ["# 图片分析报告\n"]

        # Scene
        if report.scene_analysis:
            sa = report.scene_analysis
            sections.append(f"## 场景\n{sa.description}\n")

            # Location
            if sa.location_guess:
                loc = sa.location_guess
                pct = int(loc.confidence * 100)
                sections.append(f"## 地点推测\n{loc.location}（{pct}%）\n")
                if loc.evidence:
                    sections.append("### 依据")
                    for e in loc.evidence:
                        sections.append(f"- {e}")
                    sections.append("")

            # Time
            if sa.time_guess:
                tg = sa.time_guess
                sections.append("## 时间推测")
                if tg.time_of_day:
                    sections.append(f"- {tg.time_of_day}")
                if tg.season:
                    sections.append(f"- {tg.season}")
                if tg.year_estimate:
                    sections.append(f"- {tg.year_estimate}")
                sections.append("")

            # People
            if sa.people:
                for p in sa.people:
                    parts = [f"{p.count}人"]
                    if p.age_group:
                        parts.append(p.age_group)
                    if p.activity:
                        parts.append(p.activity)
                    sections.append(f"## 人物\n{' '.join(parts)}\n")

            # Key evidence from VLM
            if sa.key_evidence:
                sections.append("## 关键证据")
                for e in sa.key_evidence:
                    sections.append(f"- {e}")
                sections.append("")

            # Uncertainties
            if sa.uncertainties:
                sections.append("## ⚠️ 不确定因素")
                for u in sa.uncertainties:
                    sections.append(f"- {u}")
                sections.append("")

        # OCR
        if report.ocr_results:
            sections.append("## OCR 文字")
            for r in report.ocr_results:
                pct = int(r.confidence * 100)
                sections.append(f"- {r.text} ({pct}%)")
            sections.append("")

        # Conclusions
        if report.conclusions:
            sections.append("## 结论")
            for c in report.conclusions:
                pct = int(c.probability * 100)
                sections.append(f"- {c.statement}（{pct}%）")
                if c.evidence:
                    for e in c.evidence[:3]:  # Top 3 evidence per conclusion
                        sections.append(f"  - [{e.source}] {e.content}")
            sections.append("")

        # Metadata
        if report.image_metadata:
            meta = report.image_metadata
            sections.append("## 图片信息")
            sections.append(f"- 尺寸: {meta.width}×{meta.height}")
            sections.append(f"- 格式: {meta.format}")
            sections.append(f"- 大小: {meta.file_size / 1024:.1f} KB")
            if meta.gps:
                sections.append(f"- GPS: {meta.gps}")
            sections.append("")

        # Footer
        sections.append("---")
        sections.append("*由 Visual Insight Agent 生成*")

        return "\n".join(sections)

    async def generate_structured_report(self, report: AnalysisReport) -> dict:
        """Generate a structured JSON report."""
        result: dict = {
            "id": report.id,
            "status": report.status.value,
            "processing_time_ms": report.processing_time_ms,
        }

        if report.image_metadata:
            result["image"] = {
                "width": report.image_metadata.width,
                "height": report.image_metadata.height,
                "format": report.image_metadata.format,
                "file_size": report.image_metadata.file_size,
            }

        if report.scene_analysis:
            sa = report.scene_analysis
            result["scene"] = {
                "type": sa.scene_type,
                "description": sa.description,
            }
            if sa.location_guess:
                result["location"] = {
                    "guess": sa.location_guess.location,
                    "confidence": sa.location_guess.confidence,
                    "evidence": sa.location_guess.evidence,
                }
            if sa.time_guess:
                result["time"] = {
                    "time_of_day": sa.time_guess.time_of_day,
                    "season": sa.time_guess.season,
                    "year_estimate": sa.time_guess.year_estimate,
                }
            if sa.people:
                result["people"] = [
                    {
                        "count": p.count,
                        "age_group": p.age_group,
                        "activity": p.activity,
                    }
                    for p in sa.people
                ]

        if report.ocr_results:
            result["ocr"] = [
                {
                    "text": r.text,
                    "confidence": r.confidence,
                    "bbox": r.bbox,
                }
                for r in report.ocr_results
            ]

        if report.conclusions:
            result["conclusions"] = [
                {
                    "statement": c.statement,
                    "probability": c.probability,
                    "category": c.category,
                    "evidence_count": len(c.evidence),
                }
                for c in report.conclusions
            ]

        if report.entities:
            result["entities"] = {
                "location_keywords": report.entities.location_keywords,
                "brands": report.entities.brands,
                "landmarks": report.entities.landmarks,
            }

        return result
