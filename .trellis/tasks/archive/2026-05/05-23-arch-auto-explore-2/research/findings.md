# Architecture Deepening Research Findings

**Project**: Visual Insight Agent (visionresult)  
**Date**: 2025-05-23  
**Scope**: Historical debt, architecture standardization, performance, security  

---

## 1. Historical Debt Cleanup

### F-1.1 Duplicated `_retry_with_backoff` — 100% copy-paste [P0]

**Files**:  
- `src/vision_insight/services/vlm/api_service.py:32–63`  
- `src/vision_insight/services/vlm/zhipu_service.py:26–57`  

The `_retry_with_backoff` function, along with its constants `MAX_RETRIES`, `RETRY_BASE_DELAY`, `RETRYABLE_STATUS_CODES`, is **byte-for-byte identical** across both files. 

**Impact**: Any bug fix or config change (e.g., making retry count configurable) must be applied twice. High Leverage — extract to `utils/retry.py` or a shared `vlm/_common.py`.

---

### F-1.2 Duplicated `_parse_json_response` × 3 copies [P0]

**Files**:  
- `src/vision_insight/services/vlm/api_service.py:296–303`  
- `src/vision_insight/services/vlm/zhipu_service.py:222–230`  
- `src/vision_insight/services/entity/llm_entity_service.py:112–118`  

All three are the same markdown-fence stripping + `json.loads()` logic. Extract to a shared utility, e.g., `utils/json_helpers.py:parse_llm_json()`.

---

### F-1.3 Duplicated `_build_scene_analysis` × 2 copies [P0]

**Files**:  
- `src/vision_insight/services/vlm/api_service.py:308–355`  
- `src/vision_insight/services/vlm/zhipu_service.py:234–274`  

Identical static methods building `SceneAnalysis` from a dict. `GeminiVLMService` already delegates to `OpenAIVLMService._build_scene_analysis()` (line 399), proving this should be a shared function. Same for `_build_detected_object` (api_service:348 vs zhipu_service:274).

---

### F-1.4 Duplicated prompt templates × 2 files [P1]

**Files**:  
- `src/vision_insight/services/vlm/api_service.py:77–192` (~115 lines)  
- `src/vision_insight/services/vlm/zhipu_service.py:70–114` (~45 lines)  

Both files define `SCENE_ANALYSIS_PROMPT_ZH`, `SCENE_ANALYSIS_PROMPT_EN`, `OBJECT_DETECTION_PROMPT_ZH`, `OBJECT_DETECTION_PROMPT_EN`, and backward-compatible aliases. The `api_service.py` versions are more detailed. Extract to `services/vlm/prompts.py`.

---

### F-1.5 Dead `if TYPE_CHECKING: pass` blocks [P0]

**Files**:  
- `src/vision_insight/services/ocr/tesseract_service.py:14–15`  
- `src/vision_insight/services/ocr/baidu_service.py:23–24`  
- `src/vision_insight/services/ocr/paddle_service.py:11–12`  

All three have `if TYPE_CHECKING: pass` — literally a no-op import guard with no types imported. Remove them.

---

### F-1.6 Unused backward-compatible prompt aliases [P0]

**Files**:  
- `src/vision_insight/services/vlm/api_service.py:160,191` — `SCENE_ANALYSIS_PROMPT = SCENE_ANALYSIS_PROMPT_EN`  
- `src/vision_insight/services/vlm/zhipu_service.py:83,114` — `SCENE_ANALYSIS_PROMPT = SCENE_ANALYSIS_PROMPT_ZH`  

These aliases are defined but never referenced anywhere in the codebase. The code only uses the `_ZH`/`_EN` suffixed names.

---

### F-1.7 Unused `AnalysisRecord.create` / `PaddleOCRService.create_for_language` factory methods [P0]

- `src/vision_insight/services/ocr/baidu_service.py:211–228` — `BaiduOCRService.create()` classmethod is never called; the `DefaultServiceFactory` uses `BaiduOCRService(...)` directly.  
- `src/vision_insight/services/ocr/paddle_service.py:126–144` — `PaddleOCRService.create_for_language()` is never called.

