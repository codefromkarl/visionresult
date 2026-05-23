"""Agent-driven test evaluation — 语义级测试质量评估

对比机械检查：
- 机械: E2E 测试有 set_input_files? → 有就通过
- Agent: 这个测试是否验证了用户上传图片后看到分析结果的完整流程？

核心能力：
1. 需求-实现-测试三角验证
2. 测试覆盖缺口分析
3. 测试质量语义评估
4. 自动生成补充测试建议
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import httpx


@dataclass
class TestGap:
    """测试覆盖缺口"""
    requirement: str          # 需求描述
    expected_behavior: str    # 期望行为
    current_coverage: str     # 当前覆盖情况
    gap_description: str      # 缺口描述
    suggested_test: str       # 建议的测试代码
    severity: str             # high / medium / low


@dataclass
class TestQualityAssessment:
    """测试质量评估结果"""
    test_file: str
    score: float                          # 0-100
    strengths: list[str]                  # 优点
    weaknesses: list[str]                 # 缺点
    gaps: list[TestGap]                   # 覆盖缺口
    recommendations: list[str]            # 改进建议
    suggested_tests: list[str]            # 建议补充的测试


@dataclass
class RequirementTestAlignment:
    """需求-测试对齐度"""
    requirement: str
    aligned_tests: list[str]              # 对齐的测试
    missing_tests: list[str]              # 缺失的测试
    alignment_score: float                # 0-1


# ─── Agent Prompts ──────────────────────────────────────────

ANALYSIS_PROMPT = """你是一个资深测试架构师。请分析以下需求、实现和测试，评估测试质量。

## 需求 (PRD)
{prd}

## 实现代码
{implementation}

## 测试代码
{tests}

## 评估维度

1. **需求覆盖度** (0-25分): 测试是否覆盖了所有需求点？
2. **行为验证度** (0-25分): 测试是否验证了真实用户行为，而非只检查结构？
3. **边界覆盖度** (0-25分): 测试是否覆盖了错误路径、边界条件？
4. **可维护性** (0-25分): 测试是否清晰、可重复、易维护？

## 输出格式 (JSON)

{{
  "score": <0-100>,
  "strengths": ["优点1", "优点2"],
  "weaknesses": ["缺点1", "缺点2"],
  "gaps": [
    {{
      "requirement": "需求点",
      "expected_behavior": "期望行为",
      "current_coverage": "当前覆盖情况",
      "gap_description": "缺口描述",
      "suggested_test": "建议的测试代码",
      "severity": "high/medium/low"
    }}
  ],
  "recommendations": ["建议1", "建议2"],
  "suggested_tests": ["补充测试1的代码", "补充测试2的代码"]
}}
"""

ALIGNMENT_PROMPT = """你是一个测试覆盖分析师。请分析需求和测试的对齐度。

## 需求列表
{requirements}

## 测试列表
{tests}

## 任务

1. 对于每个需求，判断是否有测试覆盖
2. 对于每个测试，判断它验证了哪个需求
3. 找出未覆盖的需求
4. 找出无对应需求的测试（可能是过度测试）

## 输出格式 (JSON)

