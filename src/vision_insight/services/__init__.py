"""Service interfaces for the analysis pipeline.

Each service handles one stage of the pipeline.
Implementations are in their respective subdirectories.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from vision_insight.models.schemas import (
    DetectedObject,
    EntityExtraction,
    ImageMetadata,
    OCRResult,
    SceneAnalysis,
    SearchResult,
)


class OCRService(ABC):
    """OCR text extraction service."""

    @abstractmethod
    async def extract(self, image_bytes: bytes) -> list[OCRResult]:
        """Extract text from image."""
        ...


class VLMService(ABC):
    """Vision-Language Model service for scene understanding."""

    @abstractmethod
    async def analyze(
        self, image_bytes: bytes, ocr_results: list[OCRResult] | None = None, lang: str = "zh"
    ) -> SceneAnalysis:
        """Analyze image scene with VLM.

        Args:
            image_bytes: Raw image bytes.
            ocr_results: Optional OCR results for context.
            lang: Output language - 'zh' for Chinese, 'en' for English.
        """
        ...

    @abstractmethod
    async def detect_objects(self, image_bytes: bytes, lang: str = "zh") -> list[DetectedObject]:
        """Detect objects in image."""
        ...


class EntityService(ABC):
    """Entity extraction service."""

    @abstractmethod
    async def extract(self, scene: SceneAnalysis, ocr_results: list[OCRResult]) -> EntityExtraction:
        """Extract structured entities from analysis results."""
        ...


class SearchService(ABC):
    """Web search service for verification."""

    @abstractmethod
    async def search(self, query: str, source: str = "google") -> list[SearchResult]:
        """Search the web for information."""
        ...

    @abstractmethod
    async def verify_location(self, keywords: list[str]) -> list[SearchResult]:
        """Verify location hypotheses."""
        ...


class EvidenceService(ABC):
    """Evidence fusion service."""

    @abstractmethod
    async def fuse(
        self,
        scene: SceneAnalysis,
        ocr_results: list[OCRResult],
        entities: EntityExtraction,
        search_results: list[SearchResult],
        metadata: ImageMetadata | None,
    ) -> list:
        """Fuse evidence into weighted conclusions."""
        ...


class ReportService(ABC):
    """Report generation service."""

    @abstractmethod
    async def generate_user_report(self, report, lang: str = "zh") -> str:
        """Generate user-friendly markdown report."""
        ...

    @abstractmethod
    async def generate_structured_report(self, report) -> dict:
        """Generate structured JSON report."""
        ...
