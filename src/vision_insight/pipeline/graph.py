"""LangGraph-based analysis pipeline.

Pipeline stages:
  Image Input → Preprocess → OCR → VLM Analysis → Entity Extraction →
  Web Search → Evidence Fusion → Report Generation
"""

from __future__ import annotations

import logging
import time
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from vision_insight.models.schemas import (
    AnalysisReport,
    AnalysisStatus,
    EntityExtraction,
    ImageMetadata,
    OCRResult,
    SearchResult,
    SceneAnalysis,
)
from vision_insight.services import (
    EntityService,
    EvidenceService,
    OCRService,
    SearchService,
    VLMService,
)
from vision_insight.services.report.markdown_report_service import MarkdownReportService
from vision_insight.utils.image import compress_image, get_image_metadata

logger = logging.getLogger(__name__)


class PipelineState(TypedDict):
    """State passed between pipeline nodes."""
    report: AnalysisReport
    image_bytes: bytes


# ---------------------------------------------------------------------------
# Node factories — each returns a closure that captures the injected service
# ---------------------------------------------------------------------------


def make_preprocess_node():
    """Stage 1: Image preprocessing - metadata, EXIF, resize."""
    def preprocess_node(state: PipelineState) -> dict[str, Any]:
        report: AnalysisReport = state["report"]
        try:
            raw_bytes: bytes = state["image_bytes"]
            # Compress if too large (>4MB)
            if len(raw_bytes) > 4 * 1024 * 1024:
                raw_bytes = compress_image(raw_bytes, max_size=(2048, 2048), quality=85)

            # Extract metadata
            meta_dict = get_image_metadata(raw_bytes)
            from datetime import datetime as dt

            capture_time = None
            if meta_dict.get("capture_time"):
                try:
                    capture_time = dt.fromisoformat(meta_dict["capture_time"])
                except (ValueError, TypeError):
                    pass

            report.image_metadata = ImageMetadata(
                width=meta_dict["width"],
                height=meta_dict["height"],
                format=meta_dict.get("format", "JPEG"),
                file_size=meta_dict["file_size"],
                exif=meta_dict.get("exif", {}),
                gps=meta_dict.get("gps"),
                capture_time=capture_time,
            )
            logger.info(
                "Preprocess done: %dx%d, %.1fKB",
                meta_dict["width"],
                meta_dict["height"],
                meta_dict["file_size"] / 1024,
            )
        except Exception as exc:
            logger.warning("Preprocess failed: %s", exc)
        return {"report": report}

    return preprocess_node


def make_ocr_node(ocr_service: OCRService):
    """Stage 2: OCR text extraction using PaddleOCR."""
    async def ocr_node(state: PipelineState) -> dict[str, Any]:
        report: AnalysisReport = state["report"]
        try:
            results = await ocr_service.extract(state["image_bytes"])
            report.ocr_results = results
            logger.info("OCR done: %d text regions found", len(results))
        except Exception as exc:
            logger.warning("OCR failed: %s", exc)
            report.ocr_results = []
        return {"report": report}

    return ocr_node


def make_vlm_node(vlm_service: VLMService):
    """Stage 3: VLM scene understanding using Qwen2-VL or API."""
    async def vlm_analysis_node(state: PipelineState) -> dict[str, Any]:
        report: AnalysisReport = state["report"]
        try:
            scene = await vlm_service.analyze(state["image_bytes"], report.ocr_results)
            report.scene_analysis = scene
            logger.info("VLM done: scene_type=%s", scene.scene_type)
        except Exception as exc:
            logger.warning("VLM analysis failed: %s", exc)
            report.scene_analysis = SceneAnalysis(
                scene_type="unknown",
                description=f"VLM 分析失败: {exc}",
            )
        return {"report": report}

    return vlm_analysis_node


def make_entity_node(entity_service: EntityService):
    """Stage 4: Extract structured entities from VLM + OCR results."""
    async def entity_extraction_node(state: PipelineState) -> dict[str, Any]:
        report: AnalysisReport = state["report"]
        if not report.scene_analysis:
            return {"report": report}
        try:
            entities = await entity_service.extract(report.scene_analysis, report.ocr_results)
            report.entities = entities
            logger.info(
                "Entity extraction done: %d brands, %d landmarks",
                len(entities.brands),
                len(entities.landmarks),
            )
        except Exception as exc:
            logger.warning("Entity extraction failed: %s", exc)
            report.entities = EntityExtraction()
        return {"report": report}

    return entity_extraction_node


def make_search_node(search_service: SearchService):
    """Stage 5: Search the web to verify/expand findings."""
    async def web_search_node(state: PipelineState) -> dict[str, Any]:
        report: AnalysisReport = state["report"]
        if not report.entities:
            return {"report": report}

        entities = report.entities
        all_results: list[SearchResult] = []

        # Build search queries from entities
        queries: list[str] = []
        if entities.landmarks:
            queries.extend(entities.landmarks[:2])
        if entities.location_keywords:
            queries.extend(entities.location_keywords[:2])
        if entities.brands:
            queries.extend(entities.brands[:1])

        for query in queries[:3]:  # Limit to 3 queries
            try:
                results = await search_service.search(query, source="wikipedia")
                all_results.extend(results[:3])
            except Exception as exc:
                logger.warning("Search failed for '%s': %s", query, exc)

        report.search_results = all_results
        logger.info("Web search done: %d results from %d queries", len(all_results), len(queries))
        return {"report": report}

    return web_search_node


def make_fusion_node(evidence_service: EvidenceService):
    """Stage 6: Fuse all evidence into weighted conclusions."""
    async def evidence_fusion_node(state: PipelineState) -> dict[str, Any]:
        report: AnalysisReport = state["report"]
        if not report.scene_analysis:
            return {"report": report}
        try:
            conclusions = await evidence_service.fuse(
                scene=report.scene_analysis,
                ocr_results=report.ocr_results,
                entities=report.entities or EntityExtraction(),
                search_results=report.search_results,
                metadata=report.image_metadata,
            )
            report.conclusions = conclusions
            logger.info("Evidence fusion done: %d conclusions", len(conclusions))
        except Exception as exc:
            logger.warning("Evidence fusion failed: %s", exc)
            report.conclusions = []
        return {"report": report}

    return evidence_fusion_node


def make_report_node():
    """Stage 7: Generate final markdown report."""
    report_service = MarkdownReportService()

    async def report_generation_node(state: PipelineState) -> dict[str, Any]:
        report: AnalysisReport = state["report"]
        report.report_markdown = await report_service.generate_user_report(report)
        report.status = AnalysisStatus.COMPLETED
        logger.info("Report generation done")
        return {"report": report}

    return report_generation_node


# ---------------------------------------------------------------------------
# Pipeline builder
# ---------------------------------------------------------------------------


def build_pipeline(
    ocr_service: OCRService,
    vlm_service: VLMService,
    entity_service: EntityService,
    search_service: SearchService,
    evidence_service: EvidenceService,
) -> StateGraph:
    """Build the analysis pipeline graph with injected services."""
    graph = StateGraph(PipelineState)

    graph.add_node("preprocess", make_preprocess_node())
    graph.add_node("ocr", make_ocr_node(ocr_service))
    graph.add_node("vlm_analysis", make_vlm_node(vlm_service))
    graph.add_node("entity_extraction", make_entity_node(entity_service))
    graph.add_node("web_search", make_search_node(search_service))
    graph.add_node("evidence_fusion", make_fusion_node(evidence_service))
    graph.add_node("report_generation", make_report_node())

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
