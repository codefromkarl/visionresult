"""Service registry for managing VLM, OCR, and other service providers.

This module provides a deep interface for service management:
- Single entry point: `get_services()` returns all services
- Centralized configuration handling
- Easy to test with mock factories

The Services dataclass bundles all pipeline services into one structure,
reducing the interface from 6 getters to 1 entry point.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
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


@dataclass(frozen=True)
class Services:
    """Bundle of all pipeline services.

    This is the single return type of ServiceRegistry, providing
    a deep interface: one call gets all services.
    """

    vlm: VLMService
    ocr: OCRService
    entity: EntityService
    search: SearchService
    evidence: EvidenceService

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for backward compatibility."""
        return {
            "vlm": self.vlm,
            "ocr": self.ocr,
            "entity": self.entity,
            "search": self.search,
            "evidence": self.evidence,
        }


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
        from vision_insight.services.evidence.fusion_service import FusionService, LLMPort
        from vision_insight.services.evidence.llm_ports import EmptyLLMPort, ZhipuLLMPort

        # Use Zhipu LLM if available, otherwise fallback to empty
        llm: LLMPort
        if _setting_string("zhipu_api_key"):
            llm = ZhipuLLMPort(api_key=_setting_string("zhipu_api_key"))
            logger.info("Evidence fusion: using Zhipu GLM-4-Flash for LLM reasoning")
        else:
            llm = EmptyLLMPort()
            logger.warning(
                "No LLM API key for evidence fusion, medium-confidence reasoning disabled"
            )

        return FusionService(llm=llm)


class ServiceRegistry:
    """Registry for managing service instances and their lifecycle.

    Deep interface: single entry point to get all services.
    - `get_services()` returns a Services dataclass with all service instances
    - Centralized configuration handling via ServiceFactory
    - Easy to test with mock factories
    """

    def __init__(self, factory: ServiceFactory | None = None) -> None:
        """Initialize the service registry.

        Args:
            factory: Service factory to use. If None, uses DefaultServiceFactory.
        """
        self._factory = factory or DefaultServiceFactory()
        self._services: Services | None = None

    def get_services(self) -> Services:
        """Get all service instances, initializing if needed.

        Returns:
            Services dataclass with all service instances.
        """
        if self._services is None:
            self._services = self._initialize_services()
        return self._services

    def _initialize_services(self) -> Services:
        """Initialize all services using the factory."""
        logger.info("Initializing services...")

        # Create VLM service first (needed for evidence service)
        vlm_service = self._factory.create_vlm_service()

        # Create other services
        ocr_service = self._factory.create_ocr_service()
        entity_service = self._factory.create_entity_service()
        search_service = self._factory.create_search_service()
        evidence_service = self._factory.create_evidence_service(vlm_service)

        logger.info("All services initialized successfully")

        return Services(
            vlm=vlm_service,
            ocr=ocr_service,
            entity=entity_service,
            search=search_service,
            evidence=evidence_service,
        )

    # Backward compatibility methods (deprecated)
    def get_all_services(self) -> dict[str, Any]:
        """Get all service instances as dict (deprecated, use get_services())."""
        return self.get_services().to_dict()

    def get_vlm_service(self) -> VLMService:
        """Get the VLM service instance (deprecated, use get_services().vlm)."""
        return self.get_services().vlm

    def get_ocr_service(self) -> OCRService:
        """Get the OCR service instance (deprecated, use get_services().ocr)."""
        return self.get_services().ocr

    def get_entity_service(self) -> EntityService:
        """Get the entity extraction service instance (deprecated, use get_services().entity)."""
        return self.get_services().entity

    def get_search_service(self) -> SearchService:
        """Get the search service instance (deprecated, use get_services().search)."""
        return self.get_services().search

    def get_evidence_service(self) -> EvidenceService:
        """Get the evidence fusion service instance (deprecated, use get_services().evidence)."""
        return self.get_services().evidence


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
