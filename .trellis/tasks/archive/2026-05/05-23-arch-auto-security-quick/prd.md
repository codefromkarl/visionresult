# arch-auto: security quick fixes

## Category
security / debt

## What to change and why

Two small security-related fixes from architecture audit. Evidence: `research/synthesis.md` P0-5, P0-6.

### Changes:

1. **scripts/deploy.sh line 44**: Fix `CLOUDFRAME_API_KEY` typo → `CLOUDFLARE_API_KEY`.
   This env var fallback never works because the name is misspelled.

2. **services/search/http_search_service.py line 26**: Remove hardcoded proxy fallback `"http://127.0.0.1:7897"`.
   When no proxy env var is set, the code silently routes all search traffic through a local proxy that likely doesn't exist, causing opaque failures. Use `None` instead.

## Acceptance criteria
- `ruff check src/` passes
- All existing tests pass
- No functional changes to API behavior

## Scope
Only these files:
- `scripts/deploy.sh`
- `src/vision_insight/services/search/http_search_service.py`

## No functional changes
