"""Markdown report generation service."""

from __future__ import annotations

import logging

from vision_insight.models.schemas import AnalysisReport
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
                int(loc.confidence * 100)
                bar = self._confidence_bar(loc.confidence)
                sections.append(f"## 地点推测\n{loc.location} {bar}\n")
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
                int(r.confidence * 100)
                bar = self._confidence_bar(r.confidence)
                sections.append(f"- {r.text} {bar}")
            sections.append("")

        # Entities
        if report.entities:
            ent = report.entities
            if any([ent.location_keywords, ent.brands, ent.landmarks, ent.text_entities]):
                sections.append("## 识别实体")
                if ent.location_keywords:
                    sections.append(f"- **地点关键词**: {', '.join(ent.location_keywords)}")
                if ent.brands:
                    sections.append(f"- **品牌**: {', '.join(ent.brands)}")
                if ent.landmarks:
                    sections.append(f"- **地标**: {', '.join(ent.landmarks)}")
                if ent.text_entities:
                    sections.append(f"- **文本实体**: {', '.join(ent.text_entities)}")
                sections.append("")

        # Conclusions with evidence chain
        if report.conclusions:
            sections.append("## 结论与证据链")
            for i, c in enumerate(report.conclusions, 1):
                int(c.probability * 100)
                bar = self._confidence_bar(c.probability)
                sections.append(f"### {i}. {c.statement} {bar}")
                if c.evidence:
                    sections.append("")
                    sections.append("**证据来源:**")
                    for e in c.evidence:
                        icon = self._evidence_icon(e.source)
                        conf = int(e.confidence * 100)
                        supporting = "✅" if e.supporting else "❌"
                        sections.append(
                            f"- {icon} [{e.source}] {e.content} (置信度: {conf}%) {supporting}"
                        )
                sections.append("")

        # Search results
        if report.search_results:
            sections.append("## 联网验证")
            for sr in report.search_results[:5]:
                sections.append(f"- [{sr.title}]({sr.url}) ({sr.source})")
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
        sections.append(f"*由 Visual Insight Agent 生成 | 耗时: {report.processing_time_ms}ms*")

        return "\n".join(sections)

    @staticmethod
    def _confidence_bar(confidence: float) -> str:
        """Generate a visual confidence bar."""
        filled = int(confidence * 10)
        empty = 10 - filled
        if confidence >= 0.8:
            color = "🟢"
        elif confidence >= 0.5:
            color = "🟡"
        else:
            color = "🔴"
        return f"{color} {'█' * filled}{'░' * empty} {int(confidence * 100)}%"

    @staticmethod
    def _evidence_icon(source: str) -> str:
        """Get icon for evidence source."""
        icons = {
            "ocr": "📝",
            "vlm": "👁️",
            "search": "🔍",
            "exif": "📷",
            "scene": "🎬",
        }
        return icons.get(source, "📌")

    async def generate_html_report(self, report: AnalysisReport) -> str:
        """Generate a styled HTML report."""
        md = await self.generate_user_report(report)

        # CSS styles (split for line length)
        css = """
body {
    font-family: -apple-system, BlinkMacSystemFont, sans-serif;
    max-width: 800px; margin: 0 auto; padding: 20px;
    background: #f5f5f5;
}
.report {
    background: white; border-radius: 12px; padding: 32px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}
h1 { color: #1a1a1a; border-bottom: 2px solid #4f46e5; }
h2 { color: #374151; margin-top: 24px; }
.tag {
    display: inline-block; background: #e0e7ff; color: #4338ca;
    padding: 4px 12px; border-radius: 16px; font-size: 14px;
}
.confidence { color: #059669; font-weight: 600; }
.evidence { color: #6b7280; font-size: 14px; margin-left: 16px; }
.metadata {
    background: #f9fafb; padding: 16px; border-radius: 8px;
}
"""

        # Simple markdown-to-HTML conversion
        html_lines = [
            "<!DOCTYPE html>",
            '<html lang="zh">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            "<title>图片分析报告</title>",
            "<style>",
            css,
            "</style>",
            "</head>",
            "<body>",
            '<div class="report">',
        ]

        # Convert markdown to HTML
        for line in md.split("\n"):
            if line.startswith("# "):
                html_lines.append(f"<h1>{line[2:]}</h1>")
            elif line.startswith("## "):
                html_lines.append(f"<h2>{line[3:]}</h2>")
            elif line.startswith("### "):
                html_lines.append(f"<h3>{line[4:]}</h3>")
            elif line.startswith("- "):
                html_lines.append(f"<li>{line[2:]}</li>")
            elif line.startswith("  - "):
                html_lines.append(f'<li class="evidence">{line[4:]}</li>')
            elif line == "---":
                html_lines.append("<hr>")
            elif line.strip():
                html_lines.append(f"<p>{line}</p>")

        html_lines.extend(
            [
                "</div>",
                "</body>",
                "</html>",
            ]
        )

        return "\n".join(html_lines)

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
