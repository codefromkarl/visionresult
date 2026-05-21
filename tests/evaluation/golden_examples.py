"""黄金数据集 — AI E2E 评估基准

对比 TravelAgent 的 golden-examples.ts。
每个场景定义输入图片特征、期望分析结果和验证函数。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GoldenExample:
    """黄金测试场景"""
    id: str
    description: str
    # 输入特征（模拟 OCR + VLM 输出）
    ocr_texts: list[str]
    expected_scene_type: str
    expected_location: str | None = None
    expected_location_keywords: list[str] = field(default_factory=list)
    expected_brands: list[str] = field(default_factory=list)
    expected_landmarks: list[str] = field(default_factory=list)
    # 期望置信度范围
    min_location_confidence: float = 0.0
    max_location_confidence: float = 1.0
    # 自定义验证
    validation_fn: object = None  # Callable[[AnalysisReport], tuple[bool, str]]


# ─── 黄金场景定义 ──────────────────────────────────────────


GOLDEN_EXAMPLES: list[GoldenExample] = [
    # === 场景 1: 日本商业街（高置信度） ===
    GoldenExample(
        id="shibuya-night",
        description="东京涩谷商业街夜景 — 高置信度地点识别",
        ocr_texts=["Shibuya", "109", "UNIQLO", "JR"],
        expected_scene_type="commercial_street",
        expected_location="东京涩谷",
        expected_location_keywords=["Shibuya", "涩谷", "东京"],
        expected_brands=["109", "UNIQLO"],
        expected_landmarks=["涩谷109"],
        min_location_confidence=0.7,
    ),

    # === 场景 2: 中国城市街景 ===
    GoldenExample(
        id="beijing-street",
        description="北京王府井步行街 — 中文 OCR 识别",
        ocr_texts=["王府井", "北京烤鸭", "百货大楼"],
        expected_scene_type="commercial_street",
        expected_location="北京王府井",
        expected_location_keywords=["王府井", "北京"],
        expected_brands=[],
        expected_landmarks=["王府井百货大楼"],
        min_location_confidence=0.6,
    ),

    # === 场景 3: 室内场景（低置信度） ===
    GoldenExample(
        id="indoor-unknown",
        description="普通室内场景 — 无地标，低置信度",
        ocr_texts=[],
        expected_scene_type="indoor",
        expected_location=None,
        expected_location_keywords=[],
        expected_brands=[],
        expected_landmarks=[],
        max_location_confidence=0.3,
    ),

    # === 场景 4: 自然风景 ===
    GoldenExample(
        id="mountain-landscape",
        description="山景照片 — 无文字，场景类型识别",
        ocr_texts=[],
        expected_scene_type="landscape",
        expected_location=None,
        expected_location_keywords=[],
        min_location_confidence=0.0,
        max_location_confidence=0.4,
    ),

    # === 场景 5: UI 截图 ===
    GoldenExample(
        id="ui-screenshot",
        description="手机 UI 截图 — 应用名称识别",
        ocr_texts=["微信", "发现", "朋友圈", "扫一扫"],
        expected_scene_type="ui_screenshot",
        expected_location=None,
        expected_brands=["微信"],
        expected_location_keywords=[],
        max_location_confidence=0.1,
    ),

    # === 场景 6: 餐厅场景 ===
    GoldenExample(
        id="restaurant-scene",
        description="餐厅内景 — 品牌和菜系识别",
        ocr_texts=["海底捞", "火锅", "排队等位"],
        expected_scene_type="restaurant",
        expected_location=None,
        expected_brands=["海底捞"],
        expected_location_keywords=[],
        min_location_confidence=0.0,
    ),

    # === 场景 7: 交通枢纽 ===
    GoldenExample(
        id="train-station",
        description="火车站场景 — 站名和线路识别",
        ocr_texts=["上海虹桥", "G1234", "候车室", "检票口"],
        expected_scene_type="transportation",
        expected_location="上海虹桥站",
        expected_location_keywords=["上海", "虹桥"],
        expected_landmarks=["上海虹桥站"],
        min_location_confidence=0.7,
    ),

    # === 场景 8: 游戏截图 ===
    GoldenExample(
        id="game-screenshot",
        description="游戏截图 — 非真实世界场景",
        ocr_texts=["HP", "MP", "Lv.99", "攻击力"],
        expected_scene_type="game_screenshot",
        expected_location=None,
        expected_location_keywords=[],
        max_location_confidence=0.05,
    ),
]


def get_example_by_id(example_id: str) -> GoldenExample | None:
    """按 ID 获取黄金场景。"""
    for ex in GOLDEN_EXAMPLES:
        if ex.id == example_id:
            return ex
    return None


def get_all_example_ids() -> list[str]:
    """获取所有黄金场景 ID。"""
    return [ex.id for ex in GOLDEN_EXAMPLES]
