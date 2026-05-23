"""JSON parsing helpers for LLM responses."""

import json
from typing import Any


def parse_llm_json(text: str) -> Any:
    """Extract JSON from model response, handling markdown fences."""
    text = text.strip()
    # Strip ```json ... ``` wrappers
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last lines (the fences)
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        text = "\n".join(lines)
    return json.loads(text)
