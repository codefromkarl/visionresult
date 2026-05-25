"""OpenAI GPT-4V and Gemini Pro Vision implementation of VLMService."""

import contextvars
import logging

from vision_insight.core.config import settings
from vision_insight.models.schemas import (
    DetectedObject,
    OCRResult,
    SceneAnalysis,
)
from vision_insight.services.vlm.base import BaseVLMService
from vision_insight.utils.chat_client import ChatCompletionClient, GeminiChatClient
from vision_insight.utils.image import detect_image_format

logger = logging.getLogger(__name__)

# Context variable for task_id. Pipeline nodes set this before calling VLM
# providers so lower-level request/retry logging can correlate events.
current_task_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_task_id", default="unknown"
)


class OpenAIVLMService(BaseVLMService):
    """VLM service using OpenAI GPT-4 Vision API via httpx."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o",
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 60.0,
    ) -> None:
        resolved_key = api_key or settings.openai_api_key
        if not resolved_key:
            raise ValueError("OpenAI API key is required (set VIA_OPENAI_API_KEY)")
        super().__init__(api_key=resolved_key, model=model, base_url=base_url, timeout=timeout)
        self._client = ChatCompletionClient(
            api_key=resolved_key,
            base_url=base_url,
            model=model,
            timeout=timeout,
        )

    async def _call_vlm(self, prompt: str, image_bytes: bytes) -> str:
        """Make an OpenAI vision chat completion request with retry."""
        return await self._client.vision_chat(prompt, image_bytes)


class GeminiVLMService(BaseVLMService):
    """VLM service using Google Gemini Pro Vision API via httpx."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gemini-2.0-flash",
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        timeout: float = 60.0,
    ) -> None:
        resolved_key = api_key or settings.gemini_api_key
        if not resolved_key:
            raise ValueError("Gemini API key is required (set VIA_GEMINI_API_KEY)")
        super().__init__(api_key=resolved_key, model=model, base_url=base_url, timeout=timeout)
        self._client = GeminiChatClient(
            api_key=resolved_key,
            base_url=base_url,
            model=model,
            timeout=timeout,
        )

    async def _call_vlm(self, prompt: str, image_bytes: bytes) -> str:
        """Make a Gemini generateContent request with retry."""
        return await self._client.vision_chat(prompt, image_bytes)
