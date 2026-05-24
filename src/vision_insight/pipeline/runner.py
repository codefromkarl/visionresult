"""Pipeline runner — wires services and executes the analysis pipeline."""

import logging
import time
from typing import Any

from vision_insight.core.event_logger import log_event
from vision_insight.core.service_registry import ServiceRegistry, get_service_registry
from vision_insight.models.schemas import AnalysisReport, AnalysisStatus, ReasoningTrace
from vision_insight.pipeline.graph import PipelineState, ProgressCallback, build_pipeline

logger = logging.getLogger(__name__)


class PipelineRunner:
    """Manages service lifecycle and executes the analysis pipeline.

    This module provides a deep interface for pipeline execution:
    - Simple method to execute the pipeline
    - Centralized service management via ServiceRegistry
    - Easy to test with mock registry
    """

    def __init__(self, registry: ServiceRegistry | None = None) -> None:
        """Initialize the pipeline runner.

        Args:
            registry: Service registry to use. If None, uses default singleton.
        """
        self._registry = registry or get_service_registry()
        self._pipeline: Any = None

    def _ensure_pipeline(self) -> None:
        """Lazy-initialize the pipeline graph."""
        if self._pipeline is not None:
            return

        # Get all services from registry
        services = self._registry.get_services()

        # Build pipeline graph
        self._pipeline = build_pipeline(
            ocr_service=services.ocr,
            vlm_service=services.vlm,
            entity_service=services.entity,
            search_service=services.search,
            evidence_service=services.evidence,
        )
        logger.info("Pipeline graph built")

    async def execute(
        self,
        report: AnalysisReport,
        image_bytes: bytes,
        progress_callback: ProgressCallback = None,
        verbose: bool = False,
        lang: str = "zh",
    ) -> AnalysisReport:
        """Execute the full analysis pipeline.

        Args:
            report: The AnalysisReport to populate (must have id and PENDING status).
            image_bytes: Raw image file bytes.
            progress_callback: Optional callback for progress updates.
            verbose: Whether to record detailed pipeline trace.
            lang: Output language - 'zh' for Chinese, 'en' for English.

        Returns:
            The populated AnalysisReport with status COMPLETED or FAILED.
        """
        self._ensure_pipeline()

        # Get evidence service for verbose mode
        services = self._registry.get_services()
        evidence_service = services.evidence
        if hasattr(evidence_service, "set_verbose"):
            evidence_service.set_verbose(verbose)

        task_id = report.id
        start_time = time.time()
        report.status = AnalysisStatus.PROCESSING

        log_event(task_id, "pipeline_start", image_bytes=len(image_bytes), verbose=verbose)

        state = PipelineState(
            report=report,
            image_bytes=image_bytes,
            progress_callback=progress_callback,
            verbose=verbose,
            pipeline_trace={"steps": [], "reasoning_traces": []} if verbose else {},
            lang=lang,
        )

        try:
            result = await self._pipeline.ainvoke(state)
            elapsed_ms = int((time.time() - start_time) * 1000)
            result["report"].processing_time_ms = elapsed_ms

            # Add reasoning traces to pipeline trace if verbose
            if verbose and hasattr(evidence_service, "get_reasoning_traces"):
                reasoning_traces = evidence_service.get_reasoning_traces()
                if result["report"].pipeline_trace:
                    result["report"].pipeline_trace.reasoning_traces = [
                        ReasoningTrace(**t) for t in reasoning_traces
                    ]

            scene_type = (
                result["report"].scene_analysis.scene_type
                if result["report"].scene_analysis
                else "unknown"
            )
            num_ocr = len(result["report"].ocr_results)
            num_conclusions = len(result["report"].conclusions)

            log_event(
                task_id,
                "pipeline_end",
                status="completed",
                elapsed_ms=elapsed_ms,
                scene_type=scene_type,
                num_ocr=num_ocr,
                num_conclusions=num_conclusions,
            )

            logger.info("Pipeline completed in %dms for task %s", elapsed_ms, report.id)
            return result["report"]
        except Exception as exc:
            elapsed_ms = int((time.time() - start_time) * 1000)
            log_event(
                task_id,
                "pipeline_fail",
                elapsed_ms=elapsed_ms,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            logger.exception("Pipeline failed for task %s", report.id)
            report.status = AnalysisStatus.FAILED
            report.report_markdown = f"# 分析失败\n\n错误: {exc}"
            return report


# Singleton runner
_runner: PipelineRunner | None = None


def get_pipeline_runner(registry: ServiceRegistry | None = None) -> PipelineRunner:
    """Get or create the singleton PipelineRunner.

    Args:
        registry: Optional service registry to use. Only used on first call.

    Returns:
        The singleton PipelineRunner instance.
    """
    global _runner
    if _runner is None:
        _runner = PipelineRunner(registry)
    return _runner


def reset_pipeline_runner() -> None:
    """Reset the singleton runner (for testing)."""
    global _runner
    _runner = None
