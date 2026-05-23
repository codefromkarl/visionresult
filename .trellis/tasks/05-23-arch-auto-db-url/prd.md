# PRD: Remove Unused database_url Config Field

## Category
debt / config cleanup

## Problem
`database_url: str = ""` is defined in Settings with comment "Kept here so that VIA_DATABASE_URL in .env doesn't cause a validation error." But the database module hardcodes SQLite path:
```python
DB_PATH = Path("data/vision_insight.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"
```

The config field is dead — it's never read by any code.

## What to Change

### Option A: Make it functional (preferred if VIA_DATABASE_URL is in .env)
Update `core/database.py` to use the config:
```python
DATABASE_URL = settings.database_url or f"sqlite:///{DB_PATH}"
```

### Option B: Remove it (if VIA_DATABASE_URL is NOT used)
Remove `database_url` from Settings and from `.env.example`.

## Decision
Check `.env` and `.env.example` for `VIA_DATABASE_URL`. If present, use Option A. If absent, use Option B.

## Acceptance Criteria
- Config field either functional or removed
- No validation error if VIA_DATABASE_URL is absent
- `ruff check src/` passes
- All tests pass unchanged
- No functional changes

## Scope
- `src/vision_insight/core/config.py`
- `src/vision_insight/core/database.py` (if Option A)
- `.env.example` (if Option B)

## Evidence
- `.trellis/tasks/05-23-arch-auto-scan-r2/research/new-findings-2.md` (P0 #3)
