#!/usr/bin/env python3
"""Demo script for pipeline trace functionality."""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from vision_insight.models.schemas import (
    AnalysisReport,
    AnalysisStatus,
    EntityExtraction,
    OCRResult,
    SceneAnalysis,
)
from vision_insight.services.evidence.fusion_service import FusionService


async def demo_verbose_fusion():
    """Demonstrate verbose fusion with reasoning traces."""

    print("=" * 60)
    print("Pipeline Trace Demo")
    print("=" * 60)

    # Create fusion service
    service = FusionService(llm=None)

    # Enable verbose mode
    service.set_verbose(True)
    print("\n✓ Verbose mode enabled")

    # Create sample data
    scene = SceneAnalysis(
        scene_type="commercial_street",
        description="A busy commercial street at night with Japanese signs",
        location_guess=None,
    )

    ocr_results = [
        OCRResult(text="Shibuya", bbox=[[0, 0], [100, 0], [100, 30], [0, 30]], confidence=0.95),
        OCRResult(text="109", bbox=[[0, 40], [100, 40], [100, 70], [0, 70]], confidence=0.90),
    ]

    entities = EntityExtraction(
        location_keywords=["Shibuya"],
        brands=["109"],
        landmarks=["Shibuya 109"],
    )

    print("\n📊 Input Data:")
    print(f"  - Scene: {scene.scene_type}")
    print(f"  - OCR texts: {[r.text for r in ocr_results]}")
    print(f"  - Entities: {entities.landmarks}")

    # Run fusion
    print("\n🔄 Running evidence fusion...")
    conclusions = await service.fuse(
        scene=scene,
        ocr_results=ocr_results,
        entities=entities,
        search_results=[],
        metadata=None,
    )

    # Get reasoning traces
    traces = service.get_reasoning_traces()

    print(f"\n✅ Generated {len(conclusions)} conclusions")
    print(f"📝 Recorded {len(traces)} reasoning traces")

    # Display conclusions
    print("\n" + "=" * 60)
    print("Conclusions")
    print("=" * 60)
    for i, c in enumerate(conclusions, 1):
        print(f"\n{i}. [{c.category}] {c.statement}")
        print(f"   Probability: {c.probability:.2%}")
        print(f"   Evidence count: {len(c.evidence)}")

    # Display reasoning traces
    print("\n" + "=" * 60)
    print("Reasoning Traces")
    print("=" * 60)
    for trace in traces:
        print(f"\n📍 Category: {trace['conclusion_category']}")
        print(f"   Statement: {trace['conclusion_statement']}")
        print(f"   Strategy: {trace['strategy_used']}")
        print(f"   Probability: {trace['final_probability']:.2%}")
        print(f"   Duration: {trace['total_duration_ms']}ms")

        if trace['steps']:
            print("   Steps:")
            for step in trace['steps']:
                print(f"     - {step['action']}: {step['description']}")
                print(f"       Confidence: {step['confidence_before']:.2f} → {step['confidence_after']:.2f}")

    # Disable verbose mode
    service.set_verbose(False)
    print("\n" + "=" * 60)
    print("✓ Verbose mode disabled")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(demo_verbose_fusion())
