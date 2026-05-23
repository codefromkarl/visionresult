# Backend Architecture Audit — vision_insight
Date: 2026-05-23
Sources: `src/vision_insight/` (all .py files)

## Findings

### 1. DUPLICATED PATTERN: `_retry_with_backoff` function copied 3 times
- **Files**:
  - `services/vlm/api_service.py` lines 36–63
  - `services/vlm/zhipu_service.py` lines 29–56
  - (also inline in `core/service_registry.py` ZhipuLLMPort, lines 221–247, with no retry)
- **Category**: arch
- **Severity**: medium
- **Detail**: The retry-with-exponential-backoff logic is identical in `api_service.py` and `zhipu_service.py` (same constants `MAX_RETRIES=3`, `RETRY_BASE_DELAY=1.0`, `RETRYABLE_STATUS_CODES`). Meanwhile `LLMEntityService._chat()` and `BaiduOCRService` have NO retry at all.
- **Fix**: Extract into `utils/http.py` as a shared `retry_with_backoff()` async helper. All HTTP-calling services should use it.

---

### 2. DUPLICATED PATTERN: `_parse_json_response` / `_build_scene_analysis` / `_build_detected_object` copied
- **Files**:
  - `services/vlm/api_service.py` lines 286–348
  - `services/vlm/zhipu_service.py` lines 220–290
  - `services/entity/llm_entity_service.py` lines 117–127 (`_parse_json_response`)
- **Category**: arch
- **Severity**: medium
- **Detail**: `GeminiVLMService.analyze()` explicitly calls `OpenAIVLMService._parse_json_response()` and `OpenAIVLMService._build_scene_analysis()` as static methods — a clear sign these should be shared utilities.
- **Fix**: Move JSON-parsing helpers to `utils/json.py` or `services/vlm/parsing.py`. Make `_build_scene_analysis` a standalone function or a base-class method.

---

### 3. DUPLICATED PATTERN: `httpx.AsyncClient(timeout=...)` created inline everywhere (Weak Seam)
- **Files** (11 call sites):
  - `services/vlm/api_service.py` lines 283, 444
  - `services/vlm/zhipu_service.py` line 209
  - `services/entity/llm_entity_service.py` line 100
  - `services/ocr/baidu_service.py` lines 98, 166
  - `services/search/http_search_service.py` lines 91, 124, 170
  - `core/service_registry.py` line 233
  - `api/routes.py` line 342
- **Category**: arch
- **Severity**: high
- **Detail**: No shared HTTP client factory. Each service creates and destroys its own `httpx.AsyncClient` per request, which means:
  1. No connection pooling across services
  2. No uniform timeout/proxy/retry configuration
  3. Can't inject a mock client for testing
- **Fix**: Create `core/http.py` with a singleton `get_async_client()` factory, injected into services. Services accept `client: httpx.AsyncClient` in `__init__`.

---

### 4. DUPLICATED PATTERN: Prompt constants duplicated across modules
- **Files**:
  - `services/vlm/api_service.py` lines 87–159 (SCENE_ANALYSIS_PROMPT_ZH, _EN, OBJECT_DETECTION_PROMPT_ZH, _EN)
  - `services/vlm/zhipu_service.py` lines 59–113 (same prompt names, abbreviated versions)
  - `services/__init__.py` defines abstract interface; prompts live in concrete classes
- **Category**: debt
- **Severity**: low
- **Detail**: `OBJECT_DETECTION_PROMPT_ZH` and `_EN` are byte-for-byte identical between `api_service.py` and `zhipu_service.py`. Scene analysis prompts differ (zhipu version is much shorter), but the object detection ones are the same.
- **Fix**: Extract shared prompts to `services/vlm/prompts.py`.

---

### 5. SECURITY: Gemini API key passed as URL query parameter
- **File**: `services/vlm/api_service.py` line 441
- **Category**: security
- **Severity**: high
- **Detail**: `url = f"...generateContent?key={self._api_key}"` — the API key is embedded directly in the URL. This key will appear in:
  - Server access logs
  - Proxy logs (the `http_search_service.py` proxies through `127.0.0.1:7897`)
  - Any error messages or stack traces that include the URL
  - httpx request repr
- **Fix**: Use header-based authentication (`x-goog-api-key` header) instead of query parameter.

---

