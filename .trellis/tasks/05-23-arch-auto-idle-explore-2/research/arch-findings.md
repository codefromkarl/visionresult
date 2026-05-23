# Architecture Deepening Opportunities — Idle Pass 2026-05-23 (Round 2)

## Context

Previous rounds implemented 30+ tasks covering dead code, security, performance, and architecture.
Round 1 (earlier today) implemented 3 P0 tasks: remove future annotations from prompts.py,
extract encode_image_base64 utility, remove unused _WIKIPEDIA_API constant.

This round identifies **new** opportunities after comprehensive source review of all 28 Python
source files (~6500 LOC).

## Methodology

Applied improve-codebase-architecture vocabulary (Module, Interface, Depth, Seam, Adapter,
Leverage, Locality) to every source file. Cross-referenced with 20+ archived tasks to avoid
duplication. Verified candidates against codebase state (idle-explore P0-1 through P0-3 were
already implemented in the current code).

---

## P0 — Trivial/Low-Risk, High Leverage

### P0-1: Remove unnecessary `from __future__ import annotations` from 4 files (DEBT)

**Category**: debt
**What**: Python 3.11+ natively supports `list[x]`, `dict[x,y]`, `X | None` syntax.
The `from __future__ import annotations` import is only needed for forward references.
Only `schemas.py` genuinely needs it (SceneAnalysis references LocationGuess/TimeGuess/
PeopleInfo defined later in the file). Four other files have no forward references:

- `src/vision_insight/services/vlm/prompts.py:3` — only defines `build_ocr_context` function
- `src/vision_insight/services/ocr/baidu_service.py:10` — no forward refs in class
- `src/vision_insight/services/ocr/paddle_service.py:3` — no forward refs in class
- `src/vision_insight/utils/__init__.py:3` — no forward refs in functions

**Risk**: None — removing unused imports has no effect on Python 3.11+.
**Acceptance**: ruff check passes, tests pass.

### P0-2: Pre-compile regex in `_strip_html` helper (PERF)

**Category**: perf
**What**: `http_search_service.py:_strip_html()` calls `re.sub(r"<[^>]+>", "", text)` on
every invocation. The regex is recompiled each time. Since this function is called for
every Wikipedia search result snippet, pre-compiling the pattern avoids redundant compilation.
**File**: `src/vision_insight/services/search/http_search_service.py:197`
**Risk**: None — pure performance improvement, identical behavior.
**Acceptance**: ruff check passes, tests pass.

### P0-3: Move inline `import time as _time` to module level in fusion_service.py (DEBT)

**Category**: debt
**What**: `_synthesize_conclusion()` in `fusion_service.py` imports `time as _time` at
function level (line ~291). This is the only inline import in the file. `time` is a stdlib
module with no import-time side effects — it should be imported at the top of the file.
The alias `_time` is used to avoid shadowing; can simply use `time` at module level and
reference `time.time()` / `time.monotonic()` directly in the method.
**File**: `src/vision_insight/services/evidence/fusion_service.py`
**Risk**: None — pure import reorganization, no behavior change.
**Acceptance**: ruff check passes, tests pass.

### P0-4: Extract repeated LIKE sanitization helper in database.py (DEBT)

**Category**: debt
**What**: `search_analyses()` contains identical sanitization logic for `keyword` and
`location` parameters:
```python
sanitized = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
pattern = f"%{sanitized}%"
```
Extract to a `_sanitize_like_pattern(value: str) -> str` helper function.
Improves Locality — the sanitization logic lives in one place.
**File**: `src/vision_insight/core/database.py:208-218, 227-231`
**Risk**: None — pure extraction, identical behavior.
**Acceptance**: ruff check passes, tests pass.

---

## P1 — Medium Risk (User review required)

### P1-1: `_PROXY` reads env vars instead of settings object (ARCH)
- **File**: `src/vision_insight/services/search/http_search_service.py:19`
- **Problem**: `_PROXY = os.getenv("HTTP_PROXY")` bypasses the Settings model.
- **Risk**: Changing could alter proxy behavior in existing deployments.

### P1-2: Repeated header construction in 4 service files (DEBT)
- Pattern `{"Authorization": f"Bearer {key}", "Content-Type": "application/json"}`
  appears in api_service.py, zhipu_service.py, llm_entity_service.py, llm_ports.py
- **Risk**: Part of larger OpenAI client extraction, standalone creates churn.

### P1-3: Module-level `_token_cache` in baidu_service.py (ARCH)
- Global mutable state for token caching across instances.
- **Risk**: Changing could affect multi-instance behavior.

### P1-4: Inline `import httpx` in routes.py analyze/url endpoint (DEBT)
- `httpx` is already a project dependency; could be a top-level import.
- **Risk**: Minimal, but touches routes file.

---

## P2 — High Effort

### P2-1: Pipeline graph error handling standardization (ARCH)
- 8 different `except Exception` blocks with inconsistent patterns.

### P2-2: Service registry lifecycle management (ARCH)
- No health checking, circuit breaking, or graceful degradation.

---

## P3 — Design Decisions

### P3-1: HTTP client connection pooling strategy
- Each service creates new `httpx.AsyncClient` per request.

### P3-2: Rate limiter storage backend
- In-memory vs Redis for multi-instance.
