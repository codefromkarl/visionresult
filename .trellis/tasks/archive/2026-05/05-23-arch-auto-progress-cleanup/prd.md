# PRD: Fix unbounded _progress memory leak

## Category
PERF/MEMORY

## Problem
The `_progress` dict in `src/vision_insight/api/routes.py` grows without bound. Under sustained load, old entries are never cleaned up, causing a memory leak.

## Evidence
- File: `src/vision_insight/api/routes.py:39`
- The dict is populated in `_run_analysis()` (line 229) and never cleaned up
- Only the final `("done", 100)` is appended in the finally block, but entries are never removed

## Solution
Add TTL-based cleanup to remove entries older than 1 hour. Implement a background task or cleanup-on-access pattern.

## Changes
1. Add a `_cleanup_progress()` function that removes entries older than 1 hour
2. Call this function periodically or before adding new entries
3. Keep the existing API contract unchanged

## Acceptance Criteria
- [ ] Ruff lint passes: `ruff check src/`
- [ ] Tests pass: `pytest tests/unit/ -q`
- [ ] No functional changes to API behavior
- [ ] Memory usage remains bounded under sustained load

## Scope
Only modify `src/vision_insight/api/routes.py`

## Statement
No functional changes — only memory management improvement.
