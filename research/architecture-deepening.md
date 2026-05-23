# Architecture Deepening Opportunities — VisionResult
Date: 2025-06-23
Sources: Full codebase scan of `src/vision_insight/`

---

## Findings

### 1. VLM Services: Massive Code Duplication (Shallow Modules + Repeated Patterns)

**Files:** `services/vlm/api_service.py`, `services/vlm/zhipu_service.py`
**Category:** debt
**Risk:** P0 — high leverage, low effort

**Problem:** `OpenAIVLMService`, `GeminiVLMService`, and `ZhipuVLMService` are three classes with near-identical **public API** (`analyze`, `detect_objects`) and identical **post-processing** logic (`parse_llm_json` → `build_scene_analysis` / `build_detected_object`). The only real difference is the HTTP request format in the private helper (`_vision_chat` / `_generate`).

The module interface (`VLMService` ABC: `analyze` + `detect_objects`) is **deeper** than it appears — but the three implementations duplicate:
- The `analyze()` method body (OCR context building → prompt selection → call helper → parse JSON → build model)
- The `detect_objects()` method body
- Import sets
- Constructor pattern (api_key, model, base_url, timeout)

This is a textbook **Shallow Module** — each implementation's "unique" code (the HTTP payload format) is ~20 lines, but each file is 100+ lines with duplicated orchestration.

**Recommendation:** Extract a `BaseVLMService` that implements `analyze()` and `detect_objects()` with the shared logic, requiring subclasses to implement only `_call_vlm(prompt, image_bytes) -> str`. This would cut ~60% of the VLM code.

---

### 2. `LLMEntityService._chat()` Duplicates VLM HTTP Pattern (Repeated Pattern)

**Files:** `services/entity/llm_entity_service.py`, `services/vlm/api_service.py`, `services/evidence/llm_ports.py`
**Category:** debt
**Risk:** P0 — trivial to extract

**Problem:** Three separate implementations of "call OpenAI-compatible chat completions API with retry":

1. `OpenAIVLMService._vision_chat()` — image+text chat
2. `LLMEntityService._chat()` — text-only chat
3. `ZhipuLLMPort.infer()` — text-only chat

All three share:
- Same `httpx.AsyncClient` + `retry_with_backoff` pattern
- Same `Authorization: Bearer` header construction
- Same `body["choices"][0]["message"]["content"]` extraction
- Same error handling structure

This is **Locality violation** — the same adapter pattern is scattered across 3 files.

**Recommendation:** Create a shared `ChatCompletionClient` utility class in `utils/` that handles the HTTP + retry + response extraction. All three callers would delegate to it. The VLM variants would pass image content, entity/extraction would pass text only.

---

### 3. `BaiduOCRService` Global Mutable Token Cache (Misplaced Adapter / Security)

**File:** `services/ocr/baidu_service.py` (line ~30: `_token_cache: tuple[str, float] | None = None`)
**Category:** security, arch
**Risk:** P1

**Problem:** The access token cache is a **module-level global variable** (`_token_cache`) shared across all `BaiduOCRService` instances. This creates:
- **Thread-safety issue**: No lock around read/write of `_token_cache` — concurrent requests could race.
- **Hidden coupling**: Multiple `BaiduOCRService` instances (if created) silently share the same token.
- **Test pollution**: Can't reset the cache in tests without monkey-patching the global.

The instance also stores `_access_token` and `_token_expires_at` redundantly with the global — two sources of truth.

**Recommendation:** Move token cache into the instance (or use a proper thread-safe singleton). Add `threading.Lock` if keeping the global.

---

### 4. `auth.py` — Dual Validation Path (Misplaced Adapter)

**File:** `core/auth.py`
**Category:** arch
**Risk:** P1

**Problem:** API key validation exists in **two places**:
1. `verify_api_key()` dependency (used by FastAPI route injection)
2. `check_api_key_middleware()` middleware (checks every request)

The middleware and the dependency both call `_validate_api_key()`, but the middleware handles skip-paths independently. Routes that use `verify_api_key` as a dependency get **double-checked** when the middleware is also enabled. This is a **Seam** in the wrong place — auth should be one consistent layer.

Additionally, `_get_valid_key_hashes()` uses a module-level global `_valid_key_hashes` that's never invalidated if `settings.api_keys` changes.

**Recommendation:** Remove the middleware approach entirely. Use only FastAPI's dependency injection (`verify_api_key`) on protected routes. Define a `get_current_api_key` dependency. This eliminates the skip-path list duplication and the double-check.

---

### 5. `routes.py` — Monolithic Route File (Locality Issue)

**File:** `api/routes.py` (480+ lines)
**Category:** arch
**Risk:** P2

