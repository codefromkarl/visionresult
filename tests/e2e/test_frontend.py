"""前端 E2E 测试 — Playwright

测试原则：验证用户真实行为，不只是 DOM 结构。
file:// 协议不支持 set_input_files，需要本地 HTTP 服务器。
"""

from __future__ import annotations

import http.server
import io
import json
import re
import threading
from pathlib import Path

import pytest
from PIL import Image

pytest.importorskip("playwright")
from playwright.sync_api import Page, Route, expect

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend" / "public"


def _make_test_image() -> bytes:
    """创建测试图片。"""
    img = Image.new("RGB", (100, 100), color="red")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture(scope="module")
def local_server():
    """启动本地 HTTP 服务器提供前端页面。"""

    class FrontendHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(FRONTEND_DIR), **kwargs)

    httpd = http.server.HTTPServer(("127.0.0.1", 0), FrontendHandler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    httpd.shutdown()


@pytest.fixture
def page(browser):
    """每个测试用独立页面。"""
    page = browser.new_page()
    yield page
    page.close()


@pytest.fixture
def test_image(tmp_path) -> Path:
    """创建测试图片文件。"""
    img_path = tmp_path / "test.png"
    img_path.write_bytes(_make_test_image())
    return img_path


# ─── 真正的 E2E 测试：模拟用户行为 ────────────────────────


class TestUploadFlow:
    """上传流程测试 — 模拟真实用户操作。"""

    def test_selecting_file_shows_preview(self, page: Page, test_image: Path, local_server: str):
        """选择文件后应显示预览图。"""
        page.goto(local_server)

        # 预览默认隐藏
        preview = page.locator("#previewContainer")
        expect(preview).not_to_have_class(re.compile(".*visible.*"))

        # 模拟用户选择文件
        file_input = page.locator("#fileInput")
        file_input.set_input_files(str(test_image))

        # 验证预览显示
        expect(preview).to_have_class(re.compile(".*visible.*"))
        preview_img = page.locator("#previewImg")
        expect(preview_img).to_be_visible()

    def test_upload_calls_api(self, page: Page, test_image: Path, local_server: str):
        """上传应调用 API。"""
        page.goto(local_server)

        # 拦截 API 请求
        requests = []

        def capture_request(route: Route):
            requests.append(route.request)
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"task_id": "test-123", "status": "pending", "message": "ok"}),
            )

        page.route("**/api/v1/analyze", capture_request)

        # 模拟上传
        file_input = page.locator("#fileInput")
        file_input.set_input_files(str(test_image))
        page.locator("#analyzeBtn").click()

        # 等待 API 调用
        page.wait_for_timeout(2000)

        # 验证 API 被调用
        assert len(requests) == 1, f"Expected 1 API call, got {len(requests)}"
        assert requests[0].method == "POST"

    def test_upload_shows_result_on_success(self, page: Page, test_image: Path, local_server: str):
        """上传成功后应显示分析结果。"""
        page.goto(local_server)

        # Mock API 响应
        page.route(
            "**/api/v1/analyze",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"task_id": "test-001", "status": "pending", "message": "ok"}),
            ),
        )

        # Mock 轮询响应
        page.route(
            "**/api/v1/report/test-001",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "id": "test-001",
                        "status": "completed",
                        "scene_analysis": {
                            "scene_type": "street",
                            "description": "日本商业街夜景",
                            "location_guess": {
                                "location": "东京涩谷",
                                "confidence": 0.85,
                                "evidence": ["日文招牌"],
                            },
                            "time_guess": {"time_of_day": "夜晚", "season": "冬季"},
                        },
                        "ocr_results": [{"text": "Shibuya", "confidence": 0.95, "bbox": []}],
                        "conclusions": [
                            {
                                "statement": "拍摄地点: 东京涩谷",
                                "probability": 0.85,
                                "category": "location",
                                "evidence": [],
                            }
                        ],
                        "report_markdown": "# 测试报告",
                    }
                ),
            ),
        )

        # 上传
        file_input = page.locator("#fileInput")
        file_input.set_input_files(str(test_image))
        page.locator("#analyzeBtn").click()

        # 等待结果显示
        result = page.locator("#resultContainer")
        expect(result).to_have_class(re.compile(".*visible.*"), timeout=10000)

        # 验证结果内容
        report = page.locator("#reportContent")
        expect(report).to_contain_text("# 测试报告")

    def test_upload_shows_error_on_failure(self, page: Page, test_image: Path, local_server: str):
        """API 失败时应显示错误信息。"""
        page.goto(local_server)

        # Mock API 返回错误
        page.route(
            "**/api/v1/analyze",
            lambda route: route.fulfill(
                status=500,
                content_type="application/json",
                body=json.dumps({"detail": "Internal Server Error"}),
            ),
        )

        file_input = page.locator("#fileInput")
        file_input.set_input_files(str(test_image))
        page.locator("#analyzeBtn").click()

        # 等待错误 toast 显示
        toast = page.locator("#toast-container")
        expect(toast).to_contain_text("分析失败", timeout=5000)

    def test_upload_no_file_does_nothing(self, page: Page, local_server: str):
        """不选择文件时不应调用 API。"""
        page.goto(local_server)

        api_called = []
        page.route(
            "**/api/v1/analyze",
            lambda route: (
                api_called.append(True),
                route.fulfill(status=200, content_type="application/json", body='{"task_id":"x"}'),
            ),
        )

        # 不选择文件，直接等待
        page.wait_for_timeout(1000)

        assert len(api_called) == 0, "API should not be called without file selection"


# ─── 结构测试（辅助） ────────────────────────────────────


class TestPageStructure:
    """页面结构检查。"""

    def test_page_loads(self, page: Page, local_server: str):
        page.goto(local_server)
        expect(page).to_have_title("Visual Insight Agent")

    def test_has_upload_input(self, page: Page, local_server: str):
        page.goto(local_server)
        inp = page.locator("#fileInput")
        expect(inp).to_be_attached()
        expect(inp).to_have_attribute("type", "file")
        expect(inp).to_have_attribute("accept", "image/*")

    def test_has_result_container(self, page: Page, local_server: str):
        page.goto(local_server)
        expect(page.locator("#resultContainer")).to_be_attached()

    def test_has_loading_indicator(self, page: Page, local_server: str):
        page.goto(local_server)
        expect(page.locator("#progressContainer")).to_be_attached()

    def test_features_displayed(self, page: Page, local_server: str):
        page.goto(local_server)
        formats = page.locator(".upload-zone-format")
        expect(formats).to_have_count(4)
