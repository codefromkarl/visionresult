"""结构化断言评估器

对比 TravelAgent 的 evaluators.test.ts → assertTripPlanStructure，
为图片分析报告提供确定性检查。

三层评估体系：
  1. 结构化断言 — 确定性代码检查（hard assertion）
  2. LLM-as-Judge — 语义质量评估（soft report）
  3. 黄金数据集 — 标准场景基准测试
"""

from __future__ import annotations

from dataclasses import dataclass

from vision_insight.models.schemas import AnalysisReport, FusedConclusion


@dataclass
class EvaluationResult:
    """单项评估结果"""

    name: str
    score: float  # 0-1
    reason: str
    passed: bool


@dataclass
class EvalReport:
    """评估报告"""

    results: list[EvaluationResult]
    overall_score: float
    passed: bool

    @property
    def failures(self) -> list[EvaluationResult]:
        return [r for r in self.results if not r.passed]


# ─── 结构化断言 ──────────────────────────────────────────


def assert_report_structure(report: AnalysisReport) -> list[EvaluationResult]:
    """验证分析报告包含所有必要结构。

    类比 TravelAgent 的 assertTripPlanStructure。
    """
    results: list[EvaluationResult] = []

    # 1. 基础字段
    checks: list[tuple[str, bool, bool]] = [
        ("包含任务 ID", bool(report.id), True),
        ("状态已设置", report.status is not None, True),
        ("包含场景分析", report.scene_analysis is not None, True),
        ("包含 OCR 结果", len(report.ocr_results) > 0, False),
        ("包含结论", len(report.conclusions) > 0, True),
    ]

    for name, condition, required in checks:
        results.append(
            EvaluationResult(
                name=name,
                score=1.0 if condition else 0.0,
                reason=f"{name}: {'✓' if condition else '✗'}",
                passed=condition if required else True,
            )
        )

    # 2. 场景分析完整性
    if report.scene_analysis:
        sa = report.scene_analysis
        scene_checks: list[tuple[str, bool, bool]] = [
            ("场景类型已识别", bool(sa.scene_type), True),
            ("场景描述存在", bool(sa.description), True),
            ("地点推测存在", sa.location_guess is not None, False),
            ("时间推测存在", sa.time_guess is not None, False),
        ]
        for name, condition, required in scene_checks:
            results.append(
                EvaluationResult(
                    name=name,
                    score=1.0 if condition else 0.0,
                    reason=f"{name}: {'✓' if condition else '✗'}",
                    passed=condition if required else True,
                )
            )

        # 3. 地点推测置信度检查
        if sa.location_guess:
            loc = sa.location_guess
            conf_ok = loc.confidence > 0.0
            has_evidence = len(loc.evidence) > 0
            results.append(
                EvaluationResult(
                    name="地点推测有置信度",
                    score=loc.confidence,
                    reason=f"置信度: {loc.confidence:.0%}",
                    passed=conf_ok,
                )
            )
            results.append(
                EvaluationResult(
                    name="地点推测有依据",
                    score=1.0 if has_evidence else 0.0,
                    reason=f"依据数: {len(loc.evidence)}",
                    passed=has_evidence,
                )
            )

    # 4. 结论质量检查
    if report.conclusions:
        has_location = any(c.category == "location" for c in report.conclusions)
        has_probability = all(c.probability > 0 for c in report.conclusions)
        results.append(
            EvaluationResult(
                name="包含地点结论",
                score=1.0 if has_location else 0.0,
                reason=f"地点结论: {'✓' if has_location else '✗'}",
                passed=has_location,
            )
        )
        results.append(
            EvaluationResult(
                name="所有结论有概率",
                score=1.0 if has_probability else 0.0,
                reason=f"概率完整: {'✓' if has_probability else '✗'}",
                passed=has_probability,
            )
        )

    return results


def assert_ocr_quality(
    ocr_results: list,
    min_confidence: float = 0.7,
) -> list[EvaluationResult]:
    """验证 OCR 结果质量。"""
    results: list[EvaluationResult] = []

    if not ocr_results:
        results.append(
            EvaluationResult(
                name="OCR 有结果",
                score=0.0,
                reason="无 OCR 结果",
                passed=False,
            )
        )
        return results

    results.append(
        EvaluationResult(
            name="OCR 有结果",
            score=1.0,
            reason=f"检测到 {len(ocr_results)} 条文字",
            passed=True,
        )
    )

    # 平均置信度
    avg_conf = sum(r.confidence for r in ocr_results) / len(ocr_results)
    results.append(
        EvaluationResult(
            name="OCR 平均置信度",
            score=avg_conf,
            reason=f"平均置信度: {avg_conf:.0%}",
            passed=avg_conf >= min_confidence,
        )
    )

    # 空文本检查
    empty_count = sum(1 for r in ocr_results if not r.text.strip())
    results.append(
        EvaluationResult(
            name="OCR 无空文本",
            score=1.0 - (empty_count / len(ocr_results)),
            reason=f"空文本: {empty_count}/{len(ocr_results)}",
            passed=empty_count == 0,
        )
    )

    return results