### 6. SECURITY: Hardcoded proxy address in search service
- **File**: `services/search/http_search_service.py` line 26
- **Category**: security / debt
- **Severity**: medium
- **Detail**: `_PROXY = os.getenv("HTTP_PROXY") or os.getenv("http_proxy") or "http://127.0.0.1:7897"` — the fallback proxy address is hardcoded. If the environment variables aren't set, all Google/Bing/Wikipedia requests route through a local proxy that may not exist, silently failing.
- **Fix**: Remove hardcoded fallback. Use `None` if no proxy is configured. Move proxy config to `Settings`.

---

### 7. SECURITY: API key stored in plaintext in Settings, compared in plaintext
- **File**: `core/config.py` lines 31–34 (`api_keys`, `openai_api_key`, etc.)
- **File**: `core/auth.py` lines 70–75
- **Category**: security
- **Severity**: medium
- **Detail**: `api_keys` is a comma-separated string of raw API keys stored in env vars. Auth hashes them with SHA-256 for comparison, but the valid key hashes are recomputed on every request (`_hash_api_key(k) for k in valid_keys`). Original keys are in memory. This is acceptable for a small deployment but the double-hashing on every request is wasteful.
- **Fix**: Pre-compute hashes at startup. Consider storing pre-hashed keys in config instead of raw keys.

---

### 8. SECURITY: Auth middleware has duplicated verification logic
- **File**: `core/auth.py` lines 48–80 (`verify_api_key`) and lines 108–145 (`check_api_key_middleware`)
- **Category**: debt
- **Severity**: medium
- **Detail**: The key verification logic (get key → get valid keys → hash → compare) is duplicated between the FastAPI dependency `verify_api_key()` and the middleware `check_api_key_middleware`. The middleware also imports `JSONResponse` inside the function body twice.
- **Fix**: Extract a single `_validate_key(api_key: str) -> bool` helper used by both.

---

### 9. DEAD CODE: Unused image utility functions
- **File**: `utils/image.py`
- **Category**: debt
- **Severity**: low
- **Detail**: The following functions are defined but never called anywhere in the codebase:
  - `assess_sharpness()` (line 193) — only called by `is_blurry()` which is also unused
  - `is_blurry()` (line 225) — never called
  - `assess_sharpness_async()` (line 270) — never called
  - `is_blurry_async()` (line 282) — never called
  - `get_image_metadata_async()` (line 240) — never called (pipeline uses sync version)
  - `compress_image_async()` (line 252) — never called (pipeline uses sync version)
- **Fix**: Remove unused async wrappers. Keep `assess_sharpness`/`is_blurry` if planned for future use, otherwise remove.

---

### 10. DEAD CODE: Unused SanitizedLogger and sanitize_log_message
- **File**: `core/sanitizer.py` lines 91–168
- **Category**: debt
- **Severity**: low
- **Detail**: `sanitize_log_message()` and `SanitizedLogger` class are never used. Only `sanitize_string` and `sanitize_dict` are used (by `event_logger.py`).
- **Fix**: Remove `SanitizedLogger` and `sanitize_log_message`. If needed later, restore from git.

---

### 11. DEAD CODE: `generate_api_key()` function never called
- **File**: `core/auth.py` lines 100–106
- **Category**: debt
- **Severity**: low
- **Detail**: Function exists but no endpoint or CLI tool calls it.
- **Fix**: Either wire it to a `/api/v1/admin/api-keys` endpoint or remove.

---

### 12. DEAD CODE: Unused DB functions
- **File**: `core/database.py`
- **Category**: debt
- **Severity**: low
- **Detail**:
  - `cleanup_old_analyses()` (line 238) — never called from any API endpoint or background task
  - `get_database_stats()` (line 266) — only used by `health.py`, but `api/routes.py` has its own inline stats calculation (`get_stats` endpoint at line 435) that queries `list_analyses(limit=1000)` instead of using this function
- **Fix**: Wire `cleanup_old_analyses` to a scheduled task or admin endpoint. Replace inline stats in routes.py with `get_database_stats()`.

---

### 13. DEAD CODE: `TYPE_CHECKING` imports with empty blocks
- **Files**:
  - `services/ocr/baidu_service.py` lines 15, 23–24
  - `services/ocr/paddle_service.py` lines 6, 11–12
  - `services/ocr/tesseract_service.py` lines 7, 14–15
