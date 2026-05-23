# P0-1: Remove Dead Database Config

## Category
arch / debt

## Problem
`config.py` defines `database_url` (PostgreSQL connection string) but `database.py` hardcodes `DB_PATH` and `DATABASE_URL` as SQLite. The PostgreSQL code path in `get_engine()` is dead code — it can never execute because `DATABASE_URL` always starts with `sqlite:`.

## What to Change
1. `database.py`: Remove dead PostgreSQL branch from `get_engine()`, remove unused imports, add comment explaining SQLite choice
2. `config.py`: Remove `database_url` setting that is never read

## Scope
- `src/vision_insight/core/database.py`
- `src/vision_insight/core/config.py`

## Acceptance Criteria
- `ruff check` passes
- `mypy` passes
- `pytest` passes
- No functional changes

## Evidence
- `database.py:12-13` — hardcoded DB_PATH/DATABASE_URL
- `database.py:81-93` — dead PostgreSQL branch
- `config.py:42` — unused `database_url` setting
