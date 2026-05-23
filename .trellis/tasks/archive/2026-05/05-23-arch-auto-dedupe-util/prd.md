# P0-2: Extract Shared Dedupe Utility

## Category
debt

## Problem
`fallback.py:111-120` defines `_dedupe()`. `llm_entity_service.py:108-120` has identical inline deduplication logic. Both also share the same OCR confidence >= 0.8 filtering pattern.

## What to Change
1. Move `_dedupe()` to `utils/__init__.py`
2. Import in `fallback.py` and `llm_entity_service.py`
3. Remove duplicate inline code

## Scope
- `src/vision_insight/utils/__init__.py`
- `src/vision_insight/services/fallback.py`
- `src/vision_insight/services/entity/llm_entity_service.py`

## Acceptance Criteria
- `ruff check` passes
- `mypy` passes
- `pytest` passes
- No functional changes