- **Category**: debt
- **Severity**: trivial
- **Detail**: `if TYPE_CHECKING: pass` blocks that do nothing.
- **Fix**: Remove empty TYPE_CHECKING imports.

---

### 14. SHALLOW MODULE: `api/health.py` duplicates VLM check logic
- **File**: `api/health.py` lines 66–83 (`_check_vlm_service`)
- **Category**: arch
- **Severity**: low
- **Detail**: Health check manually reimplements "is a VLM provider configured?" by checking settings directly, duplicating logic already in `DefaultServiceFactory.create_vlm_service()`. If a new provider is added, this health check must be updated separately.
- **Fix**: Delegate to ServiceRegistry or ServiceFactory for health checks.

---

### 15. SHALLOW MODULE: `_record_to_report` / `_report_to_record` conversion functions
- **File**: `api/routes.py` lines 109–220
- **Category**: arch
- **Severity**: medium
- **Detail**: These 110-line conversion functions sit in the routes module. They handle all the JSON serialization/deserialization between SQLAlchemy models and Pydantic models. This is domain logic that belongs in a mapper/repository layer, not in the HTTP handler.
- **Fix**: Move to `models/mappers.py` or add `from_orm` / `to_orm` methods on the Pydantic models.

---

### 16. WEAK SEAM: SQLite global state with no DI path for async tests
- **File**: `core/database.py` lines 90–100
- **Category**: arch
- **Severity**: medium
- **Detail**: Database uses global `_engine` and `_SessionLocal` singletons. There's no way to inject a test database URL or use an in-memory SQLite for tests without monkeypatching globals. `pool_size=5` and `max_overflow=10` are set but SQLite ignores these parameters (they're for connection-pooling backends like PostgreSQL).
- **Fix**: Create a `Database` class that accepts a URL, with a `get_database()` factory. Support `sqlite+aiosqlite` for async.

---

### 17. WEAK SEAM: PipelineRunner accesses services by magic string keys
- **File**: `pipeline/runner.py` lines 51–59
- **Category**: arch
- **Severity**: low
- **Detail**: `services = self._registry.get_all_services()` returns `dict[str, Any]` with string keys like `"ocr"`, `"vlm"`, etc. PipelineRunner accesses `services["ocr"]` — any typo fails silently at runtime.
- **Fix**: Use the typed getter methods (`get_ocr_service()`, etc.) that already exist on ServiceRegistry.

---

### 18. CONFIG MISMATCH: `database_url` defaults to PostgreSQL but code uses SQLite
- **File**: `core/config.py` line 40: `database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/vision_insight"`
- **File**: `core/database.py` line 18: `DATABASE_URL = f"sqlite:///{DB_PATH}"`
- **Category**: debt
- **Severity**: high
- **Detail**: `Settings.database_url` is defined but NEVER USED. The database module hardcodes its own `DATABASE_URL` pointing to SQLite. The PostgreSQL default with hardcoded `postgres:postgres` credentials is misleading and unused.
- **Fix**: Either remove `database_url` from Settings, or refactor `database.py` to use `settings.database_url` and support async SQLAlchemy.

---

### 19. SECURITY: `_progress` dict grows without bound in routes.py
- **File**: `api/routes.py` line 24: `_progress: dict[str, list[tuple[str, int]]] = {}`
- **Category**: perf / security
- **Severity**: medium
- **Detail**: In-memory progress store is never cleaned up after analysis completes. Only `append(("done", 100))` is added in `finally` block, but the key is never deleted. Over time this dict grows indefinitely.
- **Fix**: Delete `_progress[task_id]` in the `finally` block of `_run_analysis`, or use TTL-based eviction.

---

### 20. UNUSED PARAMETER: `analysis_depth` accepted but never used
- **File**: `api/routes.py` line 271: `analysis_depth: str = "standard"`
- **File**: `api/routes.py` line 296: `analysis_depth=analysis_depth` (passed to `_run_analysis` which ignores it)
- **Category**: debt
- **Severity**: low
- **Detail**: The `analysis_depth` parameter is accepted in the API endpoint and logged but `_run_analysis()` doesn't use it. No depth-based logic exists.
- **Fix**: Either implement depth-based analysis (e.g., skip search/web verification for "quick") or remove the parameter.

---

