"""测试数据工厂 — 集中管理 mock 数据

对比 TravelAgent 的 fixtures.ts，为所有 Pydantic 模型提供 create_mock_* 工厂函数。
变更 schema 时只需更新此文件。
"""

from __future__ import annotations

from vision_insight.models.schemas import (
    AnalysisReport,
    AnalysisStatus,
    DetectedObject,
    EntityExtraction,
    EvidenceItem,
    FusedConclusion,
    ImageMetadata,
    LocationGuess,
    OCRResult,
    PeopleInfo,
    SceneAnalysis,
    SearchResult,
    TimeGuess,
)

# ─── 基础工厂 ──────────────────────────────────────────────


def create_mock_ocr_result(
    text: str = "Shibuya 109",
    confidence: float = 0.95,
    bbox: list[list[int]] | None = None,
    **overrides,
) -> OCRResult:
    defaults = {
        "text": text,
        "bbox": bbox or [[0, 0], [100, 0], [100, 30], [0, 30]],
        "confidence": confidence,
    }
    defaults.update(overrides)
    return OCRResult(**defaults)


def create_mock_image_metadata(
    width: int = 1920,
    height: int = 1080,
    format: str = "JPEG",
    **overrides,
) -> ImageMetadata:
    defaults = {
        "width": width,
        "height": height,
        "format": format,
        "file_size": 204800,
        "exif": {},
        "gps": None,
        "capture_time": None,
    }
    defaults.update(overrides)
    return ImageMetadata(**defaults)


def create_mock_location_guess(
    location: str = "东京涩谷",
    confidence: float = 0.82,
    evidence: list[str] | None = None,
    **overrides,
) -> LocationGuess:
    defaults = {
        "location": location,
        "confidence": confidence,
        "evidence": evidence or ["日文招牌", "涩谷109", "JR标识"],
    }
    defaults.update(overrides)
    return LocationGuess(**defaults)


def create_mock_time_guess(
    time_of_day: str = "夜晚",
    season: str = "冬季",
    year_estimate: str = "2024",
    **overrides,
) -> TimeGuess:
    defaults = {
        "time_of_day": time_of_day,
        "season": season,
        "year_estimate": year_estimate,
    }
    defaults.update(overrides)
    return TimeGuess(**defaults)


def create_mock_people_info(
    count: int = 3,
    age_group: str = "年轻成年人",
    activity: str = "聚餐",
    **overrides,
) -> PeopleInfo:
    defaults = {"count": count, "age_group": age_group, "activity": activity}
    defaults.update(overrides)
    return PeopleInfo(**defaults)


def create_mock_scene_analysis(
    scene_type: str = "commercial_street",
    description: str = "日本商业街夜景",
    **overrides,
) -> SceneAnalysis:
    defaults = {
        "scene_type": scene_type,
        "description": description,
        "location_guess": create_mock_location_guess(),
        "time_guess": create_mock_time_guess(),
        "people": [create_mock_people_info()],
        "key_evidence": ["日文招牌", "涩谷109建筑"],
        "uncertainties": ["具体街道不确定"],
    }
    defaults.update(overrides)
    return SceneAnalysis(**defaults)


def create_mock_detected_object(
    label: str = "building",
    confidence: float = 0.9,
    category: str = "building",
    **overrides,
) -> DetectedObject:
    defaults = {
        "label": label,
        "confidence": confidence,
        "bbox": [100, 100, 500, 400],
        "category": category,
    }
    defaults.update(overrides)
    return DetectedObject(**defaults)


def create_mock_entity_extraction(
    location_keywords: list[str] | None = None,
    brands: list[str] | None = None,
    landmarks: list[str] | None = None,
    **overrides,
) -> EntityExtraction:
    defaults = {
        "location_keywords": location_keywords or ["Shibuya", "涩谷"],
        "brands": brands or ["109", "UNIQLO"],
        "landmarks": landmarks or ["涩谷109"],
        "text_entities": [],
    }
    defaults.update(overrides)
    return EntityExtraction(**defaults)


