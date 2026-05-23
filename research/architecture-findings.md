# Architecture Deepening Opportunities - Research Findings

## Date: 2026-05-23
## Scope: Historical debt, architecture standardization, performance, security

---

## P0 Candidates (trivial/low-risk, high leverage)

### P0-1: Dead database config — `database.py` ignores `config.py`
**Category**: arch / debt
**Files**: `src/vision_insight/core/database.py`, `src/vision_insight/core/config.py`
**Problem**: `config.py` defines `database_url` (PostgreSQL connection string) but `database.py` hardcodes `DB_PATH = Path("data/vision_insight.db")` and `DATABASE_URL = f"sqlite:///{DB_PATH}"`. The PostgreSQL code path in `get_engine()` is dead code — it can never be reached because `DATABASE_URL` always starts with `sqlite:`. The `config.py` setting creates false expectations.
**Solution**: Remove dead PostgreSQL code path from `get_engine()`, remove `database_url` from `config.py`, and add a comment explaining SQLite is the only supported backend.
**Evidence**: `database.py:12-13`, `database.py:81-93`, `config.py:42`

### P0-2: Duplicated `_dedupe` utility
**Category**: debt
**Files**: `src/vision_insight/services/fallback.py`, `src/vision_insight/services/entity/llm_entity_service.py`
**Problem**: `fallback.py:111-120` defines `_dedupe()`. `llm_entity_service.py:111-115` has identical inline deduplication logic in `_fallback_extraction()`. The `RuleBasedEntityService.extract()` in fallback.py also duplicates the same high-confidence OCR filtering pattern from `LLMEntityService._fallback_extraction()`.
**Solution**: Move `_dedupe()` to `utils/` and import it in both places.
**Evidence**: `fallback.py:111-120`, `llm_entity_service.py:108-120`

### P0-3: Duplicated VLM scene analysis prompts
**Category**: debt
**Files**: `src/vision_insight/services/vlm/api_service.py`, `src/vision_insight/services/vlm/zhipu_service.py`
**Problem**: Both files define `SCENE_ANALYSIS_PROMPT_ZH` and `SCENE_ANALYSIS_PROMPT_EN`. The `api_service.py` versions are detailed (with JSON schema, field constraints). The `zhipu_service.py` versions are minimal. The `OBJECT_DETECTION_PROMPT_*` prompts are already shared via `prompts.py`, but scene analysis prompts are not.
**Solution**: Move the detailed scene analysis prompts from `api_service.py` to `prompts.py` and import from there.
**Evidence**: `api_service.py:30-96`, `zhipu_service.py:28-39`

### P0-4: Duplicated OCR context building across VLM services
**Category**: debt
**Files**: `src/vision_insight/services/vlm/api_service.py`, `src/vision_insight/services/vlm/zhipu_service.py`
**Problem**: Three methods (`OpenAIVLMService.analyze`, `GeminiVLMService.analyze`, `ZhipuVLMService.analyze`) all contain identical OCR context building logic:
```python
ocr_context = ""
if ocr_results:
    texts = [r.text for r in ocr_results]
    if lang == "en":
        ocr_context = f"\nOCR detected these texts: {texts}\n"
    else:
        ocr_context = f"\n图片中检测到的文字：{texts}\n"
```
**Solution**: Extract `build_ocr_context(ocr_results, lang)` to `utils/` or `vlm/prompts.py`.
**Evidence**: `api_service.py:117-123`, `api_service.py:175-181`, `zhipu_service.py:68-74`

### P0-5: Duplicated entity extraction fallback logic
**Category**: debt
**Files**: `src/vision_insight/services/entity/llm_entity_service.py`, `src/vision_insight/services/fallback.py`
**Problem**: `LLMEntityService._fallback_extraction()` (lines 103-120) and `RuleBasedEntityService.extract()` (lines 85-99) implement nearly identical logic:
1. Get location from `scene.location_guess`
2. Filter OCR results by confidence >= 0.8
3. Return EntityExtraction with same fields
**Solution**: Extract shared logic into a standalone function and call from both places.
**Evidence**: `llm_entity_service.py:103-120`, `fallback.py:85-99`

### P0-6: Bound rate limiter memory (security)
**Category**: security
**Files**: `src/vision_insight/core/rate_limiter.py`
**Problem**: `_requests: dict[str, list[tuple[float, str]]]` grows unboundedly. Each unique IP adds entries. Under sustained load or DDoS, this dict will exhaust memory. The `_cleanup_old_entries` only removes entries older than 1 hour but doesn't cap total entries.
**Solution**: Add a max entries check (e.g., 10,000 IPs) and evict oldest when exceeded.
**Evidence**: `rate_limiter.py:26-28`

---

## P1 Candidates (medium effort, medium risk)

### P1-1: Per-request httpx.AsyncClient allocation
**Category**: perf
**Files**: All VLM/OCR/search/LLM services
**Problem**: Every HTTP call creates a new `httpx.AsyncClient` context manager. This loses connection pooling, adds TCP handshake overhead, and prevents HTTP/2 multiplexing. Pattern appears in ~7 files.
**Impact**: Performance degradation under concurrent requests.
**Risk**: Medium — requires lifecycle management of shared clients.

### P1-2: Duplicated VLM `analyze()` method structure
**Category**: debt
**Files**: `api_service.py`, `zhipu_service.py`
**Problem**: `OpenAIVLMService.analyze()`, `GeminiVLMService.analyze()`, `ZhipuVLMService.analyze()` all: (1) build OCR context, (2) select prompt by lang, (3) format prompt, (4) call API, (5) parse JSON, (6) call `build_scene_analysis()`. Steps 1-3 and 5-6 are identical.
**Risk**: Medium — introduces base class, may affect testing.

### P1-3: `config.py` Settings instantiated at import time
**Category**: arch
**Files**: `src/vision_insight/core/config.py`
**Problem**: `settings = Settings()` at module level means env vars are loaded at import time. This prevents test isolation and causes side effects during import.
**Risk**: Medium — changing to lazy singleton requires updating all imports.

### P1-4: SSRF risk in URL image download
**Category**: security
**Files**: `src/vision_insight/api/routes.py`
**Problem**: `create_analysis_from_url` accepts arbitrary URLs including internal network addresses (localhost, 169.254.169.254, etc.). No domain allowlist or IP validation.
**Risk**: Medium — adding validation may affect legitimate use cases.

---

## P2 Candidates (high effort)

### P2-1: Deprecated `@app.on_event("startup")` usage
**Category**: debt
**Files**: `src/vision_insight/main.py`

### P2-2: Pipeline trace imports inside functions
**Category**: arch
**Files**: `src/vision_insight/pipeline/graph.py:467-471`

### P2-3: Sanitizer sensitive keys not exhaustive
**Category**: security
**Files**: `src/vision_insight/core/sanitizer.py`

---

## P3 Candidates (design decisions)

### P3-1: SQLite vs PostgreSQL strategy
**Category**: arch
**Problem**: Project declares PostgreSQL as dependency but uses SQLite. Need explicit decision.

### P3-2: Service singleton pattern vs dependency injection
**Category**: arch
**Problem**: `service_registry.py` and `pipeline/runner.py` use module-level singletons with `reset_*` functions for testing. Consider proper DI.