### 21. PERFORMANCE: `get_stats` loads all records into memory
- **File**: `api/routes.py` lines 435–447
- **Category**: perf
- **Severity**: medium
- **Detail**: `list_analyses(limit=1000)` loads up to 1000 full analysis records (including large JSON blobs for OCR, entities, conclusions) into memory just to count statuses. `get_database_stats()` in `database.py` does this efficiently with SQL `COUNT` queries but is not used here.
- **Fix**: Replace with `get_database_stats()` call.

---

### 22. SECURITY: URL image download has no SSRF protection
- **File**: `api/routes.py` lines 321–340 (`create_analysis_from_url`)
- **Category**: security
- **Severity**: high
- **Detail**: The endpoint accepts any URL and makes a server-side request to fetch it. There's no validation against internal IPs (`127.0.0.1`, `10.x`, `192.168.x`, `169.254.x`). An attacker could use this to probe internal services (SSRF).
- **Fix**: Validate the URL scheme (http/https only), resolve the hostname, and reject private/internal IP ranges before fetching.

---

### 23. SECURITY: Gemini API key logged in URL on error
- **File**: `services/vlm/api_service.py` line 441
- **Category**: security
- **Severity**: medium
- **Detail**: If the Gemini request fails, `httpx.HTTPStatusError` includes the full URL with the API key in its string representation. The `sanitizer.py` patterns don't cover Gemini-style keys.
- **Fix**: Use header auth (see finding #5). Add Gemini key pattern to sanitizer.

---

### 24. DEAD CODE: `LLMPort.infer_with_reasoning` default impl + `EmptyLLMPort`
- **File**: `core/service_registry.py` lines 256–263 (`EmptyLLMPort`)
- **File**: `services/evidence/fusion_service.py` lines 29–38 (`infer_with_reasoning` default)
- **Category**: debt
- **Severity**: trivial
- **Detail**: `EmptyLLMPort` is used when no Zhipu key is configured — it returns empty strings. The base `LLMPort.infer_with_reasoning` provides a default that delegates to `infer()`. These are correctly architected but the `ZhipuLLMPort` inside `service_registry.py` reimplements `infer_with_reasoning` with a Chinese-language prompt hack instead of using the base class default.
- **Fix**: Move `ZhipuLLMPort` to its own file in `services/evidence/`. Consider using the base class default for `infer_with_reasoning`.

---

## Summary by Severity

| Severity | Count | Finding IDs |
|----------|-------|-------------|
| **High** | 4 | #3 (httpx seam), #5 (key in URL), #18 (config mismatch), #22 (SSRF) |
| **Medium** | 8 | #1, #2, #6, #7, #8, #15, #16, #19, #21, #23 |
| **Low** | 7 | #4, #9, #10, #11, #12, #14, #17, #20 |
| **Trivial** | 2 | #13, #24 |

## Key Files
- `core/service_registry.py` — ServiceFactory + LLMPort inline impl (lines 85–280)
- `core/database.py` — Global engine singleton, unused `database_url` setting (lines 14–100)
- `core/config.py` — Settings with dead `database_url` field (line 40)
- `core/auth.py` — Duplicated verification logic (lines 48–80, 108–145)
- `services/vlm/api_service.py` — Gemini key in URL (line 441), copied helpers
- `services/vlm/zhipu_service.py` — Copied retry/parsing/prompt code
- `services/search/http_search_service.py` — Hardcoded proxy (line 26)
- `api/routes.py` — SSRF endpoint (lines 321–340), inline stats (lines 435–447), mapper functions (lines 109–220)
- `utils/image.py` — 6 unused functions (lines 193–292)
- `core/sanitizer.py` — Unused SanitizedLogger class (lines 119–168)

## Recommendations
1. **Immediate**: Fix SSRF (#22), Gemini key exposure (#5/#23), and config mismatch (#18) before any production deployment.
2. **Short-term**: Create shared `utils/http.py` for retry logic and HTTP client factory (#1, #3). Extract prompt constants (#4) and JSON parsing helpers (#2).
3. **Medium-term**: Refactor `api/routes.py` to move DB↔Pydantic mapping out of routes (#15). Add DI for database (#16). Unify auth verification (#8).
4. **Ongoing**: Periodically run `dead-code` analysis. Remove unused async wrappers, SanitizedLogger, TYPE_CHECKING stubs.
