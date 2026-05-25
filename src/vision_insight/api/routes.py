"""API routes for Visual Insight Agent."""

import asyncio
import ipaddress
import json
import logging
import socket
import time
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse

from vision_insight.core.config import settings
from vision_insight.core.adapters import record_to_report, report_to_record
from vision_insight.core.database import (
    AnalysisRecord,
    delete_analysis,
    get_analysis,
    get_database_stats,
    list_analyses,
    save_analysis,
    search_analyses,
)
from vision_insight.core.event_logger import (
    get_task_events as _get_events,
)
from vision_insight.core.event_logger import (
    log_event,
    register_sse_queue,
    unregister_sse_queue,
)
from vision_insight.models.schemas import (
    AnalysisReport,
    AnalysisStatus,
    AnalysisTaskResponse,
    EntityExtraction,
    FusedConclusion,
    ImageMetadata,
    ImageUploadRequest,
    OCRResult,
    QuestionRequest,
    QuestionResponse,
    SearchResult,
)
from vision_insight.pipeline.runner import get_pipeline_runner
from vision_insight.services.report.markdown_report_service import MarkdownReportService
from vision_insight.utils import generate_task_id
from vision_insight.utils.image import detect_image_format

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory progress store for SSE (not persisted)
# Each entry: task_id -> (timestamp, list[(stage, percent)])
_progress: dict[str, tuple[float, list[tuple[str, int]]]] = {}
_PROGRESS_TTL_SECONDS = 3600  # 1 hour


def _cleanup_progress() -> None:
    """Remove progress entries older than _PROGRESS_TTL_SECONDS."""
    now = time.time()
    expired = [k for k, (ts, _) in _progress.items() if now - ts > _PROGRESS_TTL_SECONDS]
    for k in expired:
        del _progress[k]
    if expired:
        logger.debug("Cleaned up %d expired progress entries", len(expired))


# File upload constraints
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp", "image/bmp"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

# Image storage directory
IMAGES_DIR = settings.images_dir


def _validate_url_for_ssrf(url: str) -> None:
    """Validate URL to prevent SSRF attacks.

    Args:
        url: The URL to validate.

    Raises:
        HTTPException: If the URL is potentially dangerous.
    """
    parsed = urlparse(url)

    # Only allow http and https schemes
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid URL scheme: {parsed.scheme}. Only http and https are allowed.",
        )

    # Check for localhost
    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(status_code=400, detail="Invalid URL: no hostname")

    if hostname in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        raise HTTPException(
            status_code=400,
            detail="Invalid URL: localhost is not allowed",
        )

    # Check if hostname is an IP address
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            raise HTTPException(
                status_code=400,
                detail="Invalid URL: private/internal IP addresses are not allowed",
            )
    except ValueError:
        # Not an IP address, check via DNS resolution
        try:
            resolved = socket.getaddrinfo(hostname, None)
            for _, _, _, _, sockaddr in resolved:
                resolved_ip = ipaddress.ip_address(sockaddr[0])
                if resolved_ip.is_private or resolved_ip.is_loopback or resolved_ip.is_link_local:
                    raise HTTPException(
                        status_code=400,
                        detail="Invalid URL: resolves to private/internal IP",
                    )
        except socket.gaierror:
            raise HTTPException(status_code=400, detail="Invalid URL: hostname cannot be resolved")


def _validate_image_file(file: UploadFile, image_bytes: bytes) -> None:
    """Validate uploaded image file.

    Args:
        file: The uploaded file object.
        image_bytes: Raw file bytes.

    Raises:
        HTTPException: If validation fails.
    """
    # Check file size
    if len(image_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024 * 1024)}MB",
        )

    if len(image_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    # Check MIME type
    if file.content_type and file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid content type: {file.content_type}. "
                f"Allowed: {', '.join(ALLOWED_MIME_TYPES)}"
            ),
        )

    # Check file extension
    if file.filename:
        ext = Path(file.filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file extension: {ext}. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
            )

    # Validate magic bytes (file signature)
    detected_format = detect_image_format(image_bytes)
    # JPEG is the default fallback; verify it actually starts with JPEG magic
    if detected_format == "jpeg" and not image_bytes[:3] == b"\xff\xd8\xff":
        raise HTTPException(
            status_code=400,
            detail="Invalid image file: file signature does not match any supported format",
        )


