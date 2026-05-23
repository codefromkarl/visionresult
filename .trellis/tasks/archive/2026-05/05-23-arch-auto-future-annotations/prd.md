# PRD: Remove unnecessary `from __future__ import annotations`

## Category
DEBT

## Problem
The project requires Python >=3.11 (per `pyproject.toml`), which natively supports PEP 604 union
types (`X | Y`) and most annotation expressions. The `from __future__ import annotations` import
was needed for Python 3.9/3.10 compatibility but is now unnecessary in most files.

3 files still need it due to forward references:
- `models/schemas.py` — `SceneAnalysis` uses `LocationGuess`, `TimeGuess`, `PeopleInfo` before definition
- `services/ocr/baidu_service.py` — self-referencing return type
- `services/ocr/paddle_service.py` — self-referencing return type

## Solution
Remove `from __future__ import annotations` from 25 files that don't need it.
Keep it in the 3 files that have forward references.

## Changes
1. Remove `from __future__ import annotations` from 25 files
2. Keep in `schemas.py`, `baidu_service.py`, `paddle_service.py`

## Acceptance criteria
- `ruff check src/` passes
- `mypy src/vision_insight` passes
- `pytest tests/ -x -q` passes

## Scope
- All `.py` files under `src/vision_insight/`

## No functional changes
