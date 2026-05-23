# PRD: Remove Hardcoded Proxy Fallback

## Category: security

## What to change and why

`src/vision_insight/services/search/http_search_service.py:23` hardcodes a local proxy address:

```python
_PROXY = os.getenv("HTTP_PROXY") or os.getenv("http_proxy") or "http://127.0.0.1:7897"
```

This hardcoded fallback causes outbound search requests to route through `127.0.0.1:7897` in any
environment that doesn't explicitly set `HTTP_PROXY`. In production or CI, this silently leaks
requests to an unintended host (or fails with connection refused).

Evidence: `rg -t py -n "_PROXY" src/vision_insight/services/search/http_search_service.py`

## Acceptance criteria
- `_PROXY` defaults to `None` (no proxy) when env vars are unset
- `ruff check src/` passes
- `python3 -m pytest tests/ -x -q` passes

## Scope
- `src/vision_insight/services/search/http_search_service.py` (line 23 only)

## No functional changes
Only changes the fallback behavior when env vars are not set.
