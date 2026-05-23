"""Baidu OCR API service implementation.

Uses Baidu Cloud OCR API (通用文字识别) for text extraction.
Supports PNG, JPG, JPEG, BMP, TIFF, PNM, WebP formats.
Image base64 encoded size must be ≤ 4MB, min edge ≥ 15px, max edge ≤ 4096px.

API docs: https://cloud.baidu.com/doc/OCR/s/1k3h7y3db
"""

from __future__ import annotations

import logging
import time
from urllib.parse import urlencode

import httpx

from vision_insight.models.schemas import OCRResult
from vision_insight.services import OCRService
from vision_insight.utils.image import encode_image_base64

logger = logging.getLogger(__name__)

# Baidu OAuth2 token endpoint
_TOKEN_URL = "https://aip.baidubce.com/oauth/2.0/token"

# Baidu OCR endpoints
_OCR_GENERAL_URL = "https://aip.baidubce.com/rest/2.0/ocr/v1/general_basic"
_OCR_ACCURATE_URL = "https://aip.baidubce.com/rest/2.0/ocr/v1/accurate_basic"

# Access token cache: (token, expires_at)
_token_cache: tuple[str, float] | None = None


class BaiduOCRService(OCRService):
    """OCR service using Baidu Cloud OCR API.

    Features:
        - Auto-manages access_token (cached for 29 days, refreshed automatically)
        - Supports both standard and high-accuracy OCR modes
        - Image base64 encoding and URL encoding handled internally
        - Compatible with existing OCRService interface

    Args:
        api_key: Baidu Cloud API Key (AK).
        secret_key: Baidu Cloud Secret Key (SK).
        accurate: If True, use high-accuracy mode (accurate_basic).
                  If False, use standard mode (general_basic).
        detect_language: Whether to detect text language automatically.
        detect_direction: Whether to detect text orientation.
    """

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        accurate: bool = True,
        detect_language: bool = True,
        detect_direction: bool = True,
    ) -> None:
        self._api_key = api_key
        self._secret_key = secret_key
        self._accurate = accurate
        self._detect_language = detect_language
        self._detect_direction = detect_direction
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0

    # ------------------------------------------------------------------
    # Access token management
    # ------------------------------------------------------------------

    async def _get_access_token(self) -> str:
        """Get a valid access_token, refreshing if expired.

        Baidu access_token is valid for 30 days. We refresh at 29 days
        to avoid edge cases.
        """
        global _token_cache

        # Check in-memory cache first
        if _token_cache:
            token, expires_at = _token_cache
            if time.time() < expires_at:
                return token

        logger.info("Requesting new Baidu OCR access_token...")
        params = {
            "grant_type": "client_credentials",
            "client_id": self._api_key,
            "client_secret": self._secret_key,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(_TOKEN_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        if "error" in data:
            raise RuntimeError(
                f"Baidu OAuth failed: {data.get('error_description', data['error'])}"
            )

        token = data["access_token"]
        expires_in = data.get("expires_in", 2592000)  # Default 30 days in seconds
        # Refresh 1 day early
        expires_at = time.time() + expires_in - 86400

        # Cache globally
        _token_cache = (token, expires_at)
        self._access_token = token
        self._token_expires_at = expires_at

        logger.info("Baidu OCR access_token obtained, expires in %.0f days", expires_in / 86400)
        return token

    # ------------------------------------------------------------------
    # OCR interface
    # ------------------------------------------------------------------

    async def extract(self, image_bytes: bytes) -> list[OCRResult]:
        """Extract text from image bytes using Baidu OCR API.

        Args:
            image_bytes: Raw image file bytes (PNG, JPG, BMP, etc.).
                        Base64 encoded size must be ≤ 4MB.

        Returns:
            List of OCRResult with detected text, bbox, and confidence.
            Returns empty list if no text detected or image is invalid.
        """
        if not image_bytes:
            logger.warning("Empty image bytes provided")
            return []

        # Validate image size (base64 encoding adds ~33% overhead)
        b64_size = len(image_bytes) * 4 / 3
        if b64_size > 4 * 1024 * 1024:
            logger.warning(
                "Image too large for Baidu OCR: %.1fMB base64 (limit 4MB)",
                b64_size / (1024 * 1024),
            )
            return []

        try:
            access_token = await self._get_access_token()

            # Base64 encode (without data URI header)
            image_b64 = encode_image_base64(image_bytes)

            # Build request body
            body = {"image": image_b64}
            if self._detect_language:
                body["detect_language"] = "true"
            if self._detect_direction:
                body["detect_direction"] = "true"

            # Choose endpoint
            url = _OCR_ACCURATE_URL if self._accurate else _OCR_GENERAL_URL
            full_url = f"{url}?access_token={access_token}"

            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    full_url,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    content=urlencode(body),
                )
                resp.raise_for_status()
                data = resp.json()

            # Check for API errors
            if "error_code" in data:
                logger.error(
                    "Baidu OCR API error: [%s] %s",
                    data.get("error_code"),
                    data.get("error_msg", ""),
                )
                return []

            return self._parse_results(data)

        except httpx.HTTPStatusError as e:
            logger.error(
                "Baidu OCR HTTP error: %s %s",
                e.response.status_code,
                e.response.text[:200],
            )
            return []
        except Exception:
            logger.exception("Baidu OCR request failed")
            return []

    # ------------------------------------------------------------------
    # Result parsing
    # ------------------------------------------------------------------

    def _parse_results(self, data: dict) -> list[OCRResult]:
        """Parse Baidu OCR API response into OCRResult list.

        Baidu response format:
        {
            "words_result": [
                {
                    "words": "detected text",
                    "location": {"left": 0, "top": 0, "width": 100, "height": 20},
                    "probability": {"average": 0.95, "min": 0.9, "variance": 0.01}
                },
                ...
            ],
            "words_result_num": 5,
            "log_id": 1234567890
        }

        Note: For general_basic endpoint, location and probability may not be present.
        """
        words_result = data.get("words_result", [])
        if not words_result:
            logger.info("Baidu OCR: no text detected")
            return []

        results: list[OCRResult] = []
        for item in words_result:
            text = item.get("words", "").strip()
            if not text:
                continue

            # Extract bounding box if available
            location = item.get("location")
            if location:
                x = location.get("left", 0)
                y = location.get("top", 0)
                w = location.get("width", 0)
                h = location.get("height", 0)
                bbox = [
                    [x, y],
                    [x + w, y],
                    [x + w, y + h],
                    [x, y + h],
                ]
            else:
                # No bounding box from API, use placeholder
                bbox = [[0, 0], [0, 0], [0, 0], [0, 0]]

            # Extract confidence if available
            prob = item.get("probability")
            if prob:
                confidence = round(prob.get("average", 0.0), 4)
            else:
                # Baidu doesn't always return confidence, estimate based on result
                confidence = 0.85  # Default moderate confidence

            results.append(
                OCRResult(
                    text=text,
                    bbox=bbox,
                    confidence=confidence,
                )
            )

        logger.info("Baidu OCR done: %d text regions found", len(results))
        return results

    @classmethod
    def create(
        cls,
        api_key: str,
        secret_key: str,
        accurate: bool = True,
    ) -> BaiduOCRService:
        """Factory method to create BaiduOCRService.

        Args:
            api_key: Baidu Cloud API Key.
            secret_key: Baidu Cloud Secret Key.
            accurate: Use high-accuracy mode.

        Returns:
            Configured BaiduOCRService instance.
        """
        return cls(
            api_key=api_key,
            secret_key=secret_key,
            accurate=accurate,
        )
