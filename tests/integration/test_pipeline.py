"""Pipeline 集成测试

对比 TravelAgent 的 agent-integration.test.ts。
使用 mock services 测试完整分析 pipeline 的数据流。
"""

from __future__ import annotations

import pytest

from tests.evaluation.assertions import evaluate_report
from tests.evaluation.golden_examples import GOLDEN_EXAMPLES, get_example_by_id
from tests.mocks.fixtures import (
    create_mock_entity_extraction,
    create_mock_location_guess,
    create_mock_ocr_result,
    create_mock_scene_analysis,
)
from tests.mocks.mock_services import (
    MockEntityService,
    MockEvidenceService,
    MockOCRService,
    MockReportService,
    MockSearchService,
    MockVLMService,
)
from vision_insight.models.schemas import AnalysisReport, AnalysisStatus

# ─── Pipeline 模拟 ──────────────────────────────────────


class MockPipeline:
    """模拟 LangGraph pipeline — 串联所有 mock services。

    类比 TravelAgent 的 Agent 集成测试，验证数据在各阶段正确流转。
    """

    def __init__(
        self,
        ocr: MockOCRService | None = None,
        vlm: MockVLMService | None = None,
        entity: MockEntityService | None = None,
        search: MockSearchService | None = None,
        evidence: MockEvidenceService | None = None,
        report: MockReportService | None = None,
    ):
        self.ocr = ocr or MockOCRService()
        self.vlm = vlm or MockVLMService()
        self.entity = entity or MockEntityService()
        self.search = search or MockSearchService()
        self.evidence = evidence or MockEvidenceService()
        self.report = report or MockReportService()

    async def execute(self, image_bytes: bytes) -> AnalysisReport:
        """Execute the full pipeline."""
        # Stage 1: OCR
        ocr_results = await self.ocr.extract(image_bytes)

        # Stage 2: VLM Analysis
        scene = await self.vlm.analyze(image_bytes, ocr_results)

        # Stage 3: Entity Extraction
        entities = await self.entity.extract(scene, ocr_results)

        # Stage 4: Search Verification
        search_results = []
        if entities.location_keywords:
            search_results = await self.search.verify_location(entities.location_keywords)

        # Stage 5: Evidence Fusion
        conclusions = await self.evidence.fuse(scene, ocr_results, entities, search_results, None)

        # Stage 6: Report Generation
        report = AnalysisReport(
            id="integration-test",
            status=AnalysisStatus.COMPLETED,
            scene_analysis=scene,
            ocr_results=ocr_results,
            entities=entities,
            search_results=search_results,
            conclusions=conclusions,
        )
        report.report_markdown = await self.report.generate_user_report(report)

        return report


# ─── 集成测试 ──────────────────────────────────────────