---

### F-1.8 Unused schema import in `services/__init__.py` [P0]

**File**: `src/vision_insight/services/__init__.py:11`  

```python
from vision_insight.models.schemas import (
    DetectedObject,
    ...
)
```

`DetectedObject`, `ImageMetadata`, and `SearchResult` are imported but only used in type annotations on the abstract service classes. This is correct for the ABC signatures, but the import is fine — just noting that the abstract interfaces themselves don't use `DetectedObject` in any method signature (only VLMService.detect_objects return type uses it, which is correct). No action needed.

---

### F-1.9 Unused `_record_to_report` context assembly [P1]

**File**: `src/vision_insight/api/routes.py:562` — The line `"\n".join(context_parts)` computes a context string but **the result is never stored or used**. The `ask_question` endpoint builds context but then uses a rule-based approach instead. The variable is computed and discarded.

---

## 2. Architecture Standardization

### F-2.1 No shared HTTP client — 11 independent `httpx.AsyncClient` instances [P1]

**Pattern across**: `api_service.py`, `zhipu_service.py`, `baidu_service.py`, `http_search_service.py`, `llm_entity_service.py`, `service_registry.py` (ZhipuLLMPort), `routes.py` (URL download).

Every HTTP call creates a new `async with httpx.AsyncClient(timeout=...) as client:` — meaning:
- **No connection pooling** across the pipeline. A single analysis run may create 5–10 short-lived TCP connections to the same host.
- **No shared retry/logging/timeout config**.

**Recommendation**: Create a shared `core/http.py` module that provides a lazily-initialized singleton `httpx.AsyncClient` with connection pooling. Services receive it via dependency injection or access it via a module-level getter. This is a Seam that's currently missing.

---

### F-2.2 `ZhipuLLMPort` / `EmptyLLMPort` defined inline in `service_registry.py` [P1]

**File**: `src/vision_insight/core/service_registry.py:212–276`  

Two classes are defined **inside** `DefaultServiceFactory.create_evidence_service()`. This:
- Bloats a 290-line method to ~80 lines of inline class definition.
- Cannot be unit-tested independently.
- Duplicates the OpenAI-compatible chat API call pattern already in `llm_entity_service.py` and `vlm/api_service.py`.

**Recommendation**: Extract to `services/evidence/zhipu_llm_port.py` (or reuse `LLMEntityService` as the LLM port).

---

### F-2.3 GeminiVLMService calls OpenAIVLMService static methods [P1]

**File**: `src/vision_insight/services/vlm/api_service.py:399–413`  

`GeminiVLMService.analyze()` calls `OpenAIVLMService._parse_json_response()` and `OpenAIVLMService._build_scene_analysis()`. This is a cross-class coupling that indicates these should be free functions, not static methods on `OpenAIVLMService`.

---

### F-2.4 `config.py` module-level side effects [P0]

**File**: `src/vision_insight/core/config.py:72–74`

```python
settings = Settings()
settings.upload_dir.mkdir(parents=True, exist_ok=True)
settings.cache_dir.mkdir(parents=True, exist_ok=True)
```

Importing `config.py` triggers directory creation. This is acceptable for a FastAPI app but problematic for:
- Tests that import anything transitively (creates real dirs).
- Any future use of the module as a library.

The `_setting_string()` / `_setting_bool()` helpers in `service_registry.py` exist specifically to work around `settings` being a MagicMock in tests — a code smell that the Settings object is both a config store and a globally-mutable singleton.

---

### F-2.5 SQLite engine with `pool_size=5, max_overflow=10` [P0]

**File**: `src/vision_insight/core/database.py:81–88`

SQLite is a file-based database that does not support concurrent writes. Setting `pool_size=5` and `max_overflow=10` is misleading — it creates a pool that cannot actually be used concurrently for writes. Meanwhile, `settings.database_url` defaults to PostgreSQL (`postgresql+asyncpg://...`) but the actual database module hardcodes `sqlite:///` at line 29. The PostgreSQL config is dead code.

---

### F-2.6 No ReportService registered in ServiceRegistry [P0]

