"""LLM port adapters for evidence fusion service."""

import logging

import httpx

from vision_insight.services.evidence.fusion_service import LLMPort
from vision_insight.utils.retry import retry_with_backoff

logger = logging.getLogger(__name__)


class ZhipuLLMPort(LLMPort):
    """Use Zhipu GLM-4-Flash for text-only LLM inference."""

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._base_url = "https://open.bigmodel.cn/api/coding/paas/v4"
        self._model = "glm-4-flash"

    async def infer(self, prompt: str) -> str:
        """Send prompt to Zhipu LLM and return response."""
        try:
            payload = {
                "model": self._model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 512,
                "temperature": 0.3,
            }
            headers = {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            }

            async def _do_request():
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(
                        f"{self._base_url}/chat/completions",
                        json=payload,
                        headers=headers,
                    )
                    resp.raise_for_status()
                    return resp.json()

            body = await retry_with_backoff(_do_request)
            return body["choices"][0]["message"]["content"].strip()
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
