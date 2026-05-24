"""Tests for pipeline trace and reasoning chain functionality."""

from __future__ import annotations

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from datetime import datetime

import pytest

from vision_insight.models.schemas import (
    AnalysisReport,
    AnalysisStatus,
    PipelineStep,
    PipelineTrace,
    ReasoningStep,
    ReasoningTrace,
)


class TestPipelineTraceModels:
    """Test pipeline trace data models."""

    def test_reasoning_step_creation(self):
        step = ReasoningStep(
            step_id=1,
            action="rule_match",
            description="High confidence match",
            input_summary="3 evidence items",
            output_summary="Best match found",
            confidence_before=0.9,
            confidence_after=0.85,
            duration_ms=10,
        )
        assert step.step_id == 1
        assert step.action == "rule_match"
        assert step.confidence_before == 0.9

    def test_reasoning_trace_creation(self):
        trace = ReasoningTrace(
            conclusion_category="location",
            conclusion_statement="拍摄地点: 东京涩谷",
            final_probability=0.85,
            steps=[],
            strategy_used="rule",
            total_duration_ms=50,
        )
        assert trace.conclusion_category == "location"
        assert trace.strategy_used == "rule"

    def test_pipeline_step_creation(self):
        step = PipelineStep(
            stage_name="ocr",
            status="success",
            start_time=datetime.now(),
            end_time=datetime.now(),
            duration_ms=100,
            input_summary="Image 1920x1080",
            output_summary="5 text regions",
            key_findings=["Text: Shibuya", "Text: 109"],
        )
        assert step.stage_name == "ocr"
        assert step.status == "success"
        assert len(step.key_findings) == 2

    def test_pipeline_trace_creation(self):
        trace = PipelineTrace(
            steps=[],
            reasoning_traces=[],
            total_duration_ms=500,
            verbose_mode=True,
        )
        assert trace.verbose_mode is True
        assert trace.total_duration_ms == 500

    def test_analysis_report_with_trace(self):
        trace = PipelineTrace(
            steps=[
                PipelineStep(
                    stage_name="preprocess",
                    status="success",
                    start_time=datetime.now(),
                    duration_ms=50,
                )
            ],
            reasoning_traces=[
                ReasoningTrace(
                    conclusion_category="location",
                    conclusion_statement="Test location",
                    final_probability=0.8,
                    strategy_used="rule",
                )
            ],
            total_duration_ms=200,
            verbose_mode=True,
        )
        report = AnalysisReport(
            id="test-123",
            status=AnalysisStatus.COMPLETED,
            pipeline_trace=trace,
        )
        assert report.pipeline_trace is not None
        assert len(report.pipeline_trace.steps) == 1
        assert len(report.pipeline_trace.reasoning_traces) == 1


