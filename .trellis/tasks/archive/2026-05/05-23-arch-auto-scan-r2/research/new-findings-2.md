# Architecture Deepening Opportunity Scan - Round 2
Date: 2026-05-23
Sources: Codebase analysis of visionresult project

## Summary
Identified 8 new deepening opportunities NOT in the already-archived tasks. Focus areas: HTTP client efficiency, code deduplication, configuration consistency, and dependency injection patterns.

---

## P0 Candidates (Trivial/Low-Risk, High Leverage)

### 1. Httpx AsyncClient Connection Pool Reuse
**Files**: 
- `src/vision_insight/services/search/http_search_service.py` (3 instances)
- `src/vision_insight/services/vlm/api_service.py` (2 instances)
- `src/vision_insight/services/vlm/zhipu_service.py` (1 instance)
- `src/vision_insight/services/entity/llm_entity_service.py` (1 instance)
- `src/vision_insight/services/evidence/llm_ports.py` (1 instance)
- `src/vision_insight/services/ocr/baidu_service.py` (2 instances)
- `src/vision_insight/api/routes.py` (1 instance)

**Problem**: 11 instances of `httpx.AsyncClient()` created per-request inside `async with` blocks. Each creates a new connection pool, causing:
- TCP connection overhead on every request
- SSL handshake repeated for HTTPS endpoints
- No connection reuse between requests
- Memory churn from pool creation/destruction

**Solution**: Create a shared `httpx.AsyncClient` instance per service (lazily initialized) with proper lifecycle management. Example pattern:
```python
class HttpSearchService(SearchService):
    def __init__(self, ...):
        self._client: httpx.AsyncClient | None = None
    
    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self._timeout, proxy=_PROXY)
        return self._client
    
    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
```

**Risk**: Low — behavior unchanged, only connection lifecycle changes. Need to ensure proper cleanup on shutdown.

**Acceptance Criteria**:
- All HTTP calls reuse connections within a service instance
- No connection leak on service shutdown
- Existing tests pass unchanged
- Performance improvement measurable on repeated requests

---

### 2. Inconsistent Image Directory Configuration
**Files**:
- `src/vision_insight/core/config.py` (lines 19-20, 71-74)
- `src/vision_insight/api/routes.py` (line 76)
- `src/vision_insight/core/config.py` (line 73)

**Problem**: Image storage path is defined in 3 places with inconsistency:
- `config.py`: `upload_dir = Path("data/uploads")` and `cache_dir = Path("data/cache")`
- `routes.py`: `IMAGES_DIR = Path("data/images")` (hardcoded)
- `config.py:ensure_directories()`: `Path("data/images").mkdir(...)` (hardcoded)

The `upload_dir` config setting is unused — images go to `data/images` not `data/uploads`.

**Solution**: Add `images_dir: Path = Path("data/images")` to Settings and use it consistently:
```python
# config.py
class Settings(BaseSettings):
    images_dir: Path = Path("data/images")

def ensure_directories() -> None:
    settings.images_dir.mkdir(parents=True, exist_ok=True)
    # Remove: Path("data/images").mkdir(...)

# routes.py
IMAGES_DIR = settings.images_dir  # Use config instead of hardcoded
```

**Risk**: Low — purely configuration alignment, no behavior change.

**Acceptance Criteria**:
- Single source of truth for image directory path
- `upload_dir` and `cache_dir` either used or removed
- Health check reports correct paths

---

### 3. Unused `database_url` Config Field
**Files**: `src/vision_insight/core/config.py` (line 40)

**Problem**: `database_url: str = ""` is defined with comment "Kept here so that VIA_DATABASE_URL in .env doesn't cause a validation error." But the database module hardcodes SQLite path:
```python
DB_PATH = Path("data/vision_insight.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"
```

**Solution**: Either:
1. Remove `database_url` from Settings (if VIA_DATABASE_URL is not used)
2. Or use it in database.py: `DATABASE_URL = settings.database_url or f"sqlite:///{DB_PATH}"`

**Risk**: Low — removing unused config or making it functional.

**Acceptance Criteria**:
- Config field either used or removed
- No validation error if VIA_DATABASE_URL is absent

---

## P1 Candidates (Medium Risk, User Review Needed)

### 4. Duplicate LLM Chat Request Pattern
**Files**:
- `src/vision_insight/services/vlm/api_service.py` (lines 113-123, 202-208)
- `src/vision_insight/services/vlm/zhipu_service.py` (lines 109-119)
- `src/vision_insight/services/entity/llm_entity_service.py` (lines 102-112)
- `src/vision_insight/services/evidence/llm_ports.py` (lines 35-45)

**Problem**: 5 instances of identical pattern:
```python
async def _do_request():
    async with httpx.AsyncClient(timeout=self._timeout) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()
body = await retry_with_backoff(_do_request)
```

