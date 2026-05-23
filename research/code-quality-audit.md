# Code Quality Audit: visionresult
Date: 2026-05-23
Sources: src/vision_insight/core/, src/vision_insight/utils/, src/vision_insight/api/, tests/

## Summary

Comprehensive audit of the visionresult codebase focusing on dead code, type annotations, inconsistent patterns, security, and performance.

---

## Findings

### 1. Dead Code & Unused Functions

#### debt: `cleanup_old_analyses()` - Never Called
- **File**: `src/vision_insight/core/database.py:266-287`
- **Issue**: Function is defined but never imported or used anywhere in the codebase
- **Evidence**: `grep -rn "cleanup_old_analyses" src/` returns only the definition
- **Recommendation**: Either integrate into a scheduled task/cron job, or remove if not needed

#### debt: `sanitize_log_message()` - Unused Export
- **File**: `src/vision_insight/core/sanitizer.py:89-114`
- **Issue**: Function is defined and exported but never called outside the module
- **Evidence**: Only referenced within `sanitizer.py` itself
- **Recommendation**: Remove or keep as public API if intended for external use

#### debt: `clear_task_events()` - Unused Export
- **File**: `src/vision_insight/core/event_logger.py:123-126`
- **Issue**: Function is defined but never called in the codebase
- **Evidence**: `grep -rn "clear_task_events" src/` returns only the definition
- **Recommendation**: Either add cleanup logic that calls this, or remove

---

### 2. Missing Type Annotations

#### debt: `get_engine()` Missing Return Type
- **File**: `src/vision_insight/core/database.py:122`
- **Code**: `def get_engine():`
- **Issue**: No return type annotation; should be `-> Engine`
- **Impact**: mypy cannot verify correct usage

#### debt: `get_session()` Missing Return Type
- **File**: `src/vision_insight/core/database.py:139`
- **Code**: `def get_session() -> Session:` (correct, but underlying `_SessionLocal` is untyped)
- **Issue**: The global `_SessionLocal: None` lacks type annotation
- **Fix**: `_SessionLocal: sessionmaker | None = None`

#### debt: `setup_api_key_auth()` Missing Return Type
- **File**: `src/vision_insight/core/auth.py:127`
- **Code**: `def setup_api_key_auth(app, enabled: bool = True):`
- **Issue**: Missing return type `-> None` and `app` parameter untyped
- **Fix**: `def setup_api_key_auth(app: FastAPI, enabled: bool = True) -> None:`

#### debt: `setup_rate_limiting()` Missing Return Type
- **File**: `src/vision_insight/core/rate_limiter.py:154`
- **Code**: `def setup_rate_limiting(app, requests_per_minute: int = 60, requests_per_hour: int = 1000):`
- **Issue**: Missing return type and `app` parameter untyped

#### debt: `setup_request_id()` Missing Return Type
- **File**: `src/vision_insight/core/request_id.py:56`
- **Code**: `def setup_request_id(app):`
- **Issue**: Both `app` parameter and return type missing

#### debt: `retry_with_backoff()` Missing Type Annotations
- **File**: `src/vision_insight/utils/retry.py:17`
- **Code**: `async def retry_with_backoff(coro_factory, max_retries: int = MAX_RETRIES):`
- **Issue**: `coro_factory` parameter untyped, return type missing
- **Fix**: `async def retry_with_backoff(coro_factory: Callable[[], Awaitable[T]], max_retries: int = MAX_RETRIES) -> T:`

#### debt: Multiple Route Handlers Missing Return Types
- **File**: `src/vision_insight/api/routes.py`
- **Lines**: 292, 358, 395, 430, 458, 466, 485, 521, 596, 618, 630
- **Issue**: Many async route handlers lack explicit return type annotations

---

### 3. Inconsistent Patterns

#### debt: Inconsistent `from __future__ import annotations` Usage
- **Files**: Mixed usage across codebase
  - **Has import**: `models/schemas.py`, `services/vlm/prompts.py`, `services/ocr/baidu_service.py`, `utils/__init__.py`, `tests/`
  - **Missing**: `core/config.py`, `core/database.py`, `core/auth.py`, `core/rate_limiter.py`, `api/routes.py`, `api/health.py`
- **Impact**: Inconsistent behavior with type hints (deferred vs immediate evaluation)
- **Recommendation**: Add to all files or remove from all; prefer adding for Python 3.11+ forward compatibility

#### debt: Inconsistent `datetime` Import Pattern
- **Pattern 1** (`api/routes.py:8`, `api/health.py:4`): `from datetime import UTC, datetime`
- **Pattern 2** (`core/database.py:7`): `from datetime import datetime` (no UTC)
- **Pattern 3** (`core/database.py:269`): `from datetime import UTC, timedelta` (inside function)
- **Recommendation**: Standardize on importing `UTC` at module level when needed

#### debt: Inconsistent Logging Setup
- **Pattern 1** (`core/event_logger.py`): Custom `_StructuredFormatter` with JSON output
- **Pattern 2** (`core/database.py`, `core/service_registry.py`): Standard `logging.getLogger(__name__)`
- **Impact**: Mixed log formats in production
- **Recommendation**: Centralize logging configuration

#### debt: Global State Pattern Inconsistency
- **Files**: `core/database.py:118-119`, `core/auth.py:62`, `core/event_logger.py:159`, `core/service_registry.py:313`
- **Issue**: Multiple modules use `global` keyword for singleton patterns
- **Recommendation**: Consider using a proper singleton pattern or dependency injection

---

### 4. Security Issues

#### security: `.env` File Contains Real API Keys
- **File**: `.env` (project root)
- **Issue**: Contains production API keys for:
  - Cloudflare deploy token
  - Gemini API key
  - Zhipu API key
  - Baidu OCR credentials
