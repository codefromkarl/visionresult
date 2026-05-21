"""测试质量守卫 — 元测试

对比 TravelAgent 的 quality-guard.test.ts。
定期运行，确保测试体系不会随开发产生偏移：
  1. 所有 service 源文件都有对应测试
  2. Fixtures 工厂覆盖了所有核心 schema
  3. 测试文件命名规范
"""

from __future__ import annotations

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
            create_mock_ocr_result,
            create_mock_scene_analysis,
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


# ─── E2E 测试质量检查 ──────────────────────────────────────

# E2E 测试中必须有的用户操作关键字
BEHAVIOR_ACTION_KEYWORDS = [
    "set_input_files", "click(", "fill(", "select_option",
    "dispatch_event", "type(", "press(", "check(",
]

# E2E 测试中必须有的行为断言关键字
BEHAVIOR_ASSERT_KEYWORDS = [
    "to_contain_class", "to_contain_text", "requests",
    "wait_for_request", "wait_for_selector", "wait_for_timeout",
]

# 只有结构检查的关键字（不允许单独存在）
STRUCTURE_ONLY_KEYWORDS = [
    "to_be_attached", "to_be_visible", "to_have_count",
]


class TestE2EQuality:
    """E2E 测试质量检查 — 防止空壳测试。

    核心原则：E2E 测试必须模拟用户行为，不能只检查 DOM 结构。
    """

    def _get_e2e_test_files(self) -> list[Path]:
        """获取所有 E2E 测试文件。"""
        e2e_dir = TEST_DIR / "e2e"
        if not e2e_dir.exists():
            return []
        return list(e2e_dir.glob("test_*.py"))

    def _read_test_content(self, filepath: Path) -> str:
        """读取测试文件内容。"""
        return filepath.read_text(encoding="utf-8")

    @pytest.mark.parametrize(
        "e2e_file",
        [f.name for f in (TEST_DIR / "e2e").glob("test_*.py")] if (TEST_DIR / "e2e").exists() else [],
    )
    def test_e2e_has_user_action_simulation(self, e2e_file: str):
        """E2E 测试必须有用户操作模拟。"""
        filepath = TEST_DIR / "e2e" / e2e_file
        content = self._read_test_content(filepath)

        has_action = any(kw in content for kw in BEHAVIOR_ACTION_KEYWORDS)
        assert has_action, (
            f"{e2e_file}: 缺少用户操作模拟。"
            f"必须使用 {BEHAVIOR_ACTION_KEYWORDS} 中的至少一个。"
            f"E2E 测试必须模拟真实用户行为。"
        )

    @pytest.mark.parametrize(
        "e2e_file",
        [f.name for f in (TEST_DIR / "e2e").glob("test_*.py")] if (TEST_DIR / "e2e").exists() else [],
    )
    def test_e2e_has_behavior_assertion(self, e2e_file: str):
        """E2E 测试必须有行为断言。"""
        filepath = TEST_DIR / "e2e" / e2e_file
        content = self._read_test_content(filepath)

        has_behavior = any(kw in content for kw in BEHAVIOR_ASSERT_KEYWORDS)
        assert has_behavior, (
            f"{e2e_file}: 缺少行为断言。"
            f"必须验证操作后的状态变化（{BEHAVIOR_ASSERT_KEYWORDS}）。"
            f"只检查元素存在不够。"
        )

    @pytest.mark.parametrize(
        "e2e_file",
        [f.name for f in (TEST_DIR / "e2e").glob("test_*.py")] if (TEST_DIR / "e2e").exists() else [],
    )
    def test_e2e_not_structure_only(self, e2e_file: str):
        """E2E 测试不能只有结构检查。"""
        filepath = TEST_DIR / "e2e" / e2e_file
        content = self._read_test_content(filepath)

        has_action = any(kw in content for kw in BEHAVIOR_ACTION_KEYWORDS)
        only_structure = all(kw in content for kw in ["to_be_attached", "to_be_visible"])

        if only_structure:
            assert has_action, (
                f"{e2e_file}: 只有结构检查，没有功能测试。"
                f"必须有用户操作模拟（{BEHAVIOR_ACTION_KEYWORDS}）。"
            )

    def test_e2e_directory_exists(self):
        """E2E 测试目录应存在。"""
        e2e_dir = TEST_DIR / "e2e"
        assert e2e_dir.exists(), "缺少 tests/e2e/ 目录，前端功能需要 E2E 测试"

    def test_e2e_has_test_files(self):
        """E2E 目录应有测试文件。"""
        e2e_files = self._get_e2e_test_files()
        assert len(e2e_files) > 0, "tests/e2e/ 目录为空，需要创建 E2E 测试"


class TestMockServicesCoverage:
    """确保 mock services 覆盖所有 service 接口。"""

    def test_all_mock_services_importable(self):
        from tests.mocks.mock_services import (
            MockEntityService,
            MockEvidenceService,
            MockOCRService,
            MockReportService,
            MockSearchService,
            MockVLMService,
        )
        assert MockOCRService is not None
        assert MockVLMService is not None
        assert MockEntityService is not None
        assert MockSearchService is not None
        assert MockEvidenceService is not None
        assert MockReportService is not None
