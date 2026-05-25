"""LLM port adapters for evidence fusion service."""

import logging

from vision_insight.services.evidence.fusion_service import LLMPort
from vision_insight.utils.chat_client import ChatCompletionClient

logger = logging.getLogger(__name__)


class ZhipuLLMPort(LLMPort):
    """Use Zhipu GLM-4-Flash for text-only LLM inference."""

    def __init__(self, api_key: str):
        self._client = ChatCompletionClient(
            api_key=api_key,
            base_url="https://open.bigmodel.cn/api/coding/paas/v4",
            model="glm-4-flash",
            timeout=30.0,
            max_tokens=512,
            temperature=0.3,
        )

    async def infer(self, prompt: str) -> str:
        """Send prompt to Zhipu LLM and return response."""
        try:
            return await self._client.chat(prompt)
        except Exception as e:
            logger.warning("LLM inference failed: %s", e)
            return ""

    async def infer_with_reasoning(self, prompt: str) -> tuple[str, str]:
        """Return (response, reasoning_trace)."""
        # Add reasoning instruction to prompt
        reasoning_prompt = (
            prompt
            + "\n\n请先用一句话回答结论，然后另起一行以'推理过程:'开头，"
            + "详细说明你的推理步骤。"
        )
        response = await self.infer(reasoning_prompt)

        # Split response into answer and reasoning
        if "推理过程:" in response:
            parts = response.split("推理过程:", 1)
            return parts[0].strip(), parts[1].strip()
        return response, ""


class EmptyLLMPort(LLMPort):
    """Fallback LLM port that returns empty responses."""

    async def infer(self, prompt: str) -> str:
        """Return empty string."""
        return ""

    async def infer_with_reasoning(self, prompt: str) -> tuple[str, str]:
        """Return empty response and reasoning."""
        return "", ""
