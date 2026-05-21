"""Tests for the API routes module."""

from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from vision_insight.api.routes import (
    _record_to_report,
    _report_to_record,
    router,
)
from vision_insight.core.database import AnalysisRecord
from vision_insight.models.schemas import (
    AnalysisReport,
    AnalysisStatus,
    EntityExtraction,
    FusedConclusion,
    ImageMetadata,
    OCRResult,
    QuestionRequest,
    QuestionResponse,
    SceneAnalysis,
    SearchResult,
)


class TestRecordConversion:
    """Test _record_to_report and _report_to_record functions."""

    def test_record_to_report_basic(self):
        """Should convert database record to AnalysisReport."""
        record = AnalysisRecord(
            id="test-001",
            status="completed",
            created_at=datetime(2024, 1, 1),
            processing_time_ms=5000,
            image_width=800,
            image_height=600,
            image_format="JPEG",
            image_file_size=50000,
            scene_type="street",
            scene_description="A busy street",
            location_guess="Tokyo",
            location_confidence=0.85,
            ocr_results_json='[{"text": "Hello", "confidence": 0.95, "bbox": [[0,0],[100,0],[100,20],[0,20]]}]',
            entities_json='{"brands": ["Nike"], "landmarks": []}',
            conclusions_json='[{"statement": "Location: Tokyo", "probability": 0.85, "category": "location"}]',
            search_results_json='[{"query": "test", "source": "wikipedia", "title": "Tokyo", "snippet": "desc", "url": "https://wiki.org", "relevance": 0.8}]',
            report_markdown="# Test Report",
        )

        report = _record_to_report(record)

        assert report.id == "test-001"
        assert report.status == AnalysisStatus.COMPLETED
        assert report.processing_time_ms == 5000
        assert report.image_metadata.width == 800
        assert report.image_metadata.height == 600
        assert len(report.ocr_results) == 1
        assert report.ocr_results[0].text == "Hello"
        assert report.entities.brands == ["Nike"]
        assert len(report.conclusions) == 1
        assert report.conclusions[0].statement == "Location: Tokyo"
        assert len(report.search_results) == 1
        assert report.search_results[0].title == "Tokyo"

    def test_record_to_report_empty_json(self):
        """Should handle empty JSON fields gracefully."""
        record = AnalysisRecord(
            id="test-002",
            status="pending",
            ocr_results_json="[]",
            entities_json="{}",
            conclusions_json="[]",
            search_results_json="[]",
        )

        report = _record_to_report(record)

        assert report.id == "test-002"
        assert report.ocr_results == []
        assert report.entities is None
        assert report.conclusions == []
        assert report.search_results == []

    def test_record_to_report_no_image_metadata(self):
        """Should return None for image_metadata when no dimensions."""
        record = AnalysisRecord(
            id="test-003",
            status="pending",
            image_width=None,
            image_height=None,
        )

        report = _record_to_report(record)

        assert report.image_metadata is None

    def test_report_to_record_basic(self):
        """Should convert AnalysisReport to database record."""
        report = AnalysisReport(
            id="test-004",
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
                OCRResult(text="Test", bbox=[[0, 0], [100, 0], [100, 20], [0, 20]], confidence=0.9),
            ],
            entities=EntityExtraction(brands=["Adidas"]),
            conclusions=[
                FusedConclusion(statement="Test conclusion", probability=0.8, category="scene"),
            ],
            search_results=[
                SearchResult(query="test", source="google", title="Test", snippet="desc", url="http://test.com", relevance=0.8),
            ],
            report_markdown="# Test",
        )

        record = _report_to_record(report, "test.png")

        assert record.id == "test-004"
        assert record.status == "completed"
        assert record.image_filename == "test.png"
        assert record.image_width == 400
        assert record.processing_time_ms == 3000
        assert record.scene_type is None  # No scene_analysis set

        ocr = json.loads(record.ocr_results_json)
        assert len(ocr) == 1
        assert ocr[0]["text"] == "Test"

    def test_report_to_record_with_scene_analysis(self):
        """Should extract scene info from report."""
        from vision_insight.models.schemas import LocationGuess, TimeGuess

        report = AnalysisReport(
            id="test-005",
            status=AnalysisStatus.COMPLETED,
            scene_analysis=SceneAnalysis(
                scene_type="street",
                description="Busy street",
                location_guess=LocationGuess(location="Tokyo", confidence=0.9),
                time_guess=TimeGuess(time_of_day="night", season="winter", year_estimate="2024"),
            ),
        )

        record = _report_to_record(report)

        assert record.scene_type == "street"
        assert record.scene_description == "Busy street"
        assert record.location_guess == "Tokyo"
        assert record.location_confidence == 0.9
        assert "night" in record.time_guess