async def _run_analysis(
    task_id: str,
    image_bytes: bytes,
    filename: str | None = None,
    verbose: bool = False,
    lang: str = "zh",
) -> None:
    """Background task: run the analysis pipeline with progress tracking."""
    runner = get_pipeline_runner()

    # Create in-memory report for pipeline
    report = AnalysisReport(
        id=task_id,
        status=AnalysisStatus.PENDING,
        created_at=datetime.now(UTC),
    )
    # Cleanup old entries before adding new one
    _cleanup_progress()
    _progress[task_id] = (time.time(), [])

    def progress_callback(stage: str, percent: int):
        _, entries = _progress[task_id]
        entries.append((stage, percent))
        log_event(task_id, "progress", stage=stage, percent=percent)

    log_event(
        task_id, "background_task_start", filename=filename, image_bytes=len(image_bytes), lang=lang
    )

    try:
        updated = await runner.execute(
            report, image_bytes, progress_callback, verbose=verbose, lang=lang
        )

        # Save to database
        record = report_to_record(updated, filename)
        save_analysis(record)

        log_event(
            task_id,
            "background_task_end",
            status=updated.status.value,
            processing_time_ms=updated.processing_time_ms,
        )

    except Exception as exc:
        logger.exception("Background analysis failed for %s", task_id)
        log_event(task_id, "background_task_fail", error=str(exc), error_type=type(exc).__name__)
        # Save failure to database
        record = AnalysisRecord(
            id=task_id,
            status="failed",
            created_at=datetime.now(UTC),
            report_markdown=f"# 分析失败\n\n错误: {exc}",
        )
        save_analysis(record)
    finally:
        if task_id in _progress:
            _, entries = _progress[task_id]
            entries.append(("done", 100))
            # Delete entry to free memory; DB is the source of truth.
            # SSE clients already connected have their own event queue.
            del _progress[task_id]


@router.post(
    "/analyze", response_model=AnalysisTaskResponse, tags=["analysis"], summary="上传图片分析"
)
async def create_analysis(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    analysis_depth: str = "standard",
    verbose: bool = False,
    lang: str = "zh",
    request: Request = None,
):
    """Submit an image for analysis.

    Args:
        verbose: If true, record detailed pipeline trace with reasoning steps.
        lang: Output language - 'zh' for Chinese (default), 'en' for English.
    """
    image_bytes = await file.read()

    # Validate file (size, type, magic bytes)
    _validate_image_file(file, image_bytes)

    task_id = generate_task_id()

    client_ip = request.client.host if request and request.client else "unknown"
    log_event(
        task_id,
        "request_received",
        filename=file.filename,
        content_type=file.content_type,
        image_bytes=len(image_bytes),
        analysis_depth=analysis_depth,
        verbose=verbose,
        client_ip=client_ip,
    )

    # Create pending record in DB
    record = AnalysisRecord(
        id=task_id,
        status="pending",
        created_at=datetime.now(UTC),
        image_filename=file.filename,
    )
    save_analysis(record)

    # Save image to local storage
    image_path = IMAGES_DIR / f"{task_id}{Path(file.filename).suffix.lower()}"
    image_path.write_bytes(image_bytes)
    log_event(task_id, "image_saved", path=str(image_path))

    background_tasks.add_task(_run_analysis, task_id, image_bytes, file.filename, verbose, lang)

    log_event(task_id, "task_created", status="pending", lang=lang)

    return AnalysisTaskResponse(
        task_id=task_id,
        status=AnalysisStatus.PENDING,
        message="Analysis started. Poll /api/v1/report/{task_id} for results.",
    )


