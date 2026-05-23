"""Tests for VLM service lang parameter.

验证 VLM 服务根据 lang 参数选择不同 prompt 的能力。
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from vision_insight.models.schemas import (
    OCRResult,
)
from vision_insight.services.vlm.api_service import (
    OBJECT_DETECTION_PROMPT_EN,
    OBJECT_DETECTION_PROMPT_ZH,
    SCENE_ANALYSIS_PROMPT_EN,
    SCENE_ANALYSIS_PROMPT_ZH,
    OpenAIVLMService,
)
from vision_insight.services.vlm.zhipu_service import (
    SCENE_ANALYSIS_PROMPT_EN as ZHIPU_SCENE_EN,
)
from vision_insight.services.vlm.zhipu_service import (
    SCENE_ANALYSIS_PROMPT_ZH as ZHIPU_SCENE_ZH,
)
from vision_insight.services.vlm.zhipu_service import (
    ZhipuVLMService,
)

# ─── Prompt Content Tests ────────────────────────────────────────


class TestPromptLanguage:
    """Verify prompts contain language-specific instructions."""

    def test_zh_scene_prompt_has_chinese_instructions(self):
        assert "用中文" in SCENE_ANALYSIS_PROMPT_ZH
        assert "中文写" in SCENE_ANALYSIS_PROMPT_ZH

    def test_en_scene_prompt_has_english_instructions(self):
        assert "in English" in SCENE_ANALYSIS_PROMPT_EN
        assert "English" in SCENE_ANALYSIS_PROMPT_EN

    def test_zh_obj_prompt_is_chinese(self):
        assert "检测这张图片" in OBJECT_DETECTION_PROMPT_ZH
        assert "对象名称" in OBJECT_DETECTION_PROMPT_ZH

    def test_en_obj_prompt_is_english(self):
        assert "Detect all notable objects" in OBJECT_DETECTION_PROMPT_EN
        assert "object name" in OBJECT_DETECTION_PROMPT_EN

    def test_zh_and_en_scene_prompts_differ(self):
        assert SCENE_ANALYSIS_PROMPT_ZH != SCENE_ANALYSIS_PROMPT_EN

    def test_zh_and_en_obj_prompts_differ(self):
        assert OBJECT_DETECTION_PROMPT_ZH != OBJECT_DETECTION_PROMPT_EN

    def test_zhipu_zh_scene_prompt_is_concise(self):
        assert "分析这张图片" in ZHIPU_SCENE_ZH or "分析图片" in ZHIPU_SCENE_ZH

    def test_zhipu_en_scene_prompt_is_english(self):
        assert "analyze this image" in ZHIPU_SCENE_EN.lower()

    def test_prompts_have_json_structure(self):
        """All prompts should reference JSON output format."""
        for prompt in [
            SCENE_ANALYSIS_PROMPT_ZH,
            SCENE_ANALYSIS_PROMPT_EN,
            ZHIPU_SCENE_ZH,
            ZHIPU_SCENE_EN,
        ]:
            assert "JSON" in prompt or "json" in prompt


# ─── OCR Context Language Tests ──────────────────────────────────


class TestOCRContextLanguage:
    """Verify OCR context text changes based on lang."""

    def _make_ocr(self) -> list[OCRResult]:
        return [
            OCRResult(
                text="Hello World",
                bbox=[[0, 0], [100, 0], [100, 20], [0, 20]],
                confidence=0.95,
            )
        ]

    @pytest.mark.asyncio
    async def test_openai_zh_ocr_context(self):
        """OpenAI service should use Chinese OCR context for zh."""
        svc = OpenAIVLMService(api_key="test-key")
        ocr = self._make_ocr()

        with patch.object(svc, "_vision_chat", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = json.dumps({
                "scene_type": "unknown",
                "description": "test",
            })
            await svc.analyze(b"\x89PNG", ocr, lang="zh")

            call_args = mock_chat.call_args
            prompt = call_args[0][0]
            assert "图片中检测到的文字" in prompt

    @pytest.mark.asyncio
    async def test_openai_en_ocr_context(self):
        """OpenAI service should use English OCR context for en."""
        svc = OpenAIVLMService(api_key="test-key")
        ocr = self._make_ocr()

        with patch.object(svc, "_vision_chat", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = json.dumps({
                "scene_type": "unknown",
                "description": "test",
            })
            await svc.analyze(b"\x89PNG", ocr, lang="en")

            call_args = mock_chat.call_args
            prompt = call_args[0][0]
            assert "OCR detected these texts" in prompt

    @pytest.mark.asyncio
    async def test_zhipu_zh_ocr_context(self):
        """Zhipu service should use Chinese OCR context for zh."""
        svc = ZhipuVLMService(api_key="test-key")
        ocr = self._make_ocr()

        with patch.object(svc, "_vision_chat", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = json.dumps({
                "scene_type": "unknown",
                "description": "test",
            })
            await svc.analyze(b"\x89PNG", ocr, lang="zh")

            call_args = mock_chat.call_args
            prompt = call_args[0][0]
            assert "图片中检测到的文字" in prompt

    @pytest.mark.asyncio
    async def test_zhipu_en_ocr_context(self):
        """Zhipu service should use English OCR context for en."""
        svc = ZhipuVLMService(api_key="test-key")
        ocr = self._make_ocr()

        with patch.object(svc, "_vision_chat", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = json.dumps({
                "scene_type": "unknown",
                "description": "test",
            })
            await svc.analyze(b"\x89PNG", ocr, lang="en")

            call_args = mock_chat.call_args
            prompt = call_args[0][0]
            assert "OCR detected these texts" in prompt


# ─── Prompt Selection Tests ──────────────────────────────────────


class TestPromptSelection:
    """Verify correct prompt is selected based on lang."""

    @pytest.mark.asyncio
    async def test_openai_uses_zh_prompt_for_zh(self):
        svc = OpenAIVLMService(api_key="test-key")

        with patch.object(svc, "_vision_chat", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = json.dumps({
                "scene_type": "unknown",
                "description": "test",
            })
            await svc.analyze(b"\x89PNG", lang="zh")

            prompt = mock_chat.call_args[0][0]
            # ZH prompt has Chinese instructions
            assert "用中文" in prompt

    @pytest.mark.asyncio
    async def test_openai_uses_en_prompt_for_en(self):
        svc = OpenAIVLMService(api_key="test-key")

        with patch.object(svc, "_vision_chat", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = json.dumps({
                "scene_type": "unknown",
                "description": "test",
            })
            await svc.analyze(b"\x89PNG", lang="en")

            prompt = mock_chat.call_args[0][0]
            # EN prompt has English instructions
            assert "in English" in prompt

    @pytest.mark.asyncio
    async def test_detect_objects_lang_param(self):
        svc = OpenAIVLMService(api_key="test-key")

        with patch.object(svc, "_vision_chat", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = json.dumps([])
            await svc.detect_objects(b"\x89PNG", lang="zh")

            prompt = mock_chat.call_args[0][0]
            assert "检测这张图片" in prompt

    @pytest.mark.asyncio
    async def test_detect_objects_en_prompt(self):
        svc = OpenAIVLMService(api_key="test-key")

        with patch.object(svc, "_vision_chat", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = json.dumps([])
            await svc.detect_objects(b"\x89PNG", lang="en")

            prompt = mock_chat.call_args[0][0]
            assert "Detect all notable objects" in prompt


# ─── Default Language Tests ──────────────────────────────────────


class TestDefaultLanguage:
    """Verify default language behavior."""

    @pytest.mark.asyncio
    async def test_default_lang_is_zh(self):
        svc = OpenAIVLMService(api_key="test-key")

        with patch.object(svc, "_vision_chat", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = json.dumps({
                "scene_type": "unknown",
                "description": "test",
            })
            # No lang parameter — should default to zh
            await svc.analyze(b"\x89PNG")

            prompt = mock_chat.call_args[0][0]
            assert "用中文" in prompt


# ─── Mock Service Integration Tests ─────────────────────────────


class TestMockServiceLang:
    """Verify mock services track lang parameter."""

    @pytest.mark.asyncio
    async def test_mock_vlm_records_lang(self):
        from tests.mocks.mock_services import MockVLMService

        svc = MockVLMService()
        await svc.analyze(b"test", lang="en")
        assert svc.last_lang == "en"
        assert svc.analyze_count == 1

    @pytest.mark.asyncio
    async def test_mock_vlm_default_lang(self):
        from tests.mocks.mock_services import MockVLMService

        svc = MockVLMService()
        await svc.analyze(b"test")
        assert svc.last_lang == "zh"

    @pytest.mark.asyncio
    async def test_mock_report_records_lang(self):
        from tests.mocks.mock_services import MockReportService
        from vision_insight.models.schemas import AnalysisReport, AnalysisStatus

        svc = MockReportService()
        report = AnalysisReport(id="test", status=AnalysisStatus.COMPLETED)
        await svc.generate_user_report(report, lang="en")
        assert svc.last_lang == "en"