def create_mock_search_result(
    query: str = "Shibuya 109",
    source: str = "wikipedia",
    title: str = "涩谷109",
    relevance: float = 0.8,
    **overrides,
) -> SearchResult:
    defaults = {
        "query": query,
        "source": source,
        "title": title,
        "snippet": "涩谷109是东京涩谷的标志性购物中心",
        "url": "https://zh.wikipedia.org/wiki/109",
        "relevance": relevance,
    }
    defaults.update(overrides)
    return SearchResult(**defaults)


def create_mock_evidence_item(
    source: str = "ocr",
    content: str = "OCR detected 'Shibuya'",
    confidence: float = 0.95,
    **overrides,
) -> EvidenceItem:
    defaults = {
        "source": source,
        "content": content,
        "confidence": confidence,
        "supporting": True,
    }
    defaults.update(overrides)
    return EvidenceItem(**defaults)


def create_mock_fused_conclusion(
    statement: str = "拍摄地点: 东京涩谷",
    probability: float = 0.82,
    category: str = "location",
    **overrides,
) -> FusedConclusion:
    defaults = {
        "statement": statement,
        "probability": probability,
        "evidence": [create_mock_evidence_item()],
        "category": category,
    }
    defaults.update(overrides)
    return FusedConclusion(**defaults)


def create_mock_analysis_report(
    report_id: str = "test-001",
    status: AnalysisStatus = AnalysisStatus.COMPLETED,
    **overrides,
) -> AnalysisReport:
    defaults = {
        "id": report_id,
        "status": status,
        "image_metadata": create_mock_image_metadata(),
        "scene_analysis": create_mock_scene_analysis(),
        "ocr_results": [
            create_mock_ocr_result("Shibuya", 0.98),
            create_mock_ocr_result("109", 0.95),
        ],
        "detected_objects": [create_mock_detected_object()],
        "entities": create_mock_entity_extraction(),
        "search_results": [create_mock_search_result()],
        "conclusions": [
            create_mock_fused_conclusion("拍摄地点: 东京涩谷", 0.82, "location"),
            create_mock_fused_conclusion("场景: 商业街夜景", 0.75, "scene"),
        ],
        "report_markdown": "",
        "processing_time_ms": 3500,
    }
    defaults.update(overrides)
    return AnalysisReport(**defaults)


# ─── 场景工厂 (多步骤测试) ─────────────────────────────────


def create_shibuya_scenario() -> dict:
    """涩谷商业街场景 — 完整分析数据集"""
    return {
        "ocr_results": [
            create_mock_ocr_result("Shibuya", 0.98),
            create_mock_ocr_result("109", 0.95),
            create_mock_ocr_result("UNIQLO", 0.92),
        ],
        "scene": create_mock_scene_analysis(
            location_guess=create_mock_location_guess("东京涩谷", 0.82),
        ),
        "entities": create_mock_entity_extraction(
            location_keywords=["Shibuya", "涩谷"],
            brands=["109", "UNIQLO"],
            landmarks=["涩谷109"],
        ),
        "search_results": [
            create_mock_search_result("涩谷109", "wikipedia", "涩谷109"),
            create_mock_search_result("Shibuya", "google", "Shibuya - Tokyo"),
        ],
    }


def create_unknown_scenario() -> dict:
    """无法识别的场景 — 低置信度数据集"""
    return {
        "ocr_results": [],
        "scene": create_mock_scene_analysis(
            scene_type="unknown",
            description="模糊的室内场景",
            location_guess=create_mock_location_guess("未知", 0.2, []),
            time_guess=create_mock_time_guess("", "", ""),
            people=[],
            key_evidence=[],
            uncertainties=["无法识别具体场景", "无文字信息"],
        ),
        "entities": create_mock_entity_extraction(location_keywords=[], brands=[], landmarks=[]),
        "search_results": [],
    }
