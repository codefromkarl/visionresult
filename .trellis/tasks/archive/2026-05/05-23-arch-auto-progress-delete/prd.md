# PRD: Delete `_progress` entries after analysis completes

## Category
PERF/MEMORY

## Problem
After analysis completes (success or failure), the `_progress[task_id]` entry is never deleted.
The `_cleanup_progress()` function removes entries older than 1 hour via TTL, but under sustained
load, completed entries waste memory for up to 1 hour.

## Evidence
- File: `src/vision_insight/api/routes.py` — `_run_analysis()` function
- `_progress[task_id]` is set but never deleted in the `finally` block
- `_cleanup_progress()` only runs before adding new entries, not after completion

## Solution
In the `finally` block, delete the `_progress[task_id]` entry after appending the "done" event.
The database is the source of truth; SSE clients already connected have their own event queue.

## Changes
1. Modify `finally` block in `_run_analysis()` to delete `_progress[task_id]`

## Acceptance criteria
- `ruff check src/` passes
- `mypy src/vision_insight` passes
- `pytest tests/ -x -q` passes

## Scope
- `src/vision_insight/api/routes.py` only

## No functional changes
