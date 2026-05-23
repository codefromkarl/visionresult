# PRD: Remove Dead File frontend/index-old.html

## Category: debt

## What to change and why

`frontend/index-old.html` (47.2KB) is an obsolete frontend file not referenced anywhere in the
codebase. It appears to be a previous version of `frontend/index.html` that was left behind.

Evidence: `rg "index-old" src/` returns no results.

## Acceptance criteria
- File `frontend/index-old.html` is deleted
- `ruff check src/` passes
- `python3 -m pytest tests/ -x -q` passes

## Scope
- `frontend/index-old.html` only

## No functional changes
