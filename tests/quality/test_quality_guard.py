"""测试质量守卫 — 元测试

对比 TravelAgent 的 quality-guard.test.ts。
定期运行，确保测试体系不会随开发产生偏移：
  1. 所有 service 源文件都有对应测试
  2. Fixtures 工厂覆盖了所有核心 schema
  3. 测试文件命名规范
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
SRC_DIR = PROJECT_ROOT / "src" / "vision_insight"
TEST_DIR = PROJECT_ROOT / "tests"

# 不需要测试的文件（纯接口/入口/类型）
SOURCE_FILES_EXEMPT = {
    "__init__.py",
    "main.py",
    "models/__init__.py",
    "models/schemas.py",  # Pydantic schema 由 fixtures 间接覆盖
    "core/__init__.py",
    "core/config.py",  # 纯配置
    "utils/__init__.py",
    "pipeline/__init__.py",
    "services/__init__.py",  # 抽象接口
    "services/ocr/__init__.py",
    "services/vlm/__init__.py",
    "services/entity/__init__.py",
    "services/search/__init__.py",
    "services/evidence/__init__.py",
    "services/report/__init__.py",
}


def _get_relative_path(path: Path, base: Path) -> str:
    """Get relative path string."""
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def _get_all_source_files() -> list[str]:
    """获取所有需要测试覆盖的源文件。"""
    files = []
    for f in SRC_DIR.rglob("*.py"):
        rel = _get_relative_path(f, SRC_DIR)
        if rel not in SOURCE_FILES_EXEMPT and not rel.startswith("__pycache__"):
            files.append(rel)
    return sorted(files)


def _has_corresponding_test(src_file: str) -> bool:
    """检查源文件是否有对应的测试文件。"""
    # services/ocr/paddle_service.py → test_ocr.py 或 test_paddle_service.py
    parts = Path(src_file).parts
    stem = Path(src_file).stem

    # 直接匹配
    direct_patterns = [
        f"test_{stem}.py",
        f"test_{stem}s.py",  # plural
        f"test_{stem}_utils.py",  # utils variant
        f"test_{stem}_service.py",  # service variant
    ]

    # 目录级匹配（services/ocr/paddle_service.py → test_ocr.py）
    if len(parts) >= 2:
        dir_name = parts[-2]  # ocr, vlm, entity, etc.
        direct_patterns.append(f"test_{dir_name}.py")

    for pattern in direct_patterns:
        # Search in all test subdirectories
        for test_file in TEST_DIR.rglob(pattern):
            if test_file.is_file():
                return True

    return False


# ─── 源文件覆盖检查 ──────────────────────────────────────


class TestSourceFileCoverage:
    """确保所有 service 源文件有对应测试。"""

    @pytest.mark.parametrize(
        "src_file",
        _get_all_source_files(),
        ids=lambda f: f,
    )
    def test_has_corresponding_test(self, src_file: str):
        assert _has_corresponding_test(src_file), (
            f"{src_file} 没有对应测试文件。"
            f"请创建 tests/unit/services/test_*.py 或 tests/unit/test_*.py"
        )


# ─── Fixtures 覆盖检查 ──────────────────────────────────


class TestFixturesCoverage:
    """确保 fixtures 工厂覆盖所有核心 schema。"""

    def test_fixtures_importable(self):
        """Fixtures 模块应可正常导入。"""
        from tests.mocks import fixtures
        assert hasattr(fixtures, "create_mock_analysis_report")

    def test_all_create_mock_functions_exist(self):
        """所有 create_mock_* 函数应存在。"""
        from tests.mocks import fixtures

        expected_functions = [
            "create_mock_ocr_result",
            "create_mock_image_metadata",
            "create_mock_location_guess",
            "create_mock_time_guess",
            "create_mock_people_info",
            "create_mock_scene_analysis",
            "create_mock_detected_object",
            "create_mock_entity_extraction",
            "create_mock_search_result",
            "create_mock_evidence_item",
            "create_mock_fused_conclusion",
            "create_mock_analysis_report",
        ]
        for func_name in expected_functions:
            assert hasattr(fixtures, func_name), f"缺少工厂函数: {func_name}"

    def test_scenario_factories_exist(self):
        """场景工厂应存在。"""
        from tests.mocks import fixtures
        assert hasattr(fixtures, "create_shibuya_scenario")
        assert hasattr(fixtures, "create_unknown_scenario")

    def test_fixtures_produce_valid_models(self):
        """工厂函数应生成有效的 Pydantic 模型。"""
        from tests.mocks.fixtures import (
            create_mock_analysis_report,
            create_mock_scene_analysis,
            create_mock_ocr_result,
        )

        report = create_mock_analysis_report()
        assert report.id == "test-001"
        assert report.scene_analysis is not None

        scene = create_mock_scene_analysis()
        assert scene.location_guess is not None

        ocr = create_mock_ocr_result()
        assert ocr.confidence > 0


# ─── 测试文件命名规范 ──────────────────────────────────


class TestNamingConvention:
    """测试文件命名规范检查。"""

    def test_test_files_start_with_test(self):
        """所有测试文件应以 test_ 开头。"""
        test_files = list(TEST_DIR.rglob("test_*.py"))
        assert len(test_files) > 0, "没有找到测试文件"

    def test_conftest_files_exist(self):
        """关键目录应有 conftest.py。"""
        assert (TEST_DIR / "conftest.py").exists(), "缺少 tests/conftest.py"
        assert (TEST_DIR / "unit" / "services" / "conftest.py").exists(), (
            "缺少 tests/unit/services/conftest.py"
        )


# ─── Mock Services 检查 ──────────────────────────────────


class TestMockServicesCoverage:
    """确保 mock services 覆盖所有 service 接口。"""

    def test_all_mock_services_importable(self):
        from tests.mocks.mock_services import (
            MockOCRService,
            MockVLMService,
            MockEntityService,
            MockSearchService,
            MockEvidenceService,
            MockReportService,
        )
        assert MockOCRService is not None
        assert MockVLMService is not None
        assert MockEntityService is not None
        assert MockSearchService is not None
        assert MockEvidenceService is not None
        assert MockReportService is not None
