# Architecture Deepening Opportunities — Idle Pass 2026-05-23

## Methodology

Explored all source files under `src/vision_insight/` using improve-codebase-architecture skill vocabulary
(Module, Interface, Depth, Seam, Adapter, Leverage, Locality). Applied the deletion test to suspect
shallow modules. Cross-referenced with 20+ archived arch-auto tasks to avoid re-implementing completed work.

## Baseline: Already Completed (from archived tasks)

The following P0 items have already been implemented:
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

---

## P0 — Trivial / Low-Risk, High Leverage

### 1. Missing retry_with_backoff in LLMEntityService._chat() (DEBT/PERF)
- **File**: `src/vision_insight/services/entity/llm_entity_service.py:84-98`
- **Problem**: `_chat()` makes HTTP requests without retry logic. All VLM services
  (`api_service.py`, `zhipu_service.py`) use `retry_with_backoff()`, but entity extraction
  does not. This inconsistency means transient HTTP failures (429, 500, 502, 503, 504,
  timeouts) will immediately fail entity extraction instead of retrying.
- **Evidence**: `grep -r "retry_with_backoff" src/` shows VLM services use it; entity service does not.
- **Fix**: Wrap the HTTP call in `_chat()` with `retry_with_backoff()`.
- **Risk**: Minimal — only adds retry on transient failures, same pattern as VLM services.
- **Benefit**: Consistent retry behavior across all LLM services, improved reliability.

### 2. Missing retry_with_backoff in ZhipuLLMPort.infer() (DEBT/PERF)
- **File**: `src/vision_insight/services/evidence/llm_ports.py:27-45`
- **Problem**: `ZhipuLLMPort.infer()` makes HTTP requests without retry logic. This is
  called for each evidence fusion conclusion (3-5 times per analysis). Transient failures
  will immediately degrade evidence quality instead of retrying.
- **Evidence**: `grep -r "retry" src/vision_insight/services/evidence/` returns no results.
- **Fix**: Wrap the HTTP call in `infer()` with `retry_with_backoff()`.
- **Risk**: Minimal — only adds retry on transient failures.
- **Benefit**: Improved evidence fusion reliability.

### 3. Missing jitter in retry_with_backoff() (PERF)
- **File**: `src/vision_insight/utils/retry.py`
- **Problem**: The retry uses pure exponential backoff without jitter. Under high load,
  multiple clients could retry at the same time (thundering herd effect), causing
  cascading failures on the already-stressed upstream service.
- **Evidence**: `delay = RETRY_BASE_DELAY * (2**attempt)` — deterministic delay.
- **Fix**: Add random jitter: `delay = RETRY_BASE_DELAY * (2**attempt) * (0.5 + random.random())`.
- **Risk**: Minimal — only affects timing, not behavior.
- **Benefit**: Better behavior under load, prevents thundering herd.

---

## P1 — Medium Risk / User Decision

### 4. Shared httpx.AsyncClient in ZhipuLLMPort (PERF)
- **File**: `src/vision_insight/services/evidence/llm_ports.py`
- **Problem**: Each call to `infer()` creates a new `httpx.AsyncClient`, which has TCP
  connection overhead. The evidence service calls `infer()` 3-5 times per analysis.
- **Fix**: Create a shared client in `__init__` and reuse it.
- **Risk**: Need to handle client lifecycle carefully in tests.
- **Benefit**: Reduced connection overhead, better performance.

### 5. search_analyses() returns detached SQLAlchemy objects (ARCH)
- **File**: `src/vision_insight/core/database.py:198-235`
- **Problem**: The function uses `get_session_ctx()` which closes the session after returning.
  The returned objects are detached from the session. If any lazy-loaded attributes are
  accessed later, it would raise `DetachedInstanceError`.
- **Risk**: Currently not causing issues because only eagerly-loaded columns are accessed.
- **Benefit**: Prevents potential future bugs.

### 6. Rate limiter _requests dict cleanup interval (PERF)
- **File**: `src/vision_insight/core/rate_limiter.py:60-65`
- **Problem**: The cleanup runs every 300 seconds (5 minutes). Under high load, the
  `_requests` dict can grow significantly between cleanups.
- **Risk**: Medium — could affect memory usage under sustained load.
- **Benefit**: More predictable memory usage.

---

## P2 — High Effort

### 7. Composite retry pattern extraction (ARCH)
- **Files**: `services/fallback.py` — `CompositeOCRService`, `CompositeVLMService`
- **Problem**: Both composites implement identical try-catch-and-fallthrough logic.
  The pattern could be extracted to a generic `CompositeService[T]`.
- **Benefit**: DRY, consistent fallback behavior across all service types.

### 8. Inline JSON serialization in routes.py (ARCH)
- **File**: `src/vision_insight/api/routes.py`
- **Problem**: `_report_to_record()` and `_record_to_report()` contain 40+ lines of manual
  json.dumps/loads. This serialization should be the responsibility of the AnalysisRecord Module.
- **Benefit**: Routes become thinner, serialization logic has Locality in one place.

---

## P3 — Design Decision

### 9. SQLite vs PostgreSQL configuration (ARCH)
- **File**: `src/vision_insight/core/config.py`
- **Problem**: The config has `database_url` defaulting to PostgreSQL, but the actual
  implementation uses SQLite. This inconsistency should be resolved.
- **Decision needed**: SQLite for dev, PostgreSQL for prod? Or always SQLite?

### 10. Event store memory management (PERF)
- **File**: `src/vision_insight/core/event_logger.py:35-112`
- **Problem**: The event store has limits but cleanup logic only removes the oldest task.
  Under sustained load, this can still consume significant memory.
- **Decision needed**: Should we implement TTL-based cleanup or rely on current limits?
