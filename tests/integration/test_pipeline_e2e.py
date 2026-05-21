"""Integration test for the full analysis pipeline with mocked services."""

from __future__ import annotations

import asyncio
import io
import os
import sys
from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image

from vision_insight.models.schemas import (
    AnalysisReport,
    AnalysisStatus,
    DetectedObject,
    EntityExtraction,
    LocationGuess,
    OCRResult,
    PeopleInfo,
    SceneAnalysis,
    SearchResult,
    TimeGuess,
)
from vision_insight.services import (
    EntityService,
    OCRService,
    SearchService,
    VLMService,
)

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


def _make_test_image(text: str = "Hello World", size: tuple = (200, 150)) -> bytes:
    """Create a simple test image with text."""
    img = Image.new("RGB", size, color="white")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


class MockOCRService(OCRService):
    async def extract(self, image_bytes: bytes):
        return [
            OCRResult(
                text="涩谷109", bbox=[[10, 10], [100, 10], [100, 30], [10, 30]], confidence=0.95
            ),
            OCRResult(
                text="SHIBUYA", bbox=[[10, 40], [100, 40], [100, 60], [10, 60]], confidence=0.92
            ),
        ]


class MockVLMService(VLMService):
    async def analyze(self, image_bytes, ocr_results=None):
        return SceneAnalysis(
            scene_type="street",
            description="日本东京涩谷商业区夜景，霓虹灯闪烁，人流密集",
            location_guess=LocationGuess(
                location="东京涩谷",
                confidence=0.85,
                evidence=["日文招牌", "涩谷109建筑", "JR地铁标志"],
            ),
            time_guess=TimeGuess(
                time_of_day="night",
                season="winter",
                year_estimate="2024",
                evidence=["霓虹灯", "冬季服装"],
            ),
            people=[PeopleInfo(count=15, age_group="young", activity="逛街购物")],
            key_evidence=["涩谷109标志", "日文广告牌", "密集人群"],
            uncertainties=["具体年份不确定"],
        )

    async def detect_objects(self, image_bytes):
        return [
            DetectedObject(label="building", confidence=0.9, category="building"),
            DetectedObject(label="person", confidence=0.85, category="person"),
        ]


class MockEntityService(EntityService):
    async def extract(self, scene, ocr_results):
        return EntityExtraction(
            location_keywords=["东京", "涩谷", "Shibuya"],
            brands=["109"],
            landmarks=["涩谷109"],
            text_entities=["涩谷109", "SHIBUYA"],
        )


class MockSearchService(SearchService):
    async def search(self, query, source="google"):
        return [
            SearchResult(
                query=query,
                source="wikipedia",
                title="涩谷109",
                snippet="涩谷109是东京涩谷的标志性商业建筑",
                url="https://zh.wikipedia.org/wiki/涩谷109",
                relevance=0.9,
            ),
        ]

    async def verify_location(self, keywords):
        return await self.search(" ".join(keywords))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_full_flow():
    """Test the complete pipeline from image bytes to report."""

    from vision_insight.models.schemas import AnalysisReport, AnalysisStatus
    from vision_insight.pipeline.runner import PipelineRunner

    # Create runner and inject mock services
    runner = PipelineRunner()
    runner._ocr = MockOCRService()
    runner._vlm = MockVLMService()
    runner._entity = MockEntityService()
    runner._search = MockSearchService()

    # Evidence fusion needs a real FusionService
    from vision_insight.services.evidence.fusion_service import FusionService

    runner._evidence = FusionService(llm=None)

    # Build pipeline with mock services
    from vision_insight.pipeline.graph import build_pipeline

    runner._pipeline = build_pipeline(
        ocr_service=runner._ocr,
        vlm_service=runner._vlm,
        entity_service=runner._entity,
        search_service=runner._search,
        evidence_service=runner._evidence,
    )

    # Create report and execute
    report = AnalysisReport(
        id="test-001",
        status=AnalysisStatus.PENDING,
    )
    image_bytes = _make_test_image()

    result = await runner.execute(report, image_bytes)

    # Verify results
    assert result.status == AnalysisStatus.COMPLETED, f"Expected COMPLETED, got {result.status}"
    assert result.processing_time_ms > 0
    assert result.image_metadata is not None
    assert result.image_metadata.width == 200
    assert result.image_metadata.height == 150

    # OCR results
    assert len(result.ocr_results) == 2
    assert result.ocr_results[0].text == "涩谷109"

    # Scene analysis
    assert result.scene_analysis is not None
    assert result.scene_analysis.scene_type == "street"
    assert "涩谷" in result.scene_analysis.description

    # Location guess
    assert result.scene_analysis.location_guess is not None
    assert "涩谷" in result.scene_analysis.location_guess.location

    # Entities
    assert result.entities is not None
    assert "涩谷109" in result.entities.landmarks

    # Search results
    assert len(result.search_results) > 0

    # Conclusions
    assert len(result.conclusions) > 0

    # Report markdown
    assert len(result.report_markdown) > 0
    assert "图片分析报告" in result.report_markdown

    print("\n✅ Pipeline full flow test PASSED")
    print(f"   - Processing time: {result.processing_time_ms}ms")
    print(f"   - OCR results: {len(result.ocr_results)}")
    print(f"   - Conclusions: {len(result.conclusions)}")
    print(f"   - Report length: {len(result.report_markdown)} chars")


