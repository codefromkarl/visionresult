#!/usr/bin/env python3
"""Agent 测试评估 — 运行语义级测试质量分析

Usage:
    python scripts/eval-tests.py                        # 评估所有测试
    python scripts/eval-tests.py tests/e2e/test_frontend.py  # 评估指定测试
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tests.evaluation.agent_evaluator import (
    evaluate_test_quality,
    extract_requirements,
    extract_test_descriptions,
)


async def evaluate_single_test(test_path: str):
    """评估单个测试文件。"""
    test_file = Path(test_path)
    if not test_file.exists():
        print(f"❌ 文件不存在: {test_path}")
        return

    # 自动查找 PRD
    prd_candidates = [
        PROJECT_ROOT / ".trellis" / "tasks" / "05-21-visual-insight-agent" / "prd.md",
        PROJECT_ROOT / "docs" / "prd.md",
        PROJECT_ROOT / "PRD.md",
    ]
    prd_path = None
    for p in prd_candidates:
        if p.exists():
            prd_path = str(p)
            break

    if not prd_path:
        print("❌ 找不到 PRD 文件")
        return

    # 自动查找实现文件
    impl_dir = PROJECT_ROOT / "src" / "vision_insight"
    impl_files = list(impl_dir.rglob("*.py"))
    impl_paths = [str(f) for f in impl_files if f.is_file()][:5]  # 限制数量

    print(f"📋 PRD: {prd_path}")
    print(f"🧪 Test: {test_path}")
    print(f"💻 Implementation: {len(impl_paths)} files")
    print()

    # 运行评估
    print("🔍 Agent 分析中...")
    try:
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
            print(f"\n✅ 优点:")
            for s in assessment.strengths:
                print(f"  - {s}")

        if assessment.weaknesses:
            print(f"\n❌ 缺点:")
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
            print(f"\n💡 改进建议:")
            for r in assessment.recommendations:
                print(f"  - {r}")

    except ValueError as e:
        print(f"❌ 错误: {e}")
        print("提示: 请设置 VIA_OPENAI_API_KEY 环境变量")


async def evaluate_all_tests():
    """评估所有测试文件。"""
    test_dir = PROJECT_ROOT / "tests"
    test_files = list(test_dir.rglob("test_*.py"))

    print(f"📁 发现 {len(test_files)} 个测试文件")
    print()

    for test_file in test_files:
        print(f"\n{'='*60}")
        print(f"📄 {test_file.relative_to(PROJECT_ROOT)}")
        print(f"{'='*60}")

        # 提取测试描述
        descriptions = extract_test_descriptions(test_file)
        print(f"🧪 测试数: {len(descriptions)}")
        for d in descriptions[:5]:
            print(f"  - {d}")
        if len(descriptions) > 5:
            print(f"  ... 还有 {len(descriptions) - 5} 个")


def main():
    if len(sys.argv) > 1:
        if sys.argv[1] == "--all":
            asyncio.run(evaluate_all_tests())
        else:
            asyncio.run(evaluate_single_test(sys.argv[1]))
    else:
        print("Usage:")
        print("  python scripts/eval-tests.py <test_path>    # 评估指定测试")
        print("  python scripts/eval-tests.py --all           # 列出所有测试")
        print()
        print("Example:")
        print("  python scripts/eval-tests.py tests/e2e/test_frontend.py")


if __name__ == "__main__":
    main()
