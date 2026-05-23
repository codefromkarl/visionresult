# PRD: Add missing type annotations to public functions

## Category
debt

## Problem
Several public functions are missing type annotations, which makes mypy unable to verify correct usage:
- `get_engine()` missing return type
- `setup_api_key_auth()` missing return type and `app` parameter type
- `setup_rate_limiting()` missing return type and `app` parameter type
- `setup_request_id()` missing return type and `app` parameter type
- `retry_with_backoff()` missing `coro_factory` parameter type and return type

## What to Change
Add proper type annotations to the following functions:
1. `get_engine()` → `-> Engine`
2. `setup_api_key_auth(app: FastAPI, enabled: bool = True) -> None`
3. `setup_rate_limiting(app: FastAPI, requests_per_minute: int = 60, requests_per_hour: int = 1000) -> None`
4. `setup_request_id(app: FastAPI) -> None`
5. `retry_with_backoff(coro_factory: Callable[[], Awaitable[T]], max_retries: int = MAX_RETRIES) -> T`

## Acceptance Criteria
1. All specified functions have proper type annotations
2. mypy passes without errors
3. All existing tests pass
4. No functional changes

## Scope
- `src/vision_insight/core/database.py`
- `src/vision_insight/core/auth.py`
- `src/vision_insight/core/rate_limiter.py`
- `src/vision_insight/core/request_id.py`
- `src/vision_insight/utils/retry.py`

## Evidence
- mypy warnings for missing type annotations

## Statement
No functional changes — this is type annotation improvement only.
