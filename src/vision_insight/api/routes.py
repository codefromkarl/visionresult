"""API routes for Visual Insight Agent."""

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse

from vision_insight.core.database import (
    AnalysisRecord,
    delete_analysis,
    get_analysis,
    list_analyses,
    save_analysis,
    search_analyses,
)
from vision_insight.models.schemas import (
    AnalysisReport,
    AnalysisStatus,
    AnalysisTaskResponse,
    ImageUploadRequest,
    QuestionRequest,
    QuestionResponse,
)
from vision_insight.pipeline.runner import get_pipeline_runner

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory progress store for SSE (not persisted)
_progress: dict[str, list[tuple[str, int]]] = {}


def _record_to_report(record: AnalysisRecord) -> AnalysisReport:
    """Convert database record to AnalysisReport."""
    from vision_insight.models.schemas import (
        EntityExtraction,
        FusedConclusion,
        ImageMetadata,
        OCRResult,
        SearchResult,
    )

    # Parse JSON fields
    ocr_results = [OCRResult(**r) for r in json.loads(record.ocr_results_json or "[]")]
    entities_data = json.loads(record.entities_json or "{}")
    entities = EntityExtraction(**entities_data) if entities_data else None
    conclusions_data = json.loads(record.conclusions_json or "[]")
    conclusions = [FusedConclusion(**c) for c in conclusions_data]
    search_data = json.loads(record.search_results_json or "[]")
    search_results = [SearchResult(**s) for s in search_data]

    # Build image metadata
    image_metadata = None
    if record.image_width:
        image_metadata = ImageMetadata(
            width=record.image_width,
            height=record.image_height,
            format=record.image_format or "unknown",
            file_size=record.image_file_size or 0,
        )

    return AnalysisReport(
        id=record.id,
        status=AnalysisStatus(record.status),
        created_at=record.created_at or datetime.now(),
        processing_time_ms=record.processing_time_ms or 0,
        image_metadata=image_metadata,
        ocr_results=ocr_results,
        entities=entities,
        conclusions=conclusions,
        search_results=search_results,
        report_markdown=record.report_markdown or "",
    )


def _report_to_record(report: AnalysisReport, filename: str = None) -> AnalysisRecord:
    """Convert AnalysisReport to database record."""
    record = AnalysisRecord(
        id=report.id,
        status=report.status.value,
        created_at=report.created_at,
        completed_at=datetime.now() if report.status == AnalysisStatus.COMPLETED else None,
        processing_time_ms=report.processing_time_ms,
        image_filename=filename,
        report_markdown=report.report_markdown,
    )

    if report.image_metadata:
        record.image_width = report.image_metadata.width
        record.image_height = report.image_metadata.height
        record.image_format = report.image_metadata.format
        record.image_file_size = report.image_metadata.file_size

    if report.scene_analysis:
        record.scene_type = report.scene_analysis.scene_type
        record.scene_description = report.scene_analysis.description
        if report.scene_analysis.location_guess:
            record.location_guess = report.scene_analysis.location_guess.location
            record.location_confidence = report.scene_analysis.location_guess.confidence
        if report.scene_analysis.time_guess:
            tg = report.scene_analysis.time_guess
            record.time_guess = f"{tg.time_of_day} {tg.season} {tg.year_estimate}".strip()

    record.ocr_results_json = json.dumps(
        [{"text": r.text, "confidence": r.confidence} for r in report.ocr_results],
        ensure_ascii=False,
    )
    if report.entities:
        record.entities_json = report.entities.model_dump_json()
    record.conclusions_json = json.dumps(
        [
            {"statement": c.statement, "probability": c.probability, "category": c.category}
            for c in report.conclusions
        ],
        ensure_ascii=False,
    )
    record.search_results_json = json.dumps(
        [{"title": s.title, "source": s.source, "url": s.url} for s in report.search_results],
        ensure_ascii=False,
    )

    return record


async def _run_analysis(task_id: str, image_bytes: bytes, filename: str = None) -> None:
    """Background task: run the analysis pipeline with progress tracking."""
    runner = get_pipeline_runner()

    # Create in-memory report for pipeline
    report = AnalysisReport(
        id=task_id,
        status=AnalysisStatus.PENDING,
        created_at=datetime.now(),
    )
    _progress[task_id] = []

    def progress_callback(stage: str, percent: int):
        _progress[task_id].append((stage, percent))

    try:
        updated = await runner.execute(report, image_bytes, progress_callback)

        # Save to database
        record = _report_to_record(updated, filename)
        save_analysis(record)

    except Exception as exc:
        logger.exception("Background analysis failed for %s", task_id)
        # Save failure to database
        record = AnalysisRecord(
            id=task_id,
            status="failed",
            created_at=datetime.now(),
            report_markdown=f"# 分析失败\n\n错误: {exc}",
        )
        save_analysis(record)
    finally:
        _progress[task_id].append(("done", 100))


