"""Shared HTTP client for OpenAI-compatible chat completion APIs.

This module provides a deep interface for LLM calls:
- Single class handles HTTP + retry + response extraction
- Supports both text-only and vision (image+text) requests
- Easy to use: just call `chat(prompt)` or `vision_chat(prompt, image_bytes)`
"""

import logging
from typing import Any

import httpx

from vision_insight.utils.image import encode_image_base64
from vision_insight.utils.retry import retry_with_backoff

logger = logging.getLogger(__name__)


class ChatCompletionClient:
    """Shared client for OpenAI-compatible chat completion APIs.

    This eliminates duplicated HTTP + retry + response extraction
    across VLM services, entity service, and LLM ports.

    Usage:
        client = ChatCompletionClient(
            api_key="sk-...",
            base_url="https://api.openai.com/v1",
            model="gpt-4o",
        )
        response = await client.chat("What is the capital of France?")
        response = await client.vision_chat("Describe this image", image_bytes)
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o",
        timeout: float = 60.0,
        max_tokens: int = 2048,
        temperature: float = 0.2,
        reuse_client: bool = True,
    ) -> None:
        """Initialize the chat completion client.

        Args:
            api_key: API key for authentication.
            base_url: Base URL for the API (without trailing slash).
            model: Model identifier to use.
            timeout: Request timeout in seconds.
            max_tokens: Maximum tokens in response.
            temperature: Sampling temperature.
            reuse_client: If True, reuse httpx.AsyncClient across calls.
        """
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._reuse_client = reuse_client
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create httpx.AsyncClient."""
        if self._reuse_client:
            if self._client is None or self._client.is_closed:
                self._client = httpx.AsyncClient(timeout=self._timeout)
            return self._client
        else:
            return httpx.AsyncClient(timeout=self._timeout)

    async def close(self) -> None:
        """Close the underlying httpx.AsyncClient."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def chat(
        self,
        prompt: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """Send a text-only chat completion request.

        Args:
            prompt: The text prompt to send.
            max_tokens: Override max tokens for this request.
            temperature: Override temperature for this request.

        Returns:
            The text response from the LLM.

        Raises:
            httpx.HTTPStatusError: If the API returns an error.
            ValueError: If the response cannot be parsed.
        """
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens or self._max_tokens,
            "temperature": temperature if temperature is not None else self._temperature,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        async def _do_request():
            client = await self._get_client()
            resp = await client.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json()

        body = await retry_with_backoff(_do_request)
        return body["choices"][0]["message"]["content"]

    async def vision_chat(
        self,
        prompt: str,
        image_bytes: bytes,
        image_format: str = "jpeg",
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """Send a vision chat completion request with image.

        Args:
            prompt: The text prompt to send.
            image_bytes: Raw image bytes.
            image_format: Image format (jpeg, png, etc.).
            max_tokens: Override max tokens for this request.
            temperature: Override temperature for this request.

        Returns:
            The text response from the VLM.

        Raises:
            httpx.HTTPStatusError: If the API returns an error.
            ValueError: If the response cannot be parsed.
        """
        b64_image = encode_image_base64(image_bytes)
        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/{image_format};base64,{b64_image}",
                            },
                        },
                    ],
                }
            ],
            "max_tokens": max_tokens or self._max_tokens,
            "temperature": temperature if temperature is not None else self._temperature,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        async def _do_request():
            client = await self._get_client()
            resp = await client.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json()

        body = await retry_with_backoff(_do_request)
        return body["choices"][0]["message"]["content"]


class GeminiChatClient:
    """Client for Google Gemini API (different response format).

    This handles Gemini's unique API format while providing
    the same interface as ChatCompletionClient.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        model: str = "gemini-2.0-flash",
        timeout: float = 60.0,
        max_tokens: int = 2048,
        temperature: float = 0.2,
        reuse_client: bool = True,
    ) -> None:
        """Initialize the Gemini client.

        Args:
            api_key: API key for authentication.
            base_url: Base URL for the API.
            model: Model identifier to use.
            timeout: Request timeout in seconds.
            max_tokens: Maximum tokens in response.
            temperature: Sampling temperature.
            reuse_client: If True, reuse httpx.AsyncClient across calls.
        """
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._reuse_client = reuse_client
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create httpx.AsyncClient."""
        if self._reuse_client:
            if self._client is None or self._client.is_closed:
                self._client = httpx.AsyncClient(timeout=self._timeout)
            return self._client
        else:
            return httpx.AsyncClient(timeout=self._timeout)

    async def close(self) -> None:
        """Close the underlying httpx.AsyncClient."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def vision_chat(
        self,
        prompt: str,
        image_bytes: bytes,
        image_format: str = "jpeg",
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """Send a vision request to Gemini.

        Args:
            prompt: The text prompt to send.
            image_bytes: Raw image bytes.
            image_format: Image format (jpeg, png, etc.).
            max_tokens: Override max tokens for this request.
            temperature: Override temperature for this request.

        Returns:
            The text response from Gemini.

        Raises:
            httpx.HTTPStatusError: If the API returns an error.
            ValueError: If the response cannot be parsed.
        """
        b64_image = encode_image_base64(image_bytes)
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": f"image/{image_format}",
                                "data": b64_image,
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {
                "temperature": temperature if temperature is not None else self._temperature,
                "maxOutputTokens": max_tokens or self._max_tokens,
            },
        }
        url = f"{self._base_url}/models/{self._model}:generateContent?key={self._api_key}"

        async def _do_request():
            client = await self._get_client()
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()

        body = await retry_with_backoff(_do_request)

        # Extract text from Gemini response structure
        candidates = body.get("candidates", [])
        if not candidates:
            raise ValueError("Gemini returned no candidates")
        parts = candidates[0].get("content", {}).get("parts", [])
        for part in parts:
            if "text" in part:
                return part["text"]
        raise ValueError("Gemini returned no text content")
