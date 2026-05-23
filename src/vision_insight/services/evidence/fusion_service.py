"""Evidence fusion service — rule + LLM hybrid strategy."""

import logging
import time
from abc import ABC, abstractmethod

from vision_insight.models.schemas import (
    EntityExtraction,
    EvidenceItem,
    FusedConclusion,
    ImageMetadata,
    OCRResult,
    SceneAnalysis,
    SearchResult,
)
from vision_insight.services import EvidenceService

logger = logging.getLogger(__name__)

# Confidence thresholds
_HIGH_CONFIDENCE_THRESHOLD = 0.8
_MEDIUM_CONFIDENCE_THRESHOLD = 0.5


class LLMPort(ABC):
    """Minimal async LLM interface used by FusionService.

    Implementations should call the underlying VLM/LLM and return a
    plain-text response string.
    """

    @abstractmethod
    async def infer(self, prompt: str) -> str:
        """Send *prompt* to an LLM and return its text response."""
        ...

    async def infer_with_reasoning(self, prompt: str) -> tuple[str, str]:
        """Send *prompt* to an LLM and return (response, reasoning_trace).

        Default implementation returns empty reasoning. Override to provide
        detailed reasoning chain from the LLM.
        """
        response = await self.infer(prompt)
        return response, ""


class FusionService(EvidenceService):
    """Fuse evidence with a rule-first, LLM-assist hybrid strategy.

    Strategy:
        1. High-confidence OCR match → rule-based direct verdict.
        2. Medium-confidence items → ask LLM for reasoning.
        3. Low-confidence items → mark as uncertain.
    """

    def __init__(self, llm: LLMPort | None = None) -> None:
        self._llm = llm
        self._verbose = False
        self._reasoning_traces: list[dict] = []  # Collected reasoning traces

    def set_verbose(self, verbose: bool) -> None:
        """Enable or disable verbose mode."""
        self._verbose = verbose
        if not verbose:
            self._reasoning_traces = []

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def get_reasoning_traces(self) -> list[dict]:
        """Return collected reasoning traces."""
        return self._reasoning_traces

    def clear_reasoning_traces(self) -> None:
        """Clear collected reasoning traces."""
        self._reasoning_traces = []

    async def fuse(
        self,
        scene: SceneAnalysis,
        ocr_results: list[OCRResult],
        entities: EntityExtraction,
        search_results: list[SearchResult],
        metadata: ImageMetadata | None,
    ) -> list[FusedConclusion]:
        """Produce a list of fused conclusions from heterogeneous evidence."""
        conclusions: list[FusedConclusion] = []

        # 1) Location conclusion
        conclusions.append(await self._fuse_location(scene, ocr_results, entities, search_results))

        # 2) Scene conclusion
        conclusions.append(await self._fuse_scene(scene, entities, search_results))

        # 3) Time conclusion
        if metadata and metadata.capture_time:
            conclusions.append(await self._fuse_time_from_exif(scene, metadata))
        elif scene.time_guess and scene.time_guess.time_of_day:
            conclusions.append(await self._fuse_time_from_vlm(scene))

        # 4) OCR-based text conclusions
        conclusions.extend(await self._fuse_ocr_texts(ocr_results, search_results))

        # Filter out empty / zero-probability conclusions
        return [c for c in conclusions if c.statement and c.probability > 0]

    # ------------------------------------------------------------------
    # Location fusion
    # ------------------------------------------------------------------

    async def _fuse_location(
        self,
        scene: SceneAnalysis,
        ocr_results: list[OCRResult],
        entities: EntityExtraction,
        search_results: list[SearchResult],
    ) -> FusedConclusion:
        evidence: list[EvidenceItem] = []

        # Gather location evidence from VLM
        if scene.location_guess:
            evidence.append(
                EvidenceItem(
                    source="vlm",
                    content=scene.location_guess.location,
                    confidence=scene.location_guess.confidence,
                )
            )

        # Gather evidence from OCR keywords that match landmarks
        for kw in entities.landmarks + entities.location_keywords:
            for ocr in ocr_results:
                if kw.lower() in ocr.text.lower():
                    evidence.append(
                        EvidenceItem(
                            source="ocr",
                            content=f"OCR detected '{kw}' in text '{ocr.text}'",
                            confidence=ocr.confidence,
                        )
                    )

        # Gather supporting search evidence
        for sr in search_results:
            if any(
                kw.lower() in sr.title.lower()
                for kw in entities.landmarks + entities.location_keywords
            ):
                evidence.append(
                    EvidenceItem(
                        source="search",
                        content=f"{sr.title}: {sr.snippet}",
                        confidence=sr.relevance,
                    )
                )

        if not evidence:
            return FusedConclusion(
                statement="无法确定拍摄地点",
                probability=0.1,
                evidence=[],
                category="location",
            )

        return await self._synthesize_conclusion("location", evidence, "拍摄地点")

    # ------------------------------------------------------------------
    # Scene fusion
    # ------------------------------------------------------------------

    async def _fuse_scene(
        self,
        scene: SceneAnalysis,
        entities: EntityExtraction,
        search_results: list[SearchResult],
    ) -> FusedConclusion:
        evidence: list[EvidenceItem] = []
        evidence.append(
            EvidenceItem(
                source="vlm",
                content=scene.description,
                confidence=0.7,
            )
        )
        if scene.scene_type:
            evidence.append(
                EvidenceItem(
                    source="scene",
                    content=f"场景类型: {scene.scene_type}",
                    confidence=0.75,
                )
            )
        for sr in search_results[:3]:
            evidence.append(
                EvidenceItem(
                    source="search",
                    content=f"{sr.title}: {sr.snippet}",
                    confidence=sr.relevance * 0.5,
                    supporting=True,
                )
            )

        return await self._synthesize_conclusion("scene", evidence, "场景内容")

    # ------------------------------------------------------------------
    # Time fusion
    # ------------------------------------------------------------------

    async def _fuse_time_from_exif(
        self, scene: SceneAnalysis, metadata: ImageMetadata
    ) -> FusedConclusion:
        evidence = [
            EvidenceItem(
                source="exif",
                content=f"EXIF 拍摄时间: {metadata.capture_time}",
                confidence=0.95,
            )
        ]
        if scene.time_guess and scene.time_guess.time_of_day:
            evidence.append(
                EvidenceItem(
                    source="vlm",
                    content=f"VLM 推测时段: {scene.time_guess.time_of_day}",
                    confidence=0.6,
                )
            )
        return await self._synthesize_conclusion("time", evidence, "拍摄时间")

    async def _fuse_time_from_vlm(self, scene: SceneAnalysis) -> FusedConclusion:
        tg = scene.time_guess
        if tg is None:
            return FusedConclusion(
                statement="无法确定拍摄时间",
                probability=0.0,
                evidence=[],
                category="time",
            )
        parts = [f"时段: {tg.time_of_day}"] if tg.time_of_day else []
        if tg.season:
            parts.append(f"季节: {tg.season}")
        if tg.year_estimate:
            parts.append(f"年份估计: {tg.year_estimate}")
        evidence = [
            EvidenceItem(
                source="vlm",
                content=", ".join(parts),
                confidence=0.5,
            )
        ]
        return await self._synthesize_conclusion("time", evidence, "拍摄时间推测")

    # ------------------------------------------------------------------
    # OCR text fusion
    # ------------------------------------------------------------------

    async def _fuse_ocr_texts(
        self,
        ocr_results: list[OCRResult],
        search_results: list[SearchResult],
    ) -> list[FusedConclusion]:
        """Create conclusions for notable OCR text detections."""
        conclusions: list[FusedConclusion] = []
        for ocr in ocr_results:
            evidence = [
                EvidenceItem(
                    source="ocr",
                    content=f"OCR: '{ocr.text}' (confidence={ocr.confidence:.2f})",
                    confidence=ocr.confidence,
                )
            ]
            # Check if any search result corroborates the OCR text
            for sr in search_results:
                if ocr.text.lower() in sr.title.lower() or ocr.text.lower() in sr.snippet.lower():
                    evidence.append(
                        EvidenceItem(
                            source="search",
                            content=f"{sr.title}: {sr.snippet}",
                            confidence=sr.relevance,
                        )
                    )

            conclusion = await self._synthesize_conclusion(
                "identity", evidence, f"文本 '{ocr.text}'"
            )
            conclusions.append(conclusion)
        return conclusions

    # ------------------------------------------------------------------
    # Synthesis engine (rule + LLM)
    # ------------------------------------------------------------------

    async def _synthesize_conclusion(
        self,
        category: str,
        evidence: list[EvidenceItem],
        label: str,
    ) -> FusedConclusion:
        """Apply the hybrid rule + LLM strategy to produce a conclusion."""
        start_time = time.time()
        steps = []
        strategy_used = "none"

        if not evidence:
            result = FusedConclusion(
                statement=f"无足够证据判断{label}",
                probability=0.0,
                evidence=[],
                category=category,
            )
            if self._verbose:
                self._reasoning_traces.append({
                    "conclusion_category": category,
                    "conclusion_statement": result.statement,
                    "final_probability": 0.0,
                    "steps": [],
                    "strategy_used": "none",
                    "total_duration_ms": int((time.time() - start_time) * 1000),
                })
            return result

        max_conf = max(e.confidence for e in evidence)

        # --- High confidence → rule-based direct verdict ---
        if max_conf >= _HIGH_CONFIDENCE_THRESHOLD:
            strategy_used = "rule"
            best = max(evidence, key=lambda e: e.confidence)
            supporting = [e for e in evidence if e.supporting]
            prob = self._weighted_probability(supporting)
            steps.append({
                "step_id": 1,
                "action": "rule_match",
                "description": f"High confidence match (>{_HIGH_CONFIDENCE_THRESHOLD})",
                "input_summary": f"{len(evidence)} evidence items, max confidence={max_conf:.2f}",
                "output_summary": f"Best match: [{best.source}] {best.content[:50]}...",
                "confidence_before": max_conf,
                "confidence_after": prob,
                "duration_ms": int((time.time() - start_time) * 1000),
                "metadata": {"best_source": best.source, "num_supporting": len(supporting)},
            })
            result = FusedConclusion(
                statement=f"{label}: {best.content}",
                probability=prob,
                evidence=evidence,
                category=category,
            )
        # --- Medium confidence → LLM-assisted reasoning ---
        elif max_conf >= _MEDIUM_CONFIDENCE_THRESHOLD and self._llm is not None:
            strategy_used = "llm"
            prompt = self._build_llm_prompt(category, evidence, label, verbose=self._verbose)
            try:
                llm_response, reasoning = await self._llm.infer_with_reasoning(prompt)
                prob = self._weighted_probability([e for e in evidence if e.supporting])
                prob = min(prob, 0.75)
                steps.append({
                    "step_id": 1,
                    "action": "llm_inference",
                    "description": "Medium confidence, using LLM for reasoning",
                    "input_summary": (
                        f"{len(evidence)} evidence items, max confidence={max_conf:.2f}"
                    ),
                    "output_summary": f"LLM response: {llm_response[:100]}...",
                    "confidence_before": max_conf,
                    "confidence_after": prob,
                    "duration_ms": int((time.time() - start_time) * 1000),
                    "metadata": {"llm_reasoning": reasoning, "prompt_length": len(prompt)},
                })
                result = FusedConclusion(
                    statement=f"{label} (LLM辅助): {llm_response}",
                    probability=prob,
                    evidence=evidence,
                    category=category,
                )
            except Exception as exc:
                logger.warning("LLM inference failed: %s", exc)
                strategy_used = "fallback"
                steps.append({
                    "step_id": 1,
                    "action": "llm_failed",
                    "description": "LLM inference failed, falling back to uncertain",
                    "input_summary": f"{len(evidence)} evidence items",
                    "output_summary": str(exc),
                    "confidence_before": max_conf,
                    "confidence_after": max_conf * 0.5,
                    "duration_ms": int((time.time() - start_time) * 1000),
                    "metadata": {"error": str(exc)},
                })
                result = FusedConclusion(
                    statement=f"{label}: 证据不足，无法确定",
                    probability=max_conf * 0.5,
                    evidence=evidence,
                    category=category,
                )
        # --- Low confidence / no LLM → mark uncertain ---
        else:
            strategy_used = "uncertain"
            steps.append({
                "step_id": 1,
                "action": "low_confidence",
                "description": (
                    f"Low confidence (<{_MEDIUM_CONFIDENCE_THRESHOLD}), "
                    "no LLM available"
                ),
                "input_summary": f"{len(evidence)} evidence items, max confidence={max_conf:.2f}",
                "output_summary": "Marked as uncertain",
                "confidence_before": max_conf,
                "confidence_after": max_conf * 0.5,
                "duration_ms": int((time.time() - start_time) * 1000),
                "metadata": {},
            })
            result = FusedConclusion(
                statement=f"{label}: 证据不足，无法确定",
                probability=max_conf * 0.5,
                evidence=evidence,
                category=category,
            )

        # Record reasoning trace if verbose
        if self._verbose:
            self._reasoning_traces.append({
                "conclusion_category": category,
                "conclusion_statement": result.statement,
                "final_probability": result.probability,
                "steps": steps,
                "strategy_used": strategy_used,
                "total_duration_ms": int((time.time() - start_time) * 1000),
            })

        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _weighted_probability(evidence: list[EvidenceItem]) -> float:
        """Compute a weighted probability from supporting evidence.

        Uses the formula: 1 - ∏(1 - c_i)  (probabilistic OR).
        """
        if not evidence:
            return 0.0
        complement = 1.0
        for e in evidence:
            complement *= 1.0 - e.confidence
        return min(1.0 - complement, 1.0)

    @staticmethod
    def _build_llm_prompt(
        category: str,
        evidence: list[EvidenceItem],
        label: str,
        verbose: bool = False,
    ) -> str:
        lines = [
            f"你是一个图片分析助手。请根据以下证据，对「{label}」给出最可能的结论。",
            f"类别: {category}",
            "证据列表:",
        ]
        for i, e in enumerate(evidence, 1):
            lines.append(f"  {i}. [{e.source}] {e.content} (置信度={e.confidence:.2f})")
        if verbose:
            lines.append("请用一句话回答结论，然后另起一行以'推理过程:'开头，详细说明你的推理步骤。")
        else:
            lines.append("请用一句话回答，不要解释推理过程。")
        return "\n".join(lines)
