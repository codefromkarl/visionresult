"""LangGraph-based analysis pipeline.

Pipeline stages:
  Image Input → Preprocess → OCR → VLM Analysis → Entity Extraction →
  Web Search → Evidence Fusion → Report Generation
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from vision_insight.models.schemas import (
    AnalysisReport,
    AnalysisStatus,
    DetectedObject,
    EntityExtraction,
    FusedConclusion,
    ImageMetadata,
    OCRResult,
    SearchResult,
    SceneAnalysis,
)


class PipelineState(dict):
    """State passed between pipeline nodes."""

    @property
    def report(self) -> AnalysisReport:
        return self["report"]

    @property
    def image_bytes(self) -> bytes:
        return self["image_bytes"]

    @property
    def image_metadata(self) -> ImageMetadata | None:
        return self["report"].image_metadata

    @image_metadata.setter
    def image_metadata(self, value: ImageMetadata) -> None:
        self["report"].image_metadata = value

    @property
    def ocr_results(self) -> list[OCRResult]:
        return self["report"].ocr_results

    @ocr_results.setter
    def ocr_results(self, value: list[OCRResult]) -> None:
        self["report"].ocr_results = value

    @property
    def scene_analysis(self) -> SceneAnalysis | None:
        return self["report"].scene_analysis

    @scene_analysis.setter
    def scene_analysis(self, value: SceneAnalysis) -> None:
        self["report"].scene_analysis = value

    @property
    def entities(self) -> EntityExtraction | None:
        return self["report"].entities

    @entities.setter
    def entities(self, value: EntityExtraction) -> None:
        self["report"].entities = value

    @property
    def search_results(self) -> list[SearchResult]:
        return self["report"].search_results

    @search_results.setter
    def search_results(self, value: list[SearchResult]) -> None:
        self["report"].search_results = value

    @property
    def conclusions(self) -> list[FusedConclusion]:
        return self["report"].conclusions

    @conclusions.setter
    def conclusions(self, value: list[FusedConclusion]) -> None:
        self["report"].conclusions = value


def preprocess_node(state: PipelineState) -> dict[str, Any]:
    """Stage 1: Image preprocessing - metadata, EXIF, resize."""
    # TODO: Implement with OpenCV/Pillow
    # - Extract EXIF data
    # - Get dimensions, format
    # - Auto-rotate if needed
    # - Compress if too large
    return {}


def ocr_node(state: PipelineState) -> dict[str, Any]:
    """Stage 2: OCR text extraction using PaddleOCR."""
    # TODO: Implement PaddleOCR integration
    return {}


def vlm_analysis_node(state: PipelineState) -> dict[str, Any]:
    """Stage 3: VLM scene understanding using Qwen2-VL or API."""
    # TODO: Implement VLM analysis
    # - Send image to VLM with structured prompt
    # - Parse JSON response
    # - Populate SceneAnalysis
    return {}


def entity_extraction_node(state: PipelineState) -> dict[str, Any]:
    """Stage 4: Extract structured entities from VLM + OCR results."""
    # TODO: Implement with spaCy / LLM extraction
    return {}


def web_search_node(state: PipelineState) -> dict[str, Any]:
    """Stage 5: Search the web to verify/expand findings."""
    # TODO: Implement search integration
    # - Search for extracted entities (brands, landmarks, text)
    # - Verify location/time guesses
    return {}


def evidence_fusion_node(state: PipelineState) -> dict[str, Any]:
    """Stage 6: Fuse all evidence into weighted conclusions.

    This is the core differentiator - combines:
    - OCR text evidence
    - VLM scene understanding
    - Web search verification
    - EXIF metadata
    Using "rules + LLM" hybrid strategy.
    """
    # TODO: Implement evidence fusion
    # - Weight evidence by source reliability
    # - Apply rules for high-confidence signals
    # - Use LLM for ambiguous cases
    # - Generate probability estimates
    return {}


def report_generation_node(state: PipelineState) -> dict[str, Any]:
    """Stage 7: Generate final markdown report."""
    report = state.report
    sections = ["# 图片分析报告\n"]

    if report.scene_analysis:
        sa = report.scene_analysis
        sections.append(f"## 场景\n{sa.description}\n")

        if sa.location_guess:
            loc = sa.location_guess
            pct = int(loc.confidence * 100)
            sections.append(f"## 地点推测\n{loc.location}（{pct}%）\n")
            if loc.evidence:
                sections.append("### 依据")
                for e in loc.evidence:
                    sections.append(f"- {e}")
                sections.append("")

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

        if sa.people:
            for p in sa.people:
                sections.append(f"## 人物\n{p.count}人 {p.age_group} {p.activity}\n")

    if report.ocr_results:
        sections.append("## OCR 文字")
        for r in report.ocr_results:
            sections.append(f"- {r.text} (confidence: {r.confidence:.0%})")
        sections.append("")

    if report.conclusions:
        sections.append("## 结论")
        for c in report.conclusions:
            pct = int(c.probability * 100)
            sections.append(f"- {c.statement}（{pct}%）")
        sections.append("")

    report.report_markdown = "\n".join(sections)
    report.status = AnalysisStatus.COMPLETED
    return {"report": report}


def build_pipeline() -> StateGraph:
    """Build the analysis pipeline graph."""
    graph = StateGraph(PipelineState)

    graph.add_node("preprocess", preprocess_node)
    graph.add_node("ocr", ocr_node)
    graph.add_node("vlm_analysis", vlm_analysis_node)
    graph.add_node("entity_extraction", entity_extraction_node)
    graph.add_node("web_search", web_search_node)
    graph.add_node("evidence_fusion", evidence_fusion_node)
    graph.add_node("report_generation", report_generation_node)

    # Linear pipeline for MVP
    graph.set_entry_point("preprocess")
    graph.add_edge("preprocess", "ocr")
    graph.add_edge("ocr", "vlm_analysis")
    graph.add_edge("vlm_analysis", "entity_extraction")
    graph.add_edge("entity_extraction", "web_search")
    graph.add_edge("web_search", "evidence_fusion")
    graph.add_edge("evidence_fusion", "report_generation")
    graph.add_edge("report_generation", END)

    return graph.compile()