This violates DRY and makes it harder to add cross-cutting concerns (logging, metrics, circuit breaker).

**Solution**: Extract to shared utility in `utils/http.py`:
```python
async def post_json_with_retry(
    url: str,
    payload: dict,
    headers: dict,
    timeout: float = 30.0,
    max_retries: int = 3,
) -> dict:
    async def _do_request():
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()
    return await retry_with_backoff(_do_request, max_retries=max_retries)
```

**Risk**: Medium — changes request flow, need careful testing of each provider.

**Acceptance Criteria**:
- Single function handles all LLM API calls
- Retry behavior unchanged
- All VLM/Entity/Evidence tests pass

---

### 5. ContextVar for task_id Cross-Module Dependency
**Files**:
- `src/vision_insight/services/vlm/api_service.py` (lines 34-35)
- `src/vision_insight/pipeline/graph.py` (lines 301-309)

**Problem**: `current_task_id` ContextVar is defined in `api_service.py` but imported and used in `graph.py`. This creates a hidden dependency — graph.py must know about api_service's internal implementation.

**Solution**: Move `current_task_id` to a shared context module:
```python
# core/context.py
from contextvars import ContextVar
current_task_id: ContextVar[str] = ContextVar("current_task_id", default="unknown")
```

**Risk**: Medium — changes import paths, need to update all references.

**Acceptance Context**:
- ContextVar defined in single shared location
- No circular imports
- All pipeline tests pass

---

### 6. MarkdownReportService Instantiated Multiple Times
**Files**:
- `src/vision_insight/pipeline/graph.py` (line 651)
- `src/vision_insight/api/routes.py` (line 416)

**Problem**: `MarkdownReportService()` is instantiated in two places:
1. In `make_report_node()` factory — for pipeline use
2. In `get_report()` route — for HTML report generation

This bypasses the ServiceRegistry pattern used for other services.

**Solution**: Add `MarkdownReportService` to ServiceRegistry:
```python
class ServiceRegistry:
    def get_report_service(self) -> MarkdownReportService:
        if not self._initialized:
            self._initialize_services()
        return self._services.get("report") or MarkdownReportService()
```

**Risk**: Medium — changes service initialization flow.

**Acceptance Criteria**:
- Single instance used across pipeline and routes
- Report generation behavior unchanged
- HTML and markdown reports consistent

---

### 7. Proxy Configuration Inconsistency
**Files**:
- `src/vision_insight/services/search/http_search_service.py` (line 19)
- All other HTTP clients (no proxy support)

**Problem**: Only `HttpSearchService` reads `HTTP_PROXY`/`http_proxy` environment variables. Other services (VLM, OCR, Entity) don't support proxy, which may be needed in corporate environments.

**Solution**: Either:
1. Add proxy support to all HTTP clients via shared config
2. Or document that proxy is only for search services

**Risk**: Medium — changes network behavior for existing deployments.

**Acceptance Criteria**:
- Proxy configuration consistent across services
- Or clearly documented as search-only

---

## P2/P3 Candidates (High Effort/Design Decisions)

### 8. Pipeline Node Factory Pattern Refactoring
**Files**: `src/vision_insight/pipeline/graph.py` (733 lines, 7 node factories)

**Problem**: Each node factory (make_preprocess_node, make_ocr_node, etc.) follows the same pattern:
1. Get report from state
2. Notify progress
3. Start step tracking
4. Try/catch with logging
5. End step tracking
6. Return state

This leads to ~100 lines per node with significant duplication.

**Solution**: Create a node decorator or base class:
```python
@pipeline_node("preprocess")
async def preprocess_node(state: PipelineState, *, image_bytes: bytes) -> dict:
    # Only business logic here
    ...
```

**Risk**: High — significant refactoring of pipeline infrastructure.

**Acceptance Criteria**:
- All 7 nodes use consistent pattern
- Pipeline behavior unchanged
- Node code reduced by 50%+

---

## Key Files
- `src/vision_insight/services/search/http_search_service.py` — HTTP client pattern (lines 87, 120, 166)
- `src/vision_insight/core/config.py` — Settings class with unused fields
- `src/vision_insight/pipeline/graph.py` — 733 lines, 7 node factories with duplication
- `src/vision_insight/services/vlm/api_service.py` — ContextVar definition, duplicate patterns
- `src/vision_insight/api/routes.py` — Hardcoded IMAGES_DIR, duplicate service instantiation

## Recommendations
1. **Start with P0 #1** (httpx connection reuse) — highest performance impact, lowest risk
2. **P0 #2** (directory config) — quick cleanup, improves maintainability
3. **P1 #4** (LLM request pattern) — reduces duplication across 5 files
4. **Defer P2 #8** (node factory refactoring) — high effort, lower priority
