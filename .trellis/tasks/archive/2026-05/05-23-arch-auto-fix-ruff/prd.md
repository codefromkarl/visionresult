# PRD: Fix Ruff Lint Violations

## Category: debt

## What to change and why

Three ruff lint violations exist in the codebase:
1. `src/vision_insight/api/routes.py:213` — E501 line too long (106 > 100)
2. `src/vision_insight/api/routes.py:546` — UP041 aliased errors with TimeoutError
3. `src/vision_insight/pipeline/runner.py:3` — I001 unsorted import block

Evidence: `ruff check src/` output.

## Acceptance criteria
- `ruff check src/` passes with 0 errors
- `ruff format --check src/` passes
- Existing tests pass: `python -m pytest tests/ -x -q`

## Scope
- `src/vision_insight/api/routes.py` (lines 213, 546)
- `src/vision_insight/pipeline/runner.py` (line 3)

## No functional changes
This is purely a standards compliance fix. No behavior changes.
