"""Data adapters between database records and domain models.

This module provides a deep interface for data conversion:
- Single place for all ORM ↔ domain model conversions
- Easy to test with mock data
- Centralized conversion logic
"""

import json
from datetime import UTC, datetime

from vision_insight.core.database import AnalysisRecord
from vision_insight.models.schemas import (
    AnalysisReport,
    AnalysisStatus,
    EntityExtraction,
    FusedConclusion,
    ImageMetadata,
    OCRResult,
    SearchResult,
)


def record_to_report(record: AnalysisRecord) -> AnalysisReport:
    """Convert database record to AnalysisReport.

    Args:
        record: Database record from SQLAlchemy.

    Returns:
        Domain model AnalysisReport.
    """
    # Parse JSON fields using AnalysisRecord helper
    ocr_results = [
        OCRResult(**r) for r in AnalysisRecord.parse_json_field(record.ocr_results_json, [])
    ]
    entities_data = AnalysisRecord.parse_json_field(record.entities_json, {})
    entities = EntityExtraction(**entities_data) if entities_data else None
    conclusions_data = AnalysisRecord.parse_json_field(record.conclusions_json, [])
    conclusions = [FusedConclusion(**c) for c in conclusions_data]
    search_data = AnalysisRecord.parse_json_field(record.search_results_json, [])
    search_results = [SearchResult(**s) for s in search_data]

    # Build image metadata
    image_metadata = None
    if record.image_width:
        image_metadata = ImageMetadata(
            width=int(record.image_width),
            height=int(record.image_height),
            format=str(record.image_format or "unknown"),
            file_size=int(record.image_file_size or 0),
        )

    return AnalysisReport(
        id=str(record.id),
        status=AnalysisStatus(str(record.status)),
        created_at=(
            record.created_at if isinstance(record.created_at, datetime) else datetime.now(UTC)
        ),
        processing_time_ms=int(record.processing_time_ms or 0),
        image_metadata=image_metadata,
        ocr_results=ocr_results,
        entities=entities,
        conclusions=conclusions,
        search_results=search_results,
        report_markdown=str(record.report_markdown or ""),
    )


def report_to_record(report: AnalysisReport, filename: str | None = None) -> AnalysisRecord:
    """Convert AnalysisReport to database record.

    Args:
        report: Domain model AnalysisReport.
        filename: Original image filename.

    Returns:
        Database record for SQLAlchemy.
    """
    record = AnalysisRecord(
        id=report.id,
        status=report.status.value,
        created_at=report.created_at,
        completed_at=datetime.now(UTC) if report.status == AnalysisStatus.COMPLETED else None,
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

    # Save pipeline trace if available
    if report.pipeline_trace:
        record.pipeline_trace_json = report.pipeline_trace.model_dump_json()

    return record