{{
  "alignments": [
    {{
      "requirement": "需求描述",
      "aligned_tests": ["测试函数名1", "测试函数名2"],
      "missing_tests": ["缺失的测试描述"],
      "alignment_score": 0.8
    }}
  ],
  "uncovered_requirements": ["未覆盖的需求1"],
  "orphan_tests": ["无对应需求的测试1"],
  "overall_alignment": 0.75
}}
"""


# ─── LLM 调用 ──────────────────────────────────────────────


async def _call_llm(prompt: str, api_key: str | None = None) -> str:
    """调用 LLM API"""
    import os
    key = api_key or os.getenv("VIA_OPENAI_API_KEY", "")
    if not key:
        raise ValueError("No API key configured")

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": "gpt-4o",
                "messages": [
                    {"role": "system", "content": "你是测试架构师，只返回 JSON 格式分析结果。"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
                "max_tokens": 4000,
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


def _parse_json_response(text: str) -> dict:
    """从 LLM 响应中提取 JSON"""
    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 尝试提取 JSON 块
    import re
    json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if json_match:
        try:
            return json.loads(json_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 尝试找到第一个 { 和最后一个 }
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1:
        try:
            return json.loads(text[start:end+1])
        except json.JSONDecodeError:
            pass

    raise ValueError(f"无法从 LLM 响应中提取 JSON: {text[:200]}...")


# ─── 核心评估函数 ──────────────────────────────────────────


async def evaluate_test_quality(
    prd_path: str,
    implementation_paths: list[str],
    test_paths: list[str],
    api_key: str | None = None,
) -> TestQualityAssessment:
    """评估测试质量 — Agent 驱动的语义分析。

    Args:
        prd_path: PRD 文件路径
        implementation_paths: 实现代码文件路径列表
        test_paths: 测试代码文件路径列表
        api_key: OpenAI API Key

    Returns:
        TestQualityAssessment 评估结果
    """
    # 读取文件内容
    prd = Path(prd_path).read_text(encoding="utf-8")

    implementations = []
    for p in implementation_paths:
        implementations.append(f"### {p}\n```python\n{Path(p).read_text(encoding='utf-8')}\n```")
    impl_text = "\n\n".join(implementations)

    tests = []
    for p in test_paths:
        tests.append(f"### {p}\n```python\n{Path(p).read_text(encoding='utf-8')}\n```")
    test_text = "\n\n".join(tests)

    # 构造 prompt
    prompt = ANALYSIS_PROMPT.format(
        prd=prd[:3000],  # 限制长度
        implementation=impl_text[:5000],
        tests=test_text[:5000],
    )

    # 调用 LLM
    response = await _call_llm(prompt, api_key)
    result = _parse_json_response(response)

    # 构造评估结果
    gaps = []
    for g in result.get("gaps", []):
        gaps.append(TestGap(
            requirement=g.get("requirement", ""),
            expected_behavior=g.get("expected_behavior", ""),
            current_coverage=g.get("current_coverage", ""),
            gap_description=g.get("gap_description", ""),
            suggested_test=g.get("suggested_test", ""),
            severity=g.get("severity", "medium"),
        ))

    return TestQualityAssessment(
        test_file=", ".join(test_paths),
        score=result.get("score", 0),
        strengths=result.get("strengths", []),
        weaknesses=result.get("weaknesses", []),
        gaps=gaps,
        recommendations=result.get("recommendations", []),
        suggested_tests=result.get("suggested_tests", []),
    )


async def analyze_requirement_test_alignment(
    requirements: list[str],
    test_descriptions: list[str],
    api_key: str | None = None,
) -> list[RequirementTestAlignment]:
    """分析需求-测试对齐度。

    Args:
        requirements: 需求描述列表
        test_descriptions: 测试描述列表 (格式: "test_func_name: 测试描述")
        api_key: OpenAI API Key

    Returns:
        每个需求的对齐度分析
    """
    req_text = "\n".join(f"{i+1}. {r}" for i, r in enumerate(requirements))
    test_text = "\n".join(f"- {t}" for t in test_descriptions)

    prompt = ALIGNMENT_PROMPT.format(
        requirements=req_text,
        tests=test_text,
    )

    response = await _call_llm(prompt, api_key)
    result = _parse_json_response(response)

    alignments = []
    for a in result.get("alignments", []):
        alignments.append(RequirementTestAlignment(
            requirement=a.get("requirement", ""),
            aligned_tests=a.get("aligned_tests", []),
            missing_tests=a.get("missing_tests", []),
            alignment_score=a.get("alignment_score", 0),
        ))

    return alignments


# ─── 便捷函数 ──────────────────────────────────────────────


def extract_test_descriptions(test_file: Path) -> list[str]:
    """从测试文件中提取测试函数名和 docstring。"""
    import ast

    content = test_file.read_text(encoding="utf-8")
    tree = ast.parse(content)

    descriptions = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test_"):
                docstring = ast.get_docstring(node) or ""
                if docstring:
                    descriptions.append(f"{node.name}: {docstring.split(chr(10))[0]}")
                else:
                    descriptions.append(f"{node.name}: (无描述)")

    return descriptions


def extract_requirements(prd_file: Path) -> list[str]:
    """从 PRD 文件中提取需求点。"""
    content = prd_file.read_text(encoding="utf-8")

    requirements = []
    for line in content.split("\n"):
        line = line.strip()
        # 提取以 - 或 * 开头的列表项
        if line.startswith("- ") or line.startswith("* "):
            requirements.append(line[2:])
        # 提取 ### 标题作为需求点
        elif line.startswith("### "):
            requirements.append(line[4:])

    return [r for r in requirements if len(r) > 5]  # 过滤太短的


# ─── CLI 入口 ──────────────────────────────────────────────


async def main():
    """CLI 入口 — 运行 Agent 测试评估。"""
    import sys

    if len(sys.argv) < 3:
        print(
            "Usage: python -m tests.evaluation.agent_evaluator "
            "<prd_path> <test_path> [impl_path...]"
        )
        sys.exit(1)

    prd_path = sys.argv[1]
    test_path = sys.argv[2]
    impl_paths = sys.argv[3:] if len(sys.argv) > 3 else []

    print(f"📋 PRD: {prd_path}")
    print(f"🧪 Test: {test_path}")
    print(f"💻 Implementation: {impl_paths}")
    print()

    # 提取需求和测试描述
    requirements = extract_requirements(Path(prd_path))
    test_descriptions = extract_test_descriptions(Path(test_path))

    print(f"📝 发现 {len(requirements)} 个需求点")
    print(f"🧪 发现 {len(test_descriptions)} 个测试")
    print()

    # 运行评估
    print("🔍 Agent 分析中...")
    assessment = await evaluate_test_quality(
        prd_path=prd_path,
        implementation_paths=impl_paths,
        test_paths=[test_path],
    )

    # 输出结果
    print(f"\n{'='*60}")
    print(f"📊 测试质量评分: {assessment.score}/100")
    print(f"{'='*60}")

    if assessment.strengths:
        print("\n✅ 优点:")
        for s in assessment.strengths:
            print(f"  - {s}")

    if assessment.weaknesses:
        print("\n❌ 缺点:")
        for w in assessment.weaknesses:
            print(f"  - {w}")

    if assessment.gaps:
        print(f"\n⚠️ 覆盖缺口 ({len(assessment.gaps)} 个):")
        for g in assessment.gaps:
            severity_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(g.severity, "⚪")
            print(f"  {severity_icon} [{g.severity}] {g.gap_description}")
            print(f"    需求: {g.requirement}")
            print(f"    建议: {g.suggested_test[:100]}...")

    if assessment.recommendations:
        print("\n💡 改进建议:")
        for r in assessment.recommendations:
            print(f"  - {r}")

    if assessment.suggested_tests:
        print("\n📝 建议补充的测试:")
        for i, t in enumerate(assessment.suggested_tests, 1):
            print(f"\n  --- 测试 {i} ---")
            print(f"  {t[:200]}...")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
