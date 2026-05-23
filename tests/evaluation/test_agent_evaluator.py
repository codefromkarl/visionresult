"""Agent 评估器测试 — 验证语义级测试评估能力"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from tests.evaluation.agent_evaluator import (
    TestGap,
    TestQualityAssessment,
    _parse_json_response,
    analyze_requirement_test_alignment,
    evaluate_test_quality,
    extract_requirements,
    extract_test_descriptions,
)

# ─── JSON 解析测试 ─────────────────────────────────────────


class TestJsonParsing:
    """JSON 响应解析测试。"""

    def test_parse_valid_json(self):
        text = '{"score": 85, "strengths": ["good"]}'
        result = _parse_json_response(text)
        assert result["score"] == 85
        assert result["strengths"] == ["good"]

    def test_parse_json_in_code_block(self):
        text = '''Here is the analysis:
```json
{"score": 70, "weaknesses": ["missing error tests"]}
```
Hope this helps!'''
        result = _parse_json_response(text)
        assert result["score"] == 70

    def test_parse_json_with_surrounding_text(self):
        text = 'Based on my analysis, the result is: {"score": 90} overall.'
        result = _parse_json_response(text)
        assert result["score"] == 90

    def test_parse_invalid_json_raises(self):
        with pytest.raises(ValueError, match="无法从 LLM 响应中提取 JSON"):
            _parse_json_response("This is not JSON at all")


# ─── 需求提取测试 ──────────────────────────────────────────


class TestRequirementExtraction:
    """需求提取测试。"""

    def test_extract_from_prd(self, tmp_path):
        prd = tmp_path / "prd.md"
        prd.write_text("""# PRD

## 功能

### 图片上传
- 用户可以上传 JPG/PNG 图片
- 支持拖拽上传

### OCR 识别
- 提取图片中的文字
- 返回置信度
""")
        requirements = extract_requirements(prd)
        assert len(requirements) >= 4
        assert any("上传" in r for r in requirements)
        assert any("OCR" in r for r in requirements)


# ─── 测试描述提取 ──────────────────────────────────────────


class TestDescriptionExtraction:
    """测试描述提取测试。"""

    def test_extract_test_descriptions(self, tmp_path):
        test_file = tmp_path / "test_example.py"
        test_file.write_text('''import pytest

def test_upload_success():
    """用户上传图片后应显示预览。"""
    pass

def test_upload_error():
    """API 失败时应显示错误信息。"""
    pass

def test_no_docstring():
    pass
''')
        descriptions = extract_test_descriptions(test_file)
        assert len(descriptions) == 3
        assert any("预览" in d for d in descriptions)
        assert any("错误" in d for d in descriptions)
        assert any("无描述" in d for d in descriptions)


# ─── Agent 评估测试 ─────────────────────────────────────────


class TestAgentEvaluation:
    """Agent 评估核心功能测试。"""

    @pytest.mark.asyncio
    async def test_evaluate_test_quality(self, tmp_path):
        """评估测试质量应返回结构化结果。"""
        # 创建测试文件
        prd = tmp_path / "prd.md"
        prd.write_text("# 上传功能\n- 用户上传图片\n- 显示预览")

        impl = tmp_path / "upload.py"
        impl.write_text("async def upload(file): ...")

        test = tmp_path / "test_upload.py"
        test.write_text('''
def test_upload():
    """用户上传图片后应显示预览。"""
    assert True
''')

        # Mock LLM 响应
        mock_response = json.dumps({
            "score": 75,
            "strengths": ["覆盖了上传功能"],
            "weaknesses": ["缺少错误路径测试"],
            "gaps": [{
                "requirement": "错误处理",
                "expected_behavior": "API 失败时显示错误",
                "current_coverage": "未覆盖",
                "gap_description": "缺少上传失败测试",
                "suggested_test": "def test_upload_error(): ...",
                "severity": "high"
            }],
            "recommendations": ["添加错误路径测试"],
            "suggested_tests": ["def test_upload_error(): ..."]
        })

        with patch(
            "tests.evaluation.agent_evaluator._call_llm",
            new_callable=AsyncMock,
        ) as mock_llm:
            mock_llm.return_value = mock_response

            result = await evaluate_test_quality(
                prd_path=str(prd),
                implementation_paths=[str(impl)],
                test_paths=[str(test)],
            )

        assert isinstance(result, TestQualityAssessment)
        assert result.score == 75
        assert len(result.strengths) > 0
        assert len(result.gaps) > 0
        assert result.gaps[0].severity == "high"

    @pytest.mark.asyncio
    async def test_analyze_alignment(self):
        """分析需求-测试对齐度。"""
        requirements = ["用户上传图片", "显示预览", "错误处理"]
        tests = ["test_upload: 上传成功", "test_preview: 预览显示"]

        mock_response = json.dumps({
            "alignments": [
                {
                    "requirement": "用户上传图片",
                    "aligned_tests": ["test_upload"],
                    "missing_tests": [],
                    "alignment_score": 1.0
                },
                {
                    "requirement": "错误处理",
                    "aligned_tests": [],
                    "missing_tests": ["test_upload_error"],
                    "alignment_score": 0.0
                }
            ],
            "uncovered_requirements": ["错误处理"],
            "orphan_tests": [],
            "overall_alignment": 0.67
        })

        with patch(
            "tests.evaluation.agent_evaluator._call_llm",
            new_callable=AsyncMock,
        ) as mock_llm:
            mock_llm.return_value = mock_response

            alignments = await analyze_requirement_test_alignment(
                requirements=requirements,
                test_descriptions=tests,
            )

        assert len(alignments) == 2
        assert alignments[0].alignment_score == 1.0
        assert alignments[1].alignment_score == 0.0
        assert "test_upload_error" in alignments[1].missing_tests


# ─── 评估结果结构测试 ──────────────────────────────────────


class TestAssessmentStructure:
    """评估结果结构测试。"""

    def test_gap_structure(self):
        """TestGap 应有完整结构。"""
        gap = TestGap(
            requirement="错误处理",
            expected_behavior="显示错误信息",
            current_coverage="未覆盖",
            gap_description="缺少错误路径测试",
            suggested_test="def test_error(): ...",
            severity="high",
        )
        assert gap.severity == "high"
        assert len(gap.suggested_test) > 0

    def test_assessment_structure(self):
        """TestQualityAssessment 应有完整结构。"""
        assessment = TestQualityAssessment(
            test_file="test_upload.py",
            score=85,
            strengths=["覆盖全面"],
            weaknesses=["缺少边界测试"],
            gaps=[],
            recommendations=["添加边界测试"],
            suggested_tests=[],
        )
        assert 0 <= assessment.score <= 100
        assert len(assessment.strengths) > 0