class TestAPIEndpoints:
    """Test API endpoints."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from vision_insight.main import app

        return TestClient(app)

    def test_health_check(self, client):
        """GET /health should return ok."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data

    def test_analyze_requires_image(self, client):
        """POST /api/v1/analyze should reject non-image files."""
        response = client.post(
            "/api/v1/analyze",
            files={"file": ("test.txt", b"not an image", "text/plain")},
        )
        assert response.status_code == 400
        assert "image" in response.json()["detail"].lower()

    def test_analyze_requires_file(self, client):
        """POST /api/v1/analyze should require file."""
        response = client.post("/api/v1/analyze")
        assert response.status_code == 422  # Validation error

    @patch("vision_insight.api.routes.save_analysis")
    @patch("vision_insight.api.routes.get_pipeline_runner")
    def test_analyze_accepts_image(self, mock_runner, mock_save, client):
        """POST /api/v1/analyze should accept image files."""
        mock_runner.return_value = MagicMock()

        # Create a valid JPEG image
        import io

        from PIL import Image

        img = Image.new("RGB", (100, 100), color="red")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        image_bytes = buf.getvalue()

        response = client.post(
            "/api/v1/analyze",
            files={"file": ("test.jpg", image_bytes, "image/jpeg")},
        )

        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert data["status"] == "pending"

    def test_report_not_found(self, client):
        """GET /api/v1/report/{id} should return 404 for unknown IDs."""
        response = client.get("/api/v1/report/nonexistent")
        assert response.status_code == 404

    def test_analyze_url_requires_url(self, client):
        """POST /api/v1/analyze/url should require image_url."""
        response = client.post(
            "/api/v1/analyze/url",
            json={},
        )
        assert response.status_code == 400
        assert "image_url" in response.json()["detail"].lower()

    def test_batch_requires_files(self, client):
        """POST /api/v1/analyze/batch should require files."""
        response = client.post("/api/v1/analyze/batch")
        assert response.status_code == 422  # Validation error

    def test_batch_rejects_too_many_files(self, client):
        """POST /api/v1/analyze/batch should reject >10 files."""
        import io

        from PIL import Image

        img = Image.new("RGB", (10, 10), color="red")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        image_bytes = buf.getvalue()

        files = [("files", (f"test{i}.jpg", image_bytes, "image/jpeg")) for i in range(11)]
        response = client.post("/api/v1/analyze/batch", files=files)
        assert response.status_code == 400
        assert "10" in response.json()["detail"]

    def test_ask_requires_analysis_id(self, client):
        """POST /api/v1/ask should return 404 for unknown analysis."""
        response = client.post(
            "/api/v1/ask",
            json={"analysis_id": "nonexistent", "question": "What is this?"},
        )
        assert response.status_code == 404

    def test_delete_not_found(self, client):
        """DELETE /api/v1/report/{id} should return 404 for unknown IDs."""
        response = client.delete("/api/v1/report/nonexistent")
        assert response.status_code == 404

    def test_stats_endpoint(self, client):
        """GET /api/v1/stats should return statistics."""
        response = client.get("/api/v1/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total_analyses" in data
        assert "completed" in data
        assert "failed" in data
        assert "pending" in data

    def test_list_reports_empty(self, client):
        """GET /api/v1/reports should return list."""
        response = client.get("/api/v1/reports")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_list_reports_with_filters(self, client):
        """GET /api/v1/reports with filters should work."""
        response = client.get("/api/v1/reports?keyword=test&scene_type=street")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_list_reports_with_location_filter(self, client):
        """GET /api/v1/reports with location filter should work."""
        response = client.get("/api/v1/reports?location=Tokyo")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    @patch("vision_insight.api.routes.get_analysis")
    def test_ask_location_question(self, mock_get_analysis, client):
        """POST /api/v1/ask should answer location questions."""
        mock_record = MagicMock()
        mock_record.status = "completed"
        mock_record.scene_description = "A busy street in Tokyo"
        mock_record.location_guess = "Tokyo, Japan"
        mock_record.location_confidence = 0.85
        mock_record.time_guess = "night winter"
        mock_record.ocr_results_json = '[]'
        mock_record.entities_json = '{"brands": [], "landmarks": ["Shibuya 109"]}'
        mock_record.report_markdown = "# Test Report"
        mock_get_analysis.return_value = mock_record

        response = client.post(
            "/api/v1/ask",
            json={"analysis_id": "test-001", "question": "Where was this photo taken?"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "answer" in data
        assert "confidence" in data
        assert "Tokyo" in data["answer"]

    @patch("vision_insight.api.routes.get_analysis")
    def test_ask_time_question(self, mock_get_analysis, client):
        """POST /api/v1/ask should answer time questions."""
        mock_record = MagicMock()
        mock_record.status = "completed"
        mock_record.scene_description = "Night scene"
        mock_record.location_guess = "Tokyo"
        mock_record.location_confidence = 0.8
        mock_record.time_guess = "night winter 2024"
        mock_record.ocr_results_json = '[]'
        mock_record.entities_json = '{}'
        mock_record.report_markdown = "# Test"
        mock_get_analysis.return_value = mock_record

        response = client.post(
            "/api/v1/ask",
            json={"analysis_id": "test-001", "question": "What time was this taken?"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "night" in data["answer"].lower() or "time" in data["answer"].lower()

    @patch("vision_insight.api.routes.get_analysis")
    def test_ask_ocr_question(self, mock_get_analysis, client):
        """POST /api/v1/ask should answer OCR questions."""
        mock_record = MagicMock()
        mock_record.status = "completed"
        mock_record.scene_description = "Street scene"
        mock_record.location_guess = "Tokyo"
        mock_record.location_confidence = 0.8
        mock_record.time_guess = "night"
        mock_record.ocr_results_json = '[{"text": "Shibuya 109", "confidence": 0.95}]'
        mock_record.entities_json = '{"brands": [], "landmarks": []}'
        mock_record.report_markdown = "# Test"
        mock_get_analysis.return_value = mock_record

        response = client.post(
            "/api/v1/ask",
            json={"analysis_id": "test-001", "question": "Show me the OCR text"},
        )
        assert response.status_code == 200
        data = response.json()
        # OCR question should return detected texts
        assert "Shibuya" in data["answer"] or "109" in data["answer"] or "检测到的文字" in data["answer"]

    @patch("vision_insight.api.routes.get_analysis")
    def test_ask_brand_question(self, mock_get_analysis, client):
        """POST /api/v1/ask should answer brand questions."""
        mock_record = MagicMock()
        mock_record.status = "completed"
        mock_record.scene_description = "Store front"
        mock_record.location_guess = "New York"
        mock_record.location_confidence = 0.7
        mock_record.time_guess = "day"
        mock_record.ocr_results_json = '[]'
        mock_record.entities_json = '{"brands": ["Nike", "Adidas"], "landmarks": []}'
        mock_record.report_markdown = "# Test"
        mock_get_analysis.return_value = mock_record

        response = client.post(
            "/api/v1/ask",
            json={"analysis_id": "test-001", "question": "Show me the brands or logos"},
        )
        assert response.status_code == 200
        data = response.json()
        # Brand question should return brands
        assert "Nike" in data["answer"] or "Adidas" in data["answer"] or "品牌" in data["answer"]

    @patch("vision_insight.api.routes.get_analysis")
    def test_ask_generic_question(self, mock_get_analysis, client):
        """POST /api/v1/ask should handle generic questions."""
        mock_record = MagicMock()
        mock_record.status = "completed"
        mock_record.scene_description = "A beautiful sunset over the ocean"
        mock_record.location_guess = "Hawaii"
        mock_record.location_confidence = 0.6
        mock_record.time_guess = "evening"
        mock_record.ocr_results_json = '[]'
        mock_record.entities_json = '{}'
        mock_record.report_markdown = "# Test"
        mock_get_analysis.return_value = mock_record

        response = client.post(
            "/api/v1/ask",
            json={"analysis_id": "test-001", "question": "Tell me about this image"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "answer" in data
        assert len(data["answer"]) > 0

    @patch("vision_insight.api.routes.get_analysis")
    def test_ask_on_pending_analysis(self, mock_get_analysis, client):
        """POST /api/v1/ask should reject pending analyses."""
        mock_record = MagicMock()
        mock_record.status = "pending"
        mock_get_analysis.return_value = mock_record

        response = client.post(
            "/api/v1/ask",
            json={"analysis_id": "test-001", "question": "What is this?"},
        )
        assert response.status_code == 400
        assert "not completed" in response.json()["detail"].lower()

    def test_ask_nonexistent_analysis(self, client):
        """POST /api/v1/ask should return 404 for unknown analysis."""
        response = client.post(
            "/api/v1/ask",
            json={"analysis_id": "nonexistent", "question": "What is this?"},
        )
        assert response.status_code == 404

    def test_batch_rejects_non_image_files(self, client):
        """POST /api/v1/analyze/batch should reject non-image files."""
        files = [("files", ("test.txt", b"not an image", "text/plain"))]
        response = client.post("/api/v1/analyze/batch", files=files)
        assert response.status_code == 200
        data = response.json()
        # Should have error for the non-image file
        assert "error" in data["tasks"][0]

    def test_delete_existing_report(self, client):
        """DELETE /api/v1/report/{id} should delete existing report."""
        # First create a report
        import io
        from PIL import Image

        img = Image.new("RGB", (10, 10), color="red")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        image_bytes = buf.getvalue()

        # Create
        create_response = client.post(
            "/api/v1/analyze",
            files={"file": ("test.jpg", image_bytes, "image/jpeg")},
        )
        task_id = create_response.json()["task_id"]

        # Delete
        delete_response = client.delete(f"/api/v1/report/{task_id}")
        assert delete_response.status_code == 200
        assert delete_response.json()["task_id"] == task_id

        # Verify deleted
        get_response = client.get(f"/api/v1/report/{task_id}")
        assert get_response.status_code == 404
