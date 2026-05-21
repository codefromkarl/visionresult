"""Pipeline runner — wires services and executes the analysis pipeline."""

from __future__ import annotations

import logging
import time

from vision_insight.core.config import settings
from vision_insight.models.schemas import AnalysisReport, AnalysisStatus
from vision_insight.pipeline.graph import PipelineState, ProgressCallback, build_pipeline
from vision_insight.services import (
    EntityService,
    EvidenceService,
    OCRService,
    SearchService,
    VLMService,
)
from vision_insight.services.entity.llm_entity_service import LLMEntityService
from vision_insight.services.evidence.fusion_service import FusionService
from vision_insight.services.search.http_search_service import HttpSearchService

logger = logging.getLogger(__name__)


class PipelineRunner:
    """Manages service lifecycle and executes the analysis pipeline."""

    def __init__(self) -> None:
        self._ocr: OCRService | None = None
        self._vlm: VLMService | None = None
        self._entity: EntityService | None = None
        self._search: SearchService | None = None
        self._evidence: EvidenceService | None = None
        self._pipeline = None

    def _init_services(self) -> None:
        """Lazy-initialize all services based on config."""
        if self._pipeline is not None:
            return

        # OCR
        from vision_insight.services.ocr.paddle_service import PaddleOCRService
        self._ocr = PaddleOCRService(lang=settings.ocr_lang, use_gpu=False)

        # VLM — select based on config
        vlm_provider = settings.vlm_provider.lower()
        if vlm_provider == "openai":
            from vision_insight.services.vlm.api_service import OpenAIVLMService
            self._vlm = OpenAIVLMService()
        elif vlm_provider == "gemini":
            from vision_insight.services.vlm.api_service import GeminiVLMService
            self._vlm = GeminiVLMService()
        else:
            # Default: try OpenAI if key available, else Gemini
            if settings.openai_api_key:
                from vision_insight.services.vlm.api_service import OpenAIVLMService
                self._vlm = OpenAIVLMService()
                logger.info("VLM: using OpenAI GPT-4o")
            elif settings.gemini_api_key:
                from vision_insight.services.vlm.api_service import GeminiVLMService
                self._vlm = GeminiVLMService()
                logger.info("VLM: using Gemini")
            else:
                raise ValueError("No VLM API key configured. Set VIA_OPENAI_API_KEY or VIA_GEMINI_API_KEY")

        # Entity extraction — use the same provider as VLM
        if settings.openai_api_key:
            self._entity = LLMEntityService()
        elif settings.gemini_api_key:
            # Use Gemini via OpenAI-compatible endpoint
            self._entity = LLMEntityService(
                api_key=settings.gemini_api_key,
                model="gemini-2.0-flash",
                base_url="https://generativelanguage.googleapis.com/v1beta/openai",
            )
        else:
            raise ValueError("No API key for entity extraction")

        # Search
        self._search = HttpSearchService()

        # Evidence fusion — reuse VLM as LLM port for medium-confidence reasoning
        class _VLMPortAdapter:
            """Adapt VLM service to the LLMPort interface used by FusionService."""
            def __init__(self, vlm: VLMService):
                self._vlm = vlm

            async def infer(self, prompt: str) -> str:
                # Use VLM's analyze method won't work (needs image),
                # so we use a simple fallback: return empty to skip LLM assist
                return ""

        self._evidence = FusionService(llm=_VLMPortAdapter(self._vlm))

        # Build pipeline graph
        self._pipeline = build_pipeline(
            ocr_service=self._ocr,
            vlm_service=self._vlm,
            entity_service=self._entity,
            search_service=self._search,
            evidence_service=self._evidence,
        )
        logger.info("Pipeline services initialized")

    async def execute(
        self,
        report: AnalysisReport,
        image_bytes: bytes,
        progress_callback: ProgressCallback = None,
    ) -> AnalysisReport:
        """Execute the full analysis pipeline.

        Args:
            report: The AnalysisReport to populate (must have id and PENDING status).
            image_bytes: Raw image file bytes.
            progress_callback: Optional callback for progress updates.

        Returns:
            The populated AnalysisReport with status COMPLETED or FAILED.
        """
        self._init_services()

        start_time = time.time()
        report.status = AnalysisStatus.PROCESSING

        state = PipelineState(
            report=report,
            image_bytes=image_bytes,
            progress_callback=progress_callback,
        )

        try:
            result = await self._pipeline.ainvoke(state)
            elapsed_ms = int((time.time() - start_time) * 1000)
            result["report"].processing_time_ms = elapsed_ms
            logger.info("Pipeline completed in %dms for task %s", elapsed_ms, report.id)
            return result["report"]
        except Exception as exc:
            logger.exception("Pipeline failed for task %s", report.id)
            report.status = AnalysisStatus.FAILED
            report.report_markdown = f"# 分析失败\n\n错误: {exc}"
            return report


# Singleton runner
_runner: PipelineRunner | None = None


def get_pipeline_runner() -> PipelineRunner:
    """Get or create the singleton PipelineRunner."""
    global _runner
    if _runner is None:
        _runner = PipelineRunner()
    return _runner
