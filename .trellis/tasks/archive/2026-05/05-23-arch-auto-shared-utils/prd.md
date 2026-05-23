# PRD: Extract Shared VLM Utilities

**Category**: debt  
**Priority**: P0

## Problem

Three utility functions are duplicated across 2–3 files (~200 lines of duplication):

1. `_retry_with_backoff` — byte-for-byte identical in `api_service.py` and `zhipu_service.py` (60+ lines each)
2. `_parse_json_response` — identical in `api_service.py`, `zhipu_service.py`, `llm_entity_service.py` (~8 lines each)
3. `_build_scene_analysis` + `_build_detected_object` — identical in `api_service.py` and `zhipu_service.py` (~50 lines each)

GeminiVLMService also couples to `OpenAIVLMService._parse_json_response()` and `OpenAIVLMService._build_scene_analysis()` — these should be free functions.

## Solution

1. Create `src/vision_insight/utils/retry.py` — extract `retry_with_backoff`, `MAX_RETRIES`, `RETRY_BASE_DELAY`, `RETRYABLE_STATUS_CODES`
2. Create `src/vision_insight/utils/json_helpers.py` — extract `parse_llm_json()`
3. Create `src/vision_insight/utils/scene_builders.py` — extract `build_scene_analysis()`, `build_detected_object()`
4. Update imports in `api_service.py`, `zhipu_service.py`, `llm_entity_service.py`
5. Update `GeminiVLMService` to call free functions instead of `OpenAIVLMService._static_method()`

## Evidence

- Research: `.trellis/tasks/05-23-arch-auto-explore-2/research/findings.md` (F-1.1, F-1.2, F-1.3)

## Scope

Only these files:
- `src/vision_insight/utils/retry.py` (NEW)
- `src/vision_insight/utils/json_helpers.py` (NEW)
- `src/vision_insight/utils/scene_builders.py` (NEW)
- `src/vision_insight/services/vlm/api_service.py` (remove dupes, import from utils)
- `src/vision_insight/services/vlm/zhipu_service.py` (remove dupes, import from utils)
- `src/vision_insight/services/entity/llm_entity_service.py` (remove dupe, import from utils)

## Acceptance Criteria

- No functional changes — behavior is identical
- All existing tests pass
- Lint / typecheck clean

## Explicit Statement

**No functional changes.** This is pure code relocation with identical logic.