**Problem:** All API routes live in a single file with heavy business logic inlined:
- `_validate_image_file()` — file validation logic
- `_record_to_report()` / `_report_to_record()` — ORM ↔ domain model conversion (100+ lines)
- `_run_analysis()` — background task orchestration
- `ask_question()` — rule-based QA logic

The route handler layer **absorbs** concerns that belong in service/adapter layers. The `_record_to_report` / `_report_to_record` functions are pure data adapters that should live near the database layer.

**Recommendation:** Extract `_record_to_report` / `_report_to_record` into `core/database.py` or a dedicated `adapters/` module. Extract `_run_analysis` into `pipeline/runner.py`. Keep routes as thin dispatchers.

---

### 6. `httpx.AsyncClient` Created Per-Request (Performance)

**Files:** `services/vlm/api_service.py`, `services/vlm/zhipu_service.py`, `services/evidence/llm_ports.py`, `services/entity/llm_entity_service.py`, `services/search/http_search_service.py`, `services/ocr/baidu_service.py`
**Category:** perf
**Risk:** P1

**Problem:** Every single HTTP call creates a **new `httpx.AsyncClient`** instance inside a `async with` block. This means:
- No connection pooling across calls
- TCP handshake + TLS negotiation on every request
- For VLM calls (which are expensive), this adds ~100-200ms per request

In `api_service.py` line 98: `async with httpx.AsyncClient(timeout=self._timeout) as client:` — inside a `_do_request()` closure that's called by `retry_with_backoff`, so a new client is created **on every retry attempt**.

**Recommendation:** Create `httpx.AsyncClient` instances at service initialization time (lazy or eager) and reuse them. The client should be closed during application shutdown.

---

### 7. Pipeline Graph Nodes — Boilerplate Explosion (Repeated Pattern)

**File:** `pipeline/graph.py` (500+ lines)
**Category:** debt
**Risk:** P1

**Problem:** Every pipeline node (`make_preprocess_node`, `make_ocr_node`, `make_vlm_node`, `make_entity_node`, `make_search_node`, `make_fusion_node`, `make_report_node`) follows the **exact same pattern**:

```python
def make_X_node(service):
    async def X_node(state):
        report = state["report"]
        task_id = report.id
        _notify_progress(state, "X")
        step_info = _start_pipeline_step(state, "X")
        log_event(task_id, "node_start", node="X")
        try:
            # ... unique logic ...
            log_event(task_id, "insight", ...)
            _end_pipeline_step(state, step_info, ...)
        except Exception as exc:
            log_event(task_id, "node_fail", ...)
            _end_pipeline_step(state, step_info, status="failed", ...)
        return {"report": report}
    return X_node
```

The progress notification, step tracking, logging, and error handling boilerplate is **identical** across all 7 nodes. This is ~50 lines of boilerplate per node × 7 = ~350 lines of duplicated scaffolding.

**Recommendation:** Create a `@pipeline_node(name)` decorator or a `PipelineNode` base that wraps the unique logic with the standard scaffolding. The unique logic per node would be ~20-30 lines instead of ~80-100.

---

### 8. `json_helpers.py` — Shallow Module (Low-Leverage Abstraction)

**File:** `utils/json_helpers.py`
**Category:** debt
**Risk:** P2

**Problem:** `parse_llm_json()` is a 10-line function that strips markdown fences and calls `json.loads()`. The module has one function. The "interface" (call `parse_llm_json(text)`) is exactly as complex as the implementation (strip fences + parse JSON). This is a **Shallow Module** with near-zero Depth.

It's used by 3 callers, so it's not useless, but it doesn't warrant its own module.

**Recommendation:** Merge into `utils/__init__.py` or `utils/json_utils.py` alongside other JSON-related helpers if more are added. Low priority.

---

### 9. `scene_builders.py` — Another Shallow Module

**File:** `utils/scene_builders.py`
**Category:** debt
**Risk:** P2

**Problem:** Two simple builder functions (`build_scene_analysis`, `build_detected_object`) that do basic dict → Pydantic model conversion. Total: ~40 lines. The module exists solely because the VLM services were refactored to extract these, but they could live alongside the schemas or in a `builders/` package.

Combined with `json_helpers.py`, there are **two** utility modules that are essentially thin wrappers with minimal Depth.

**Recommendation:** Consolidate `json_helpers.py` + `scene_builders.py` into a single `utils/llm_utils.py` module.

---

### 10. `service_registry.py` — Over-Abstracted Factory Layer (Low-Leverage Abstraction)

**File:** `core/service_registry.py`
**Category:** arch
**Risk:** P2

**Problem:** The module introduces:
- `ServiceFactory` (abstract base with 5 abstract methods)
- `DefaultServiceFactory` (concrete implementation)
- `ServiceRegistry` (wraps factory, adds caching)
- `get_service_registry()` (singleton accessor)

