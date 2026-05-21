"""Pydantic models for API and pipeline data structures."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class AnalysisStatus(str, Enum):
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
    bbox: list[list[int]] = Field(description="Bounding box coordinates [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]")
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
