"""LangGraph-based analysis pipeline.

Pipeline stages:
  Image Input → Preprocess → OCR → VLM Analysis → Entity Extraction →
  Web Search → Evidence Fusion → Report Generation
"""

import logging
from datetime import datetime as dt
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from vision_insight.core.config import settings
from vision_insight.core.event_logger import log_event
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
    lang: str  # Output language: 'zh' or 'en'


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


def _end_pipeline_step(
    state: PipelineState,
    step_info: dict,
    status: str = "success",
    output_summary: str = "",
    key_findings: list[str] | None = None,
    error_message: str | None = None,
    output_data: dict[Any, Any] | None = None,
) -> None:
    """Complete a pipeline step recording."""
    if not step_info or not state.get("verbose"):
        return

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
        task_id = report.id
        _notify_progress(state, "preprocess")
        step_info = _start_pipeline_step(state, "preprocess")
        step_info["input_summary"] = f"Image size: {len(state['image_bytes'])} bytes"
        step_info["input_data"] = {"image_size_bytes": len(state["image_bytes"])}
        log_event(task_id, "node_start", node="preprocess", image_bytes=len(state["image_bytes"]))
        try:
            raw_bytes: bytes = state["image_bytes"]
            original_size = len(raw_bytes)
            # Compress if too large (>4MB)
            if len(raw_bytes) > 4 * 1024 * 1024:
                raw_bytes = compress_image(raw_bytes, max_size=(2048, 2048), quality=85)
                log_event(
                    task_id,
                    "image_compressed",
                    original_bytes=original_size,
                    compressed_bytes=len(raw_bytes),
                )

            # Extract metadata
            meta_dict = get_image_metadata(raw_bytes)

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
            log_event(
                task_id,
                "node_end",
                node="preprocess",
                width=meta_dict["width"],
                height=meta_dict["height"],
                format=meta_dict.get("format", "JPEG"),
                has_gps=bool(meta_dict.get("gps")),
                has_exif=bool(meta_dict.get("exif")),
            )
            logger.info(
                "Preprocess done: %dx%d, %.1fKB",
                meta_dict["width"],
                meta_dict["height"],
                meta_dict["file_size"] / 1024,
            )
            _end_pipeline_step(
                state,
                step_info,
                output_summary=(
                    f"{meta_dict['width']}x{meta_dict['height']}, "
                    f"{meta_dict['file_size'] / 1024:.1f}KB"
                ),
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
            log_event(task_id, "node_fail", node="preprocess", error=str(exc))
            logger.warning("Preprocess failed: %s", exc)
            _end_pipeline_step(state, step_info, status="failed", error_message=str(exc))
        return {"report": report}

    return preprocess_node


def make_ocr_node(ocr_service: OCRService):
    """Stage 2: OCR text extraction."""

    async def ocr_node(state: PipelineState) -> dict[str, Any]:
        report: AnalysisReport = state["report"]
        task_id = report.id
        _notify_progress(state, "ocr")
        step_info = _start_pipeline_step(state, "ocr")
        step_info["input_summary"] = (
            f"Image: {report.image_metadata.width}x{report.image_metadata.height}"
            if report.image_metadata
            else "Image"
        )
        log_event(task_id, "node_start", node="ocr")
        try:
            results = await ocr_service.extract(state["image_bytes"])
            report.ocr_results = results
            texts = [r.text for r in results]
            avg_conf = sum(r.confidence for r in results) / len(results) if results else 0
            log_event(
                task_id,
                "node_end",
                node="ocr",
                num_regions=len(results),
                avg_confidence=round(avg_conf, 3),
            )
            # Send insight event with actual results
            log_event(
                task_id,
                "insight",
                node="ocr",
                icon="📝",
                title="OCR 文字识别",
                tool="OCR Service",
                tool_detail=settings.ocr_provider,
                summary=f"发现 {len(results)} 个文字区域",
                results=[
                    {"label": "识别文字", "value": texts[:10]},
                    {"label": "平均置信度", "value": f"{avg_conf:.1%}"},
                    {
                        "label": "图片尺寸",
                        "value": f"{report.image_metadata.width}x{report.image_metadata.height}"
                        if report.image_metadata
                        else "unknown",
                    },
                ],
            )
            logger.info("OCR done: %d text regions found", len(results))
            _end_pipeline_step(
                state,
                step_info,
                output_summary=f"{len(results)} text regions detected",
                key_findings=[f"Text: '{t}'" for t in texts[:5]],
                output_data={
                    "num_regions": len(results),
                    "texts": texts,
                    "avg_confidence": avg_conf,
                },
            )
        except Exception as exc:
            log_event(task_id, "node_fail", node="ocr", error=str(exc))
            logger.warning("OCR failed: %s", exc)
            report.ocr_results = []
            _end_pipeline_step(state, step_info, status="failed", error_message=str(exc))
        return {"report": report}

    return ocr_node


def make_vlm_node(vlm_service: VLMService):
    """Stage 3: VLM scene understanding using Qwen2-VL or API."""

    async def vlm_analysis_node(state: PipelineState) -> dict[str, Any]:
        report: AnalysisReport = state["report"]
        task_id = report.id
        lang = state.get("lang", "zh")
        _notify_progress(state, "vlm_analysis")
        step_info = _start_pipeline_step(state, "vlm_analysis")
        ocr_texts = [r.text for r in report.ocr_results]
        step_info["input_summary"] = f"Image + {len(ocr_texts)} OCR texts"
        step_info["input_data"] = {"ocr_texts": ocr_texts}
        log_event(task_id, "node_start", node="vlm_analysis", ocr_count=len(ocr_texts))
        try:
            from vision_insight.services.vlm.api_service import current_task_id

            token = current_task_id.set(task_id)
            try:
                scene = await vlm_service.analyze(
                    state["image_bytes"], report.ocr_results, lang=lang
                )
            finally:
                current_task_id.reset(token)
            report.scene_analysis = scene
            findings = [f"Scene: {scene.scene_type}", f"Description: {scene.description[:100]}..."]
            if scene.location_guess:
                findings.append(f"Location guess: {scene.location_guess.location}")
            if scene.time_guess:
                findings.append(f"Time guess: {scene.time_guess.time_of_day}")
            log_event(
                task_id,
                "node_end",
                node="vlm_analysis",
                scene_type=scene.scene_type,
                location=scene.location_guess.location if scene.location_guess else None,
                location_confidence=round(scene.location_guess.confidence, 3)
                if scene.location_guess
                else None,
            )
            # Send insight event with actual results
            results_items: list[dict[str, Any]] = [
                {"label": "场景类型", "value": scene.scene_type},
                {"label": "场景描述", "value": scene.description},
            ]
            if scene.location_guess:
                results_items.append(
                    {
                        "label": "地点推测",
                        "value": (
                            f"{scene.location_guess.location} "
                            f"({scene.location_guess.confidence:.0%})"
                        ),
                    }
                )
                results_items.append({"label": "地点依据", "value": scene.location_guess.evidence})
            if scene.time_guess:
                results_items.append(
                    {
                        "label": "时间推测",
                        "value": f"{scene.time_guess.time_of_day} {scene.time_guess.season}",
                    }
                )
                results_items.append({"label": "时间依据", "value": scene.time_guess.evidence})
            if scene.people:
                results_items.append({"label": "人物", "value": f"{len(scene.people)} 人"})
            if scene.key_evidence:
                results_items.append({"label": "关键证据", "value": scene.key_evidence})
            if scene.uncertainties:
                results_items.append({"label": "不确定项", "value": scene.uncertainties})
            provider = "Gemini" if "gemini" in str(type(vlm_service)).lower() else "OpenAI"
            log_event(
                task_id,
                "insight",
                node="vlm_analysis",
                icon="👁️",
                title="VLM 场景理解",
                tool=f"{provider} Vision API",
                tool_detail=f"{len(ocr_texts)} OCR文本 + 图片",
                summary=f"场景: {scene.scene_type} | {scene.description[:60]}...",
                results=results_items,
            )
            logger.info("VLM done: scene_type=%s", scene.scene_type)
            _end_pipeline_step(
                state,
                step_info,
                output_summary=f"Scene: {scene.scene_type}",
                key_findings=findings,
                output_data={
                    "scene_type": scene.scene_type,
                    "description": scene.description,
                    "location_guess": scene.location_guess.location
                    if scene.location_guess
                    else None,
                    "time_guess": scene.time_guess.time_of_day if scene.time_guess else None,
                    "num_people": len(scene.people),
                },
            )
        except Exception as exc:
            log_event(
                task_id,
                "node_fail",
                node="vlm_analysis",
                error=str(exc),
                error_type=type(exc).__name__,
            )
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
        task_id = report.id
        _notify_progress(state, "entity_extraction")
        step_info = _start_pipeline_step(state, "entity_extraction")
        step_info["input_summary"] = f"Scene analysis + {len(report.ocr_results)} OCR results"
        if not report.scene_analysis:
            _end_pipeline_step(
                state, step_info, status="skipped", output_summary="No scene analysis available"
            )
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
            # Send insight event with actual results
            results_items: list[dict[str, Any]] = []
            if entities.brands:
                results_items.append({"label": "品牌", "value": entities.brands})
            if entities.landmarks:
                results_items.append({"label": "地标", "value": entities.landmarks})
            if entities.location_keywords:
                results_items.append({"label": "地点关键词", "value": entities.location_keywords})
            if entities.text_entities:
                results_items.append({"label": "文字实体", "value": entities.text_entities})
            log_event(
                task_id,
                "insight",
                node="entity_extraction",
                icon="🏷️",
                title="实体抽取",
                tool="spaCy + LLM",
                tool_detail=f"场景描述 + {len(report.ocr_results)} OCR文本",
                summary=(
                    f"{len(entities.brands)} 品牌, {len(entities.landmarks)} 地标, "
                    f"{len(entities.location_keywords)} 关键词"
                ),
                results=results_items,
            )
            _end_pipeline_step(
                state,
                step_info,
                output_summary=(
                    f"{len(entities.brands)} brands, "
                    f"{len(entities.landmarks)} landmarks"
                ),
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
        task_id = report.id
        _notify_progress(state, "web_search")
        step_info = _start_pipeline_step(state, "web_search")
        if not report.entities:
            _end_pipeline_step(
                state, step_info, status="skipped", output_summary="No entities to search"
            )
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

        # Send insight event with actual results
        results_items: list[dict[str, Any]] = [
            {"label": "搜索词", "value": queries[:3]},
            {"label": "结果数量", "value": f"{len(all_results)} 条"},
        ]
        if all_results:
            results_items.append(
                {"label": "来源", "value": list(set(r.source for r in all_results))}
            )
            results_items.append(
                {
                    "label": "搜索结果",
                    "value": [
                        {"title": r.title, "snippet": r.snippet[:80]} for r in all_results[:3]
                    ],
                }
            )
        log_event(
            task_id,
            "insight",
            node="web_search",
            icon="🌐",
            title="联网验证",
            tool="Wikipedia / Bing",
            tool_detail=f"{len(queries)} 个搜索词",
            summary=f"搜索 {len(queries)} 个关键词，找到 {len(all_results)} 条结果",
            results=results_items,
        )

        _end_pipeline_step(
            state,
            step_info,
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
        task_id = report.id
        _notify_progress(state, "evidence_fusion")
        step_info = _start_pipeline_step(state, "evidence_fusion")
        step_info["input_summary"] = (
            f"{len(report.ocr_results)} OCR, {len(report.search_results)} search results"
        )
        if not report.scene_analysis:
            _end_pipeline_step(
                state, step_info, status="skipped", output_summary="No scene analysis available"
            )
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
            # Send insight event with actual results
            results_items: list[dict[str, Any]] = [
                {"label": "结论数量", "value": f"{len(conclusions)} 条"},
            ]
            if conclusions:
                results_items.append(
                    {
                        "label": "推理策略",
                        "value": conclusions[0].category if conclusions else "none",
                    }
                )
                for c in conclusions[:5]:
                    results_items.append(
                        {
                            "label": c.category,
                            "value": f"{c.statement} ({c.probability:.0%})",
                        }
                    )
            log_event(
                task_id,
                "insight",
                node="evidence_fusion",
                icon="🔬",
                title="证据融合",
                tool="规则 + LLM",
                tool_detail="VLM + OCR + 搜索 + EXIF",
                summary=f"综合 {len(conclusions)} 条结论",
                results=results_items,
            )
            _end_pipeline_step(
                state,
                step_info,
                output_summary=f"{len(conclusions)} conclusions generated",
                key_findings=findings,
                output_data={
                    "num_conclusions": len(conclusions),
                    "categories": list(set(c.category for c in conclusions)),
                    "conclusions_summary": [
                        {
                            "category": c.category,
                            "statement": c.statement[:100],
                            "probability": c.probability,
                        }
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
        lang = state.get("lang", "zh")
        _notify_progress(state, "report_generation")
        step_info = _start_pipeline_step(state, "report_generation")
        step_info["input_summary"] = (
            f"{len(report.conclusions)} conclusions, {len(report.ocr_results)} OCR results"
        )
        try:
            report.report_markdown = await report_service.generate_user_report(report, lang=lang)
            report.status = AnalysisStatus.COMPLETED
            logger.info("Report generation done")
            _end_pipeline_step(
                state,
                step_info,
                output_summary=f"Report generated: {len(report.report_markdown)} chars",
                key_findings=[f"Report length: {len(report.report_markdown)} characters"],
                output_data={"report_length": len(report.report_markdown)},
            )
            # Build PipelineTrace from state if verbose
            if state.get("verbose") and "pipeline_trace" in state:
                from vision_insight.models.schemas import (
                    PipelineStep as PStep,
                )
                from vision_insight.models.schemas import (
                    PipelineTrace,
                )

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
) -> CompiledStateGraph:
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