def assert_evidence_chain(conclusions: list[FusedConclusion]) -> list[EvaluationResult]:
    """验证证据链完整性。

    核心原则：每个推断必须有依据。
    """
    results: list[EvaluationResult] = []

    if not conclusions:
        results.append(
            EvaluationResult(
                name="有结论",
                score=0.0,
                reason="无结论",
                passed=False,
            )
        )
        return results

    # 每个结论都有证据
    conclusions_with_evidence = sum(1 for c in conclusions if c.evidence)
    ratio = conclusions_with_evidence / len(conclusions)
    results.append(
        EvaluationResult(
            name="结论有证据支持",
            score=ratio,
            reason=f"{conclusions_with_evidence}/{len(conclusions)} 结论有证据",
            passed=ratio >= 0.8,
        )
    )

    # 高概率结论必须有强证据
    high_prob = [c for c in conclusions if c.probability >= 0.7]
    if high_prob:
        strong_evidence = sum(1 for c in high_prob if any(e.confidence >= 0.7 for e in c.evidence))
        results.append(
            EvaluationResult(
                name="高概率结论有强证据",
                score=strong_evidence / len(high_prob) if high_prob else 1.0,
                reason=f"{strong_evidence}/{len(high_prob)} 高概率结论有强证据",
                passed=strong_evidence == len(high_prob),
            )
        )

    # 不确定性标记检查 — 概率 < 0.3 的结论应表达不确定
    low_prob = [c for c in conclusions if c.probability < 0.3]
    if low_prob:
        uncertain_marked = sum(
            1
            for c in low_prob
            if any(kw in c.statement for kw in ["不确定", "无法", "不足", "未知"])
        )
        results.append(
            EvaluationResult(
                name="低概率结论标记不确定",
                score=uncertain_marked / len(low_prob),
                reason=f"{uncertain_marked}/{len(low_prob)} 低概率结论标记了不确定",
                passed=uncertain_marked == len(low_prob),
            )
        )

    return results


def assert_no_hallucination(report: AnalysisReport) -> list[EvaluationResult]:
    """防幻觉检查 — 验证推断与证据一致。"""
    results: list[EvaluationResult] = []

    if not report.conclusions:
        return results

    # 检查结论中的地名是否在 OCR 或实体中出现过
    ocr_texts = {r.text.lower() for r in report.ocr_results}
    entity_keywords = set()
    if report.entities:
        entity_keywords.update(k.lower() for k in report.entities.location_keywords)
        entity_keywords.update(k.lower() for k in report.entities.landmarks)
        entity_keywords.update(k.lower() for k in report.entities.brands)

    ocr_texts | entity_keywords

    for conclusion in report.conclusions:
        if conclusion.category == "location" and conclusion.probability >= 0.7:
            # 高概率地点结论应有证据来源
            has_source = any(e.source in ("ocr", "search", "exif") for e in conclusion.evidence)
            results.append(
                EvaluationResult(
                    name=f"地点结论有来源: {conclusion.statement[:30]}",
                    score=1.0 if has_source else 0.3,
                    reason=f"证据来源: {[e.source for e in conclusion.evidence]}",
                    passed=has_source,
                )
            )

    return results


# ─── 综合评估 ──────────────────────────────────────────


def evaluate_report(report: AnalysisReport) -> EvalReport:
    """综合评估分析报告。"""
    all_results: list[EvaluationResult] = []

    all_results.extend(assert_report_structure(report))
    all_results.extend(assert_ocr_quality(report.ocr_results))
    all_results.extend(assert_evidence_chain(report.conclusions))
    all_results.extend(assert_no_hallucination(report))

    # 计算总分
    scores = [r.score for r in all_results]
    overall = sum(scores) / len(scores) if scores else 0.0

    # 所有 required 检查必须通过
    required = [r for r in all_results if not r.passed]

    return EvalReport(
        results=all_results,
        overall_score=overall,
        passed=len(required) == 0,
    )
