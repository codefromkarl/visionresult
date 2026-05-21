"""评估框架测试

对比 TravelAgent 的 evaluators.test.ts。
测试结构化断言评估器和黄金数据集。
"""

from __future__ import annotations

import pytest

from tests.evaluation.assertions import (
    assert_evidence_chain,
    assert_no_hallucination,
    assert_ocr_quality,
    assert_report_structure,
    evaluate_report,
)
from tests.evaluation.golden_examples import GOLDEN_EXAMPLES, get_all_example_ids, get_example_by_id
from tests.mocks.fixtures import (
    create_mock_analysis_report,
    create_mock_fused_conclusion,
    create_mock_ocr_result,
)
from vision_insight.models.schemas import (
    AnalysisReport,
    AnalysisStatus,
    EvidenceItem,
    FusedConclusion,
)

# ─── 结构化断言测试 ──────────────────────────────────────


class TestReportStructure:
    """报告结构检查。"""

    def test_complete_report_passes_all_checks(self):
        report = create_mock_analysis_report()
        results = assert_report_structure(report)
        required = [r for r in results if not r.passed]
        assert len(required) == 0, f"Failed: {[r.name for r in required]}"

    def test_missing_scene_analysis_fails(self):
        report = create_mock_analysis_report(scene_analysis=None, conclusions=[])
        results = assert_report_structure(report)
        scene_check = next(r for r in results if r.name == "包含场景分析")
        assert not scene_check.passed

    def test_missing_conclusions_fails(self):
        report = create_mock_analysis_report(conclusions=[])
        results = assert_report_structure(report)
        conclusion_check = next(r for r in results if r.name == "包含结论")
        assert not conclusion_check.passed

    def test_empty_report_fails_required_checks(self):
        report = AnalysisReport(id="empty", status=AnalysisStatus.COMPLETED)
        results = assert_report_structure(report)
        failures = [r for r in results if not r.passed]
        assert len(failures) > 0


class TestOCRQuality:
    """OCR 质量检查。"""

    def test_high_confidence_ocr_passes(self):
        ocr = [create_mock_ocr_result("Test", 0.95)]
        results = assert_ocr_quality(ocr)
        assert all(r.passed for r in results)

    def test_empty_ocr_fails(self):
        results = assert_ocr_quality([])
        assert any(not r.passed for r in results)

    def test_low_confidence_flagged(self):
        ocr = [create_mock_ocr_result("Test", 0.3)]
        results = assert_ocr_quality(ocr, min_confidence=0.7)
        conf_check = next(r for r in results if r.name == "OCR 平均置信度")
        assert not conf_check.passed

    def test_empty_text_detected(self):
        ocr = [
            create_mock_ocr_result("Valid", 0.9),
            create_mock_ocr_result("", 0.8),
        ]
        results = assert_ocr_quality(ocr)
        empty_check = next(r for r in results if r.name == "OCR 无空文本")
        assert not empty_check.passed


class TestEvidenceChain:
    """证据链检查。"""

    def test_conclusions_with_evidence_pass(self):
        conclusions = [
            create_mock_fused_conclusion("东京涩谷", 0.82, "location"),
        ]
        results = assert_evidence_chain(conclusions)
        assert all(r.passed for r in results)

    def test_empty_conclusions_fail(self):
        results = assert_evidence_chain([])
        assert any(not r.passed for r in results)

    def test_high_prob_needs_strong_evidence(self):
        conclusions = [
            FusedConclusion(
                statement="东京涩谷",
                probability=0.9,
                evidence=[EvidenceItem(source="vlm", content="test", confidence=0.3)],
                category="location",
            ),
        ]
        results = assert_evidence_chain(conclusions)
        strong_check = next(r for r in results if r.name == "高概率结论有强证据")
        assert not strong_check.passed

    def test_low_prob_must_mark_uncertain(self):
        conclusions = [
            FusedConclusion(
                statement="这是确定的地点",  # 没有不确定标记
                probability=0.2,
                evidence=[],
                category="location",
            ),
        ]
        results = assert_evidence_chain(conclusions)
        uncertain_check = next(r for r in results if r.name == "低概率结论标记不确定")
        assert not uncertain_check.passed


class TestNoHallucination:
    """防幻觉检查。"""

    def test_location_with_source_passes(self):
        report = create_mock_analysis_report()
        results = assert_no_hallucination(report)
        assert all(r.passed for r in results)

    def test_high_prob_location_needs_source(self):
        report = create_mock_analysis_report(
            conclusions=[
                FusedConclusion(
                    statement="拍摄地点: 月球表面",
                    probability=0.9,
                    evidence=[EvidenceItem(source="vlm", content="猜测", confidence=0.5)],
                    category="location",
                ),
            ]
        )
        results = assert_no_hallucination(report)
        # VLM-only high probability conclusion should be flagged
        assert any(not r.passed for r in results)


# ─── 综合评估测试 ──────────────────────────────────────


class TestEvaluateReport:
    """综合评估。"""

    def test_good_report_scores_high(self):
        report = create_mock_analysis_report()
        eval_report = evaluate_report(report)
        assert eval_report.overall_score >= 0.6
        assert eval_report.passed

    def test_empty_report_scores_low(self):
        report = AnalysisReport(id="empty", status=AnalysisStatus.COMPLETED)
        eval_report = evaluate_report(report)
        assert eval_report.overall_score < 0.5
        assert not eval_report.passed


# ─── 黄金数据集测试 ──────────────────────────────────────


class TestGoldenExamples:
    """黄金数据集基准测试。"""

    def test_all_examples_have_required_fields(self):
        for ex in GOLDEN_EXAMPLES:
            assert ex.id, "Example missing id"
            assert ex.description, f"{ex.id} missing description"
            assert ex.ocr_texts is not None, f"{ex.id} missing ocr_texts"

    def test_get_example_by_id(self):
        ex = get_example_by_id("shibuya-night")
        assert ex is not None
        assert ex.expected_location == "东京涩谷"

    def test_get_nonexistent_example(self):
        assert get_example_by_id("nonexistent") is None

    def test_all_ids_unique(self):
        ids = get_all_example_ids()
        assert len(ids) == len(set(ids))

    @pytest.mark.parametrize("example_id", [ex.id for ex in GOLDEN_EXAMPLES])
    def test_example_location_confidence_range(self, example_id):
        """验证每个黄金场景的置信度范围合理。"""
        ex = get_example_by_id(example_id)
        assert ex is not None
        assert 0.0 <= ex.min_location_confidence <= ex.max_location_confidence <= 1.0

    def test_shibuya_has_expected_keywords(self):
        ex = get_example_by_id("shibuya-night")
        assert ex is not None
        assert "Shibuya" in ex.ocr_texts
        assert "109" in ex.ocr_texts
        assert "涩谷109" in ex.expected_landmarks

    def test_game_screenshot_no_location(self):
        ex = get_example_by_id("game-screenshot")
        assert ex is not None
        assert ex.max_location_confidence <= 0.1
        assert ex.expected_location is None
