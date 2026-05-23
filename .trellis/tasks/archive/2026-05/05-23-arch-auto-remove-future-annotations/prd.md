# PRD: Remove unnecessary `from __future__ import annotations`

## Category
debt

## Context
The project requires Python 3.11+ (`requires-python = ">=3.11"` in pyproject.toml). The `from __future__ import annotations` import (PEP 563) is only needed for Python 3.9- to enable PEP 604 (`X | Y`) and PEP 585 (`list[x]`) syntax at runtime. In Python 3.10+, these are native features and the import is unnecessary.

However, some files use forward references (e.g., class referencing itself in type annotations) or `TYPE_CHECKING` imports that require the future annotations import. These files MUST keep the import.

## What to Change
Remove `from __future__ import annotations` from this file:
1. `src/vision_insight/services/vlm/prompts.py` — only uses TYPE_CHECKING for imports, no forward references

## Files That MUST Keep the Import
These files use forward references or TYPE_CHECKING patterns that require the import:
- `src/vision_insight/utils/__init__.py` — uses TYPE_CHECKING imports in function signatures
- `src/vision_insight/models/schemas.py` — uses forward references to classes defined later
- `src/vision_insight/services/ocr/baidu_service.py` — uses forward reference to BaiduOCRService
- `src/vision_insight/services/ocr/paddle_service.py` — uses forward reference to PaddleOCRService

## Why
- Reduces unnecessary imports (code cleanliness)
- The `prompts.py` file only uses TYPE_CHECKING for imports but doesn't need the future annotations import since it doesn't use forward references in runtime-evaluated positions

## Acceptance Criteria
1. `ruff check src/vision_insight/` passes with no new errors
2. `mypy src/vision_insight/` passes with no new errors
3. `pytest tests/` passes
4. No functional changes to behavior

## Scope
Only `src/vision_insight/services/vlm/prompts.py`. No other changes.

## Risk Assessment
None — removing the import from prompts.py has no effect since it doesn't use forward references.

## Evidence
- `pyproject.toml` line 4: `requires-python = ">=3.11"`
- `prompts.py` only uses TYPE_CHECKING for OCRResult import, which is used in a function signature that's evaluated at runtime (not a forward reference)
