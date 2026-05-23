"""Fallback service implementations used when external providers are unavailable.

These services keep the pipeline usable in local development and under provider
outages/rate limits. They deliberately return explicit "degraded" data instead
of pretending an AI analysis succeeded.
"""

import logging
from collections.abc import Iterable

from vision_insight.models.schemas import (
    DetectedObject,
    EntityExtraction,
    OCRResult,
    SceneAnalysis,
)
from vision_insight.services import EntityService, OCRService, VLMService
from vision_insight.utils import extract_entities_rule_based

logger = logging.getLogger(__name__)


class CompositeOCRService(OCRService):
    """Try multiple OCR providers and return the first useful result.

    OCR engines often fail because of native/runtime compatibility issues. This
    composite keeps the pipeline moving by trying the next configured provider
    when the current provider raises or returns no text.
    """

    def __init__(self, services: Iterable[tuple[str, OCRService]]) -> None:
        self._services = list(services)

    async def extract(self, image_bytes: bytes) -> list[OCRResult]:
        """Extract text using the first OCR provider that produces results."""
        if not self._services:
            logger.warning("No OCR providers configured; returning empty OCR result")
            return []

        last_error: Exception | None = None
        for name, service in self._services:
            try:
                results = await service.extract(image_bytes)
                if results:
                    logger.info("OCR provider '%s' returned %d regions", name, len(results))
                    return results
                logger.info("OCR provider '%s' returned no text; trying next provider", name)
            except Exception as exc:  # noqa: BLE001 - provider boundary must not break pipeline
                last_error = exc
                logger.warning("OCR provider '%s' failed; trying next provider: %s", name, exc)

        if last_error:
            logger.warning("All OCR providers failed; returning empty OCR result")
        return []


class DegradedVLMService(VLMService):
    """Explicit VLM fallback for missing keys, provider outages, or rate limits."""

    async def analyze(
        self,
        image_bytes: bytes,
        ocr_results: list[OCRResult] | None = None,
        lang: str = "zh",
    ) -> SceneAnalysis:
        """Return an honest unknown scene when no VLM provider is usable."""
        if lang == "en":
            description = (
                "VLM analysis is currently unavailable. The report is generated from "
                "OCR, metadata, and rule-based evidence only."
            )
            uncertainties = ["No vision-language model provider was available"]
            evidence = [r.text for r in (ocr_results or [])[:5]]
            key_evidence = [f"OCR text: {text}" for text in evidence]
        else:
            description = "VLM 分析当前不可用，报告仅基于 OCR、元数据和规则证据生成。"
            uncertainties = ["没有可用的视觉语言模型提供商"]
            evidence = [r.text for r in (ocr_results or [])[:5]]
            key_evidence = [f"OCR 文字：{text}" for text in evidence]

        return SceneAnalysis(
            scene_type="unknown",
            description=description,
            key_evidence=key_evidence,
            uncertainties=uncertainties,
        )

    async def detect_objects(self, image_bytes: bytes, lang: str = "zh") -> list[DetectedObject]:
        """Return no objects in degraded mode."""
        return []


class CompositeVLMService(VLMService):
    """Try configured VLM providers in order, then fall back to degraded mode."""

    def __init__(self, services: Iterable[tuple[str, VLMService]]) -> None:
        self._services = list(services)
        self._degraded = DegradedVLMService()

    async def analyze(
        self,
        image_bytes: bytes,
        ocr_results: list[OCRResult] | None = None,
        lang: str = "zh",
    ) -> SceneAnalysis:
        """Analyze with the first available VLM provider."""
        for name, service in self._services:
            try:
                scene = await service.analyze(image_bytes, ocr_results, lang=lang)
                logger.info("VLM provider '%s' completed scene analysis", name)
                return scene
            except Exception as exc:  # noqa: BLE001 - external provider fallback boundary
                logger.warning("VLM provider '%s' failed; trying next provider: %s", name, exc)

        logger.warning("All VLM providers failed or are missing; using degraded VLM result")
        return await self._degraded.analyze(image_bytes, ocr_results, lang=lang)

    async def detect_objects(self, image_bytes: bytes, lang: str = "zh") -> list[DetectedObject]:
        """Detect objects with the first provider that succeeds."""
        for name, service in self._services:
            try:
                objects = await service.detect_objects(image_bytes, lang=lang)
                logger.info("VLM provider '%s' completed object detection", name)
                return objects
            except Exception as exc:  # noqa: BLE001 - external provider fallback boundary
                logger.warning(
                    "VLM provider '%s' object detection failed; trying next provider: %s",
                    name,
                    exc,
                )
        return []


class RuleBasedEntityService(EntityService):
    """Entity extraction fallback that uses VLM hints and high-confidence OCR."""

    async def extract(self, scene: SceneAnalysis, ocr_results: list[OCRResult]) -> EntityExtraction:
        """Extract conservative entities without an LLM call."""
        return extract_entities_rule_based(scene, ocr_results)