For a single-node application with one configuration source, this is **over-engineered**. The `ServiceFactory` ABC is never subclassed by anyone other than `DefaultServiceFactory`. The `ServiceRegistry` adds lazy initialization but the factory itself does all the real work.

The **Leverage** is low: the abstraction exists to enable testing with mock factories, but in practice tests could mock the individual services directly.

**Recommendation:** Simplify to a single `create_services(config) -> dict[str, Service]` function. Keep the registry for caching. Remove the ABC unless a second factory implementation is actually needed.

---

### 11. URL Image Download — No SSRF Protection (Security)

**File:** `api/routes.py` line ~210 (`create_analysis_from_url`)
**Category:** security
**Risk:** P1

**Problem:** The `/analyze/url` endpoint accepts an arbitrary URL and fetches it with `httpx.AsyncClient.get(request.image_url)`. There is **no validation** of the URL target:
- An attacker could pass `http://169.254.169.254/latest/meta-data/` (AWS metadata)
- Or `http://localhost:6379/` (internal Redis)
- Or `file:///etc/passwd` (file protocol)

This is a classic **SSRF** (Server-Side Request Forgery) vulnerability.

**Recommendation:** Add URL validation: block private IPs (10.x, 172.16-31.x, 192.168.x, 127.x, 169.254.x), block non-HTTP(S) schemes, optionally use a allowlist of domains.

---

### 12. Image Upload — Path Traversal in Filename (Security)

**File:** `api/routes.py` line ~179
**Category:** security
**Risk:** P1

**Problem:** Image is saved as:
```python
image_path = IMAGES_DIR / f"{task_id}{Path(file.filename).suffix.lower()}"
```

The `file.filename` comes from user input. While `Path.suffix` extracts the extension, a filename like `../../etc/cron.d/evil` would have suffix `.evil` (not in ALLOWED_EXTENSIONS), so it's partially mitigated by the extension check. However, the code doesn't sanitize the extension itself — a `.jpg` extension with crafted content could still be problematic in some contexts.

More critically, the `_validate_image_file` check happens **after** `await file.read()` but the file is saved to disk **without** waiting for validation in the batch endpoint — no, actually validation happens first. This is acceptable.

**Recommendation:** Use `secure_filename()` or explicitly extract only the extension with `os.path.splitext()`. Validate extension against allowlist before constructing the path.

---

### 13. `sanitize_dict` Leaks Partial Secrets (Security)

**File:** `core/sanitizer.py`
**Category:** security
**Risk:** P1

**Problem:** The `sanitize_dict` function partially reveals secrets:
```python
if isinstance(value, str) and len(value) > 4:
    sanitized[key] = value[:2] + '***' + value[-2:]
```

For a key like `api_key = "sk-abc123def456ghi789"`, this outputs `sk-***89`. The first 2 and last 2 characters are leaked. For short keys (< 5 chars), it fully redacts, but most API keys are longer. This defeats the purpose of redaction — an attacker with log access can narrow down the key space.

**Recommendation:** Fully redact all values under sensitive keys: `sanitized[key] = "***"`. Only the key name should be visible.

---

### 14. Rate Limiter — No Thread Safety (Performance / Security)

**File:** `core/rate_limiter.py`
**Category:** security, perf
**Risk:** P1

**Problem:** The `RateLimitMiddleware` uses `_requests: dict[str, list]` with **no locking**. FastAPI with uvicorn runs async code in a single thread, but:
- If deployed with workers > 1, each worker has its own rate limiter (no shared state)
- If any middleware or handler uses `run_in_executor`, concurrent access to `_requests` is possible
- The `_cleanup_old_entries` method iterates and mutates the dict — not safe under concurrent access

Additionally, the sliding window stores every request timestamp — for a busy API, this list grows unbounded between cleanups.

**Recommendation:** Use `asyncio.Lock` for async safety. Consider using a more memory-efficient data structure (e.g., circular buffer or Redis for multi-worker).

---

### 15. `event_logger.py` — Mixed Async/Threading Concerns (Architecture)

**File:** `core/event_logger.py`
**Category:** arch
**Risk:** P2

**Problem:** The module uses `threading.Lock` (`_store_lock`, `_sse_lock`) but also manages `asyncio.Queue` objects. The `_broadcast_event` method is called from sync code but puts into async queues. This works because `put_nowait()` is sync-safe, but the design conflates two concurrency models.

The `_event_store` is an in-memory dict with no persistence — if the process restarts, all event history is lost. Combined with the SSE queues (which are also in-memory), this means:
- No event replay capability
- Memory grows with number of tracked tasks (capped at 50 tasks × 200 events)

**Recommendation:** For production, consider SQLite-backed event storage (the project already uses SQLite for analyses). For now, document the in-memory limitation clearly.

---

### 16. `ask_question` Endpoint — Hardcoded Rule-Based QA (Low-Leverage Abstraction)

