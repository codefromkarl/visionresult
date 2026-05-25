"""Zhipu GLM-4V implementation of VLMService."""

import logging

from vision_insight.core.config import settings
from vision_insight.services.vlm.base import BaseVLMService
from vision_insight.utils.chat_client import ChatCompletionClient
from vision_insight.utils.image import detect_image_format

logger = logging.getLogger(__name__)


class ZhipuVLMService(BaseVLMService):
    """VLM service using Zhipu GLM-4V API."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "glm-4v-flash",
        base_url: str = "https://open.bigmodel.cn/api/coding/paas/v4",
        timeout: float = 60.0,
    ) -> None:
        resolved_key = api_key or settings.zhipu_api_key
        if not resolved_key:
            raise ValueError("Zhipu API key is required (set VIA_ZHIPU_API_KEY)")
        super().__init__(api_key=resolved_key, model=model, base_url=base_url, timeout=timeout)
        self._client = ChatCompletionClient(
            api_key=resolved_key,
            base_url=base_url,
            model=model,
            timeout=timeout,
            max_tokens=1024,
        )

    async def _call_vlm(self, prompt: str, image_bytes: bytes) -> str:
        """Make a Zhipu vision chat completion request with retry."""
        image_format = detect_image_format(image_bytes)
        return await self._client.vision_chat(prompt, image_bytes, image_format=image_format)
