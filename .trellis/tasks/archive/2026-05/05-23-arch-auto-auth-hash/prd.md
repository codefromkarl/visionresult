# arch-auto: precompute auth hashes

## Category
perf

## What to change and why

Currently, `verify_api_key()` and `check_api_key_middleware` both compute SHA-256 hashes of ALL valid API keys on EVERY request. Evidence: `research/backend-audit.md` finding #7.

The valid key hashes should be computed once and cached, avoiding repeated hashing on every request.

### Changes:

1. **core/auth.py**: Add a module-level `_valid_key_hashes: list[str] | None = None` cache.
2. Add `_get_valid_key_hashes() -> list[str]` that computes and caches hashes.
3. Update both `verify_api_key()` and `check_api_key_middleware()` to use the cached hashes.
4. This also eliminates the duplicated key verification logic — both callers now use the same cache.

## Acceptance criteria
- `ruff check src/vision_insight/core/auth.py` passes
- `tests/unit/core/test_auth.py` passes
- No functional changes

## Scope
Only `src/vision_insight/core/auth.py`

## No functional changes
