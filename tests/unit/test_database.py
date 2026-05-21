"""Tests for the database module."""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from vision_insight.core.database import AnalysisRecord


class TestAnalysisRecord:
    """Test AnalysisRecord model."""

    def test_create_record(self):
        record = AnalysisRecord(
            id="test-001",
            status="pending",
            created_at=datetime.now(),
        )
        assert record.id == "test-001"
        assert record.status == "pending"

    def test_to_dict(self):
        record = AnalysisRecord(
            id="test-002",
            status="completed",
            created_at=datetime(2024, 1, 1, 12, 0, 0),
            completed_at=datetime(2024, 1, 1, 12, 0, 5),
            processing_time_ms=5000,
            image_width=800,
            image_height=600,
            image_format="JPEG",
            image_file_size=50000,
            scene_type="street",
            scene_description="A busy street",
            location_guess="Tokyo",
            location_confidence=0.85,
            report_markdown="# Test Report",
        )
        d = record.to_dict()
        assert d["id"] == "test-002"
        assert d["status"] == "completed"
        assert d["processing_time_ms"] == 5000
        assert d["image"]["width"] == 800
        assert d["scene"]["type"] == "street"
        assert d["location"]["guess"] == "Tokyo"

    def test_json_fields_default(self):
        record = AnalysisRecord(id="test-003", status="pending")
        # Column defaults are applied at insert, not on object creation
        assert record.ocr_results_json is None or json.loads(record.ocr_results_json) == []
        assert record.entities_json is None or json.loads(record.entities_json) == {}
        assert record.conclusions_json is None or json.loads(record.conclusions_json) == []


class TestRecordConversion:
    """Test conversion between AnalysisReport and AnalysisRecord."""

    def test_report_to_record(self):
        from vision_insight.api.routes import _report_to_record
        from vision_insight.models.schemas import (
            AnalysisReport,
            AnalysisStatus,
            ImageMetadata,
            OCRResult,
        )

        report = AnalysisReport(
            id="conv-001",
            status=AnalysisStatus.COMPLETED,
            created_at=datetime(2024, 1, 1),
            processing_time_ms=3000,
            image_metadata=ImageMetadata(
                width=400,
                height=300,
                format="PNG",
                file_size=25000,
            ),
            ocr_results=[
                OCRResult(text="Hello", bbox=[[0, 0], [100, 0], [100, 20], [0, 20]], confidence=0.95),
            ],
            report_markdown="# Test",
        )

        record = _report_to_record(report, "test.png")
        assert record.id == "conv-001"
        assert record.status == "completed"
        assert record.image_filename == "test.png"
        assert record.image_width == 400
        assert record.processing_time_ms == 3000

        ocr = json.loads(record.ocr_results_json)
        assert len(ocr) == 1
        assert ocr[0]["text"] == "Hello"