- **Mitigation**: `.env` is in `.gitignore` (good), but file exists on disk
- **Risk**: If `.gitignore` is modified or repo is shared, keys leak
- **Recommendation**: Use `.env.example` with placeholder values; rotate keys if exposed

#### security: `request: Request = None` Default Parameter
- **File**: `src/vision_insight/api/routes.py:298`
- **Code**: `request: Request = None`
- **Issue**: FastAPI's `Request` should not have `None` as default; should use `Optional[Request]` or make it required
- **Impact**: Potential `NoneType` errors if request is not provided

#### security: No SSRF Protection on Image URL Download
- **File**: `src/vision_insight/api/routes.py:365-375`
- **Code**: `resp = await client.get(request.image_url)`
- **Issue**: No validation of URL scheme/host before downloading; attacker could provide internal URLs (e.g., `http://localhost:8000/admin`, `file:///etc/passwd`)
- **Recommendation**: Validate URL scheme (only http/https), block private IP ranges, add timeout

#### security: Rate Limiter Trusts X-Forwarded-For Header
- **File**: `src/vision_insight/core/rate_limiter.py:39-44`
- **Issue**: Directly uses `X-Forwarded-For` header for IP extraction without validation
- **Impact**: Attacker can bypass rate limiting by spoofing header
- **Recommendation**: Only trust forwarded headers when behind a known reverse proxy; configure trusted proxies

#### security: API Key Hash Cache Never Invalidated
- **File**: `src/vision_insight/core/auth.py:62`
- **Issue**: `_valid_key_hashes` is computed once and cached forever; if API keys change at runtime, old keys remain valid
- **Recommendation**: Add cache invalidation or TTL

---

### 5. Performance Anti-patterns

#### perf: `get_database_stats()` Makes 4 Separate Queries
- **File**: `src/vision_insight/core/database.py:288-305`
- **Issue**: Executes 4 separate `COUNT` queries instead of one aggregated query
- **Code**:
  ```python
  total = session.query(AnalysisRecord).count()  # Query 1
  completed = session.query(AnalysisRecord).filter_by(status="completed").count()  # Query 2
  failed = session.query(AnalysisRecord).filter_by(status="failed").count()  # Query 3
  pending = session.query(AnalysisRecord).filter(...).count()  # Query 4
  ```
- **Fix**: Use single query with `GROUP BY`:
  ```python
  from sqlalchemy import func
  results = session.query(AnalysisRecord.status, func.count()).group_by(AnalysisRecord.status).all()
  ```

#### perf: `_cleanup_progress()` Called on Every Analysis
- **File**: `src/vision_insight/api/routes.py:237`
- **Issue**: Scans all progress entries on every new analysis request
- **Impact**: O(n) operation on each request; could block under load
- **Recommendation**: Use TTL-based cache (e.g., `cachetools.TTLCache`) or background cleanup task

#### perf: Rate Limiter Cleanup Runs on Every Request
- **File**: `src/vision_insight/core/rate_limiter.py:53-79`
- **Issue**: `_cleanup_old_entries()` is called inside `_check_rate_limit()` which runs on every request
- **Mitigation**: Has `cleanup_interval` check (good), but still adds overhead
- **Recommendation**: Move cleanup to background task or use Redis for distributed rate limiting

#### perf: SSE Event Generator Creates New DB Connection per Heartbeat
- **File**: `src/vision_insight/api/routes.py:560-575`
- **Issue**: On timeout (heartbeat), calls `get_analysis(task_id)` which opens a new DB session
- **Impact**: Each SSE connection holds a DB connection open during heartbeats
- **Recommendation**: Cache the status or use a lighter mechanism (e.g., in-memory status flag)

#### perf: Image Saved to Disk Before Background Task Starts
- **File**: `src/vision_insight/api/routes.py:335`
- **Code**: `image_path.write_bytes(image_bytes)`
- **Issue**: Disk I/O happens in the request handler, blocking the response
- **Recommendation**: Move file save to background task or use async file I/O

---

## Key Files

| File | Issues Found |
|------|--------------|
| `src/vision_insight/core/database.py` | Dead code (`cleanup_old_analyses`), missing types, N+1 queries |
| `src/vision_insight/core/auth.py` | Missing types, cache invalidation, unused `Request` import |
| `src/vision_insight/core/rate_limiter.py` | Missing types, X-Forwarded-For trust |
| `src/vision_insight/core/sanitizer.py` | Unused export (`sanitize_log_message`) |
| `src/vision_insight/core/event_logger.py` | Unused export (`clear_task_events`) |
| `src/vision_insight/api/routes.py` | SSRF vulnerability, missing types, performance issues |
| `src/vision_insight/utils/retry.py` | Missing type annotations |
| `.env` | Contains real API keys (mitigated by .gitignore) |

---

## Recommendations

### Immediate Actions
1. **Rotate API keys** in `.env` if they've been committed to git history
2. **Add SSRF protection** to URL download endpoint
3. **Fix `request: Request = None`** type annotation

### Short-term Improvements
1. Add return type annotations to all public functions
2. Standardize `from __future__ import annotations` usage
3. Optimize `get_database_stats()` to use single query
4. Remove or integrate dead code (`cleanup_old_analyses`, `clear_task_events`)

### Long-term Architecture
1. Replace global state singletons with dependency injection
2. Centralize logging configuration
3. Add Redis-based rate limiting for production
4. Implement proper caching layer for DB status checks

---

## Category Summary

| Category | Count | Severity |
|----------|-------|----------|
| **debt** | 12 | Low-Medium |
| **security** | 5 | Medium-High |
| **perf** | 5 | Low-Medium |
| **arch** | 3 | Medium |
