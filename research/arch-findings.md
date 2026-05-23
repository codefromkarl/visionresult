# Architecture Deepening Opportunities — VisionResult

> Generated: 2026-05-23 | Scope: debt / arch / perf / security

## Glossary (per improve-codebase-architecture)

- **Module** — anything with an interface and an implementation
- **Depth** — leverage at the interface: high behaviour behind small interface
- **Seam** — where an interface lives; a place behaviour can be altered
- **Adapter** — concrete thing satisfying an interface at a seam
- **Leverage** — what callers get from depth
- **Locality** — change/bugs/knowledge concentrated in one place

---

## P0 — Trivial / Low-risk / High Leverage

### P0-1: Repeated `json.loads(str(...or...))` deserialization pattern [debt]

**Files**: `src/vision_insight/api/routes.py` (lines 125-130, 415, 661, 672), `src/vision_insight/core/database.py` (lines 89-91)

**Problem**: 10 instances of `json.loads(str(record.xxx_json or "[]"))` scattered across two files. This pattern is:
- Duplicated across `_record_to_report()`, `to_dict()`, and `ask_question()`
- Fragile: the `str()` cast is a defensive wrapper for SQLAlchemy Column types
- Error-prone: each call site independently handles the default value

**Solution**: Add a `_parse_json_field(value, default)` helper to `AnalysisRecord` or `database.py`. Each call site becomes `self._parse_json(self.ocr_results_json, [])`.

**Benefits**: 
- Locality: JSON deserialization logic in one place
- Leverage: single point to add error handling, caching, or type validation

**Risk**: Very low — pure extract-refactor, no behavior change.

---

### P0-2: `datetime.now()` without timezone [debt]

**Files**: `src/vision_insight/api/routes.py` (lines 146, 163, 224, 262, 315, 368, 503), `src/vision_insight/core/database.py` (line 257)

**Problem**: 8 instances of `datetime.now()` without timezone info. The event_logger already uses `datetime.now(UTC)` correctly, but routes.py and database.py don't. This causes:
- Inconsistent timezone handling across the codebase
- Potential bugs when comparing timezone-aware vs naive datetimes
- SQLite stores as string anyway, so UTC is the correct choice

**Solution**: Replace `datetime.now()` with `datetime.now(UTC)` and add `from datetime import UTC` import.

**Benefits**:
- Consistency with event_logger.py
- Correctness for any future timezone-aware operations

**Risk**: Very low — SQLite stores ISO strings, no schema change needed.

---

### P0-3: Inline imports in routes.py [debt]

**Files**: `src/vision_insight/api/routes.py` (lines 116, 352, 403, 413, 520, 597)

**Problem**: 6 inline imports inside function bodies:
- `from vision_insight.models.schemas import ...` at line 116 (inside `_record_to_report`)
- `import httpx` at line 352 (inside `create_analysis_from_url`)
- `from vision_insight.services.report...` at line 403 (inside `get_report`)
- `import json` at line 413 (inside `get_report` — json already imported at top!)
- `from vision_insight.core.event_logger import ...` at line 520 (inside `stream_progress`)
- `from vision_insight.core.event_logger import ...` at line 597 (inside `get_task_events`)

The `import json` at line 413 is especially redundant since `json` is already imported at the module level (line 4).

**Solution**: Move all inline imports to the module top level. The original reason for inline imports (avoiding circular deps) is no longer valid since the module structure is stable.

**Benefits**:
- Cleaner code, no redundant imports
- Slight startup performance improvement (Python caches module-level imports)

**Risk**: Very low — if there were circular import issues, they'd manifest immediately at import time.

---

## P1 — Medium Effort / Medium Leverage

### P1-1: httpx.AsyncClient created per-request [perf]

**Files**: 11 instances across `services/vlm/api_service.py`, `services/vlm/zhipu_service.py`, `services/ocr/baidu_service.py`, `services/entity/llm_entity_service.py`, `services/search/http_search_service.py`, `services/evidence/llm_ports.py`, `api/routes.py`

**Problem**: Each HTTP call creates a new `httpx.AsyncClient` context manager. This means:
- No connection pooling between requests
- TLS handshake overhead on every call
- 11 separate client instantiations across the codebase

**Solution**: Create a shared `httpx.AsyncClient` in the service registry with proper lifecycle management (created once, closed on shutdown). Services receive the client via dependency injection.

**Benefits**:
- Performance: connection reuse, pooled TLS sessions
- Locality: HTTP client configuration in one place
- Leverage: single point to configure timeouts, retries, proxy

**Risk**: Medium — requires lifecycle management (close on shutdown), and services must not hold references after client is closed.

---