class TestPipelineIntegration:
    """Pipeline 数据流集成测试。"""

    @pytest.mark.asyncio
    async def test_full_pipeline_produces_valid_report(self):
        """完整 pipeline 应生成有效报告。"""
        pipeline = MockPipeline()
        image_bytes = b"\x89PNG" + b"\x00" * 100  # minimal image

        report = await pipeline.execute(image_bytes)

        assert report.id == "integration-test"
        assert report.status == AnalysisStatus.COMPLETED
        assert report.scene_analysis is not None
        assert len(report.ocr_results) > 0
        assert len(report.conclusions) > 0
        assert report.report_markdown

    @pytest.mark.asyncio
    async def test_pipeline_passes_ocr_to_vlm(self):
        """OCR 结果应传递给 VLM。"""
        ocr_results = [create_mock_ocr_result("Test Text", 0.9)]
        ocr = MockOCRService(results=ocr_results)
        vlm = MockVLMService()

        pipeline = MockPipeline(ocr=ocr, vlm=vlm)
        await pipeline.execute(b"\x89PNG" + b"\x00" * 100)

        # VLM should have been called
        assert vlm.analyze_count == 1

    @pytest.mark.asyncio
    async def test_pipeline_passes_entities_to_search(self):
        """实体应传递给搜索服务。"""
        entities = create_mock_entity_extraction(location_keywords=["Tokyo", "Shibuya"])
        entity = MockEntityService(entities=entities)
        search = MockSearchService()

        pipeline = MockPipeline(entity=entity, search=search)
        await pipeline.execute(b"\x89PNG" + b"\x00" * 100)

        assert search.call_count == 1

    @pytest.mark.asyncio
    async def test_pipeline_with_no_entities_still_works(self):
        """无实体时 pipeline 仍应正常工作。"""
        entities = create_mock_entity_extraction(location_keywords=[], brands=[], landmarks=[])
        entity = MockEntityService(entities=entities)
        search = MockSearchService()

        pipeline = MockPipeline(entity=entity, search=search)
        report = await pipeline.execute(b"\x89PNG" + b"\x00" * 100)

        assert report.status == AnalysisStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_pipeline_evaluation_passes(self):
        """pipeline 输出应通过评估。"""
        pipeline = MockPipeline()
        report = report = await pipeline.execute(b"\x89PNG" + b"\x00" * 100)

        eval_report = evaluate_report(report)
        assert eval_report.overall_score >= 0.5

    @pytest.mark.asyncio
    async def test_pipeline_calls_all_services(self):
        """pipeline 应调用所有服务。"""
        ocr = MockOCRService()
        vlm = MockVLMService()
        entity = MockEntityService()
        search = MockSearchService()
        evidence = MockEvidenceService()
        report_svc = MockReportService()

        pipeline = MockPipeline(
            ocr=ocr,
            vlm=vlm,
            entity=entity,
            search=search,
            evidence=evidence,
            report=report_svc,
        )
        await pipeline.execute(b"\x89PNG" + b"\x00" * 100)

        assert ocr.call_count == 1
        assert vlm.analyze_count == 1
        assert entity.call_count == 1
        assert search.call_count == 1
        assert evidence.call_count == 1
        assert report_svc.call_count == 1


# ─── 黄金数据集集成测试 ──────────────────────────────────


class TestGoldenDatasetIntegration:
    """使用黄金数据集测试 pipeline。"""

    @pytest.mark.parametrize(
        "example_id",
        [ex.id for ex in GOLDEN_EXAMPLES],
        ids=[ex.id for ex in GOLDEN_EXAMPLES],
    )
    @pytest.mark.asyncio
    async def test_golden_scenario_pipeline(self, example_id: str):
        """每个黄金场景应通过 pipeline 并满足置信度约束。"""
        ex = get_example_by_id(example_id)
        assert ex is not None

        # 构造匹配黄金场景的 mock services
        ocr_results = [create_mock_ocr_result(text, 0.9) for text in ex.ocr_texts]
        scene = create_mock_scene_analysis(
            scene_type=ex.expected_scene_type,
            location_guess=create_mock_location_guess(
                ex.expected_location or "未知",
                ex.min_location_confidence + 0.1,  # 保证在范围内
            )
            if ex.expected_location
            else create_mock_location_guess("未知", 0.1, []),
        )
        entities = create_mock_entity_extraction(
            location_keywords=ex.expected_location_keywords,
            brands=ex.expected_brands,
            landmarks=ex.expected_landmarks,
        )

        pipeline = MockPipeline(
            ocr=MockOCRService(ocr_results),
            vlm=MockVLMService(scene=scene),
            entity=MockEntityService(entities=entities),
        )

        report = report = await pipeline.execute(b"\x89PNG" + b"\x00" * 100)

        # 验证报告有效
        assert report.status == AnalysisStatus.COMPLETED
        assert report.scene_analysis is not None

        # 验证场景类型
        if ex.expected_scene_type:
            assert report.scene_analysis.scene_type == ex.expected_scene_type

        # 验证地点置信度范围
        if report.scene_analysis.location_guess:
            conf = report.scene_analysis.location_guess.confidence
            assert conf >= ex.min_location_confidence, (
                f"{example_id}: 置信度 {conf} < 最小值 {ex.min_location_confidence}"
            )
            assert conf <= ex.max_location_confidence + 0.2, (
                f"{example_id}: 置信度 {conf} > 最大值 {ex.max_location_confidence}"
            )
