# PRD: Move Inline Imports to Module Level

## Category
debt

## Problem
6 inline imports inside function bodies in `routes.py`:
- `from vision_insight.models.schemas import ...` at line ~116 (inside `_record_to_report`)
- `import httpx` at line ~352 (inside `create_analysis_from_url`)
- `from vision_insight.services.report...` at line ~403 (inside `get_report`)
- `from vision_insight.core.event_logger import ...` at line ~520 (inside `stream_progress`)
- `from vision_insight.core.event_logger import ...` at line ~597 (inside `get_task_events`)

The original reason for inline imports (avoiding circular deps) is no longer valid since the module structure is stable.

## What to change
1. Move all inline imports to the module top level
2. Remove any duplicate imports (e.g., `import json` was already removed in P0-1)

## Evidence
- `routes.py` lines 116, 352, 403, 520, 597

## Acceptance criteria
- [ ] All imports are at module level
- [ ] No inline imports remain
- [ ] `ruff check` passes
- [ ] `mypy` passes
- [ ] All existing tests pass
- [ ] No functional changes

## Scope
- `src/vision_insight/api/routes.py`

## Statement
No functional changes. Cleaner code, consistent import style.