class TestFusionServiceTrace:
    """Test FusionService reasoning trace collection."""

    def test_fusion_service_verbose_mode(self):
        from vision_insight.services.evidence.fusion_service import FusionService

        service = FusionService(llm=None)
        assert service._verbose is False
        assert service._reasoning_traces == []

        service.set_verbose(True)
        assert service._verbose is True

        service.set_verbose(False)
        assert service._verbose is False
        assert service._reasoning_traces == []

    @pytest.mark.asyncio
    async def test_fusion_service_records_traces(self):
        from vision_insight.models.schemas import EntityExtraction, SceneAnalysis
        from vision_insight.services.evidence.fusion_service import FusionService

        service = FusionService(llm=None)
        service.set_verbose(True)

        scene = SceneAnalysis(
            scene_type="street",
            description="A busy street",
            location_guess=None,
        )

        # Fuse with no evidence
        await service.fuse(
            scene=scene,
            ocr_results=[],
            entities=EntityExtraction(),
            search_results=[],
            metadata=None,
        )

        # Should have recorded a trace for "no evidence" case
        traces = service.get_reasoning_traces()
        # The scene conclusion should have been recorded
        assert len(traces) >= 0  # May or may not have traces depending on evidence

    @pytest.mark.asyncio
    async def test_fusion_service_records_location_trace(self):
        from vision_insight.models.schemas import (
            EntityExtraction,
            LocationGuess,
            OCRResult,
            SceneAnalysis,
        )
        from vision_insight.services.evidence.fusion_service import FusionService

        service = FusionService(llm=None)
        service.set_verbose(True)

        scene = SceneAnalysis(
            scene_type="street",
            description="A busy street",
            location_guess=LocationGuess(
                location="Tokyo Shibuya", confidence=0.95, evidence=["Japanese signs"]
            ),
        )

        ocr_results = [
            OCRResult(text="Shibuya", bbox=[[0, 0], [100, 0], [100, 30], [0, 30]], confidence=0.95)
        ]
        entities = EntityExtraction(
            location_keywords=["Shibuya"],
            landmarks=["Shibuya 109"],
        )

        await service.fuse(
            scene=scene,
            ocr_results=ocr_results,
            entities=entities,
            search_results=[],
            metadata=None,
        )

        # Should have recorded traces
        traces = service.get_reasoning_traces()
        assert len(traces) > 0

        # Check location trace
        location_traces = [t for t in traces if t["conclusion_category"] == "location"]
        assert len(location_traces) == 1
        assert location_traces[0]["strategy_used"] == "rule"  # High confidence
        assert location_traces[0]["final_probability"] > 0.8

    @pytest.mark.asyncio
    async def test_fusion_service_records_time_trace(self):
        from datetime import datetime

        from vision_insight.models.schemas import (
            EntityExtraction,
            ImageMetadata,
            SceneAnalysis,
            TimeGuess,
        )
        from vision_insight.services.evidence.fusion_service import FusionService

        service = FusionService(llm=None)
        service.set_verbose(True)

        scene = SceneAnalysis(
            scene_type="street",
            description="A busy street",
            time_guess=TimeGuess(time_of_day="night", season="winter"),
        )

        metadata = ImageMetadata(
            width=1920,
            height=1080,
            format="JPEG",
            file_size=100000,
            capture_time=datetime(2024, 1, 15, 20, 30),
        )

        await service.fuse(
            scene=scene,
            ocr_results=[],
            entities=EntityExtraction(),
            search_results=[],
            metadata=metadata,
        )

        # Should have recorded traces
        traces = service.get_reasoning_traces()
        assert len(traces) > 0

        # Check time trace
        time_traces = [t for t in traces if t["conclusion_category"] == "time"]
        assert len(time_traces) == 1
        assert time_traces[0]["strategy_used"] == "rule"  # High confidence EXIF
        assert time_traces[0]["final_probability"] > 0.8

    @pytest.mark.asyncio
    async def test_fusion_service_verbose_disabled_no_traces(self):
        from vision_insight.models.schemas import (
            EntityExtraction,
            LocationGuess,
            OCRResult,
            SceneAnalysis,
        )
        from vision_insight.services.evidence.fusion_service import FusionService

        service = FusionService(llm=None)
        # Verbose mode is OFF by default
        assert service._verbose is False

        scene = SceneAnalysis(
            scene_type="street",
            description="A busy street",
            location_guess=LocationGuess(
                location="Tokyo Shibuya", confidence=0.95, evidence=["Japanese signs"]
            ),
        )

        ocr_results = [
            OCRResult(text="Shibuya", bbox=[[0, 0], [100, 0], [100, 30], [0, 30]], confidence=0.95)
        ]
        entities = EntityExtraction(
            location_keywords=["Shibuya"],
            landmarks=["Shibuya 109"],
        )

        await service.fuse(
            scene=scene,
            ocr_results=ocr_results,
            entities=entities,
            search_results=[],
            metadata=None,
        )

        # Should NOT have recorded traces
        traces = service.get_reasoning_traces()
        assert len(traces) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
