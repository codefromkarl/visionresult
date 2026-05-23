"""Shared prompt templates and helpers for VLM services."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vision_insight.models.schemas import OCRResult


def build_ocr_context(ocr_results: list[OCRResult] | None, lang: str = "zh") -> str:
    """Build OCR context string for scene analysis prompts.

    Args:
        ocr_results: OCR results from the image.
        lang: Output language - 'zh' for Chinese, 'en' for English.

    Returns:
        Formatted OCR context string, or empty string if no results.
    """
    if not ocr_results:
        return ""
    texts = [r.text for r in ocr_results]
    if lang == "en":
        return f"\nOCR detected these texts: {texts}\n"
    return f"\n图片中检测到的文字:{texts}\n"


# ---------------------------------------------------------------------------
# Scene analysis prompts (shared across all VLM providers)
# ---------------------------------------------------------------------------

SCENE_ANALYSIS_PROMPT_ZH = """\
你是一个视觉场景分析师。请仔细分析这张图片。

重要规则:
1. 只返回有效的JSON对象,不要markdown,不要额外文本。
2. "scene_type" 必须是以下之一:indoor, outdoor, street, restaurant, office, home, transport,
   event, nature, unknown
3. "description" 用中文写2-4个不重复的句子描述场景。
4. "location_guess.location" 用中文写具体地点(如"东京涩谷"、"北京故宫"),不要写大洲或地区。
5. "time_guess.time_of_day" 必须是以下之一:morning, afternoon, evening, night
6. "time_guess.season" 必须是以下之一:spring, summer, autumn, winter
7. 所有文字描述(description, evidence, key_evidence, uncertainties)都用中文。

返回这个JSON结构:
{{
  "scene_type": "<indoor|outdoor|street|restaurant|office|home|transport|event|nature|unknown>",
  "description": "<用中文描述场景>"
  "location_guess": {{
    "location": "<用中文写具体地点>",
    "confidence": <0.0-1.0>,
    "evidence": ["<视觉线索1>", "<视觉线索2>"]
  }},
  "time_guess": {{
    "time_of_day": "<morning|afternoon|evening|night>",
    "season": "<spring|summer|autumn|winter>",
    "year_estimate": "<如 2020s, 2024>",
    "evidence": ["<时间线索1>"]
  }},
  "people": [
    {{
      "count": <int>,
      "age_group": "<young|middle-aged|elderly>",
      "activity": "<用中文描述活动>"
    }}
  ],
  "key_evidence": ["<重要的视觉细节1>", "<重要的视觉细节2>"],
  "uncertainties": ["<不确定的地方>"]
}}

{ocr_context}"""

SCENE_ANALYSIS_PROMPT_EN = """\
You are a visual scene analyst. Carefully analyze this image.

Important rules:
1. Return ONLY a valid JSON object. No markdown, no extra text.
2. "scene_type" must be one of: indoor, outdoor, street, restaurant, office, home, transport,
   event, nature, unknown
3. "description" must be 2-4 sentences in English.
4. "location_guess.location" must be a specific place in English.
5. "time_guess.time_of_day" must be one of: morning, afternoon, evening, night
6. "time_guess.season" must be one of: spring, summer, autumn, winter
7. All text fields must be in English.

Return this JSON structure:
{{
  "scene_type": "<indoor|outdoor|street|restaurant|office|home|transport|event|nature|unknown>",
  "description": "<describe scene in English>"
  "location_guess": {{
    "location": "<specific location in English>",
    "confidence": <0.0-1.0>,
    "evidence": ["<visual clue 1>", "<visual clue 2>"]
  }},
  "time_guess": {{
    "time_of_day": "<morning|afternoon|evening|night>",
    "season": "<spring|summer|autumn|winter>",
    "year_estimate": "<e.g. 2020s, 2024>",
    "evidence": ["<time clue 1>"]
  }},
  "people": [
    {{
      "count": <int>,
      "age_group": "<young|middle-aged|elderly>",
      "activity": "<describe activity in English>"
    }}
  ],
  "key_evidence": ["<important detail 1>", "<important detail 2>"],
  "uncertainties": ["<uncertain aspects>"]
}}

{ocr_context}"""

# ---------------------------------------------------------------------------
# Object detection prompts (shared across all VLM providers)
# ---------------------------------------------------------------------------

OBJECT_DETECTION_PROMPT_ZH = """\
检测这张图片中的所有显著对象。返回一个 JSON 数组(纯 JSON,不要 markdown):

[
  {{
    "label": "<对象名称>",
    "confidence": <0.0-1.0>,
    "bbox": [x1, y1, x2, y2],
    "category": "<person|building|food|logo|vehicle|text|sign|other>"
  }}
]

如果没有可检测的对象,返回空数组 []。"""

OBJECT_DETECTION_PROMPT_EN = """\
Detect all notable objects in this image. Return a JSON array (no markdown, pure JSON):

[
  {{
    "label": "<object name>",
    "confidence": <0.0-1.0>,
    "bbox": [x1, y1, x2, y2],
    "category": "<person|building|food|logo|vehicle|text|sign|other>"
  }}
]

If no objects are detectable, return an empty array []."""
