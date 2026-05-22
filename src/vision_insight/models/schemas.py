"""Pydantic models for API and pipeline data structures."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class AnalysisStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# === Request Models ===


class ImageUploadRequest(BaseModel):
    """Request for image upload analysis."""

    image_url: str | None = None
    analysis_depth: str = "standard"  # quick | standard | deep


# === Pipeline Data Models ===


class OCRResult(BaseModel):
    """Single OCR detection."""

    text: str
    bbox: list[list[int]] = Field(
        description="Bounding box coordinates [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]"
    )
    confidence: float = Field(ge=0.0, le=1.0)


class ImageMetadata(BaseModel):
    """Image EXIF and basic metadata."""

    width: int
    height: int
    format: str
    file_size: int
    exif: dict = Field(default_factory=dict)
    gps: dict | None = None
    capture_time: datetime | None = None


class DetectedObject(BaseModel):
    """Object detected in image."""

    label: str
    confidence: float = Field(ge=0.0, le=1.0)
    bbox: list[int] | None = None  # [x1, y1, x2, y2]
    category: str = ""  # person, building, food, logo, vehicle, etc.


class SceneAnalysis(BaseModel):
    """Scene-level understanding from VLM."""

    scene_type: str
    description: str
    location_guess: LocationGuess | None = None
    time_guess: TimeGuess | None = None
    people: list[PeopleInfo] = Field(default_factory=list)
    key_evidence: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)


class LocationGuess(BaseModel):
    """Location prediction with confidence."""

    location: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)


class TimeGuess(BaseModel):
    """Time period prediction."""

    time_of_day: str = ""  # morning, afternoon, evening, night
    season: str = ""  # spring, summer, autumn, winter
    year_estimate: str = ""  # e.g., "2020s", "2024"
    evidence: list[str] = Field(default_factory=list)


class PeopleInfo(BaseModel):
    """People detected in image."""

    count: int
    age_group: str = ""  # young, middle-aged, elderly
    activity: str = ""


class EntityExtraction(BaseModel):
    """Structured entities extracted from analysis."""

    location_keywords: list[str] = Field(default_factory=list)
    brands: list[str] = Field(default_factory=list)
    landmarks: list[str] = Field(default_factory=list)
    text_entities: list[str] = Field(default_factory=list)


class SearchResult(BaseModel):
    """Web search verification result."""

    query: str
    source: str  # google, bing, wikipedia, maps
    title: str
    snippet: str
    url: str
    relevance: float = Field(ge=0.0, le=1.0)


class EvidenceItem(BaseModel):
    """Single piece of evidence in the chain."""

    source: str  # ocr, vlm, search, exif, scene
    content: str
    confidence: float = Field(ge=0.0, le=1.0)
    supporting: bool = True  # True = supports conclusion, False = contradicts


class FusedConclusion(BaseModel):
    """Evidence-fused conclusion."""

    statement: str
    probability: float = Field(ge=0.0, le=1.0)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    category: str = ""  # location, time, scene, identity


# === Pipeline Trace Models (for verbose/debug mode) ===


class ReasoningStep(BaseModel):
    """Single step in the reasoning chain."""

    step_id: int
    action: str  # e.g., "rule_match", "llm_inference", "evidence_weight"
    description: str
    input_summary: str = ""
    output_summary: str = ""
    confidence_before: float = 0.0
    confidence_after: float = 0.0
    duration_ms: int = 0
    metadata: dict = Field(default_factory=dict)


class ReasoningTrace(BaseModel):
    """Complete reasoning trace for a conclusion."""

    conclusion_category: str
    conclusion_statement: str
    final_probability: float
    steps: list[ReasoningStep] = Field(default_factory=list)
    strategy_used: str = ""  # rule, llm, hybrid
    total_duration_ms: int = 0


class PipelineStep(BaseModel):
    """Detailed information about a pipeline stage execution."""

    stage_name: str  # preprocess, ocr, vlm_analysis, etc.
    status: str  # success, failed, skipped
    start_time: datetime
    end_time: datetime | None = None
    duration_ms: int = 0
    input_summary: str = ""  # Brief description of inputs
    output_summary: str = ""  # Brief description of outputs
    key_findings: list[str] = Field(default_factory=list)  # Notable discoveries
    error_message: str | None = None
    # Detailed data (only included in verbose mode)
    input_data: dict = Field(default_factory=dict)
    output_data: dict = Field(default_factory=dict)


class PipelineTrace(BaseModel):
    """Complete trace of the analysis pipeline execution."""

    steps: list[PipelineStep] = Field(default_factory=list)
    reasoning_traces: list[ReasoningTrace] = Field(default_factory=list)
    total_duration_ms: int = 0
    verbose_mode: bool = True


# === Response Models ===


class AnalysisReport(BaseModel):
    """Final analysis report."""

    id: str
    status: AnalysisStatus
    image_metadata: ImageMetadata | None = None
    scene_analysis: SceneAnalysis | None = None
    ocr_results: list[OCRResult] = Field(default_factory=list)
    detected_objects: list[DetectedObject] = Field(default_factory=list)
    entities: EntityExtraction | None = None
    search_results: list[SearchResult] = Field(default_factory=list)
    conclusions: list[FusedConclusion] = Field(default_factory=list)
    report_markdown: str = ""
    created_at: datetime = Field(default_factory=datetime.now)
    processing_time_ms: int = 0
    # Pipeline trace for verbose mode
    pipeline_trace: PipelineTrace | None = None


class AnalysisTaskResponse(BaseModel):
    """Response when submitting an analysis task."""

    task_id: str
    status: AnalysisStatus
    message: str


class QuestionRequest(BaseModel):
    """Request for asking a question about an analysis."""

    question: str
    analysis_id: str


class QuestionResponse(BaseModel):
    """Response to a question about an analysis."""

    answer: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.8)
    sources: list[str] = Field(default_factory=list)
