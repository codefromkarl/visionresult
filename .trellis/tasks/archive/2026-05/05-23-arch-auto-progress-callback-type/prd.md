# PRD: Fix ProgressCallback Type Alias

## Category
debt

## Problem
`ProgressCallback = Any` in `graph.py` loses type information. The actual type is `Callable[[str, int], None] | None`. Using `Any` means no type checking on callback usage and no IDE autocompletion.

## What to change
1. Replace `ProgressCallback = Any` with proper type alias
2. Import `Callable` from `collections.abc`

## Evidence
- `src/vision_insight/pipeline/graph.py` line 30

## Acceptance criteria
- [ ] `ProgressCallback` has proper type annotation
- [ ] `ruff check` passes
- [ ] `mypy` passes
- [ ] All existing tests pass
- [ ] No functional changes

## Scope
- `src/vision_insight/pipeline/graph.py`

## Statement
No functional changes. Better type safety and IDE support.
