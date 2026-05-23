# PRD: Fix Security Config Issues

**Category**: security  
**Priority**: P0

## Problem

Two security config issues:

1. **F-4.2**: `http_search_service.py:23` has a hardcoded proxy fallback `http://127.0.0.1:7897`. If deployed without a proxy, every search request hangs until timeout. Should default to `None`.
2. **F-4.4**: `auth.py` re-hashes all configured API keys on every request. Both `verify_api_key()` and the middleware independently compute hashes. Should cache hashes at first use.

## Solution

1. Change proxy fallback from `"http://127.0.0.1:7897"` to `None` in `http_search_service.py`
2. Add lazy module-level cache for key hashes in `auth.py`:
   - Add `_cached_key_hashes: list[str] | None = None`
   - Add `_get_key_hashes()` that computes and caches once
   - Update both `verify_api_key()` and middleware to use `_get_key_hashes()`

## Evidence

- Research: `.trellis/tasks/05-23-arch-auto-explore-2/research/findings.md` (F-4.2, F-4.4)

## Scope

Only these files:
- `src/vision_insight/services/search/http_search_service.py`
- `src/vision_insight/core/auth.py`

## Acceptance Criteria

- No functional changes — behavior is identical
- All existing tests pass
- Lint / typecheck clean

## Explicit Statement

**No functional changes.** Pure security config hardening.
