# Architecture Deepening Opportunities — 2026-05-23

## Context

Previous audit (05-23-arch-auto-audit-research) identified and implemented 30+ tasks covering:
- Dead code removal (sanitizer, TYPE_CHECKING blocks, unused functions, etc.)
- Security hardening (proxy removal, config fixes)
- Performance (auth hash caching, SQLite pool, progress cleanup)
- Architecture (LLM ports extraction, prompt extraction, UUID utils, etc.)

This report identifies **new** deepening opportunities not covered by prior work.

---

## P0 — Trivial/Low-Risk, High Leverage

### P0-1: Remove unnecessary `from __future__ import annotations` (debt)

**Category**: debt  
**What**: The project requires Python 3.11+ (`requires-python = ">=3.11"`). The `from __future__ import annotations` import is only needed for Python 3.9- to enable PEP 604 (`X | Y`) and PEP 585 (`list[x]`) syntax. In Python 3.10+, these are native.  
**Files**:
- `src/vision_insight/utils/__init__.py:3`
- `src/vision_insight/models/schemas.py:3`
- `src/vision_insight/services/vlm/prompts.py:3`
- `src/vision_insight/services/ocr/baidu_service.py:10`
- `src/vision_insight/services/ocr/paddle_service.py:3`

**Evidence**: All files use `list[x]`, `dict[x, y]`, `X | None` syntax which is native in Python 3.11.  
**Risk**: None — removing the import has no effect on Python 3.11+.  
**Acceptance**: `ruff check` passes, `mypy` passes, tests pass.

### P0-2: Extract duplicate `base64.b64encode(image_bytes).decode("utf-8")` (debt)

**Category**: debt  
**What**: The pattern `base64.b64encode(image_bytes).decode("utf-8")` is repeated in 4 locations across VLM services. Extract to a shared utility function.  
**Files**:
- `src/vision_insight/services/vlm/api_service.py:88,180`
- `src/vision_insight/services/vlm/zhipu_service.py:80`
- `src/vision_insight/services/ocr/baidu_service.py:149`

**Proposed**: Add `encode_image_base64(image_bytes: bytes) -> str` to `utils/image.py`.  
**Risk**: None — pure extraction, no behavior change.  
**Acceptance**: `ruff check` passes, `mypy` passes, tests pass.

### P0-3: Rate limiter linear scan optimization (perf)

**Category**: perf  
**What**: `RateLimitMiddleware._check_rate_limit()` does a linear scan of all request timestamps for each request: `sum(1 for ts, _ in requests if ts > minute_ago)`. Under high load with many requests per IP, this is O(n) per request.  
**File**: `src/vision_insight/core/rate_limiter.py:94-97`  
**Proposed**: Maintain separate counters for minute/hour windows instead of scanning.  
**Risk**: Low — internal implementation detail, no API change.  
**Acceptance**: `ruff check` passes, tests pass.

### P0-4: Remove unused `_WIKIPEDIA_API` constant (debt)

**Category**: debt  
**What**: `_WIKIPEDIA_API` constant is defined at line 17 but never used. The actual Wikipedia URLs are constructed dynamically in `_search_wikipedia()`.  
**File**: `src/vision_insight/services/search/http_search_service.py:17`  
**Risk**: None — removing unused constant.  
**Acceptance**: `ruff check` passes.

---

## P1 — Medium Risk (User review required)

### P1-1: Extract shared OpenAI-compatible chat client (arch)

**Category**: arch  
**What**: Three services (`llm_entity_service.py`, `llm_ports.py`, `api_service.py`, `zhipu_service.py`) all implement nearly identical OpenAI-compatible chat completion logic: construct payload, set Bearer auth header, POST to `/chat/completions`, parse `choices[0].message.content`.  
**Why not P0**: Touches 4+ service files, needs careful testing of each provider.  
**Proposed**: Create `utils/openai_client.py` with shared `chat_completion()` helper.

### P1-2: Consolidate duplicate header construction (debt)

**Category**: debt  
**What**: `{"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}` is constructed identically in 4 service files.  
**Why not P0**: Part of larger OpenAI client extraction (P1-1), doing standalone would create churn.

### P1-3: Database session management improvement (arch)

**Category**: arch  
**What**: Database uses module-level globals (`_engine`, `_SessionLocal`) with manual session management. The `get_session()` context manager exists but `save_analysis()` and `delete_analysis()` create their own sessions.  
**Why not P0**: Touches core database module, needs integration testing.

### P1-4: Event logger memory leak potential (perf)

**Category**: perf  
**What**: `_event_store` and `_sse_queues` are unbounded dictionaries. While `_MAX_TASKS = 50` caps stored tasks, there's no cleanup of old tasks when the cap is exceeded (new tasks are just rejected).  
**Why not P0**: Needs design decision on eviction strategy.

---

## P2 — High Effort

### P2-1: Pipeline graph error handling standardization (arch)

**Category**: arch  
**What**: Error handling in `pipeline/graph.py` uses 8 different `except Exception` blocks with inconsistent patterns (some log, some re-raise, some return degraded results).  
**Why**: Would touch core pipeline logic, needs comprehensive testing.

### P2-2: Service registry lifecycle management (arch)

**Category**: arch  
**What**: ServiceRegistry creates service instances lazily but doesn't support health checking, circuit breaking, or graceful degradation at the registry level.  
**Why**: Major architectural change.

---

## P3 — Design Decisions

### P3-1: HTTP client connection pooling strategy

**Category**: arch  
**What**: Currently each service creates a new `httpx.AsyncClient` per request. Should there be a shared connection pool?  
**Why**: Design decision affecting performance and resource usage.

### P3-2: Rate limiter storage backend

**Category**: arch  
**What**: Rate limiter uses in-memory storage. Should it use Redis for multi-instance deployments?  
**Why**: Deployment architecture decision.
