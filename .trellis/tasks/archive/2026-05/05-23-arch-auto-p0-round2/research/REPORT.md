# Trellis Architecture Auto-Implementation Report — Round 2
Date: 2026-05-23
Repository: /home/yuanzhi/Develop/ai-research/visionresult

## P0 Tasks Implemented and Archived ✅

### Task 1: arch-auto-p0-round2 (Category: debt/perf)
**What changed (7 fixes):**

1. **Dead code removal** — Removed unused `"\n".join(context_parts)` expression in `api/routes.py:676` whose result was discarded.

2. **Deprecated API fix** — Replaced `datetime.utcnow()` with `datetime.now(UTC)` in `api/health.py` (2 locations). Added `from datetime import UTC` import.

3. **SQLAlchemy 2.x fix** — Changed `conn.execute("SELECT 1")` to `conn.execute(text("SELECT 1"))` in `api/health.py`. Added `from sqlalchemy import text` import.

4. **Import-time side effect removal** — Removed `DB_PATH.parent.mkdir()` from `core/database.py` (line 20). Directory creation already handled by `ensure_directories()`.

5. **Import-time side effect removal** — Removed `IMAGES_DIR.mkdir()` from `api/routes.py` (line 62). Added `data/images` to `ensure_directories()` in `config.py`.

6. **Performance: hot-path import** — Moved `from datetime import datetime as dt` to module level in `pipeline/graph.py`. Removed 3 inline imports inside functions (`_start_pipeline_step`, `_end_pipeline_step`, `preprocess_node`).

7. **Deduplicated image format detection** — Extracted `detect_image_format(image_bytes: bytes) -> str` to `utils/image.py`. Replaced duplicate magic byte detection in `routes.py` (`IMAGE_MAGIC_BYTES` dict) and `zhipu_service.py` (inline if/elif) with shared utility.

**Verification:** 414 tests passed, 0 failures, ruff clean

---

## P1 Candidates — Requires User Decision

| # | Category | Finding | Effort |
|---|----------|---------|--------|
| P1-1 | arch | Extract shared `retry_with_backoff()` to `utils/http.py` — copied 3 times in VLM/entity services | Medium |
| P1-2 | arch | Extract shared JSON parsing helpers (`_parse_json_response`, `_build_scene_analysis`) — copied 3 times | Medium |
| P1-3 | arch | Create shared httpx client factory with DI — 11 call sites create `AsyncClient` inline | High |
| P1-4 | arch | Move 110-line DB↔Pydantic mappers from `routes.py` to `models/mappers.py` | Medium |
| P1-5 | security | Gemini API key in URL query param → use `x-goog-api-key` header instead | Low |
| P1-6 | security | Add SSRF protection to URL image download endpoint (`routes.py:321-340`) | Medium |
| P1-7 | debt | Config mismatch: `Settings.database_url` unused, `database.py` hardcodes SQLite | Medium |
| P1-8 | debt | Consolidate duplicated mock classes in integration tests → reuse `tests/mocks/` | Low |
| P1-9 | security | Dockerfile runs as root — add non-root `USER` directive | Low |
| P1-10 | debt | Remove hardcoded Cloudflare account ID from `deploy.sh:49` | Low |
| P1-11 | perf | Replace inline stats calculation in `routes.py` with existing `get_database_stats()` | Low |
| P1-12 | perf | Delete `_progress[task_id]` entries after analysis completes (memory leak) | Low |
| P1-13 | arch | PipelineRunner uses magic string dict keys instead of typed getters | Low |
| P1-14 | arch | Extract shared prompt constants to `services/vlm/prompts.py` | Low |

## P2 Candidates — High Effort

| # | Category | Finding |
|---|----------|---------|
| P2-1 | arch | Database DI refactoring (global `_engine` singleton → class-based with injection) |
| P2-2 | arch | Frontend build pipeline unification (3 divergent copies tracked in git) |
| P2-3 | security | `deploy/_worker.js` has hardcoded Gemini API key — needs key rotation + env binding |
| P2-4 | arch | Health check (`api/health.py`) duplicates VLM configuration logic from ServiceRegistry |

## P3 Candidates — Design Decisions

| # | Category | Finding |
|---|----------|---------|
| P3-1 | arch | Database strategy: SQLite vs PostgreSQL (current code hardcodes SQLite, Settings defines PostgreSQL) |
| P3-2 | arch | Frontend deployment approach: Pages Functions vs Workers (`_worker.js` vs `functions/`) |
| P3-3 | debt | `analysis_depth` parameter accepted but never used (feature decision) |
| P3-4 | debt | `cleanup_old_analyses()` never wired (needs scheduling decision) |
