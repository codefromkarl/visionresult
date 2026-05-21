"""API routes for Visual Insight Agent."""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import AsyncGenerator

from fastapi import APIRouter, BackgroundTasks, File, UploadFile, HTTPException
from fastapi.responses import StreamingResponse

from vision_insight.models.schemas import (
    AnalysisReport,
    AnalysisStatus,
    AnalysisTaskResponse,
    ImageUploadRequest,
)
from vision_insight.pipeline.runner import get_pipeline_runner

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory task store (replace with DB in production)
_tasks: dict[str, AnalysisReport] = {}
# In-memory progress store for SSE
_progress: dict[str, list[tuple[str, int]]] = {}


async def _run_analysis(task_id: str, image_bytes: bytes) -> None:
    """Background task: run the analysis pipeline with progress tracking."""
    runner = get_pipeline_runner()
    report = _tasks[task_id]
    _progress[task_id] = []

    def progress_callback(stage: str, percent: int):
        _progress[task_id].append((stage, percent))

    try:
        updated = await runner.execute(report, image_bytes, progress_callback)
        _tasks[task_id] = updated
    except Exception as exc:
        logger.exception("Background analysis failed for %s", task_id)
        report.status = AnalysisStatus.FAILED
        report.report_markdown = f"# 分析失败\n\n错误: {exc}"
    finally:
        # Mark as done
        _progress[task_id].append(("done", 100))


@router.post("/analyze", response_model=AnalysisTaskResponse)
async def create_analysis(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    analysis_depth: str = "standard",
):
    """Submit an image for analysis.

    Accepts image upload and starts the analysis pipeline.
    Returns a task ID for tracking progress.
    """
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty file")

    task_id = str(uuid.uuid4())[:8]
    report = AnalysisReport(
        id=task_id,
        status=AnalysisStatus.PENDING,
        created_at=datetime.now(),
    )
    _tasks[task_id] = report

    # Trigger async pipeline execution
    background_tasks.add_task(_run_analysis, task_id, image_bytes)

    return AnalysisTaskResponse(
        task_id=task_id,
        status=AnalysisStatus.PENDING,
        message="Analysis started. Poll /api/v1/report/{task_id} for results.",
    )


@router.post("/analyze/url", response_model=AnalysisTaskResponse)
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
    report = AnalysisReport(
        id=task_id,
        status=AnalysisStatus.PENDING,
        created_at=datetime.now(),
    )
    _tasks[task_id] = report

    background_tasks.add_task(_run_analysis, task_id, image_bytes)

    return AnalysisTaskResponse(
        task_id=task_id,
        status=AnalysisStatus.PENDING,
        message="Analysis started.",
    )


@router.get("/report/{task_id}", response_model=AnalysisReport)
async def get_report(task_id: str):
    """Get analysis report by task ID."""
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    return _tasks[task_id]


@router.get("/reports", response_model=list[AnalysisReport])
async def list_reports(limit: int = 20, offset: int = 0):
    """List recent analysis reports."""
    reports = list(_tasks.values())
    reports.sort(key=lambda r: r.created_at, reverse=True)
    return reports[offset : offset + limit]


@router.get("/analyze/{task_id}/stream")
async def stream_progress(task_id: str):
    """Stream analysis progress via SSE.

    Returns Server-Sent Events with progress updates.
    Event format: data: {"stage": "ocr", "progress": 25}
    """
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    async def event_generator() -> AsyncGenerator[str, None]:
        last_idx = 0
        while True:
            # Check if task is done
            report = _tasks.get(task_id)
            if report and report.status in (AnalysisStatus.COMPLETED, AnalysisStatus.FAILED):
                # Send final event
                yield f"data: {json.dumps({'stage': 'done', 'progress': 100, 'status': report.status.value})}\n\n"
                break

            # Check for new progress updates
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
