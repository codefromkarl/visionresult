# arch-auto: add retry to evidence LLM port

## Category
DEBT

## What to change and why

`ZhipuLLMPort.infer()` in `src/vision_insight/services/evidence/llm_ports.py` makes HTTP requests without retry logic. This is called for each evidence fusion conclusion (3-5 times per analysis). Transient failures will immediately degrade evidence quality instead of retrying.

### Changes:

1. **services/evidence/llm_ports.py**: Import `retry_with_backoff` from `vision_insight.utils.retry`
2. Wrap the HTTP call in `infer()` with `retry_with_backoff()`, following the same pattern as VLM services

### Evidence:
- `grep -r "retry" src/vision_insight/services/evidence/` returns no results
- File: `src/vision_insight/services/evidence/llm_ports.py:27-45`

## Acceptance criteria
- `ruff check src/` passes
- `mypy src/` passes
- Existing tests pass
- The `infer()` method now retries on transient HTTP failures

## Scope
Only modify: `src/vision_insight/services/evidence/llm_ports.py`

## Statement
No functional changes — only adds retry behavior on transient failures.
