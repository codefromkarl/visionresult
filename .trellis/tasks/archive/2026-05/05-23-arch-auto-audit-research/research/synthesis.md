# Architecture Audit — Synthesized Findings & Priority Classification
Date: 2026-05-23
Source: research/backend-audit.md + research/frontend-infra-audit.md

## P0 — Trivial/Low-Risk, High Leverage (Auto-implement)

| # | Category | Finding | Files | Risk |
|---|----------|---------|-------|------|
| P0-1 | debt | Remove unused SanitizedLogger + sanitize_log_message | core/sanitizer.py | None |
| P0-2 | debt | Remove empty TYPE_CHECKING blocks | 3 OCR service files | None |
| P0-3 | debt | Remove unused generate_api_key() | core/auth.py | None |
| P0-4 | debt | Remove unused async image utility functions (6 funcs) | utils/image.py | None |
| P0-5 | debt | Fix CLOUDFRAME_API_KEY typo in deploy.sh | scripts/deploy.sh | None |
| P0-6 | security | Remove hardcoded proxy fallback (127.0.0.1:7897) | services/search/http_search_service.py | None |
| P0-7 | perf | Pre-compute auth key hashes at startup | core/auth.py | None |

## P1 — Medium Risk (User review required)

| # | Category | Finding | Why not auto |
|---|----------|---------|--------------|
| P1-1 | arch | Extract shared retry_with_backoff to utils/http.py | Touches 5+ service files |
| P1-2 | arch | Extract shared JSON parsing helpers | Touches service internals |
| P1-3 | arch | Extract httpx client factory with DI | Major refactor, 11 call sites |
| P1-4 | arch | Move DB↔Pydantic mappers out of routes.py | 110-line move, touches routes |
| P1-5 | security | Gemini key in URL → use header auth | Functional change in VLM service |
| P1-6 | security | SSRF protection on URL download endpoint | Functional change in routes |
| P1-7 | debt | Config mismatch: database_url unused vs hardcoded SQLite | Needs design decision |
| P1-8 | debt | Consolidate test mocks from integration tests into tests/mocks/ | Test infra refactor |
| P1-9 | security | Dockerfile runs as root | Deployment concern |
| P1-10 | debt | Remove hardcoded Cloudflare account ID from deploy.sh | Deployment concern |
| P1-11 | perf | Replace inline stats with get_database_stats() | Touches routes.py |
| P1-12 | perf | Delete _progress entries after completion | Touches routes.py state |
| P1-13 | debt | PipelineRunner: use typed getters instead of magic strings | Touches pipeline runner |
| P1-14 | arch | Extract shared prompt constants to prompts.py | Borderline: touches LLM prompts |

## P2 — High Effort

| # | Category | Finding |
|---|----------|---------|
| P2-1 | arch | Database DI refactoring (global → class-based) |
| P2-2 | arch | Frontend build pipeline unification (delete stale copies, build from src/) |
| P2-3 | security | Frontend deploy/_worker.js hardcoded API keys (needs key rotation) |
| P2-4 | arch | Health check delegates to ServiceRegistry instead of duplicating logic |

## P3 — Design Decisions

| # | Category | Finding |
|---|----------|---------|
| P3-1 | arch | Database URL config strategy (SQLite vs PostgreSQL) |
| P3-2 | arch | Frontend deployment approach (Pages Functions vs Workers) |
| P3-3 | debt | Unused analysis_depth parameter (feature decision) |
| P3-4 | debt | Unused cleanup_old_analyses() (needs scheduling decision) |