The `ServiceRegistry` manages VLM, OCR, Entity, Search, and Evidence services, but **ReportService** is not in the registry. Instead, `MarkdownReportService` is instantiated directly in:
- `pipeline/graph.py:make_report_node()` (line 21)
- `api/routes.py:get_report()` (line 393)

This breaks the ServiceFactory pattern and makes it harder to swap report formats.

---

### F-2.7 Shallow Depth in `utils/image.py` [P1]

**File**: `src/vision_insight/utils/image.py` — 285 lines with 4 async wrappers that are trivial `asyncio.to_thread()` delegations. The `assess_sharpness` and `is_blurry` functions are defined but never called in the pipeline. They're only utility functions that could be useful, but they add dead code weight.

---

## 3. Performance Optimization

### F-3.1 New `httpx.AsyncClient` per request — no connection reuse [P1]

Every service method creates and destroys an `AsyncClient`. During a single analysis pipeline run:
1. OCR (Baidu): 2 clients (token fetch + OCR call)
2. VLM (Zhipu/OpenAI/Gemini): 1–2 clients
3. Entity (LLM): 1 client
4. Search (Wikipedia × 2 langs + Google + Bing): up to 4 clients
5. Evidence fusion LLM: 1 client
6. URL download (routes.py): 1 client

**Total: 8–12 short-lived clients per analysis.** Each incurs TCP handshake + TLS negotiation overhead.

**Recommendation**: Shared connection pool via a singleton `httpx.AsyncClient` with `limits=httpx.Limits(max_connections=20, max_keepalive_connections=10)`.

---

### F-3.2 PaddleOCR writes to temp file on every call [P1]

**File**: `src/vision_insight/services/ocr/paddle_service.py:98–107`

Every OCR call writes image bytes to a temp file (`tempfile.NamedTemporaryFile`) because PaddleOCR doesn't accept bytes directly. This is I/O overhead + cleanup risk. Consider converting bytes to numpy array via `cv2.imdecode()` (already imported in `utils/image.py`) and passing the array to PaddleOCR.

---

### F-3.3 `image_bytes` passed through entire pipeline without compression [P1]

The pipeline compresses images > 4MB in the preprocess node, but the compressed bytes are not stored back — the original `state["image_bytes"]` is passed to OCR, VLM, etc. Looking at the code more carefully:

**File**: `src/vision_insight/pipeline/graph.py:make_preprocess_node()` (line ~163)

```python
raw_bytes = compress_image(raw_bytes, ...)  # compressed locally
# But state["image_bytes"] is never updated!
```

The compressed bytes are only used for metadata extraction. OCR and VLM receive the original uncompressed bytes. This means:
- Baidu OCR may reject > 4MB images (it checks at line 131).
- VLM services base64-encode the full original image.

**Fix**: Update `state["image_bytes"]` after compression.

---

### F-3.4 `get_stats()` loads all records into memory [P0]

**File**: `src/vision_insight/api/routes.py:540–548`

```python
records = list_analyses(limit=1000)
total = len(records)
```

This loads up to 1000 records to count them. A `database.get_database_stats()` function already exists (line 276 in `database.py`) that uses `COUNT()` queries. The route should use it instead.

---

### F-3.5 `SanitizedLogger` never used [P0]

**File**: `src/vision_insight/core/sanitizer.py:104–160`

The `SanitizedLogger` class wraps Python's `logging.Logger` with automatic sanitization, but it's never instantiated anywhere. All code uses `logging.getLogger(__name__)` directly.

---

### F-3.6 `_strip_html` imports `re` inside the function [P0]

**File**: `src/vision_insight/services/search/http_search_service.py:201`

```python
def _strip_html(text: str) -> str:
    import re
    return re.sub(r"<[^>]+>", "", text)
```

`re` is imported on every call. Move to module level or use `str` methods.

---

### F-3.7 Rate limiter uses synchronous dict — no locking for concurrent access [P1]

**File**: `src/vision_insight/core/rate_limiter.py:32`

```python
self._requests: dict[str, list[tuple[float, str]]] = defaultdict(list)
```