@router.post(
    "/analyze", response_model=AnalysisTaskResponse, tags=["analysis"], summary="上传图片分析"
)
async def create_analysis(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    analysis_depth: str = "standard",
):
    """Submit an image for analysis."""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty file")

    task_id = str(uuid.uuid4())[:8]

    # Create pending record in DB
    record = AnalysisRecord(
        id=task_id,
        status="pending",
        created_at=datetime.now(),
        image_filename=file.filename,
    )
    save_analysis(record)

    background_tasks.add_task(_run_analysis, task_id, image_bytes, file.filename)

    return AnalysisTaskResponse(
        task_id=task_id,
        status=AnalysisStatus.PENDING,
        message="Analysis started. Poll /api/v1/report/{task_id} for results.",
    )


@router.post(
    "/analyze/url", response_model=AnalysisTaskResponse, tags=["analysis"], summary="URL图片分析"
)
async def create_analysis_from_url(
    background_tasks: BackgroundTasks,
    request: ImageUploadRequest,
):
    """Submit an image URL for analysis."""
    if not request.image_url:
        raise HTTPException(status_code=400, detail="image_url is required")

    import httpx

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(request.image_url)
            resp.raise_for_status()
            image_bytes = resp.content
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to download image: {exc}")

    task_id = str(uuid.uuid4())[:8]
    record = AnalysisRecord(
        id=task_id,
        status="pending",
        created_at=datetime.now(),
        image_filename=request.image_url.split("/")[-1][:100],
    )
    save_analysis(record)

    background_tasks.add_task(_run_analysis, task_id, image_bytes)

    return AnalysisTaskResponse(
        task_id=task_id,
        status=AnalysisStatus.PENDING,
        message="Analysis started.",
    )


@router.get("/report/{task_id}", tags=["reports"], summary="获取分析报告")
async def get_report(task_id: str, format: str = "json"):
    """Get analysis report by task ID.

    Args:
        format: Response format - 'json' (default) or 'html'
    """
    record = get_analysis(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="Task not found")

    if format == "html":
        report = _record_to_report(record)
        if report.status != AnalysisStatus.COMPLETED:
            raise HTTPException(
                status_code=400, detail=f"Report not ready (status: {report.status.value})"
            )
        from vision_insight.services.report.markdown_report_service import MarkdownReportService

        service = MarkdownReportService()
        html = await service.generate_html_report(report)
        return HTMLResponse(content=html)

    return record.to_dict()


@router.get("/reports", tags=["reports"], summary="历史报告列表")
async def list_reports(
    limit: int = 20,
    offset: int = 0,
    keyword: str = None,
    scene_type: str = None,
    location: str = None,
):
    """List recent analysis reports with optional filters.

    Args:
        keyword: Search in report text, scene description, filename
        scene_type: Filter by scene type (street, indoor, outdoor, etc.)
        location: Filter by location guess
    """
    if keyword or scene_type or location:
        records = search_analyses(
            keyword=keyword,
            scene_type=scene_type,
            location=location,
            limit=limit,
            offset=offset,
        )
    else:
        records = list_analyses(limit=limit, offset=offset)
    return [r.to_dict() for r in records]


@router.delete("/report/{task_id}", tags=["reports"], summary="删除报告")
async def delete_report(task_id: str):
    """Delete an analysis report."""
    if not delete_analysis(task_id):
        raise HTTPException(status_code=404, detail="Task not found")
    return {"message": "Deleted", "task_id": task_id}


@router.post("/analyze/batch", tags=["analysis"], summary="批量图片分析")
async def create_batch_analysis(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
):
    """Submit multiple images for batch analysis."""
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    if len(files) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 files per batch")

    results = []
    for file in files:
        if not file.content_type or not file.content_type.startswith("image/"):
            results.append({"filename": file.filename, "error": "Not an image file"})
            continue

        image_bytes = await file.read()
        if not image_bytes:
            results.append({"filename": file.filename, "error": "Empty file"})
            continue

        task_id = str(uuid.uuid4())[:8]
        record = AnalysisRecord(
            id=task_id,
            status="pending",
            created_at=datetime.now(),
            image_filename=file.filename,
        )
        save_analysis(record)
        background_tasks.add_task(_run_analysis, task_id, image_bytes, file.filename)
        results.append({"filename": file.filename, "task_id": task_id, "status": "pending"})

    return {"tasks": results}


