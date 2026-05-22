"""LangGraph-based analysis pipeline.

Pipeline stages:
  Image Input → Preprocess → OCR → VLM Analysis → Entity Extraction →
  Web Search → Evidence Fusion → Report Generation
"""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from vision_insight.models.schemas import (
    AnalysisReport,
    AnalysisStatus,
    EntityExtraction,
    ImageMetadata,
    SceneAnalysis,
    SearchResult,
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

# Progress callback type: (stage_name, progress_percent)
ProgressCallback = Any  # Callable[[str, int], None] | None

# Stage progress mapping
STAGE_PROGRESS = {
    "preprocess": 10,
    "ocr": 25,
    "vlm_analysis": 45,
    "entity_extraction": 60,
    "web_search": 75,
    "evidence_fusion": 85,
    "report_generation": 95,
}


class PipelineState(TypedDict):
    """State passed between pipeline nodes."""

    report: AnalysisReport
    image_bytes: bytes
    progress_callback: ProgressCallback
    verbose: bool  # Whether to record detailed trace information
    pipeline_trace: dict  # PipelineTrace data (built incrementally)


# ---------------------------------------------------------------------------
# Node factories — each returns a closure that captures the injected service
# ---------------------------------------------------------------------------


def _notify_progress(state: PipelineState, stage: str) -> None:
    """Send progress notification if callback is provided."""
    callback = state.get("progress_callback")
    if callback:
        progress = STAGE_PROGRESS.get(stage, 0)
        try:
            callback(stage, progress)
        except Exception:
            pass  # Don't let callback errors break the pipeline


def _start_pipeline_step(state: PipelineState, stage_name: str) -> dict:
    """Record the start of a pipeline step if verbose mode is enabled."""
    if not state.get("verbose"):
        return {}
    from datetime import datetime as dt
    return {
        "stage_name": stage_name,
        "status": "running",
        "start_time": dt.now().isoformat(),
        "input_summary": "",
        "output_summary": "",
        "key_findings": [],
        "error_message": None,
        "input_data": {},
        "output_data": {},
    }


def _end_pipeline_step(state: PipelineState, step_info: dict, status: str = "success",
                       output_summary: str = "", key_findings: list[str] = None,
                       error_message: str = None, output_data: dict = None) -> None:
    """Complete a pipeline step recording."""
    if not step_info or not state.get("verbose"):
        return
    from datetime import datetime as dt
    step_info["end_time"] = dt.now().isoformat()
    step_info["status"] = status
    if output_summary:
        step_info["output_summary"] = output_summary
    if key_findings:
        step_info["key_findings"] = key_findings
    if error_message:
        step_info["error_message"] = error_message
    if output_data:
        step_info["output_data"] = output_data
    # Calculate duration
    start = dt.fromisoformat(step_info["start_time"])
    end = dt.fromisoformat(step_info["end_time"])
    step_info["duration_ms"] = int((end - start).total_seconds() * 1000)
    # Append to trace
    if "pipeline_trace" in state:
        state["pipeline_trace"].setdefault("steps", []).append(step_info)


def make_preprocess_node():
    """Stage 1: Image preprocessing - metadata, EXIF, resize."""

    def preprocess_node(state: PipelineState) -> dict[str, Any]:
        report: AnalysisReport = state["report"]
        _notify_progress(state, "preprocess")
        step_info = _start_pipeline_step(state, "preprocess")
        step_info["input_summary"] = f"Image size: {len(state['image_bytes'])} bytes"
        step_info["input_data"] = {"image_size_bytes": len(state["image_bytes"])}
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
            _end_pipeline_step(
                state, step_info,
                output_summary=f"{meta_dict['width']}x{meta_dict['height']}, {meta_dict['file_size']/1024:.1f}KB",
                key_findings=[
                    f"Format: {meta_dict.get('format', 'JPEG')}",
                    f"GPS: {'Yes' if meta_dict.get('gps') else 'No'}",
                    f"Capture time: {capture_time or 'Not available'}",
                ],
                output_data={
                    "width": meta_dict["width"],
                    "height": meta_dict["height"],
                    "format": meta_dict.get("format", "JPEG"),
                    "has_gps": bool(meta_dict.get("gps")),
                    "has_capture_time": bool(capture_time),
                },
            )
        except Exception as exc:
            logger.warning("Preprocess failed: %s", exc)
            _end_pipeline_step(state, step_info, status="failed", error_message=str(exc))
        return {"report": report}

    return preprocess_node


def make_ocr_node(ocr_service: OCRService):
    """Stage 2: OCR text extraction using PaddleOCR."""

    async def ocr_node(state: PipelineState) -> dict[str, Any]:
        report: AnalysisReport = state["report"]
        _notify_progress(state, "ocr")
        step_info = _start_pipeline_step(state, "ocr")
        step_info["input_summary"] = f"Image: {report.image_metadata.width}x{report.image_metadata.height}" if report.image_metadata else "Image"
        try:
            results = await ocr_service.extract(state["image_bytes"])
            report.ocr_results = results
            logger.info("OCR done: %d text regions found", len(results))
            texts = [r.text for r in results]
            _end_pipeline_step(
                state, step_info,
                output_summary=f"{len(results)} text regions detected",
                key_findings=[f"Text: '{t}'" for t in texts[:5]],
                output_data={
                    "num_regions": len(results),
                    "texts": texts,
                    "avg_confidence": sum(r.confidence for r in results) / len(results) if results else 0,
                },
            )
        except Exception as exc:
            logger.warning("OCR failed: %s", exc)
            report.ocr_results = []
            _end_pipeline_step(state, step_info, status="failed", error_message=str(exc))
        return {"report": report}

    return ocr_node


def make_vlm_node(vlm_service: VLMService):
    """Stage 3: VLM scene understanding using Qwen2-VL or API."""

    async def vlm_analysis_node(state: PipelineState) -> dict[str, Any]:
        report: AnalysisReport = state["report"]
        _notify_progress(state, "vlm_analysis")
        step_info = _start_pipeline_step(state, "vlm_analysis")
        ocr_texts = [r.text for r in report.ocr_results]
        step_info["input_summary"] = f"Image + {len(ocr_texts)} OCR texts"
        step_info["input_data"] = {"ocr_texts": ocr_texts}
        try:
            scene = await vlm_service.analyze(state["image_bytes"], report.ocr_results)
            report.scene_analysis = scene
            logger.info("VLM done: scene_type=%s", scene.scene_type)
            findings = [f"Scene: {scene.scene_type}", f"Description: {scene.description[:100]}..."]
            if scene.location_guess:
                findings.append(f"Location guess: {scene.location_guess.location}")
            if scene.time_guess:
                findings.append(f"Time guess: {scene.time_guess.time_of_day}")
            _end_pipeline_step(
                state, step_info,
                output_summary=f"Scene: {scene.scene_type}",
                key_findings=findings,
                output_data={
                    "scene_type": scene.scene_type,
                    "description": scene.description,
                    "location_guess": scene.location_guess.location if scene.location_guess else None,
                    "time_guess": scene.time_guess.time_of_day if scene.time_guess else None,
                    "num_people": len(scene.people),
                },
            )
        except Exception as exc:
            logger.warning("VLM analysis failed: %s", exc)
            report.scene_analysis = SceneAnalysis(
                scene_type="unknown",
                description=f"VLM 分析失败: {exc}",
            )
            _end_pipeline_step(state, step_info, status="failed", error_message=str(exc))
        return {"report": report}

    return vlm_analysis_node


def make_entity_node(entity_service: EntityService):
    """Stage 4: Extract structured entities from VLM + OCR results."""

    async def entity_extraction_node(state: PipelineState) -> dict[str, Any]:
        report: AnalysisReport = state["report"]
        _notify_progress(state, "entity_extraction")
        step_info = _start_pipeline_step(state, "entity_extraction")
        step_info["input_summary"] = f"Scene analysis + {len(report.ocr_results)} OCR results"
        if not report.scene_analysis:
            _end_pipeline_step(state, step_info, status="skipped", output_summary="No scene analysis available")
            return {"report": report}
        try:
            entities = await entity_service.extract(report.scene_analysis, report.ocr_results)
            report.entities = entities
            logger.info(
                "Entity extraction done: %d brands, %d landmarks",
                len(entities.brands),
                len(entities.landmarks),
            )
            findings = []
            if entities.brands:
                findings.append(f"Brands: {', '.join(entities.brands[:3])}")
            if entities.landmarks:
                findings.append(f"Landmarks: {', '.join(entities.landmarks[:3])}")
            if entities.location_keywords:
                findings.append(f"Location keywords: {', '.join(entities.location_keywords[:3])}")
            _end_pipeline_step(
                state, step_info,
                output_summary=f"{len(entities.brands)} brands, {len(entities.landmarks)} landmarks",
                key_findings=findings,
                output_data={
                    "brands": entities.brands,
                    "landmarks": entities.landmarks,
                    "location_keywords": entities.location_keywords,
                    "text_entities": entities.text_entities,
                },
            )
        except Exception as exc:
            logger.warning("Entity extraction failed: %s", exc)
            report.entities = EntityExtraction()
            _end_pipeline_step(state, step_info, status="failed", error_message=str(exc))
        return {"report": report}

    return entity_extraction_node


def make_search_node(search_service: SearchService):
    """Stage 5: Search the web to verify/expand findings."""

    async def web_search_node(state: PipelineState) -> dict[str, Any]:
        report: AnalysisReport = state["report"]
        _notify_progress(state, "web_search")
        step_info = _start_pipeline_step(state, "web_search")
        if not report.entities:
            _end_pipeline_step(state, step_info, status="skipped", output_summary="No entities to search")
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

        step_info["input_summary"] = f"{len(queries)} search queries from entities"
        step_info["input_data"] = {"queries": queries}

        for query in queries[:3]:  # Limit to 3 queries
            try:
                results = await search_service.search(query, source="wikipedia")
                all_results.extend(results[:3])
            except Exception as exc:
                logger.warning("Search failed for '%s': %s", query, exc)

        report.search_results = all_results
        logger.info("Web search done: %d results from %d queries", len(all_results), len(queries))
        _end_pipeline_step(
            state, step_info,
            output_summary=f"{len(all_results)} results from {len(queries)} queries",
            key_findings=[f"Query: '{q}'" for q in queries[:3]],
            output_data={
                "num_queries": len(queries),
                "num_results": len(all_results),
                "sources": list(set(r.source for r in all_results)),
            },
        )
        return {"report": report}

    return web_search_node


def make_fusion_node(evidence_service: EvidenceService):
    """Stage 6: Fuse all evidence into weighted conclusions."""

    async def evidence_fusion_node(state: PipelineState) -> dict[str, Any]:
        report: AnalysisReport = state["report"]
        _notify_progress(state, "evidence_fusion")
        step_info = _start_pipeline_step(state, "evidence_fusion")
        step_info["input_summary"] = f"{len(report.ocr_results)} OCR, {len(report.search_results)} search results"
        if not report.scene_analysis:
            _end_pipeline_step(state, step_info, status="skipped", output_summary="No scene analysis available")
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
            findings = []
            for c in conclusions[:3]:
                findings.append(f"{c.category}: {c.statement[:50]}... (prob={c.probability:.2f})")
            _end_pipeline_step(
                state, step_info,
                output_summary=f"{len(conclusions)} conclusions generated",
                key_findings=findings,
                output_data={
                    "num_conclusions": len(conclusions),
                    "categories": list(set(c.category for c in conclusions)),
                    "conclusions_summary": [
                        {"category": c.category, "statement": c.statement[:100], "probability": c.probability}
                        for c in conclusions
                    ],
                },
            )
        except Exception as exc:
            logger.warning("Evidence fusion failed: %s", exc)
            report.conclusions = []
            _end_pipeline_step(state, step_info, status="failed", error_message=str(exc))
        return {"report": report}

    return evidence_fusion_node


def make_report_node():
    """Stage 7: Generate final markdown report."""
    report_service = MarkdownReportService()

    async def report_generation_node(state: PipelineState) -> dict[str, Any]:
        report: AnalysisReport = state["report"]
        _notify_progress(state, "report_generation")
        step_info = _start_pipeline_step(state, "report_generation")
        step_info["input_summary"] = f"{len(report.conclusions)} conclusions, {len(report.ocr_results)} OCR results"
        try:
            report.report_markdown = await report_service.generate_user_report(report)
            report.status = AnalysisStatus.COMPLETED
            logger.info("Report generation done")
            _end_pipeline_step(
                state, step_info,
                output_summary=f"Report generated: {len(report.report_markdown)} chars",
                key_findings=[f"Report length: {len(report.report_markdown)} characters"],
                output_data={"report_length": len(report.report_markdown)},
            )
            # Build PipelineTrace from state if verbose
            if state.get("verbose") and "pipeline_trace" in state:
                from vision_insight.models.schemas import PipelineTrace, PipelineStep as PStep, ReasoningTrace
                trace_data = state["pipeline_trace"]
                steps = [PStep(**s) for s in trace_data.get("steps", [])]
                total_ms = sum(s.duration_ms for s in steps)
                report.pipeline_trace = PipelineTrace(
                    steps=steps,
                    reasoning_traces=[],  # Will be populated by fusion service
                    total_duration_ms=total_ms,
                    verbose_mode=True,
                )
        except Exception as exc:
            logger.warning("Report generation failed: %s", exc)
            report.report_markdown = f"# 报告生成失败\n\n错误: {exc}"
            report.status = AnalysisStatus.COMPLETED
            _end_pipeline_step(state, step_info, status="failed", error_message=str(exc))
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
