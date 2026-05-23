# PRD: Remove unused `_WIKIPEDIA_API` constant

## Category
debt

## Context
The `_WIKIPEDIA_API` constant is defined at line 17 of `http_search_service.py` but never used. The actual Wikipedia URLs are constructed dynamically in the `_search_wikipedia()` method.

## What to Change
Remove the unused `_WIKIPEDIA_API` constant from `src/vision_insight/services/search/http_search_service.py:17`.

## Why
- Removes dead code
- Reduces confusion about which Wikipedia API URL is actually used

## Acceptance Criteria
1. `ruff check src/vision_insight/` passes
2. `pytest tests/` passes
3. No functional changes to behavior

## Scope
Only `src/vision_insight/services/search/http_search_service.py`. No other changes.

## Risk Assessment
None — removing unused constant.

## Evidence
- `rg -n '_WIKIPEDIA_API' src/vision_insight/` shows only the definition, no usage
