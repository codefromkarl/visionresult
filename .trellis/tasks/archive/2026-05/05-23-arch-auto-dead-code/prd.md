# PRD: Remove dead code

## Category
debt

## Problem
Two functions are defined but never called anywhere in the codebase:
1. `cleanup_old_analyses()` in `core/database.py` - defined but never imported or used
2. `sanitize_log_message()` in `core/sanitizer.py` - defined but never called outside the module

Note: `clear_task_events()` in `core/event_logger.py` is used in tests for cleanup, so it's kept.

## What to Change
Remove the three unused functions to reduce code surface area and improve maintainability.

## Acceptance Criteria
1. `cleanup_old_analyses()` removed from `core/database.py`
2. `sanitize_log_message()` removed from `core/sanitizer.py`
3. All existing tests pass
4. No imports are broken

## Scope
- `src/vision_insight/core/database.py`
- `src/vision_insight/core/sanitizer.py`

## Evidence
- `grep -rn "cleanup_old_analyses" src/` returns only the definition
- `grep -rn "sanitize_log_message" src/` returns only the definition

## Statement
No functional changes — this is dead code removal only.
