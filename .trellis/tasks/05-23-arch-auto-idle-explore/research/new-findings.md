# Architecture Deepening Opportunities — Idle Pass 2026-05-23 (Round 2)

## Methodology

Explored all source files under `src/vision_insight/` using improve-codebase-architecture skill vocabulary
(Module, Interface, Depth, Seam, Adapter, Leverage, Locality). Applied the deletion test to suspect
shallow modules. Cross-referenced with 20+ archived arch-auto tasks to avoid re-implementing completed work.

## Baseline: Already Completed (from archived tasks)

All previous P0 items have been implemented:
- ✅ Unbounded _progress dict — TTL cleanup + deletion after analysis
- ✅ Session context manager — `get_session_ctx()` exists
- ✅ SQLite pool configuration — uses StaticPool
- ✅ Settings directory creation — deferred to `ensure_directories()` at startup
- ✅ LLM port adapters extracted — `services/evidence/llm_ports.py`
- ✅ Prompt templates extracted — `services/vlm/prompts.py`
- ✅ UUID generation extracted — `utils/__init__.py`
- ✅ Auth hash caching — `_valid_key_hashes` cached
- ✅ Dead code removed (sanitize_log_message, context_parts, etc.)
- ✅ `from __future__ import annotations` cleanup
- ✅ Ruff/mypy fixes
- ✅ Deprecated datetime.utcnow() fixes
- ✅ Performance micro-issues (get_stats using COUNT, inline imports)
- ✅ Base64 encoding utility extracted
- ✅ Unused Wikipedia constant removed

---

## P0 — Trivial / Low-Risk, High Leverage

### 1. EvidenceService.fuse() return type annotation (ARCH)
- **File**: `src/vision_insight/services/__init__.py:84`
- **Problem**: The abstract method `fuse()` returns bare `list` instead of `list[FusedConclusion]`.
  This weakens the Interface contract — callers and type checkers can't verify the return type.
- **Evidence**: `-> list:` on line 84, but `FusionService.fuse()` returns `list[FusedConclusion]`.
- **Fix**: Change `-> list:` to `-> list[FusedConclusion]:` and add import.
- **Risk**: Minimal — type annotation only, no behavior change.
- **Benefit**: Stronger Interface contract, better IDE support, type checking.

### 2. Fix `request: Request = None` default parameter (DEBT)
- **File**: `src/vision_insight/api/routes.py:298`
- **Problem**: `request: Request = None` should be `request: Request | None = None` for proper type safety.
  FastAPI handles this correctly at runtime, but mypy/ruff would flag this as a type error.
- **Evidence**: Line 298: `request: Request = None,`
- **Fix**: Change to `request: Request | None = None,`
- **Risk**: Minimal — type annotation only, no behavior change.
- **Benefit**: Type safety, consistent with Python 3.11+ style.

### 3. ReportService.generate_structured_report() return type (ARCH)
- **File**: `src/vision_insight/services/__init__.py:98`
- **Problem**: Returns bare `dict` instead of a more specific type. The actual implementation
  in `markdown_report_service.py` returns a dict with specific structure.
- **Evidence**: `-> dict:` on line 98.
- **Fix**: Change to `-> dict[str, Any]:` and add import.
- **Risk**: Minimal — type annotation only.
- **Benefit**: Better type documentation.

### 4. get_database_stats() return type (ARCH)
- **File**: `src/vision_insight/core/database.py:288`
- **Problem**: Returns bare `dict` instead of a TypedDict or specific type.
- **Evidence**: `-> dict:` on line 288, but the function returns `{"total": int, "completed": int, ...}`.
- **Fix**: Change to `-> dict[str, int]:` for better type documentation.
- **Risk**: Minimal — type annotation only.
- **Benefit**: Better type documentation.

### 5. get_image_metadata() return type (ARCH)
- **File**: `src/vision_insight/utils/image.py:124`
- **Problem**: Returns bare `dict` instead of a TypedDict or specific type.
- **Evidence**: `-> dict:` on line 124.
- **Fix**: Change to `-> dict[str, Any]:` and add import.
- **Risk**: Minimal — type annotation only.
- **Benefit**: Better type documentation.

---

## P1 — Medium Risk / User Decision

### 6. Shared httpx.AsyncClient across services (PERF)
- **Files**: `api_service.py`, `zhipu_service.py`, `llm_entity_service.py`, `llm_ports.py`, `baidu_service.py`, `http_search_service.py`
- **Problem**: Each service creates a new `httpx.AsyncClient` per request, causing TCP connection overhead.
  The pipeline calls multiple services per analysis.
- **Fix**: Create a shared client pool or reuse clients across requests.
- **Risk**: Need to handle client lifecycle carefully in tests.
- **Benefit**: Reduced connection overhead, better performance.

### 7. PaddleOCR deprecation warnings (DEBT)
- **File**: `src/vision_insight/services/ocr/paddle_service.py`
- **Problem**: Using deprecated `use_angle_cls=True` and `.ocr()` method. PaddleOCR now uses
  `use_textline_orientation` and `.predict()`.
- **Fix**: Update to new API.
- **Risk**: Medium — new API has different return format, needs testing.
- **Benefit**: Remove deprecation warnings, future-proof code.

### 8. _progress dict not thread-safe (ARCH)
- **File**: `src/vision_insight/api/routes.py:30-32`
- **Problem**: `_progress` dict is accessed from background tasks and SSE handlers without synchronization.
- **Fix**: Use threading.Lock or asyncio.Lock.
- **Risk**: Medium — could affect performance.
- **Benefit**: Prevent potential race conditions.

### 9. Rate limiter X-Forwarded-For spoofing (SEC)
- **File**: `src/vision_insight/core/rate_limiter.py:40-45`
- **Problem**: Trusts `X-Forwarded-For` header without validation. In production behind a reverse proxy,
  this should be configured to only trust known proxies.
- **Fix**: Add configurable trusted proxies list.
- **Risk**: Medium — needs configuration.
- **Benefit**: Prevent IP spoofing attacks.

### 10. search_analyses() returns detached SQLAlchemy objects (ARCH)
- **File**: `src/vision_insight/core/database.py:198-235`
- **Problem**: The function uses `get_session_ctx()` which closes the session after returning.
  The returned objects are detached from the session.
- **Risk**: Currently not causing issues because only eagerly-loaded columns are accessed.
- **Benefit**: Prevent potential future bugs.

---

## P2 — High Effort

### 11. Pipeline graph error handling standardization (ARCH)
- **Files**: `pipeline/graph.py` — all node factories
- **Problem**: Each node catches exceptions and sets status to failed, but the pipeline continues.
  This is by design for resilience, but the error handling pattern is duplicated.
- **Benefit**: DRY, consistent error handling.

### 12. Service registry lifecycle management (ARCH)
- **File**: `src/vision_insight/core/service_registry.py`
- **Problem**: Singleton pattern with global state. Could be improved with dependency injection.
- **Benefit**: Better testability, clearer lifecycle.

---

## P3 — Design Decisions

### 13. HTTP client connection pooling strategy (ARCH)
- **Problem**: Each service creates its own client. Should there be a shared pool?
- **Decision needed**: Pool size, lifecycle, cleanup strategy.

### 14. Rate limiter storage backend (ARCH)
- **File**: `src/vision_insight/core/rate_limiter.py`
- **Problem**: In-memory storage doesn't persist across restarts.
- **Decision needed**: Should we use Redis or keep in-memory?
