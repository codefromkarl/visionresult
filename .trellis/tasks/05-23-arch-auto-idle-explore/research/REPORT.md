# Architecture Deepening Report — 2026-05-23 (Round 2)

## Phase 1: Exploration

Explored all source files under `src/vision_insight/` using improve-codebase-architecture skill vocabulary.
Cross-referenced with 20+ archived arch-auto tasks to avoid re-implementing completed work.

## Phase 2: P0 Implementation

### Implemented and Archived

| Task | Category | What Changed | Status |
|------|----------|--------------|--------|
| `05-23-arch-auto-type-annotations` | arch | Fixed 4 type annotations: `EvidenceService.fuse()` return type `list` → `list[FusedConclusion]`, `ReportService.generate_structured_report()` return type `dict` → `dict[str, Any]`, `get_database_stats()` return type `dict` → `dict[str, int]`, `get_image_metadata()` return type `dict` → `dict[str, Any]` | ✅ archived |

### Demoted (Not Implemented)

| Candidate | Category | Why Demoted |
|-----------|----------|-------------|
| Fix `request: Request = None` default | debt | FastAPI doesn't support `Request | None` type hint for dependency injection. The current syntax is correct for FastAPI's parameter injection system. |

## Phase 3: P1/P2/P3 Candidates Left for User Decision

### P1 — Medium Risk

| # | Category | Finding | Why not auto |
|---|----------|---------|--------------|
| P1-1 | arch | Extract shared OpenAI-compatible chat client | Touches 4+ service files, needs careful testing |
| P1-2 | debt | Consolidate duplicate header construction | Part of larger OpenAI client extraction (P1-1) |
| P1-3 | arch | `_parse_json_field` encapsulation violation | Static method on `AnalysisRecord` called externally from `routes.py` |
| P1-4 | perf | Event logger memory leak potential | Needs design decision on eviction strategy |
| P1-5 | perf | Rate limiter linear scan optimization | Bounded by rate limit, minimal benefit |
| P1-6 | debt | PaddleOCR deprecation warnings | New API has different return format, needs testing |
| P1-7 | arch | `_progress` dict not thread-safe | Access from background tasks and SSE handlers |
| P1-8 | sec | Rate limiter X-Forwarded-For spoofing | Needs configurable trusted proxies list |
| P1-9 | arch | search_analyses() returns detached SQLAlchemy objects | Currently not causing issues |
| P1-10 | arch | `to_dict()` return type annotation | Should be `dict[str, Any]` |

### P2 — High Effort

| # | Category | Finding |
|---|----------|---------|
| P2-1 | arch | Pipeline graph error handling standardization |
| P2-2 | arch | Service registry lifecycle management |

### P3 — Design Decisions

| # | Category | Finding |
|---|----------|---------|
| P3-1 | arch | HTTP client connection pooling strategy |
| P3-2 | arch | Rate limiter storage backend |

## Verification

All changes verified:
- `ruff check src/vision_insight/` — All checks passed
- `mypy src/vision_insight/ --ignore-missing-imports` — No issues found
- `pytest tests/` — 414 passed, 1 skipped, 19 warnings
- No functional changes to behavior

## Files Modified

1. `src/vision_insight/services/__init__.py` — Fixed `EvidenceService.fuse()` and `ReportService.generate_structured_report()` return types
2. `src/vision_insight/core/database.py` — Fixed `get_database_stats()` return type
3. `src/vision_insight/utils/image.py` — Fixed `get_image_metadata()` return type
4. `src/vision_insight/services/report/markdown_report_service.py` — Fixed `generate_structured_report()` return type to match interface
