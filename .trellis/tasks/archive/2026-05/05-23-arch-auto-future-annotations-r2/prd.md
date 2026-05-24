# PRD: Remove Unnecessary `from __future__ import annotations`

## Category
debt / dead code cleanup

## Problem
5 files still have `from __future__ import annotations` which is unnecessary for Python 3.11+:
- `src/vision_insight/models/schemas.py:3`
- `src/vision_insight/services/vlm/prompts.py:3`
- `src/vision_insight/services/ocr/baidu_service.py:10`
- `src/vision_insight/services/ocr/paddle_service.py:3`
- `src/vision_insight/utils/__init__.py:3`

These files use `X | Y`, `list[x]`, `dict[x]` syntax which is native in Python 3.10+. No forward references exist.

## What to Change
Remove `from __future__ import annotations` from all 5 files.

## Acceptance Criteria
- `ruff check src/` passes
- `pytest tests/ -x` passes
- No functional changes

## Scope
- `src/vision_insight/models/schemas.py`
- `src/vision_insight/services/vlm/prompts.py`
- `src/vision_insight/services/ocr/baidu_service.py`
- `src/vision_insight/services/ocr/paddle_service.py`
- `src/vision_insight/utils/__init__.py`
