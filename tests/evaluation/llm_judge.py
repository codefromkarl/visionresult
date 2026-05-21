"""LLM-as-Judge 评估器

对比 TravelAgent 的 llmJudgeReasonableness。
使用 LLM 对分析报告进行语义质量评分（soft report，不作为 fail 条件）。
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


@dataclass
class JudgeResult:
    """LLM 评估结果"""

    dimension: str
    score: float  # 0-1
    reason: str
    passed: bool  # True = 不阻塞


# ─── LLM 调用 ──────────────────────────────────────────


async def _call_llm(prompt: str, api_key: str | None = None) -> str:
    """调用 LLM API 获取评估结果。"""
    key = api_key or os.getenv("VIA_OPENAI_API_KEY", "")
    if not key:
        raise ValueError("No API key available")

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {
                        "role": "system",
                        "content": "你是一个图片分析质量评审专家。只返回 JSON 格式的评分结果。",
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.1,
                "max_tokens": 200,
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


# ─── 评估维度 ──────────────────────────────────────────


async def judge_location_accuracy(
    report_markdown: str,
    ocr_texts: list[str],
    api_key: str | None = None,
) -> JudgeResult:
    """评估地点推测的准确性。"""
    prompt = f"""请评估以下图片分析报告中地点推测的合理性（1-5 分）。

OCR 检测到的文字: {ocr_texts}

分析报告:
{report_markdown[:1500]}

评分标准:
- 5分：地点推测有充分证据，OCR/地标/品牌一致
- 4分：推测合理，证据基本充分
- 3分：推测可能正确，但证据不足
- 2分：推测缺乏依据
- 1分：推测明显错误或无依据

只返回 JSON: {{"score": <1-5>, "reason": "<简短说明>"}}"""

    try:
        response = await _call_llm(prompt, api_key)
        parsed = json.loads(response.strip().strip("`").replace("json\n", ""))
        score = float(parsed.get("score", 0)) / 5.0
        return JudgeResult(
            dimension="地点准确性",
            score=min(score, 1.0),
            reason=parsed.get("reason", ""),
            passed=True,  # soft report
        )
    except Exception as e:
        logger.warning("LLM Judge 失败: %s", e)
        return JudgeResult(
            dimension="地点准确性",
            score=0.0,
            reason=f"评估失败: {e}",
            passed=True,
        )


async def judge_report_completeness(
    report_markdown: str,
    api_key: str | None = None,
) -> JudgeResult:
    """评估报告完整性。"""
    prompt = f"""请评估以下图片分析报告的完整性（1-5 分）。

分析报告:
{report_markdown[:1500]}

评分标准:
- 5分：包含场景、地点、时间、人物、OCR、证据链，结构清晰
- 4分：主要维度齐全，个别缺失
- 3分：基本框架有，但多个维度缺失
- 2分：只有简单描述
- 1分：几乎无有效信息

只返回 JSON: {{"score": <1-5>, "reason": "<简短说明>"}}"""

    try:
        response = await _call_llm(prompt, api_key)
        parsed = json.loads(response.strip().strip("`").replace("json\n", ""))
        score = float(parsed.get("score", 0)) / 5.0
        return JudgeResult(
            dimension="报告完整性",
            score=min(score, 1.0),
            reason=parsed.get("reason", ""),
            passed=True,
        )
    except Exception as e:
        logger.warning("LLM Judge 失败: %s", e)
        return JudgeResult(
            dimension="报告完整性",
            score=0.0,
            reason=f"评估失败: {e}",
            passed=True,
        )


async def judge_evidence_quality(
    conclusions_json: list[dict],
    api_key: str | None = None,
) -> JudgeResult:
    """评估证据链质量。"""
    prompt = f"""请评估以下图片分析的证据链质量（1-5 分）。

结论列表:
{json.dumps(conclusions_json, ensure_ascii=False, indent=2)[:1000]}

评分标准:
- 5分：每个结论有明确证据来源，证据与结论逻辑一致
- 4分：大部分结论有证据，逻辑基本一致
- 3分：部分结论缺证据
- 2分：证据与结论不一致
- 1分：无证据或证据完全不相关

只返回 JSON: {{"score": <1-5>, "reason": "<简短说明>"}}"""

    try:
        response = await _call_llm(prompt, api_key)
        parsed = json.loads(response.strip().strip("`").replace("json\n", ""))
        score = float(parsed.get("score", 0)) / 5.0
        return JudgeResult(
            dimension="证据链质量",
            score=min(score, 1.0),
            reason=parsed.get("reason", ""),
            passed=True,
        )
    except Exception as e:
        logger.warning("LLM Judge 失败: %s", e)
        return JudgeResult(
            dimension="证据链质量",
            score=0.0,
            reason=f"评估失败: {e}",
            passed=True,
        )


# ─── 综合 LLM 评估 ──────────────────────────────────────


async def llm_judge_report(
    report_markdown: str,
    ocr_texts: list[str],
    conclusions_json: list[dict],
    api_key: str | None = None,
) -> list[JudgeResult]:
    """综合 LLM 评估（所有维度）。"""
    results: list[JudgeResult] = []

    results.append(await judge_location_accuracy(report_markdown, ocr_texts, api_key))
    results.append(await judge_report_completeness(report_markdown, api_key))
    results.append(await judge_evidence_quality(conclusions_json, api_key))

    return results
