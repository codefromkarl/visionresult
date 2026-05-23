# PRD: Extract shared prompt templates

## Category
DEBT

## Problem
Both `api_service.py` and `zhipu_service.py` define identical `OBJECT_DETECTION_PROMPT_ZH` and `OBJECT_DETECTION_PROMPT_EN` templates. This is duplication that should be shared.

## Evidence
- File: `src/vision_insight/services/vlm/api_service.py:85-105`
- File: `src/vision_insight/services/vlm/zhipu_service.py:45-65`
- Both files define identical prompt templates

## Solution
Extract shared prompt templates to a common module.

## Changes
1. Create `src/vision_insight/services/vlm/prompts.py`
2. Move shared prompt templates to the new file
3. Update imports in both service files

## Acceptance Criteria
- [ ] Ruff lint passes: `ruff check src/`
- [ ] Tests pass: `pytest tests/unit/ -q`
- [ ] No functional changes to API behavior
- [ ] Prompt templates are shared and reusable

## Scope
Only modify `src/vision_insight/services/vlm/api_service.py`, `src/vision_insight/services/vlm/zhipu_service.py`, and create `src/vision_insight/services/vlm/prompts.py`

## Statement
No functional changes — only code deduplication.
