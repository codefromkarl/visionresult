"""Tests for Baidu OCR API service."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vision_insight.models.schemas import OCRResult
from vision_insight.services.ocr.baidu_service import BaiduOCRService

# === Fixtures ===


@pytest.fixture
def baidu_service():
    """Create BaiduOCRService with test credentials."""
    return BaiduOCRService(
        api_key="test_api_key",
        secret_key="test_secret_key",
    )


@pytest.fixture
def baidu_service_standard():
    """Create BaiduOCRService in standard (non-accurate) mode."""
    return BaiduOCRService(
        api_key="test_api_key",
        secret_key="test_secret_key",
        accurate=False,
    )


@pytest.fixture(autouse=True)
def _clear_token_cache():
    """Clear the global token cache between tests."""
    import vision_insight.services.ocr.baidu_service as baidu_mod
    original = baidu_mod._token_cache
    baidu_mod._token_cache = None
    yield
    baidu_mod._token_cache = original


def _mock_token_response():
    """Build a fake Baidu OAuth token response."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "access_token": "mock_token_123",
        "expires_in": 2592000,
    }
    return mock_resp


def _mock_ocr_response(words_result):
    """Build a fake Baidu OCR API response.

    Args:
        words_result: List of dicts with 'words', optionally 'location' and 'probability'.
    """
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "words_result": words_result,
        "words_result_num": len(words_result),
        "log_id": 1234567890,
    }
    return mock_resp


# === Initialization tests ===


class TestBaiduOCRInit:
    def test_default_init(self):
        svc = BaiduOCRService(api_key="ak", secret_key="sk")
        assert svc._api_key == "ak"
        assert svc._secret_key == "sk"
        assert svc._accurate is True
        assert svc._detect_language is True
        assert svc._detect_direction is True

    def test_standard_mode(self):
        svc = BaiduOCRService(api_key="ak", secret_key="sk", accurate=False)
        assert svc._accurate is False

    def test_factory_method(self):
        svc = BaiduOCRService.create(api_key="ak", secret_key="sk")
        assert isinstance(svc, BaiduOCRService)
        assert svc._accurate is True


# === Access token tests ===


class TestBaiduOCRToken:
    @pytest.mark.asyncio
    async def test_get_access_token_success(self, baidu_service):
        mock_resp = _mock_token_response()
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            token = await baidu_service._get_access_token()

        assert token == "mock_token_123"

    @pytest.mark.asyncio
    async def test_get_access_token_cached(self, baidu_service):
        """Second call should use cached token without HTTP request."""
        import time

        import vision_insight.services.ocr.baidu_service as baidu_mod
        baidu_mod._token_cache = ("cached_token", time.time() + 86400)

        token = await baidu_service._get_access_token()
        assert token == "cached_token"

    @pytest.mark.asyncio
    async def test_get_access_token_oauth_error(self, baidu_service):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "error": "invalid_client",
            "error_description": "unknown client id",
        }

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with pytest.raises(RuntimeError, match="Baidu OAuth failed"):
                await baidu_service._get_access_token()


# === Extract tests ===