Under high concurrency, the in-memory dict may have race conditions. The `_cleanup_old_entries` iterates and mutates the dict. While asyncio is single-threaded, `_check_rate_limit` is called synchronously from the middleware's `dispatch()` which could interleave. This is a minor risk but worth noting.

---

## 4. Security Hardening

### F-4.1 SSRF vulnerability in `/analyze/url` [P2]

**File**: `src/vision_insight/api/routes.py:341–351`

```python
async with httpx.AsyncClient(timeout=30.0) as client:
    resp = await client.get(request.image_url)
```

The server fetches any user-provided URL without validation. An attacker could:
- Access internal services (`http://169.254.169.254/latest/meta-data/` for cloud metadata).
- Scan internal network (`http://192.168.x.x`).
- Trigger requests to localhost services.

**Recommendation**: Add URL validation (block private IPs, link-local, localhost). Use an allowlist of URL schemes (https only).

---

### F-4.2 Hardcoded proxy address in search service [P0]

**File**: `src/vision_insight/services/search/http_search_service.py:23`

```python
_PROXY = os.getenv("HTTP_PROXY") or os.getenv("http_proxy") or "http://127.0.0.1:7897"
```

Falls back to a hardcoded local proxy. If deployed without a proxy, every search request will fail silently or hang for the timeout duration. Should be `None` as default, or configured via `settings`.

---

### F-4.3 API keys logged/transaced in event_logger [P1]

While `event_logger.py` sanitizes data via `sanitize_dict()`, the `log_event` in `api/routes.py:263` logs `client_ip`. The `ask_question` endpoint (`routes.py:635`) includes `report_markdown` content in the response, which may contain sensitive extracted text. The SSE stream (`routes.py:504`) broadcasts all events including potentially sensitive OCR text.

---

### F-4.4 Auth middleware rehashes all keys on every request [P0]

**File**: `src/vision_insight/core/auth.py:107–111`

```python
valid_keys = _get_configured_api_keys()
if valid_keys:
    hashed_key = _hash_api_key(api_key)
    valid_hashes = [_hash_api_key(k) for k in valid_keys]
```

Both `verify_api_key()` and the middleware re-hash all configured keys on every request. SHA-256 is fast, but this should be cached at startup. More importantly, the same pattern exists in two places (the `verify_api_key` function and the middleware) — duplicated auth logic.

---

### F-4.5 `datetime.now()` without timezone — potential issues [P0]

**Files**: Multiple — see F-2.5 above.

`database.py:32` uses `datetime.now` (no UTC). `schemas.py:207` uses `default_factory=datetime.now`. `health.py` uses `datetime.utcnow()` (deprecated in Python 3.12+). All should use `datetime.now(UTC)` for consistency with `event_logger.py`.

---

### F-4.6 No input length limit on `question` field [P0]

**File**: `src/vision_insight/api/routes.py:616` — `QuestionRequest.question` has no max length. A malicious user could submit a multi-MB string. Add `Field(max_length=1000)`.

---

### F-4.7 `format` query parameter shadowing built-in [P0]

**File**: `src/vision_insight/api/routes.py:373`

```python
async def get_report(task_id: str, format: str = "json", ...):
```

`format` shadows Python's built-in `format()`. While not a security issue, it's a code quality concern. Rename to `output_format` or `report_format`.

---

### F-4.8 Unsanitized URL passed to image download [P1]

**File**: `src/vision_insight/api/routes.py:341`

The `request.image_url` is used directly with `httpx.get()` without any URL scheme validation. Could be `file:///etc/passwd` or other dangerous schemes.

---

## Summary Table

