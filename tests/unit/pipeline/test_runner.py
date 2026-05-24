"""Tests for the PipelineRunner module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from vision_insight.core.service_registry import ServiceRegistry, Services
from vision_insight.models.schemas import (
    AnalysisReport,
    AnalysisStatus,
)
from vision_insight.pipeline.runner import (
    PipelineRunner,
    get_pipeline_runner,
    reset_pipeline_runner,
)
from vision_insight.services import (
    EntityService,
    EvidenceService,
    OCRService,
    SearchService,
    VLMService,
)


def _create_mock_services() -> Services:
    """Create a Services instance with mock services."""
    evidence = MagicMock(spec=EvidenceService)
    evidence.set_verbose = MagicMock()
    evidence.get_reasoning_traces = MagicMock(return_value=[])

    return Services(
        vlm=MagicMock(spec=VLMService),
        ocr=MagicMock(spec=OCRService),
        entity=MagicMock(spec=EntityService),
        search=MagicMock(spec=SearchService),
        evidence=evidence,
    )


class TestPipelineRunner:
    """Test PipelineRunner class."""

    def test_init_creates_runner_with_registry(self):
        """Runner should initialize with a service registry."""
        mock_registry = MagicMock(spec=ServiceRegistry)
        runner = PipelineRunner(registry=mock_registry)
        assert runner._registry is mock_registry
        assert runner._pipeline is None

    def test_init_creates_runner_with_default_registry(self):
        """Runner should use default registry when none provided."""
        runner = PipelineRunner()
        assert runner._registry is not None
        assert runner._pipeline is None

    def test_ensure_pipeline_builds_graph(self):
        """_ensure_pipeline should build the pipeline graph."""
        mock_registry = MagicMock(spec=ServiceRegistry)
        mock_registry.get_services.return_value = _create_mock_services()

        runner = PipelineRunner(registry=mock_registry)
        runner._ensure_pipeline()

        assert runner._pipeline is not None
        mock_registry.get_services.assert_called_once()

    def test_ensure_pipeline_idempotent(self):
        """_ensure_pipeline should not rebuild if already initialized."""
        mock_registry = MagicMock(spec=ServiceRegistry)
        mock_registry.get_services.return_value = _create_mock_services()

        runner = PipelineRunner(registry=mock_registry)
        runner._ensure_pipeline()
        first_pipeline = runner._pipeline

        # Call again - should not rebuild
        runner._ensure_pipeline()
        assert runner._pipeline is first_pipeline
        # get_services should only be called once
        mock_registry.get_services.assert_called_once()


class TestPipelineRunnerExecute:
    """Test PipelineRunner.execute method."""

    @pytest.mark.asyncio
    async def test_execute_success(self):
        """Should return completed report on success."""
        mock_registry = MagicMock(spec=ServiceRegistry)
        mock_services = _create_mock_services()
        mock_registry.get_services.return_value = mock_services

        runner = PipelineRunner(registry=mock_registry)

        # Mock the pipeline
        mock_report = AnalysisReport(
            id="test-001",
            status=AnalysisStatus.COMPLETED,
            report_markdown="# Test Report",
        )
        mock_pipeline = AsyncMock()
        mock_pipeline.ainvoke.return_value = {"report": mock_report}
        runner._pipeline = mock_pipeline

        report = AnalysisReport(id="test-001", status=AnalysisStatus.PENDING)
        result = await runner.execute(report, b"fake-image-bytes")

        assert result.status == AnalysisStatus.COMPLETED
        assert result.report_markdown == "# Test Report"
        assert result.processing_time_ms >= 0
        mock_services.evidence.set_verbose.assert_called_once_with(False)

    @pytest.mark.asyncio
    async def test_execute_with_progress_callback(self):
        """Should call progress callback during execution."""
        mock_registry = MagicMock(spec=ServiceRegistry)
        mock_services = _create_mock_services()
        mock_registry.get_services.return_value = mock_services

        runner = PipelineRunner(registry=mock_registry)

        # Mock the pipeline to simulate progress
        async def mock_ainvoke(state):
            callback = state.get("progress_callback")
            if callback:
                callback("ocr", 25)
                callback("vlm_analysis", 50)
            return {"report": state["report"]}

        mock_pipeline = AsyncMock()
        mock_pipeline.ainvoke.side_effect = mock_ainvoke
        runner._pipeline = mock_pipeline

        progress_calls = []

        def progress_callback(stage, percent):
            progress_calls.append((stage, percent))

        report = AnalysisReport(id="test-002", status=AnalysisStatus.PENDING)
        await runner.execute(report, b"fake-image", progress_callback)

        assert len(progress_calls) == 2
        assert progress_calls[0] == ("ocr", 25)
        assert progress_calls[1] == ("vlm_analysis", 50)

    @pytest.mark.asyncio
    async def test_execute_failure_returns_failed_report(self):
        """Should return FAILED status when pipeline raises exception."""
        mock_registry = MagicMock(spec=ServiceRegistry)
        mock_services = _create_mock_services()
        mock_registry.get_services.return_value = mock_services

        runner = PipelineRunner(registry=mock_registry)

        mock_pipeline = AsyncMock()
        mock_pipeline.ainvoke.side_effect = RuntimeError("Pipeline error")
        runner._pipeline = mock_pipeline

        report = AnalysisReport(id="test-003", status=AnalysisStatus.PENDING)
        result = await runner.execute(report, b"fake-image")

        assert result.status == AnalysisStatus.FAILED
        assert "Pipeline error" in result.report_markdown

    @pytest.mark.asyncio
    async def test_execute_sets_processing_status(self):
        """Should set status to PROCESSING during execution."""
        mock_registry = MagicMock(spec=ServiceRegistry)
        mock_services = _create_mock_services()
        mock_registry.get_services.return_value = mock_services

        runner = PipelineRunner(registry=mock_registry)

        captured_status = None

        async def mock_ainvoke(state):
            nonlocal captured_status
            captured_status = state["report"].status
            return {"report": state["report"]}

        mock_pipeline = AsyncMock()
        mock_pipeline.ainvoke.side_effect = mock_ainvoke
        runner._pipeline = mock_pipeline

        report = AnalysisReport(id="test-004", status=AnalysisStatus.PENDING)
        await runner.execute(report, b"fake-image")

        assert captured_status == AnalysisStatus.PROCESSING

    @pytest.mark.asyncio
    async def test_execute_with_verbose_mode(self):
        """Should set verbose mode on evidence service."""
        mock_registry = MagicMock(spec=ServiceRegistry)
        mock_services = _create_mock_services()
        mock_registry.get_services.return_value = mock_services

        runner = PipelineRunner(registry=mock_registry)

        mock_report = AnalysisReport(
            id="test-005",
            status=AnalysisStatus.COMPLETED,
        )
        mock_pipeline = AsyncMock()
        mock_pipeline.ainvoke.return_value = {"report": mock_report}
        runner._pipeline = mock_pipeline

        report = AnalysisReport(id="test-005", status=AnalysisStatus.PENDING)
        await runner.execute(report, b"fake-image", verbose=True)

        mock_services.evidence.set_verbose.assert_called_once_with(True)


class TestGetPipelineRunner:
    """Test get_pipeline_runner singleton."""

    def setup_method(self):
        """Reset singleton before each test."""
        reset_pipeline_runner()

    def teardown_method(self):
        """Reset singleton after each test."""
        reset_pipeline_runner()

    def test_returns_same_instance(self):
        """Should return the same instance on multiple calls."""
        runner1 = get_pipeline_runner()
        runner2 = get_pipeline_runner()
        assert runner1 is runner2
        assert isinstance(runner1, PipelineRunner)

    def test_accepts_custom_registry(self):
        """Should use custom registry when provided."""
        mock_registry = MagicMock(spec=ServiceRegistry)
        runner = get_pipeline_runner(registry=mock_registry)
        assert runner._registry is mock_registry

    def test_reset_pipeline_runner(self):
        """Should reset the singleton instance."""
        runner1 = get_pipeline_runner()
        reset_pipeline_runner()
        runner2 = get_pipeline_runner()
        assert runner1 is not runner2
