"""Mock service implementations for integration tests.

对比 TravelAgent 的 mock-llm.ts，提供所有 service 的 mock 实现，
用于 pipeline 集成测试，避免调用真实 AI API。
"""

from __future__ import annotations

from tests.mocks.fixtures import (
    create_mock_entity_extraction,
    create_mock_fused_conclusion,
    create_mock_ocr_result,
    create_mock_scene_analysis,
    create_mock_search_result,
)
from vision_insight.models.schemas import (
    DetectedObject,
    EntityExtraction,
    OCRResult,
    SceneAnalysis,
    SearchResult,
)
from vision_insight.services import (
    EntityService,
    EvidenceService,
    OCRService,
    ReportService,
    SearchService,
    VLMService,
)


class MockOCRService(OCRService):
    """Mock OCR service — 返回预设结果，不调用 PaddleOCR."""

    def __init__(self, results: list[OCRResult] | None = None):
        self._results = results or [create_mock_ocr_result()]
        self.call_count = 0

    async def extract(self, image_bytes: bytes) -> list[OCRResult]:
        self.call_count += 1
        return self._results


class MockVLMService(VLMService):
    """Mock VLM service — 返回预设场景分析，不调用 LLM API."""

    def __init__(
        self,
        scene: SceneAnalysis | None = None,
        objects: list[DetectedObject] | None = None,
    ):
        self._scene = scene or create_mock_scene_analysis()
        self._objects = objects or []
        self.analyze_count = 0
        self.detect_count = 0

    async def analyze(
        self, image_bytes: bytes, ocr_results: list[OCRResult] | None = None
    ) -> SceneAnalysis:
        self.analyze_count += 1
        return self._scene

    async def detect_objects(self, image_bytes: bytes) -> list[DetectedObject]:
        self.detect_count += 1
        return self._objects


class MockEntityService(EntityService):
    """Mock entity extraction service."""

    def __init__(self, entities: EntityExtraction | None = None):
        self._entities = entities or create_mock_entity_extraction()
        self.call_count = 0

    async def extract(
        self, scene: SceneAnalysis, ocr_results: list[OCRResult]
    ) -> EntityExtraction:
        self.call_count += 1
        return self._entities


class MockSearchService(SearchService):
    """Mock search service — 返回预设搜索结果，不调用外部 API."""

    def __init__(self, results: list[SearchResult] | None = None):
        self._results = results or [create_mock_search_result()]
        self.call_count = 0

    async def search(self, query: str, source: str = "google") -> list[SearchResult]:
        self.call_count += 1
        return self._results

    async def verify_location(self, keywords: list[str]) -> list[SearchResult]:
        self.call_count += 1
        return self._results


class MockEvidenceService(EvidenceService):
    """Mock evidence fusion service."""

    def __init__(self, conclusions=None):
        self._conclusions = conclusions or [
            create_mock_fused_conclusion("拍摄地点: 东京涩谷", 0.82, "location"),
        ]
        self.call_count = 0

    async def fuse(self, scene, ocr_results, entities, search_results, metadata):
        self.call_count += 1
        return self._conclusions


class MockReportService(ReportService):
    """Mock report generation service."""

    def __init__(self, markdown: str = "# Mock Report\n分析完成"):
        self._markdown = markdown
        self.call_count = 0

    async def generate_user_report(self, report) -> str:
        self.call_count += 1
        return self._markdown

    async def generate_structured_report(self, report) -> dict:
        self.call_count += 1
        return {"id": report.id, "status": "completed", "mock": True}
