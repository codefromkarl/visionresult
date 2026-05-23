# arch-auto: add jitter to retry backoff

## Category
PERF

## What to change and why

`retry_with_backoff()` in `src/vision_insight/utils/retry.py` uses pure exponential backoff without jitter. Under high load, multiple clients could retry at the same time (thundering herd effect), causing cascading failures on the already-stressed upstream service.

### Changes:

1. **utils/retry.py**: Import `random` module
2. Add jitter to the delay calculation: `delay = RETRY_BASE_DELAY * (2**attempt) * (0.5 + random.random())`

### Evidence:
- File: `src/vision_insight/utils/retry.py:24` — `delay = RETRY_BASE_DELAY * (2**attempt)` — deterministic delay
- Standard best practice for retry logic to prevent thundering herd

## Acceptance criteria
- `ruff check src/` passes
- `mypy src/` passes
- Existing tests pass
- The retry delay now includes random jitter

## Scope
Only modify: `src/vision_insight/utils/retry.py`

## Statement
No functional changes — only adds jitter to retry timing to prevent thundering herd.
