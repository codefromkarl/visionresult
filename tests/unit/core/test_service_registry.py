"""Tests for the ServiceRegistry module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from vision_insight.core.service_registry import (
    ServiceRegistry,
    Services,
    create_services,
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

    def test_init_with_custom_services(self):
        """Should use custom services when provided."""
        mock_services = MagicMock(spec=Services)
        registry = ServiceRegistry(services=mock_services)
        assert registry._services is mock_services

    def test_init_without_services(self):
        """Should initialize with None services."""
        registry = ServiceRegistry()
        assert registry._services is None

    def test_get_services_initializes_once(self):
        """Should initialize services only once."""
        mock_services = MagicMock(spec=Services)
        registry = ServiceRegistry(services=mock_services)

        # First call should return provided services
        result1 = registry.get_services()
        assert result1 is mock_services

        # Second call should return same instance
        result2 = registry.get_services()
        assert result2 is mock_services

    def test_get_services_creates_from_config(self):
        """Should create services from config when none provided."""
        registry = ServiceRegistry()

        with patch("vision_insight.core.service_registry.create_services") as mock_create:
            mock_services = MagicMock(spec=Services)
            mock_create.return_value = mock_services

            result = registry.get_services()
            assert result is mock_services
            mock_create.assert_called_once()

    def test_backward_compatibility_methods(self):
        """Should provide backward compatibility methods."""
        mock_vlm = MagicMock(spec=VLMService)
        mock_ocr = MagicMock(spec=OCRService)
        mock_entity = MagicMock(spec=EntityService)
        mock_search = MagicMock(spec=SearchService)
        mock_evidence = MagicMock(spec=EvidenceService)

        mock_services = Services(
            vlm=mock_vlm,
            ocr=mock_ocr,
            entity=mock_entity,
            search=mock_search,
            evidence=mock_evidence,
        )
        registry = ServiceRegistry(services=mock_services)

        # Test deprecated methods
        assert registry.get_all_services() == mock_services.to_dict()
        assert registry.get_vlm_service() == mock_vlm
        assert registry.get_ocr_service() == mock_ocr
        assert registry.get_entity_service() == mock_entity
        assert registry.get_search_service() == mock_search
        assert registry.get_evidence_service() == mock_evidence


class TestServices:
    """Test Services dataclass."""

    def test_to_dict(self):
        """Should convert to dictionary."""
        mock_vlm = MagicMock(spec=VLMService)
        mock_ocr = MagicMock(spec=OCRService)
        mock_entity = MagicMock(spec=EntityService)
        mock_search = MagicMock(spec=SearchService)
        mock_evidence = MagicMock(spec=EvidenceService)

        services = Services(
            vlm=mock_vlm,
            ocr=mock_ocr,
            entity=mock_entity,
            search=mock_search,
            evidence=mock_evidence,
        )

        result = services.to_dict()
        assert result["vlm"] is mock_vlm
        assert result["ocr"] is mock_ocr
        assert result["entity"] is mock_entity
        assert result["search"] is mock_search
        assert result["evidence"] is mock_evidence


class TestGetServiceRegistry:
    """Test get_service_registry function."""

    def test_singleton_behavior(self):
        """Should return same instance on multiple calls."""
        reset_service_registry()

        registry1 = get_service_registry()
        registry2 = get_service_registry()

        assert registry1 is registry2

    def test_reset_clears_singleton(self):
        """Should clear singleton on reset."""
        reset_service_registry()

        registry1 = get_service_registry()
        reset_service_registry()
        registry2 = get_service_registry()

        assert registry1 is not registry2


class TestCreateServices:
    """Test create_services function."""

    def test_creates_all_services(self):
        """Should create all services."""
        with patch("vision_insight.core.service_registry.create_vlm_service") as mock_vlm, \
             patch("vision_insight.core.service_registry.create_ocr_service") as mock_ocr, \
             patch("vision_insight.core.service_registry.create_entity_service") as mock_entity, \
             patch("vision_insight.core.service_registry.create_search_service") as mock_search, \
             patch("vision_insight.core.service_registry.create_evidence_service") as mock_evidence:

            mock_vlm.return_value = MagicMock(spec=VLMService)
            mock_ocr.return_value = MagicMock(spec=OCRService)
            mock_entity.return_value = MagicMock(spec=EntityService)
            mock_search.return_value = MagicMock(spec=SearchService)
            mock_evidence.return_value = MagicMock(spec=EvidenceService)

            services = create_services()

            assert isinstance(services, Services)
            mock_vlm.assert_called_once()
            mock_ocr.assert_called_once()
            mock_entity.assert_called_once()
            mock_search.assert_called_once()
            mock_evidence.assert_called_once()