**File:** `api/routes.py` lines ~370-430
**Category:** arch
**Risk:** P2

**Problem:** The `/ask` endpoint uses keyword matching (`if any(kw in question for kw in [...])`) to answer questions. This is brittle:
- Chinese/English keyword overlap can cause wrong matches
- No semantic understanding
- Confidence values are hardcoded guesses (0.5-0.95)
- The `sources` field lists module names, not actual evidence

The endpoint presents itself as "分析问答" (analysis Q&A) but is actually a simple keyword router with fabricated confidence scores.

**Recommendation:** Either (a) remove the endpoint and document that Q&A requires LLM integration, or (b) use the existing `LLMPort` to answer questions with the analysis context.

---

### 17. Singleton Pattern Without Lifecycle Management (Architecture)

**Files:** `core/service_registry.py`, `pipeline/runner.py`
**Category:** arch
**Risk:** P2

**Problem:** Both `get_service_registry()` and `get_pipeline_runner()` use module-level globals with `reset_*()` functions for testing. This pattern:
- Doesn't integrate with FastAPI's lifespan events
- Services hold `httpx.AsyncClient` instances that should be closed on shutdown
- No graceful shutdown for database connections
- `reset_*()` functions exist only for tests, polluting the public API

**Recommendation:** Use FastAPI's dependency injection (`app.dependency_overrides`) for testing. Use `app.add_event_handler("shutdown", ...)` for cleanup. Consider `@lru_cache` or a proper DI container.

---

### 18. Database — No Migration System (Architecture)

**File:** `core/database.py`
**Category:** arch
**Risk:** P2

**Problem:** `Base.metadata.create_all(_engine)` creates tables at startup but has **no migration support**. If a column is added or changed, existing SQLite databases will be silently incompatible. There's no Alembic or similar migration tool configured.

**Recommendation:** Add Alembic for schema migrations. At minimum, add a startup check that validates the schema matches the models.

---

## Summary Table

| # | Finding | Category | Risk | Files |
|---|---------|----------|------|-------|
| 1 | VLM services: massive code duplication | debt | P0 | `vlm/api_service.py`, `vlm/zhipu_service.py` |
| 2 | Chat completion HTTP pattern × 3 | debt | P0 | `vlm/api_service.py`, `entity/llm_entity_service.py`, `evidence/llm_ports.py` |
| 3 | BaiduOCR global token cache, no lock | security | P1 | `ocr/baidu_service.py` |
| 4 | Dual auth validation (middleware + dependency) | arch | P1 | `core/auth.py` |
| 5 | Monolithic routes.py with inlined adapters | arch | P2 | `api/routes.py` |
| 6 | httpx.AsyncClient created per-request | perf | P1 | All service files |
| 7 | Pipeline node boilerplate × 7 | debt | P1 | `pipeline/graph.py` |
| 8 | json_helpers.py — shallow module | debt | P2 | `utils/json_helpers.py` |
| 9 | scene_builders.py — shallow module | debt | P2 | `utils/scene_builders.py` |
| 10 | Over-abstracted ServiceFactory ABC | arch | P2 | `core/service_registry.py` |
| 11 | SSRF vulnerability in URL analysis | security | P1 | `api/routes.py` |
| 12 | Filename extension not fully sanitized | security | P1 | `api/routes.py` |
| 13 | sanitize_dict leaks partial secrets | security | P1 | `core/sanitizer.py` |
| 14 | Rate limiter has no thread safety | security | P1 | `core/rate_limiter.py` |
| 15 | Mixed async/threading in event_logger | arch | P2 | `core/event_logger.py` |
| 16 | Hardcoded rule-based QA with fake confidence | arch | P2 | `api/routes.py` |
| 17 | Singletons without lifecycle management | arch | P2 | `core/service_registry.py`, `pipeline/runner.py` |
| 18 | No database migration system | arch | P2 | `core/database.py` |

## Recommendations Summary

**Quick Wins (P0):**
1. Extract `BaseVLMService` to eliminate VLM duplication — saves ~200 lines
2. Extract shared `ChatCompletionClient` — eliminates 3 copies of the same HTTP adapter

**High-Leverage (P1):**
3. Fix SSRF in `/analyze/url` — security vulnerability
4. Create `httpx.AsyncClient` per-service, not per-request — ~100-200ms savings per VLM call
5. Fix `sanitize_dict` to fully redact secrets
6. Add `asyncio.Lock` to rate limiter
7. Consolidate pipeline node boilerplate with decorator pattern
8. Remove duplicate auth middleware, keep only dependency injection

**Design Debt (P2):**
9. Split `routes.py` into thin route handlers + service adapters
10. Simplify `ServiceRegistry` to a function + cache
11. Add Alembic for database migrations
12. Integrate singletons with FastAPI lifespan
