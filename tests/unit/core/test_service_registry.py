"""Tests for the ServiceRegistry module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from vision_insight.core.service_registry import (
    DefaultServiceFactory,
    ServiceFactory,
    ServiceRegistry,
    get_service_registry,
    reset_service_registry,
)
from vision_insight.services import (
    EntityService,
    EvidenceService,
    OCRService,
    SearchService,
    VLMService,
)


class TestServiceRegistry:
    """Test ServiceRegistry class."""

    def test_init_with_custom_factory(self):
        """Should use custom factory when provided."""
        mock_factory = MagicMock(spec=ServiceFactory)
        registry = ServiceRegistry(factory=mock_factory)
        assert registry._factory is mock_factory
        assert not registry._initialized

    def test_init_with_default_factory(self):
        """Should use DefaultServiceFactory when none provided."""
        registry = ServiceRegistry()
        assert isinstance(registry._factory, DefaultServiceFactory)

    def test_get_all_services_initializes_once(self):
        """Should initialize services only once."""
        mock_factory = MagicMock(spec=ServiceFactory)
        mock_factory.create_vlm_service.return_value = MagicMock(spec=VLMService)
        mock_factory.create_ocr_service.return_value = MagicMock(spec=OCRService)
        mock_factory.create_entity_service.return_value = MagicMock(spec=EntityService)
        mock_factory.create_search_service.return_value = MagicMock(spec=SearchService)
        mock_factory.create_evidence_service.return_value = MagicMock(spec=EvidenceService)

        registry = ServiceRegistry(factory=mock_factory)

        # First call should initialize
        services1 = registry.get_all_services()
        assert registry._initialized

        # Second call should not reinitialize
        services2 = registry.get_all_services()
        assert services1 == services2

        # Factory methods should only be called once
        mock_factory.create_vlm_service.assert_called_once()
        mock_factory.create_ocr_service.assert_called_once()
        mock_factory.create_entity_service.assert_called_once()
        mock_factory.create_search_service.assert_called_once()
        mock_factory.create_evidence_service.assert_called_once()

    def test_get_all_services_returns_copy(self):
        """Should return a copy of services dictionary."""
        mock_factory = MagicMock(spec=ServiceFactory)
        mock_factory.create_vlm_service.return_value = MagicMock(spec=VLMService)
        mock_factory.create_ocr_service.return_value = MagicMock(spec=OCRService)
        mock_factory.create_entity_service.return_value = MagicMock(spec=EntityService)
        mock_factory.create_search_service.return_value = MagicMock(spec=SearchService)
        mock_factory.create_evidence_service.return_value = MagicMock(spec=EvidenceService)

        registry = ServiceRegistry(factory=mock_factory)

        services1 = registry.get_all_services()
        services2 = registry.get_all_services()

        # Should be equal but not the same object
        assert services1 == services2
        assert services1 is not services2

    def test_get_individual_services(self):
        """Should return individual service instances."""
        mock_factory = MagicMock(spec=ServiceFactory)
        mock_vlm = MagicMock(spec=VLMService)
        mock_ocr = MagicMock(spec=OCRService)
        mock_entity = MagicMock(spec=EntityService)
        mock_search = MagicMock(spec=SearchService)
        mock_evidence = MagicMock(spec=EvidenceService)

        mock_factory.create_vlm_service.return_value = mock_vlm
        mock_factory.create_ocr_service.return_value = mock_ocr
        mock_factory.create_entity_service.return_value = mock_entity
        mock_factory.create_search_service.return_value = mock_search
        mock_factory.create_evidence_service.return_value = mock_evidence

        registry = ServiceRegistry(factory=mock_factory)

        assert registry.get_vlm_service() is mock_vlm
        assert registry.get_ocr_service() is mock_ocr
        assert registry.get_entity_service() is mock_entity
        assert registry.get_search_service() is mock_search
        assert registry.get_evidence_service() is mock_evidence

    def test_get_individual_services_initializes_if_needed(self):
        """Should initialize services when getting individual service."""
        mock_factory = MagicMock(spec=ServiceFactory)
        mock_factory.create_vlm_service.return_value = MagicMock(spec=VLMService)
        mock_factory.create_ocr_service.return_value = MagicMock(spec=OCRService)
        mock_factory.create_entity_service.return_value = MagicMock(spec=EntityService)
        mock_factory.create_search_service.return_value = MagicMock(spec=SearchService)
        mock_factory.create_evidence_service.return_value = MagicMock(spec=EvidenceService)

        registry = ServiceRegistry(factory=mock_factory)

        # Should initialize when getting individual service
        vlm = registry.get_vlm_service()
        assert vlm is not None
        assert registry._initialized


class TestDefaultServiceFactory:
    """Test DefaultServiceFactory class."""

    @patch("vision_insight.core.service_registry.settings")
    def test_create_ocr_service(self, mock_settings):
        """Should create Tesseract OCR service."""
        mock_settings.ocr_lang = "ch"

        factory = DefaultServiceFactory()
        service = factory.create_ocr_service()

        assert service is not None
        assert isinstance(service, OCRService)

    @patch("vision_insight.core.service_registry.settings")
    def test_create_search_service(self, mock_settings):
        """Should create HTTP search service."""
        factory = DefaultServiceFactory()
        service = factory.create_search_service()

        assert service is not None
        assert isinstance(service, SearchService)

    @patch("vision_insight.core.service_registry.settings")
    def test_create_vlm_service_openai(self, mock_settings):
        """Should create OpenAI VLM service when configured."""
        mock_settings.vlm_provider = "openai"
        mock_settings.openai_api_key = "test-key"

        factory = DefaultServiceFactory()

        with patch("vision_insight.services.vlm.api_service.OpenAIVLMService") as mock_cls:
            mock_cls.return_value = MagicMock(spec=VLMService)
            factory.create_vlm_service()
            mock_cls.assert_called_once()

    @patch("vision_insight.core.service_registry.settings")
    def test_create_vlm_service_gemini(self, mock_settings):
        """Should create Gemini VLM service when configured."""
        mock_settings.vlm_provider = "gemini"
        mock_settings.gemini_api_key = "test-key"

        factory = DefaultServiceFactory()

        with patch("vision_insight.services.vlm.api_service.GeminiVLMService") as mock_cls:
            mock_cls.return_value = MagicMock(spec=VLMService)
            factory.create_vlm_service()
            mock_cls.assert_called_once()

    @patch("vision_insight.core.service_registry.settings")
    def test_create_vlm_service_zhipu(self, mock_settings):
        """Should create Zhipu VLM service when configured."""
        mock_settings.vlm_provider = "zhipu"
        mock_settings.zhipu_api_key = "test-key"

        factory = DefaultServiceFactory()

        with patch("vision_insight.services.vlm.zhipu_service.ZhipuVLMService") as mock_cls:
            mock_cls.return_value = MagicMock(spec=VLMService)
            factory.create_vlm_service()
            mock_cls.assert_called_once()

    @patch("vision_insight.core.service_registry.settings")
    def test_create_vlm_service_auto_selects_zhipu(self, mock_settings):
        """Auto mode should prefer Zhipu when available."""
        mock_settings.vlm_provider = "auto"
        mock_settings.zhipu_api_key = "zhipu-key"
        mock_settings.openai_api_key = "openai-key"
        mock_settings.gemini_api_key = "gemini-key"

        factory = DefaultServiceFactory()

        with patch("vision_insight.services.vlm.zhipu_service.ZhipuVLMService") as mock_cls:
            mock_cls.return_value = MagicMock(spec=VLMService)
            factory.create_vlm_service()
            mock_cls.assert_called_once()

    @patch("vision_insight.core.service_registry.settings")
    def test_create_vlm_service_auto_falls_back_to_openai(self, mock_settings):
        """Auto mode should fall back to OpenAI when Zhipu key is missing."""
        mock_settings.vlm_provider = "auto"
        mock_settings.zhipu_api_key = ""
        mock_settings.openai_api_key = "openai-key"
        mock_settings.gemini_api_key = "gemini-key"

        factory = DefaultServiceFactory()

        with patch("vision_insight.services.vlm.api_service.OpenAIVLMService") as mock_cls:
            mock_cls.return_value = MagicMock(spec=VLMService)
            factory.create_vlm_service()
            mock_cls.assert_called_once()

    @patch("vision_insight.core.service_registry.settings")
    def test_create_vlm_service_auto_falls_back_to_gemini(self, mock_settings):
        """Auto mode should fall back to Gemini when OpenAI key is missing."""
        mock_settings.vlm_provider = "auto"
        mock_settings.zhipu_api_key = ""
        mock_settings.openai_api_key = ""
        mock_settings.gemini_api_key = "gemini-key"

        factory = DefaultServiceFactory()

        with patch("vision_insight.services.vlm.api_service.GeminiVLMService") as mock_cls:
            mock_cls.return_value = MagicMock(spec=VLMService)
            factory.create_vlm_service()
            mock_cls.assert_called_once()

    @patch("vision_insight.core.service_registry.settings")
    def test_create_vlm_service_no_key_uses_degraded_service(self, mock_settings):
        """Should use degraded VLM service when no API key is configured."""
        from vision_insight.services.fallback import DegradedVLMService

        mock_settings.vlm_provider = "auto"
        mock_settings.zhipu_api_key = ""
        mock_settings.openai_api_key = ""
        mock_settings.gemini_api_key = ""

        factory = DefaultServiceFactory()

        service = factory.create_vlm_service()

        assert isinstance(service, DegradedVLMService)

    @patch("vision_insight.core.service_registry.settings")
    def test_create_entity_service_zhipu(self, mock_settings):
        """Should create entity service with Zhipu when configured."""
        mock_settings.zhipu_api_key = "test-key"

        factory = DefaultServiceFactory()

        with patch(
            "vision_insight.services.entity.llm_entity_service.LLMEntityService"
        ) as mock_cls:
            mock_cls.return_value = MagicMock(spec=EntityService)
            factory.create_entity_service()
            mock_cls.assert_called_once_with(
                api_key="test-key",
                model="glm-4-flash",
                base_url="https://open.bigmodel.cn/api/coding/paas/v4",
            )

    @patch("vision_insight.core.service_registry.settings")
    def test_create_entity_service_openai(self, mock_settings):
        """Should create entity service with OpenAI when configured."""
        mock_settings.zhipu_api_key = ""
        mock_settings.openai_api_key = "test-key"

        factory = DefaultServiceFactory()

        with patch(
            "vision_insight.services.entity.llm_entity_service.LLMEntityService"
        ) as mock_cls:
            mock_cls.return_value = MagicMock(spec=EntityService)
            factory.create_entity_service()
            mock_cls.assert_called_once()

    @patch("vision_insight.core.service_registry.settings")
    def test_create_entity_service_no_key_uses_rule_based_fallback(self, mock_settings):
        """Should use rule-based entity service when no LLM key is configured."""
        from vision_insight.services.fallback import RuleBasedEntityService

        mock_settings.zhipu_api_key = ""
        mock_settings.openai_api_key = ""
        mock_settings.gemini_api_key = ""

        factory = DefaultServiceFactory()

        service = factory.create_entity_service()

        assert isinstance(service, RuleBasedEntityService)

    @patch("vision_insight.core.service_registry.settings")
    def test_create_evidence_service(self, mock_settings):
        """Should create evidence service with VLM port adapter."""
        mock_vlm = MagicMock(spec=VLMService)

        factory = DefaultServiceFactory()
        service = factory.create_evidence_service(mock_vlm)

        assert service is not None
        assert isinstance(service, EvidenceService)


class TestGetServiceRegistry:
    """Test get_service_registry singleton."""

    def setup_method(self):
        """Reset singleton before each test."""
        reset_service_registry()

    def teardown_method(self):
        """Reset singleton after each test."""
        reset_service_registry()

    def test_returns_same_instance(self):
        """Should return the same instance on multiple calls."""
        registry1 = get_service_registry()
        registry2 = get_service_registry()
        assert registry1 is registry2
        assert isinstance(registry1, ServiceRegistry)

    def test_accepts_custom_factory(self):
        """Should use custom factory when provided."""
        mock_factory = MagicMock(spec=ServiceFactory)
        registry = get_service_registry(factory=mock_factory)
        assert registry._factory is mock_factory

    def test_reset_service_registry(self):
        """Should reset the singleton instance."""
        registry1 = get_service_registry()
        reset_service_registry()
        registry2 = get_service_registry()
        assert registry1 is not registry2