class TestBaiduOCRExtract:
    @pytest.mark.asyncio
    async def test_extract_with_location_and_probability(self, baidu_service):
        """Normal case: full response with location and probability."""
        words = [
            {
                "words": "你好世界",
                "location": {"left": 10, "top": 20, "width": 100, "height": 30},
                "probability": {"average": 0.98, "min": 0.95, "variance": 0.01},
            },
            {
                "words": "Hello World",
                "location": {"left": 10, "top": 60, "width": 150, "height": 30},
                "probability": {"average": 0.92, "min": 0.88, "variance": 0.02},
            },
        ]
        ocr_resp = _mock_ocr_response(words)
        token_resp = _mock_token_response()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = [token_resp, ocr_resp]
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            results = await baidu_service.extract(b"fake_image_bytes")

        assert len(results) == 2
        assert isinstance(results[0], OCRResult)
        assert results[0].text == "你好世界"
        assert results[0].confidence == pytest.approx(0.98, abs=0.01)
        assert results[0].bbox == [[10, 20], [110, 20], [110, 50], [10, 50]]
        assert results[1].text == "Hello World"

    @pytest.mark.asyncio
    async def test_extract_without_location(self, baidu_service):
        """Baidu general_basic may not return location."""
        words = [
            {"words": "Text without location"},
        ]
        ocr_resp = _mock_ocr_response(words)
        token_resp = _mock_token_response()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = [token_resp, ocr_resp]
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            results = await baidu_service.extract(b"fake_image_bytes")

        assert len(results) == 1
        assert results[0].text == "Text without location"
        assert results[0].bbox == [[0, 0], [0, 0], [0, 0], [0, 0]]
        assert results[0].confidence == 0.85  # Default when no probability

    @pytest.mark.asyncio
    async def test_extract_empty_bytes(self, baidu_service):
        results = await baidu_service.extract(b"")
        assert results == []

    @pytest.mark.asyncio
    async def test_extract_image_too_large(self, baidu_service):
        """Images with base64 > 4MB should be rejected."""
        large_bytes = b"x" * (4 * 1024 * 1024 + 1)  # > 4MB raw bytes
        results = await baidu_service.extract(large_bytes)
        assert results == []

    @pytest.mark.asyncio
    async def test_extract_no_text_detected(self, baidu_service):
        ocr_resp = _mock_ocr_response([])
        token_resp = _mock_token_response()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = [token_resp, ocr_resp]
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            results = await baidu_service.extract(b"fake_image_bytes")

        assert results == []

    @pytest.mark.asyncio
    async def test_extract_api_error(self, baidu_service):
        """Baidu API returns error_code in response."""
        error_resp = MagicMock()
        error_resp.status_code = 200
        error_resp.raise_for_status = MagicMock()
        error_resp.json.return_value = {
            "error_code": "110",
            "error_msg": "Access token invalid",
        }
        token_resp = _mock_token_response()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = [token_resp, error_resp]
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            results = await baidu_service.extract(b"fake_image_bytes")

        assert results == []

    @pytest.mark.asyncio
    async def test_extract_http_error(self, baidu_service):
        """HTTP-level error (e.g. 500)."""
        import httpx

        token_resp = _mock_token_response()
        error_resp = MagicMock()
        error_resp.status_code = 500
        error_resp.text = "Internal Server Error"
        error_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500", request=MagicMock(), response=error_resp
        )

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = [token_resp, error_resp]
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            results = await baidu_service.extract(b"fake_image_bytes")

        assert results == []

    @pytest.mark.asyncio
    async def test_extract_uses_accurate_endpoint(self, baidu_service):
        """Accurate mode should use accurate_basic URL."""
        token_resp = _mock_token_response()
        ocr_resp = _mock_ocr_response([{"words": "test"}])

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = [token_resp, ocr_resp]
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await baidu_service.extract(b"fake_image_bytes")

            # Second call is OCR, check URL
            ocr_call = mock_client.post.call_args_list[1]
            called_url = ocr_call[0][0] if ocr_call[0] else ocr_call[1].get("url", "")
            assert "accurate_basic" in called_url

    @pytest.mark.asyncio
    async def test_extract_uses_standard_endpoint(self, baidu_service_standard):
        """Standard mode should use general_basic URL."""
        token_resp = _mock_token_response()
        ocr_resp = _mock_ocr_response([{"words": "test"}])

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = [token_resp, ocr_resp]
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await baidu_service_standard.extract(b"fake_image_bytes")

            ocr_call = mock_client.post.call_args_list[1]
            called_url = ocr_call[0][0] if ocr_call[0] else ocr_call[1].get("url", "")
            assert "general_basic" in called_url

    @pytest.mark.asyncio
    async def test_extract_skips_empty_words(self, baidu_service):
        """Empty/whitespace words should be filtered out."""
        words = [
            {"words": "valid text"},
            {"words": "   "},
            {"words": ""},
        ]
        ocr_resp = _mock_ocr_response(words)
        token_resp = _mock_token_response()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = [token_resp, ocr_resp]
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            results = await baidu_service.extract(b"fake_image_bytes")

        assert len(results) == 1
        assert results[0].text == "valid text"

    @pytest.mark.asyncio
    async def test_extract_token_cached_reused(self, baidu_service):
        """Second extract call should reuse cached token (only 1 HTTP post for token)."""
        import time

        import vision_insight.services.ocr.baidu_service as baidu_mod
        baidu_mod._token_cache = ("cached_token", time.time() + 86400)

        ocr_resp = _mock_ocr_response([{"words": "test"}])

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = ocr_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            results = await baidu_service.extract(b"fake_image_bytes")

        # Only 1 post call (OCR), no token request
        assert mock_client.post.call_count == 1
        assert len(results) == 1