@router.post(
    "/analyze/url",
    response_model=AnalysisTaskResponse,
    tags=["analysis"],
    summary="URL图片分析",
)
async def create_analysis_from_url(
    background_tasks: BackgroundTasks,
    request: ImageUploadRequest,
):
    """Submit an image URL for analysis."""
    if not request.image_url:
        raise HTTPException(status_code=400, detail="image_url is required")

    # Validate URL to prevent SSRF attacks
    _validate_url_for_ssrf(request.image_url)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(request.image_url)
            resp.raise_for_status()
            image_bytes = resp.content
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to download image: {exc}")

    task_id = generate_task_id()
    record = AnalysisRecord(
        id=task_id,
        status="pending",
        created_at=datetime.now(UTC),
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
async def get_report(
    task_id: str, format: str = "json", include_trace: bool = False, lang: str = "zh"
):
    """Get analysis report by task ID.

    Args:
        format: Response format - 'json' (default) or 'html'
        include_trace: If true, include pipeline trace in JSON response (only if available)
        lang: Language for HTML report - 'zh' (default) or 'en'
    """
    record = get_analysis(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="Task not found")

    if format == "html":
        report = record_to_report(record)
        if report.status != AnalysisStatus.COMPLETED:
            raise HTTPException(
                status_code=400, detail=f"Report not ready (status: {report.status.value})"
            )

        service = MarkdownReportService()
        html = await service.generate_html_report(report, lang=lang)
        return HTMLResponse(content=html)

    result = record.to_dict()

    # Include pipeline trace if requested and available
    if include_trace and record.pipeline_trace_json:
        result["pipeline_trace"] = AnalysisRecord.parse_json_field(record.pipeline_trace_json, {})

    return result


@router.get("/reports", tags=["reports"], summary="历史报告列表")
async def list_reports(
    limit: int = 20,
    offset: int = 0,
    keyword: str | None = None,
    scene_type: str | None = None,
    location: str | None = None,
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


@router.get("/image/{task_id}", tags=["images"], summary="获取分析图片")
async def get_image(task_id: str):
    """Get the analyzed image by task ID."""
    # Find image file
    for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"]:
        image_path = IMAGES_DIR / f"{task_id}{ext}"
        if image_path.exists():
            media_type = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".gif": "image/gif",
                ".webp": "image/webp",
                ".bmp": "image/bmp",
            }.get(ext, "image/jpeg")
            return FileResponse(image_path, media_type=media_type)
    raise HTTPException(status_code=404, detail="Image not found")


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
        image_bytes = await file.read()

        # Validate each file
        try:
            _validate_image_file(file, image_bytes)
        except HTTPException as e:
            results.append({"filename": file.filename, "error": e.detail})
            continue

        task_id = generate_task_id()
        record = AnalysisRecord(
            id=task_id,
            status="pending",
            created_at=datetime.now(UTC),
            image_filename=file.filename,
        )
        save_analysis(record)
        background_tasks.add_task(_run_analysis, task_id, image_bytes, file.filename)
        results.append({"filename": file.filename, "task_id": task_id, "status": "pending"})

    return {"tasks": results}


@router.get("/analyze/{task_id}/stream", tags=["analysis"], summary="实时进度SSE")
async def stream_progress(task_id: str):
    """Stream analysis progress and events via SSE."""
    record = get_analysis(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="Task not found")

    log_event(task_id, "sse_connect")

    async def event_generator() -> AsyncGenerator[str, None]:
        # Register for real-time events
        event_queue = register_sse_queue(task_id)
        try:
            # Check if already completed
            rec = get_analysis(task_id)
            if rec and rec.status in ("completed", "failed"):
                data = {"type": "progress", "stage": "done", "progress": 100, "status": rec.status}
                yield f"data: {json.dumps(data)}\n\n"
                return

            while True:
                try:
                    # Wait for event from queue with timeout
                    event_data = await asyncio.wait_for(event_queue.get(), timeout=30.0)
                    yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"

                    # Check if this was a terminal event
                    if event_data.get("type") == "progress" and event_data.get("stage") == "done":
                        break
                    if event_data.get("type") == "event" and event_data.get("data", {}).get(
                        "event"
                    ) in ("background_task_end", "background_task_fail"):
                        # Send done signal
                        rec = get_analysis(task_id)
                        status = rec.status if rec else "failed"
                        data = {
                            "type": "progress",
                            "stage": "done",
                            "progress": 100,
                            "status": status,
                        }
                        yield f"data: {json.dumps(data)}\n\n"
                        break

                except TimeoutError:
                    # Send heartbeat to keep connection alive
                    yield ": heartbeat\n\n"

                    # Check if completed (fallback)
                    rec = get_analysis(task_id)
                    if rec and rec.status in ("completed", "failed"):
                        data = {
                            "type": "progress",
                            "stage": "done",
                            "progress": 100,
                            "status": rec.status,
                        }
                        yield f"data: {json.dumps(data)}\n\n"
                        break

            log_event(task_id, "sse_end", status="stream_complete")
        finally:
            unregister_sse_queue(task_id, event_queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/analyze/{task_id}/events", tags=["analysis"], summary="执行链路事件")
async def get_task_events(task_id: str):
    """Get the execution trace events for a task.

    Returns all recorded events for the task's execution lifecycle,
    including pipeline stages, VLM retries, timeouts, etc.
    """
    events = _get_events(task_id)
    if not events:
        # Also check if task exists in DB
        record = get_analysis(task_id)
        if not record:
            raise HTTPException(status_code=404, detail="Task not found")
        return {
            "task_id": task_id,
            "events": [],
            "message": "No events recorded (task may have run before events feature was enabled)",
        }

    return {"task_id": task_id, "events": events, "total": len(events)}


@router.get("/stats", tags=["system"], summary="系统统计")
async def get_stats():
    """Get database statistics."""
    stats = get_database_stats()
    return {
        "total_analyses": stats["total"],
        "completed": stats["completed"],
        "failed": stats["failed"],
        "pending": stats["pending"],
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

    # Simple rule-based QA (could be enhanced with LLM)
    question = request.question.lower()
    answer = ""
    confidence = 0.7
    sources = []

    if any(kw in question for kw in ["地点", "位置", "哪里", "where", "location"]):
        answer = f"根据分析，拍摄地点推测为: {record.location_guess or '未知'}"
        confidence = float(record.location_confidence or 0.5)
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
        ocr = AnalysisRecord.parse_json_field(record.ocr_results_json, [])
        if ocr:
            texts = [r.get("text", "") for r in ocr]
            answer = f"检测到的文字: {', '.join(texts)}"
            confidence = 0.9
        else:
            answer = "未检测到文字"
            confidence = 0.95
        sources = ["OCR文字识别"]

    elif any(kw in question for kw in ["品牌", "logo", "brand"]):
        ent = AnalysisRecord.parse_json_field(record.entities_json, {})
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