### P1-2: `ProgressCallback = Any` type alias [debt]

**Files**: `src/vision_insight/pipeline/graph.py` (line 30)

**Problem**: `ProgressCallback = Any` loses type information. The actual type is `Callable[[str, int], None] | None`. Using `Any` means:
- No type checking on callback usage
- No IDE autocompletion for callback parameters
- Inconsistent with the project's mypy configuration

**Solution**: Replace with `ProgressCallback = Callable[[str, int], None] | None` and import from `collections.abc`.

**Benefits**: Better type safety and IDE support.

**Risk**: Very low — type alias only, no runtime change.

---

### P1-3: `_record_to_report` / `_report_to_record` should live on the model [arch]

**Files**: `src/vision_insight/api/routes.py` (lines 113-190), `src/vision_insight/core/database.py`

**Problem**: These two functions in routes.py handle serialization between `AnalysisRecord` and `AnalysisReport`. They:
- Duplicate JSON serialization logic (see P0-1)
- Are tightly coupled to the database model
- Belong in the data access layer, not the API layer

**Solution**: Move `to_report()` and `from_report()` methods onto `AnalysisRecord` in database.py. This improves locality — the model knows how to convert itself.

**Benefits**:
- Locality: serialization logic co-located with the model
- Leverage: routes.py becomes thinner, focused on HTTP concerns
- Testability: model conversion testable without HTTP layer

**Risk**: Medium — requires updating all call sites in routes.py.

---

### P1-4: `_report_to_record` loses scene_analysis data [debt]

**Files**: `src/vision_insight/api/routes.py` (lines 156-190)

**Problem**: `_report_to_record()` manually extracts fields from `report.scene_analysis` but misses some fields (e.g., `scene_analysis.people`, `scene_analysis.key_evidence`, `scene_analysis.uncertainties`). The round-trip is lossy.

**Solution**: Store the full `scene_analysis` as JSON (like `ocr_results_json`) instead of extracting individual fields. This preserves all data for the `/ask` endpoint.

**Benefits**: Data completeness, simpler serialization.

**Risk**: Medium — requires DB schema consideration (adding a column or replacing existing columns).

---

## P2 — High Effort

### P2-1: Singleton pattern duplication [arch]

**Files**: `src/vision_insight/core/service_registry.py`, `src/vision_insight/pipeline/runner.py`

**Problem**: Both modules implement identical singleton patterns:
```python
_singleton = None
def get_singleton(): ...
def reset_singleton(): ...
```

**Solution**: Extract a generic `Singleton[T]` utility or use a module-level instance pattern.

**Benefits**: DRY, consistent reset-for-testing behavior.

**Risk**: Low-medium, but touches core infrastructure.

---

### P2-2: routes.py is too large (692 lines) [arch]

**Files**: `src/vision_insight/api/routes.py`

**Problem**: routes.py contains:
- API endpoint definitions (HTTP layer)
- Record↔Report conversion logic (data layer)
- Progress tracking (infrastructure)
- File validation (utility)

This violates separation of concerns and makes the file hard to navigate.

**Solution**: Extract `_record_to_report`/`_report_to_record` to database.py, extract `_validate_image_file` to utils, extract progress tracking to its own module.

**Benefits**: Locality — each concern in its own module. Leverage — smaller files are easier to test and modify.

**Risk**: Medium-high — many imports and call sites to update.

---

## P3 — Design Decisions

### P3-1: Rate limiter memory management [perf/security]

**Files**: `src/vision_insight/core/rate_limiter.py`

**Problem**: The `_requests` dict grows unbounded between cleanup intervals. Under DDoS with many unique IPs, memory could grow significantly before cleanup kicks in.

**Current mitigation**: `_MAX_TRACKED_IPS = 10_000` cap during cleanup, but this only runs every 300 seconds.

**Options**:
1. Use an LRU cache with max size (e.g., `functools.lru_cache` or `cachetools.TTLCache`)
2. Move to Redis-based rate limiting for production
3. Accept current implementation as sufficient for single-node deployment

**Decision needed**: Is this a real threat given the deployment model?

---

### P3-2: URL analysis security boundary [security]

**Files**: `src/vision_insight/api/routes.py` (lines 340-375)

**Problem**: The `/analyze/url` endpoint downloads arbitrary URLs without:
- Content-Length validation (could download gigabytes)
- Content-Type validation before download
- SSRF protection (could hit internal services)
- Download timeout is only 30s but no size limit

**Options**:
1. Add streaming download with size limit
2. Add URL allowlist/blocklist
3. Add Content-Type header check before full download
4. Accept as-is if behind a reverse proxy with its own limits

**Decision needed**: Level of SSRF protection required for deployment environment.
