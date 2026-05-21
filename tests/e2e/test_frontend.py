"""前端 E2E 测试 — Playwright

对比 TravelAgent 的 web/__tests__/interaction.spec.ts。
测试前端页面结构、交互、上传功能。
"""

from __future__ import annotations

import pytest

# Skip if playwright not installed
pytest.importorskip("playwright")

from playwright.sync_api import sync_playwright, expect


@pytest.fixture(scope="module")
def browser():
    """Launch browser for all tests."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture
def page(browser):
    """Create a new page for each test."""
    page = browser.new_page()
    yield page
    page.close()


# ─── 页面结构测试 ──────────────────────────────────────────


class TestPageStructure:
    """页面基础结构检查。"""

    def test_page_loads(self, page):
        """页面应正常加载。"""
        page.goto("file:///home/yuanzhi/Develop/ai-research/visionresult/frontend/public/index.html")
        expect(page).to_have_title("Visual Insight Agent")

    def test_has_heading(self, page):
        """应有标题。"""
        page.goto("file:///home/yuanzhi/Develop/ai-research/visionresult/frontend/public/index.html")
        heading = page.locator("h1")
        expect(heading).to_contain_text("Visual Insight")

    def test_has_upload_zone(self, page):
        """应有上传区域。"""
        page.goto("file:///home/yuanzhi/Develop/ai-research/visionresult/frontend/public/index.html")
        upload = page.locator("#uploadZone")
        expect(upload).to_be_visible()

    def test_has_features(self, page):
        """应有功能卡片。"""
        page.goto("file:///home/yuanzhi/Develop/ai-research/visionresult/frontend/public/index.html")
        features = page.locator(".feature")
        expect(features).to_have_count(3)

    def test_has_file_input(self, page):
        """上传区域应有隐藏的 file input。"""
        page.goto("file:///home/yuanzhi/Develop/ai-research/visionresult/frontend/public/index.html")
        file_input = page.locator("#fileInput")
        expect(file_input).to_be_attached()


# ─── 交互测试 ──────────────────────────────────────────────


class TestUploadInteraction:
    """上传交互测试。"""

    def test_file_input_accepts_images(self, page):
        """file input 应只接受图片。"""
        page.goto("file:///home/yuanzhi/Develop/ai-research/visionresult/frontend/public/index.html")
        file_input = page.locator("#fileInput")
        expect(file_input).to_have_attribute("accept", "image/*")

    def test_upload_zone_has_cursor_pointer(self, page):
        """上传区域应有 pointer cursor。"""
        page.goto("file:///home/yuanzhi/Develop/ai-research/visionresult/frontend/public/index.html")
        upload = page.locator("#uploadZone")
        expect(upload).to_have_css("cursor", "pointer")

    def test_upload_zone_has_file_input_overlay(self, page):
        """file input 应覆盖整个上传区域。"""
        page.goto("file:///home/yuanzhi/Develop/ai-research/visionresult/frontend/public/index.html")
        file_input = page.locator("#fileInput")
        # File input should be positioned absolute to cover the zone
        expect(file_input).to_have_css("position", "absolute")


# ─── API 文档链接测试 ──────────────────────────────────────


class TestAPILinks:
    """API 文档链接测试。"""

    def test_has_swagger_link(self, page):
        """应有 Swagger UI 链接。"""
        page.goto("file:///home/yuanzhi/Develop/ai-research/visionresult/frontend/public/index.html")
        link = page.locator('a[href="/docs"]')
        expect(link).to_be_visible()

    def test_has_health_link(self, page):
        """应有 Health Check 链接。"""
        page.goto("file:///home/yuanzhi/Develop/ai-research/visionresult/frontend/public/index.html")
        link = page.locator('a[href="/health"]')
        expect(link).to_be_visible()
