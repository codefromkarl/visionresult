# PRD: Fix Performance Micro-issues

**Category**: perf  
**Priority**: P0

## Problem

Two minor performance issues:

1. **F-3.4**: `get_stats()` in `routes.py:602-612` loads up to 1000 records via `list_analyses(limit=1000)` just to count them. A `get_database_stats()` function already exists in `database.py:266` that uses efficient `COUNT()` queries.
2. **F-3.6**: `import re` inside function body in `http_search_service.py:201` — imports on every call.

## Solution

1. Replace the `get_stats()` route implementation to use `get_database_stats()` from `database.py` instead of loading and counting records.
2. Move `import re` to module-level in `http_search_service.py`.

## Evidence

- Research: `.trellis/tasks/05-23-arch-auto-explore-2/research/findings.md` (F-3.4, F-3.6)

## Scope

Only these files:
- `src/vision_insight/api/routes.py` (get_stats function)
- `src/vision_insight/services/search/http_search_service.py` (import re)

## Acceptance Criteria

- No functional changes — same stats returned
- All existing tests pass
- Lint / typecheck clean

## Explicit Statement

**No functional changes.** Pure performance optimization.
