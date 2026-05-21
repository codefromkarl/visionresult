"""API routes for Visual Insight Agent."""

import uuid
from datetime import datetime

from fastapi import APIRouter, File, UploadFile, HTTPException

from vision_insight.models.schemas import (
    AnalysisReport,
    AnalysisStatus,
    AnalysisTaskResponse,
    ImageUploadRequest,
)

router = APIRouter()

# In-memory task store (replace with DB in production)
_tasks: dict[str, AnalysisReport] = {}


@router.post("/analyze", response_model=AnalysisTaskResponse)
async def create_analysis(
    file: UploadFile = File(...),
    analysis_depth: str = "standard",
):
    """Submit an image for analysis.

    Accepts image upload and starts the analysis pipeline.
    Returns a task ID for tracking progress.
    """
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    task_id = str(uuid.uuid4())[:8]

    report = AnalysisReport(
        id=task_id,
        status=AnalysisStatus.PENDING,
        created_at=datetime.now(),
    )
    _tasks[task_id] = report

    # TODO: Trigger async pipeline execution
    # pipeline = InsightPipeline()
    # await pipeline.execute(task_id, file, analysis_depth)

    return AnalysisTaskResponse(
        task_id=task_id,
        status=AnalysisStatus.PENDING,
        message="Analysis task created. Poll /api/v1/report/{task_id} for results.",
    )


@router.post("/analyze/url", response_model=AnalysisTaskResponse)
async def create_analysis_from_url(request: ImageUploadRequest):
    """Submit an image URL for analysis."""
    if not request.image_url:
        raise HTTPException(status_code=400, detail="image_url is required")

    task_id = str(uuid.uuid4())[:8]

    report = AnalysisReport(
        id=task_id,
        status=AnalysisStatus.PENDING,
        created_at=datetime.now(),
    )
    _tasks[task_id] = report

    # TODO: Trigger async pipeline execution
    return AnalysisTaskResponse(
        task_id=task_id,
        status=AnalysisStatus.PENDING,
        message="Analysis task created.",
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
