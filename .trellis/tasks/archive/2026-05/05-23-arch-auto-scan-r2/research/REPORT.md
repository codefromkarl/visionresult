# Architecture Auto-Implementation Report — 2026-05-23 (Session 2)

## Phase 1: Exploration

Dispatched trellis-research subagent to inspect codebase for new deepening opportunities not covered by 40+ previously archived tasks.

Found 8 new candidates:
- 3 P0 (trivial/low-risk)
- 4 P1 (medium risk)
- 1 P2/P3 (high effort/design decision)

## Phase 2: P0 Implementation

### Implemented and Archived

| Task | Category | What Changed | Status |
|------|----------|--------------|--------|
| `05-23-arch-auto-images-dir` | debt/config | Added `images_dir` to Settings, updated `routes.py` and `health.py` to use config instead of hardcoded `Path("data/images")`. Single source of truth for image directory. | ✅ archived |
| `05-23-arch-auto-future-annotations-r2` | debt | Removed unnecessary `from __future__ import annotations` from `schemas.py`. Other 4 files confirmed to need it (TYPE_CHECKING patterns, self-referencing classmethods). | ✅ archived |
| `05-23-arch-auto-parse-json-public` | debt/arch | Renamed `_parse_json_field` → `parse_json_field` in `AnalysisRecord`. Method was accessed externally from `routes.py` in 7 places despite private naming. | ✅ archived |

### Demoted (Not Implemented)

| Candidate | Category | Why Demoted |
|-----------|----------|-------------|
| httpx AsyncClient connection pool reuse | perf | Touches 11 files, changes resource lifecycle management (from auto `async with` to manual `aclose()`). Medium risk, not P0. |
| Unused `database_url` config field | config | `.env` has PostgreSQL URL but code hardcodes SQLite. This is a design decision (P3), not simple cleanup. |

## Phase 3: P1/P2/P3 Candidates Left for User Decision

### P1 — Medium Risk

| # | Category | Finding | Why not auto |
|---|----------|---------|--------------|
| P1-1 | perf | httpx AsyncClient connection pool reuse | Touches 11 files, needs lifecycle management |
| P1-2 | arch | Duplicate LLM chat request pattern (5 files) | Touches 4+ service files |
| P1-3 | arch | ContextVar for task_id cross-module dependency | Changes import paths |
| P1-4 | arch | MarkdownReportService multiple instantiation | Changes service initialization |

### P2 — High Effort

| # | Category | Finding |
|---|----------|---------|
| P2-1 | arch | Pipeline node factory pattern refactoring (733 lines, 7 nodes) |

### P3 — Design Decisions

| # | Category | Finding |
|---|----------|---------|
| P3-1 | config | database_url config field — should code use PostgreSQL? |
| P3-2 | arch | HTTP client connection pooling strategy |

## Verification

All changes verified:
- `ruff check src/` — All checks passed
- `pytest tests/` — 414 passed, 1 skipped, 17 warnings
- No functional changes to behavior

## Files Modified

1. `src/vision_insight/core/config.py` — Added `images_dir` field
2. `src/vision_insight/api/routes.py` — Use `settings.images_dir`, renamed `parse_json_field` calls
3. `src/vision_insight/api/health.py` — Added `images_dir` health check
4. `src/vision_insight/models/schemas.py` — Removed unnecessary `from __future__ import annotations`
5. `src/vision_insight/core/database.py` — Renamed `_parse_json_field` → `parse_json_field`
