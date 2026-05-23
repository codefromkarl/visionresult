# arch-auto: add retry to entity LLM calls

## Category
DEBT

## What to change and why

`LLMEntityService._chat()` in `src/vision_insight/services/entity/llm_entity_service.py` makes HTTP requests without retry logic. All VLM services (`api_service.py`, `zhipu_service.py`) use `retry_with_backoff()`, but entity extraction does not.

This inconsistency means transient HTTP failures (429, 500, 502, 503, 504, timeouts) will immediately fail entity extraction instead of retrying.

### Changes:

1. **services/entity/llm_entity_service.py**: Import `retry_with_backoff` from `vision_insight.utils.retry`
2. Wrap the HTTP call in `_chat()` with `retry_with_backoff()`, following the same pattern as VLM services

### Evidence:
- `grep -r "retry_with_backoff" src/` shows VLM services use it; entity service does not
- File: `src/vision_insight/services/entity/llm_entity_service.py:84-98`

## Acceptance criteria
- `ruff check src/` passes
- `mypy src/` passes
- Existing tests pass
- The `_chat()` method now retries on transient HTTP failures

## Scope
Only modify: `src/vision_insight/services/entity/llm_entity_service.py`

## Statement
No functional changes — only adds retry behavior on transient failures.
