"""Tests for vision_insight.utils.json_helpers."""

from __future__ import annotations

import json

import pytest

from vision_insight.utils.json_helpers import parse_llm_json


class TestParseLlmJson:
    """parse_llm_json 应能处理多种 LLM 输出格式。"""

    def test_plain_json(self):
        data = parse_llm_json('{"key": "value", "num": 42}')
        assert data == {"key": "value", "num": 42}

    def test_json_with_whitespace(self):
        data = parse_llm_json('  {"key": "value"}  \n')
        assert data == {"key": "value"}

    def test_json_with_markdown_fence(self):
        text = '```json\n{"key": "value"}\n```'
        data = parse_llm_json(text)
        assert data == {"key": "value"}

    def test_json_with_bare_fence(self):
        text = '```\n{"key": "value"}\n```'
        data = parse_llm_json(text)
        assert data == {"key": "value"}

    def test_invalid_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            parse_llm_json("not valid json")

    def test_nested_json(self):
        payload = '{"outer": {"inner": [1, 2, 3]}}'
        data = parse_llm_json(payload)
        assert data == {"outer": {"inner": [1, 2, 3]}}

    def test_json_array(self):
        data = parse_llm_json("[1, 2, 3]")
        assert data == [1, 2, 3]
