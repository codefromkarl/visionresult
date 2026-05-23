# PRD: Remove dead `context_parts` in `ask_question()`

## Category
DEBT

## Problem
`context_parts` list is built from the analysis record (22 lines of code) in `ask_question()` but never used.
The answer is constructed independently using direct `record.*` field access.

## Evidence
- File: `src/vision_insight/api/routes.py:636-657` (before edit)
- `context_parts` is assigned, populated through 22 lines, then never referenced
- The `answer` variable is built from `record.location_guess`, `record.scene_description`, etc.

## Solution
Remove the dead `context_parts` construction block.

## Changes
1. Remove lines 636-657 in `routes.py` (the `context_parts` construction)

## Acceptance criteria
- `ruff check src/` passes
- `mypy src/vision_insight` passes
- `pytest tests/ -x -q` passes

## Scope
- `src/vision_insight/api/routes.py` only

## No functional changes
