# PRD: Fix SQLite pool configuration

## Category
PERF/ARCH

## Problem
The SQLite engine is configured with `pool_size=5, max_overflow=10`, but SQLite doesn't support concurrent writes. The pool settings are misleading and could cause issues.

## Evidence
- File: `src/vision_insight/core/database.py:84-89`
- `create_engine("sqlite:///...", pool_size=5, max_overflow=10, ...)` — SQLite doesn't support concurrent writes
- For SQLite, `StaticPool` or `NullPool` would be more appropriate

## Solution
Use `StaticPool` for SQLite to ensure single connection usage, which is appropriate for SQLite's concurrency model.

## Changes
1. Detect if the database URL is SQLite
2. Use `StaticPool` for SQLite connections
3. Keep existing pool settings for PostgreSQL (future use)

## Acceptance Criteria
- [ ] Ruff lint passes: `ruff check src/`
- [ ] Tests pass: `pytest tests/unit/ -q`
- [ ] No functional changes to API behavior
- [ ] SQLite uses appropriate connection pooling

## Scope
Only modify `src/vision_insight/core/database.py`

## Statement
No functional changes — only connection pooling improvement.