@router.get("/analyze/{task_id}/stream", tags=["analysis"], summary="实时进度SSE")
async def stream_progress(task_id: str):
    """Stream analysis progress via SSE."""
    record = get_analysis(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="Task not found")

    async def event_generator() -> AsyncGenerator[str, None]:
        last_idx = 0
        while True:
            # Check database for completion
            rec = get_analysis(task_id)
            if rec and rec.status in ("completed", "failed"):
                data = {"stage": "done", "progress": 100, "status": rec.status}
                yield f"data: {json.dumps(data)}\n\n"
                break

            # Check in-memory progress
            progress_list = _progress.get(task_id, [])
            while last_idx < len(progress_list):
                stage, percent = progress_list[last_idx]
                yield f"data: {json.dumps({'stage': stage, 'progress': percent})}\n\n"
                last_idx += 1

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/stats", tags=["system"], summary="系统统计")
async def get_stats():
    """Get database statistics."""
    records = list_analyses(limit=1000)
    total = len(records)
    completed = sum(1 for r in records if r.status == "completed")
    failed = sum(1 for r in records if r.status == "failed")
    pending = sum(1 for r in records if r.status in ("pending", "processing"))

    return {
        "total_analyses": total,
        "completed": completed,
        "failed": failed,
        "pending": pending,
    }


@router.post("/ask", tags=["knowledge"], summary="分析问答")
async def ask_question(request: QuestionRequest):
    """Ask a question about a completed analysis.

    Uses the analysis context to answer questions about the image.
    """
    record = get_analysis(request.analysis_id)
    if not record:
        raise HTTPException(status_code=404, detail="Analysis not found")

    if record.status != "completed":
        raise HTTPException(status_code=400, detail="Analysis not completed yet")

    # Build context from the analysis
    context_parts = []
    if record.scene_description:
        context_parts.append(f"场景描述: {record.scene_description}")
    if record.location_guess:
        context_parts.append(
            f"地点推测: {record.location_guess} (置信度: {record.location_confidence})"
        )
    if record.time_guess:
        context_parts.append(f"时间推测: {record.time_guess}")
    if record.ocr_results_json:
        ocr = json.loads(record.ocr_results_json)
        if ocr:
            texts = [r.get("text", "") for r in ocr]
            context_parts.append(f"OCR文字: {', '.join(texts)}")
    if record.entities_json:
        ent = json.loads(record.entities_json)
        if ent.get("brands"):
            context_parts.append(f"品牌: {', '.join(ent['brands'])}")
        if ent.get("landmarks"):
            context_parts.append(f"地标: {', '.join(ent['landmarks'])}")
    if record.report_markdown:
        context_parts.append(f"完整报告:\n{record.report_markdown[:1000]}")

    "\n".join(context_parts)

    # Simple rule-based QA (could be enhanced with LLM)
    question = request.question.lower()
    answer = ""
    confidence = 0.7
    sources = []

    if any(kw in question for kw in ["地点", "位置", "哪里", "where", "location"]):
        answer = f"根据分析，拍摄地点推测为: {record.location_guess or '未知'}"
        confidence = record.location_confidence or 0.5
        sources = ["VLM场景分析", "实体抽取"]

    elif any(kw in question for kw in ["时间", "什么时候", "when", "time"]):
        answer = f"时间推测: {record.time_guess or '未知'}"
        confidence = 0.6
        sources = ["VLM场景分析", "EXIF元数据"]

    elif any(kw in question for kw in ["场景", "什么", "描述", "what", "scene"]):
        answer = f"场景描述: {record.scene_description or '未知'}"
        confidence = 0.8
        sources = ["VLM场景分析"]

    elif any(kw in question for kw in ["文字", "OCR", "text", "写了什么"]):
        ocr = json.loads(record.ocr_results_json or "[]")
        if ocr:
            texts = [r.get("text", "") for r in ocr]
            answer = f"检测到的文字: {', '.join(texts)}"
            confidence = 0.9
        else:
            answer = "未检测到文字"
            confidence = 0.95
        sources = ["OCR文字识别"]

    elif any(kw in question for kw in ["品牌", "logo", "brand"]):
        ent = json.loads(record.entities_json or "{}")
        brands = ent.get("brands", [])
        if brands:
            answer = f"检测到的品牌: {', '.join(brands)}"
            confidence = 0.85
        else:
            answer = "未检测到品牌"
            confidence = 0.7
        sources = ["实体抽取"]

    else:
        # Generic answer based on report
        answer = f"关于这张图片的分析: {record.scene_description or '暂无详细描述'}"
        confidence = 0.5
        sources = ["综合分析"]

    return QuestionResponse(
        answer=answer,
        confidence=confidence,
        sources=sources,
    )