| ID | Category | Priority | Description | File(s) |
|----|----------|----------|-------------|---------|
| F-1.1 | Debt | P0 | Duplicated `_retry_with_backoff` | api_service.py, zhipu_service.py |
| F-1.2 | Debt | P0 | Duplicated `_parse_json_response` × 3 | api_service.py, zhipu_service.py, llm_entity_service.py |
| F-1.3 | Debt | P0 | Duplicated `_build_scene_analysis` × 2 | api_service.py, zhipu_service.py |
| F-1.4 | Debt | P1 | Duplicated prompt templates | api_service.py, zhipu_service.py |
| F-1.5 | Debt | P0 | Dead `if TYPE_CHECKING: pass` | 3 OCR services |
| F-1.6 | Debt | P0 | Unused prompt aliases | api_service.py, zhipu_service.py |
| F-1.7 | Debt | P0 | Unused factory methods | baidu_service.py, paddle_service.py |
| F-1.9 | Debt | P1 | Unused context string in ask endpoint | routes.py:562 |
| F-2.1 | Arch | P1 | No shared HTTP client (11 separate clients) | 6 files |
| F-2.2 | Arch | P1 | Inline LLM port classes in registry | service_registry.py:212–276 |
| F-2.3 | Arch | P1 | GeminiVLMService couples to OpenAIVLMService | api_service.py:399 |
| F-2.4 | Arch | P0 | Module-level side effects on import | config.py:72–74 |
| F-2.5 | Arch | P0 | SQLite pool_size with PostgreSQL dead config | database.py:29 vs config.py |
| F-2.6 | Arch | P0 | ReportService not in ServiceRegistry | graph.py, routes.py |
| F-2.7 | Arch | P1 | Shallow Depth: unused sharpness functions | utils/image.py |
| F-3.1 | Perf | P1 | 8–12 HTTP clients per analysis run | 6 files |
| F-3.2 | Perf | P1 | PaddleOCR temp file per call | paddle_service.py:98 |
| F-3.3 | Perf | P1 | Compressed bytes not propagated in pipeline | graph.py:preprocess |
| F-3.4 | Perf | P0 | get_stats loads 1000 records instead of COUNT | routes.py:540 |
| F-3.5 | Perf | P0 | SanitizedLogger defined but never used | sanitizer.py:104–160 |
| F-3.6 | Perf | P0 | `import re` inside function body | http_search_service.py:201 |
| F-4.1 | Sec | P2 | SSRF in `/analyze/url` | routes.py:341 |
| F-4.2 | Sec | P0 | Hardcoded proxy fallback | http_search_service.py:23 |
| F-4.3 | Sec | P1 | Sensitive data in SSE events | routes.py, event_logger.py |
| F-4.4 | Sec | P0 | Auth rehashes keys every request | auth.py:107–111 |
| F-4.5 | Sec | P0 | `datetime.now()` without UTC | database.py, schemas.py, health.py |
| F-4.6 | Sec | P0 | No input length limit on question | routes.py:616 |
| F-4.7 | Sec | P0 | `format` shadows built-in | routes.py:373 |
| F-4.8 | Sec | P1 | Unsanitized URL for image download | routes.py:341 |

---

## Recommended Priority Order

### Sprint 1 (P0 — Quick Wins)
1. Extract shared `_retry_with_backoff`, `_parse_json_response`, `_build_scene_analysis` (F-1.1, F-1.2, F-1.3)
2. Remove dead code: TYPE_CHECKING guards, unused aliases, unused factories (F-1.5, F-1.6, F-1.7)
3. Fix `get_stats` to use COUNT query (F-3.4)
4. Remove unused `SanitizedLogger` or adopt it (F-3.5)
5. Move `import re` to module level (F-3.6)
6. Fix hardcoded proxy (F-4.2)
7. Fix `datetime.now()` → `datetime.now(UTC)` (F-4.5)
8. Add question length limit (F-4.6)
9. Register ReportService in ServiceRegistry (F-2.6)
10. Resolve SQLite vs PostgreSQL config conflict (F-2.5)

### Sprint 2 (P1 — Medium Effort)
1. Create shared HTTP client with connection pooling (F-2.1 / F-3.1)
2. Extract inline LLM port classes (F-2.2)
3. Extract prompt templates to shared module (F-1.4)
4. Fix compressed image bytes propagation (F-3.3)
5. Fix PaddleOCR temp file issue (F-3.2)
6. Add URL validation for SSRF prevention (F-4.1, F-4.8)

### Sprint 3 (P2 — Design Decisions)
1. Comprehensive security audit of SSE event broadcasting
2. Rate limiter thread safety review
3. Config singleton testability redesign
