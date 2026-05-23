"""Service registry for managing VLM, OCR, and other service providers.

This module provides a centralized way to discover and initialize services
based on configuration, reducing the complexity of PipelineRunner.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from vision_insight.core.config import settings
from vision_insight.services import (
    EntityService,
    EvidenceService,
    OCRService,
    SearchService,
    VLMService,
)

logger = logging.getLogger(__name__)


def _setting_string(name: str, default: str = "") -> str:
    """Return a real string setting, ignoring MagicMock/unset test attributes."""
    value = getattr(settings, name, default)
    return value.strip() if isinstance(value, str) else default


def _setting_bool(name: str, default: bool = False) -> bool:
    """Return a real boolean setting, ignoring MagicMock/unset test attributes."""
    value = getattr(settings, name, default)
    return value if isinstance(value, bool) else default


class ServiceFactory(ABC):
    """Abstract factory for creating service instances."""

    @abstractmethod
    def create_vlm_service(self) -> VLMService:
        """Create a VLM service instance."""
        ...

    @abstractmethod
    def create_ocr_service(self) -> OCRService:
        """Create an OCR service instance."""
        ...

    @abstractmethod
    def create_entity_service(self) -> EntityService:
        """Create an entity extraction service instance."""
        ...

    @abstractmethod
    def create_search_service(self) -> SearchService:
        """Create a search service instance."""
        ...

    @abstractmethod
    def create_evidence_service(self, vlm_service: VLMService) -> EvidenceService:
        """Create an evidence fusion service instance."""
        ...


class DefaultServiceFactory(ServiceFactory):
    """Default service factory using configuration settings."""

    def create_vlm_service(self) -> VLMService:
        """Create VLM service based on configuration with provider fallback."""
        from vision_insight.services.fallback import CompositeVLMService, DegradedVLMService

        provider = _setting_string("vlm_provider", "auto").lower()
        preferred = provider if provider in {"zhipu", "openai", "gemini"} else "auto"

        provider_order = ["zhipu", "openai", "gemini"]
        if preferred != "auto":
            provider_order = [preferred, *[name for name in provider_order if name != preferred]]

        services: list[tuple[str, VLMService]] = []
        for name in provider_order:
            try:
                service = self._create_single_vlm_service(name)
            except ValueError as exc:
                logger.info("VLM provider '%s' unavailable: %s", name, exc)
                continue
            services.append((name, service))
            logger.info("VLM: configured provider '%s'", name)

        if not services:
            logger.warning(
                "No VLM API key configured; using degraded VLM service. "
                "Set VIA_ZHIPU_API_KEY, VIA_OPENAI_API_KEY or VIA_GEMINI_API_KEY for full analysis."
            )
            return DegradedVLMService()

        if len(services) == 1:
            return services[0][1]
        return CompositeVLMService(services)

    def _create_single_vlm_service(self, provider: str) -> VLMService:
        """Create one VLM provider or raise ValueError when its key is missing."""
        if provider == "openai":
            if not _setting_string("openai_api_key"):
                raise ValueError("VIA_OPENAI_API_KEY is not configured")
            from vision_insight.services.vlm.api_service import OpenAIVLMService

            return OpenAIVLMService(api_key=_setting_string("openai_api_key"))
        if provider == "gemini":
            if not _setting_string("gemini_api_key"):
                raise ValueError("VIA_GEMINI_API_KEY is not configured")
            from vision_insight.services.vlm.api_service import GeminiVLMService

            return GeminiVLMService(api_key=_setting_string("gemini_api_key"))
        if provider == "zhipu":
            if not _setting_string("zhipu_api_key"):
                raise ValueError("VIA_ZHIPU_API_KEY is not configured")
            from vision_insight.services.vlm.zhipu_service import ZhipuVLMService

            return ZhipuVLMService(api_key=_setting_string("zhipu_api_key"))
        raise ValueError(f"Unsupported VLM provider: {provider}")

    def create_ocr_service(self) -> OCRService:
        """Create OCR service based on configuration with local fallback."""
        from vision_insight.services.fallback import CompositeOCRService

        provider = _setting_string("ocr_provider", "auto").lower()
        preferred = provider if provider in {"baidu", "tesseract", "paddle"} else "auto"
        provider_order = ["baidu", "tesseract", "paddle"]
        if preferred != "auto":
            provider_order = [preferred, *[name for name in provider_order if name != preferred]]

        services: list[tuple[str, OCRService]] = []
        for name in provider_order:
            try:
                service = self._create_single_ocr_service(name)
            except ValueError as exc:
                logger.info("OCR provider '%s' unavailable: %s", name, exc)
                continue
            services.append((name, service))
            logger.info("OCR: configured provider '%s'", name)

        if not services:
            logger.warning("No OCR providers could be configured; OCR will return empty results")
            return CompositeOCRService([])
        if len(services) == 1:
            return services[0][1]
        return CompositeOCRService(services)

    def _create_single_ocr_service(self, provider: str) -> OCRService:
        """Create one OCR provider or raise ValueError when configuration is missing."""
        if provider == "baidu":
            api_key = _setting_string("baidu_ocr_api_key")
            secret_key = _setting_string("baidu_ocr_secret_key")
            if not api_key or not secret_key:
                raise ValueError("VIA_BAIDU_OCR_API_KEY and VIA_BAIDU_OCR_SECRET_KEY are required")
            from vision_insight.services.ocr.baidu_service import BaiduOCRService

            return BaiduOCRService(
                api_key=api_key,
                secret_key=secret_key,
                accurate=_setting_bool("baidu_ocr_accurate", True),
            )
        if provider == "paddle":
            from vision_insight.services.ocr.paddle_service import PaddleOCRService

            return PaddleOCRService(lang=_setting_string("ocr_lang", "ch"))
        if provider == "tesseract":
            from vision_insight.services.ocr.tesseract_service import TesseractOCRService

            return TesseractOCRService(lang=_setting_string("ocr_lang", "ch"))
        raise ValueError(f"Unsupported OCR provider: {provider}")

    def create_entity_service(self) -> EntityService:
        """Create entity extraction service with rule-based fallback."""
        from vision_insight.services.entity.llm_entity_service import LLMEntityService
        from vision_insight.services.fallback import RuleBasedEntityService

        zhipu_key = _setting_string("zhipu_api_key")
        openai_key = _setting_string("openai_api_key")
        gemini_key = _setting_string("gemini_api_key")

        if zhipu_key:
            return LLMEntityService(
                api_key=zhipu_key,
                model="glm-4-flash",
                base_url="https://open.bigmodel.cn/api/coding/paas/v4",
            )
        if openai_key:
            return LLMEntityService(api_key=openai_key)
        if gemini_key:
            return LLMEntityService(
                api_key=gemini_key,
                model="gemini-2.0-flash",
                base_url="https://generativelanguage.googleapis.com/v1beta/openai",
            )

        logger.warning("No LLM API key for entity extraction; using rule-based fallback")
        return RuleBasedEntityService()

    def create_search_service(self) -> SearchService:
        """Create search service based on configuration."""
        from vision_insight.services.search.http_search_service import HttpSearchService
        return HttpSearchService()

    def create_evidence_service(self, vlm_service: VLMService) -> EvidenceService:
        """Create evidence fusion service with LLM port adapter."""
        import httpx

        from vision_insight.services.evidence.fusion_service import FusionService, LLMPort

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
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        resp = await client.post(
                            f"{self._base_url}/chat/completions",
                            json=payload,
                            headers=headers,
                        )
                        resp.raise_for_status()
                        body = resp.json()
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

        # Use Zhipu LLM if available, otherwise fallback to empty
        if _setting_string("zhipu_api_key"):
            llm = ZhipuLLMPort(api_key=_setting_string("zhipu_api_key"))
            logger.info("Evidence fusion: using Zhipu GLM-4-Flash for LLM reasoning")
        else:
            # Fallback: empty LLM (will skip medium-confidence reasoning)
            class EmptyLLMPort(LLMPort):
                async def infer(self, prompt: str) -> str:
                    return ""
                async def infer_with_reasoning(self, prompt: str) -> tuple[str, str]:
                    return "", ""
            llm = EmptyLLMPort()
            logger.warning(
                "No LLM API key for evidence fusion, medium-confidence reasoning disabled"
            )

        return FusionService(llm=llm)


class ServiceRegistry:
    """Registry for managing service instances and their lifecycle.

    This module provides a deep interface for service management:
    - Simple method to get all services
    - Centralized configuration handling
    - Easy to test with mock factories
    """

    def __init__(self, factory: ServiceFactory | None = None) -> None:
        """Initialize the service registry.

        Args:
            factory: Service factory to use. If None, uses DefaultServiceFactory.
        """
        self._factory = factory or DefaultServiceFactory()
        self._services: dict[str, Any] = {}
        self._initialized = False

    def get_all_services(self) -> dict[str, Any]:
        """Get all service instances, initializing if needed.

        Returns:
            Dictionary with service names as keys and service instances as values.
        """
        if not self._initialized:
            self._initialize_services()
        return self._services.copy()

    def get_vlm_service(self) -> VLMService:
        """Get the VLM service instance."""
        if not self._initialized:
            self._initialize_services()
        return self._services["vlm"]

    def get_ocr_service(self) -> OCRService:
        """Get the OCR service instance."""
        if not self._initialized:
            self._initialize_services()
        return self._services["ocr"]

    def get_entity_service(self) -> EntityService:
        """Get the entity extraction service instance."""
        if not self._initialized:
            self._initialize_services()
        return self._services["entity"]

    def get_search_service(self) -> SearchService:
        """Get the search service instance."""
        if not self._initialized:
            self._initialize_services()
        return self._services["search"]

    def get_evidence_service(self) -> EvidenceService:
        """Get the evidence fusion service instance."""
        if not self._initialized:
            self._initialize_services()
        return self._services["evidence"]

    def _initialize_services(self) -> None:
        """Initialize all services using the factory."""
        logger.info("Initializing services...")

        # Create VLM service first (needed for evidence service)
        vlm_service = self._factory.create_vlm_service()
        self._services["vlm"] = vlm_service

        # Create other services
        self._services["ocr"] = self._factory.create_ocr_service()
        self._services["entity"] = self._factory.create_entity_service()
        self._services["search"] = self._factory.create_search_service()
        self._services["evidence"] = self._factory.create_evidence_service(vlm_service)

        self._initialized = True
        logger.info("All services initialized successfully")


# Singleton registry
_registry: ServiceRegistry | None = None


def get_service_registry(factory: ServiceFactory | None = None) -> ServiceRegistry:
    """Get or create the singleton ServiceRegistry.

    Args:
        factory: Optional service factory to use. Only used on first call.

    Returns:
        The singleton ServiceRegistry instance.
    """
    global _registry
    if _registry is None:
        _registry = ServiceRegistry(factory)
    return _registry


def reset_service_registry() -> None:
    """Reset the singleton registry (for testing)."""
    global _registry
    _registry = None
