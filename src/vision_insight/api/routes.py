"""API routes for Visual Insight Agent."""

import asyncio
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, File, UploadFile, HTTPException

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


async def _run_analysis(task_id: str, image_bytes: bytes) -> None:
    """Background task: run the analysis pipeline."""
    runner = get_pipeline_runner()
    report = _tasks[task_id]
    try:
        updated = await runner.execute(report, image_bytes)
        _tasks[task_id] = updated
    except Exception as exc:
        logger.exception("Background analysis failed for %s", task_id)
        report.status = AnalysisStatus.FAILED
        report.report_markdown = f"# 分析失败\n\n错误: {exc}"


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
