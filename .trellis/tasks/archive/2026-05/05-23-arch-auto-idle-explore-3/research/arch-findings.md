# Architecture Deepening — Idle Pass 3 (2026-05-23)

## Methodology

Followed improve-codebase-architecture skill vocabulary (Module, Interface, Depth, Seam, Adapter, Leverage, Locality).
Applied deletion test and cross-referenced with 19 previously completed arch-auto tasks.

## Current State

- All previous P0 tasks completed and archived
- Ruff: 0 errors
- Mypy: 0 errors (43 files)
- Tests: 414 passed, 1 skipped

---

## P0 — Trivial / Low-Risk, High Leverage

### 1. Dead `context_parts` in `ask_question()` (DEBT)
- **File**: `src/vision_insight/api/routes.py:636-657`
- **Problem**: `context_parts` list is built from the analysis record (22 lines of code) but never used.
  The answer is constructed independently using direct `record.*` field access (lines 660+).
  This is dead code — the deletion test confirms: removing it changes nothing.
- **Evidence**: `context_parts` is assigned on line 636, populated through line 657, then never referenced.
  The `answer` variable is built from `record.location_guess`, `record.scene_description`, etc.
- **Fix**: Remove lines 636-657 (the `context_parts` construction block).
- **Risk**: None — pure dead code removal, no behavioral change.
- **Category**: debt

### 2. Delete `_progress[task_id]` entry after analysis completes (PERF/MEMORY)
- **File**: `src/vision_insight/api/routes.py` — `_run_analysis()` function
- **Problem**: After analysis completes (success or failure), the `_progress[task_id]` entry is never
  deleted. The `_cleanup_progress()` function removes entries older than 1 hour via TTL, but under
  sustained load, completed entries waste memory for up to 1 hour. The `finally` block only appends
  `("done", 100)` but doesn't clean up the entry itself.
- **Evidence**: `_progress[task_id]` is set on line 229, `finally` block on line 266 only appends.
  `_cleanup_progress()` is called on line 228 (before adding new entry), not after completion.
- **Fix**: In the `finally` block, after appending `("done", 100)`, schedule deletion of the entry
  after a short delay (e.g., 30 seconds to allow SSE clients to read the final event).
  Alternatively, simply delete the entry in the `finally` block since the DB record is the source of truth.
- **Risk**: Minimal — SSE clients that connect after the entry is deleted will fall back to DB status check.
- **Category**: perf

### 3. `from __future__ import annotations` unnecessary for Python 3.11+ (DEBT)
- **Files**: All 28 `.py` files under `src/vision_insight/`
- **Problem**: The project requires Python >=3.11 (per `pyproject.toml`), which natively supports
  PEP 604 union types (`X | Y`) and most annotation expressions. The `from __future__ import annotations`
  import was needed for Python 3.9/3.10 compatibility but is now unnecessary dead code in every file.
  The deletion test confirms: removing these imports changes no runtime behavior.
- **Evidence**: `pyproject.toml` line 4: `requires-python = ">=3.11"`. All 28 files have this import.
- **Fix**: Remove `from __future__ import annotations` from all 28 files.
- **Risk**: None — the import has no effect at runtime with Python 3.11+.
- **Category**: debt

---

## P1 — Medium Risk / User Decision

### 4. `_record_to_report` / `_report_to_record` mapper functions in routes.py (ARCH)
- **File**: `src/vision_insight/api/routes.py:96-190`
- **Problem**: 95 lines of DB↔Pydantic mapping logic lives in the route handler file.
  This gives routes.py low Locality — understanding the data model requires reading both
  the ORM model, the Pydantic schemas, AND the route handler.
- **Fix**: Extract to `models/mappers.py` for better Locality.
- **Why not P0**: Touches routes.py structure, might affect import chains.

### 5. Gemini API key in URL query param (SECURITY)
- **File**: `src/vision_insight/services/vlm/api_service.py:282`
- **Problem**: `url = f"{self._base_url}/models/{self._model}:generateContent?key={self._api_key}"`
  The API key is sent as a URL query parameter, which gets logged in server access logs,
  proxy logs, and browser history. Should use `x-goog-api-key` header instead.
- **Fix**: Move API key to request header.
- **Why not P0**: Changes VLM service behavior, needs testing with actual API.

### 6. SSRF protection on URL download endpoint (SECURITY)
- **File**: `src/vision_insight/api/routes.py:321-340`
- **Problem**: The `/analyze/url` endpoint downloads images from user-provided URLs without
  SSRF protection. An attacker could use this to scan internal networks or access cloud metadata.
- **Fix**: Add URL validation (block private IPs, localhost, cloud metadata endpoints).
- **Why not P0**: Changes endpoint behavior, needs careful validation.

### 7. `LLMEntityService._chat()` lacks retry logic (ARCH)
- **File**: `src/vision_insight/services/entity/llm_entity_service.py:83-96`
- **Problem**: All VLM services use `retry_with_backoff()` for HTTP calls, but `LLMEntityService._chat()`
  makes HTTP calls without retry. This is inconsistent and makes entity extraction fragile.
- **Fix**: Wrap `_chat()` with `retry_with_backoff()`.
- **Why not P0**: Changes service behavior, touches entity extraction.

---

## P2 — High Effort

### 8. Shared httpx client factory (ARCH)
- **Problem**: 11+ call sites create `httpx.AsyncClient` inline. Could benefit from a shared
  factory with connection pooling, consistent timeout, and retry configuration.
- **Why P2**: Major refactor touching many service files.

### 9. Pipeline node boilerplate reduction (ARCH)
- **Problem**: All 7 pipeline nodes follow the same pattern: get report, notify progress,
  start step, try/except, end step. Could be reduced with a decorator or wrapper.
- **Why P2**: Significant refactor of pipeline/graph.py.

---

## P3 — Design Decisions

### 10. `from __future__ import annotations` convention (DEBT)
- **Decision**: Keep for forward compatibility even on 3.11+? Or remove for cleanliness?
- **Note**: If kept, it's a deliberate convention, not dead code.

### 11. `cleanup_old_analyses()` never wired (DEBT)
- **Decision**: Needs a scheduling mechanism (background task, cron, etc.)
