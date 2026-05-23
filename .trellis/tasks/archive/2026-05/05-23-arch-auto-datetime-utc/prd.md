# PRD: Add UTC Timezone to datetime.now()

## Category
debt

## Problem
8 instances of `datetime.now()` without timezone info in `routes.py` and `database.py`. The `event_logger.py` already uses `datetime.now(UTC)` correctly, creating inconsistency. Naive datetimes can cause bugs when compared with timezone-aware ones.

## What to change
1. Add `from datetime import UTC` to routes.py
2. Replace all `datetime.now()` with `datetime.now(UTC)` in routes.py and database.py

## Evidence
- `routes.py` lines 146, 163, 224, 262, 315, 368, 503
- `database.py` line 257

## Acceptance criteria
- [ ] All `datetime.now()` calls include `UTC` parameter
- [ ] `ruff check` passes
- [ ] `mypy` passes
- [ ] All existing tests pass
- [ ] No functional changes — identical behavior

## Scope
- `src/vision_insight/api/routes.py`
- `src/vision_insight/core/database.py`

## Statement
No functional changes. Consistent timezone handling across the codebase.