@pytest.mark.asyncio
async def test_pipeline_handles_vlm_failure():
    """Test that pipeline gracefully handles VLM failure."""
    from vision_insight.pipeline.runner import PipelineRunner
    from vision_insight.services.evidence.fusion_service import FusionService

    class FailingVLMService(VLMService):
        async def analyze(self, image_bytes, ocr_results=None):
            raise RuntimeError("VLM API timeout")

        async def detect_objects(self, image_bytes):
            raise RuntimeError("VLM API timeout")

    runner = PipelineRunner()
    runner._ocr = MockOCRService()
    runner._vlm = FailingVLMService()
    runner._entity = MockEntityService()
    runner._search = MockSearchService()
    runner._evidence = FusionService(llm=None)

    from vision_insight.pipeline.graph import build_pipeline

    runner._pipeline = build_pipeline(
        ocr_service=runner._ocr,
        vlm_service=runner._vlm,
        entity_service=runner._entity,
        search_service=runner._search,
        evidence_service=runner._evidence,
    )

    report = AnalysisReport(id="test-fail", status=AnalysisStatus.PENDING)
    result = await runner.execute(report, _make_test_image())

    # Should still complete (with degraded results)
    assert result.status == AnalysisStatus.COMPLETED
    assert result.scene_analysis is not None
    assert (
        "失败" in result.scene_analysis.description or result.scene_analysis.scene_type == "unknown"
    )
    print("\n✅ Pipeline VLM failure graceful degradation PASSED")


@pytest.mark.asyncio
async def test_api_analyze_endpoint():
    """Test the /api/v1/analyze endpoint with mocked pipeline."""

    from fastapi.testclient import TestClient

    from vision_insight.main import app
    from vision_insight.models.schemas import AnalysisReport, AnalysisStatus

    # Create a mock runner that returns immediately
    mock_runner = AsyncMock()
    mock_report = AnalysisReport(
        id="api-test",
        status=AnalysisStatus.COMPLETED,
        report_markdown="# 测试报告",
    )
    mock_runner.execute.return_value = mock_report

    with patch("vision_insight.api.routes.get_pipeline_runner", return_value=mock_runner):
        client = TestClient(app)
        image_bytes = _make_test_image()

        response = client.post(
            "/api/v1/analyze",
            files={"file": ("test.jpg", image_bytes, "image/jpeg")},
        )

        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert data["status"] == "pending"

        # Check report endpoint
        report_response = client.get(f"/api/v1/report/{data['task_id']}")
        assert report_response.status_code == 200

    print("\n✅ API analyze endpoint PASSED")


if __name__ == "__main__":
    asyncio.run(test_pipeline_full_flow())
    asyncio.run(test_pipeline_handles_vlm_failure())
    test_api_analyze_endpoint()
    print("\n🎉 All integration tests passed!")
