# PRD: arch-auto: debt/perf cleanup round 2

## Category
debt + perf

## Summary
Four small, low-risk code quality improvements identified during architecture exploration.

## Changes

### 1. Remove unnecessary `from __future__ import annotations` (debt)
**Files**:
- `src/vision_insight/services/vlm/prompts.py` — line 3
- `src/vision_insight/services/ocr/baidu_service.py` — line 10
- `src/vision_insight/services/ocr/paddle_service.py` — line 3
- `src/vision_insight/utils/__init__.py` — line 3

**Why**: Project requires Python 3.11+. These files have no forward references.
Only `schemas.py` genuinely needs the import (SceneAnalysis→LocationGuess forward ref).

### 2. Pre-compile regex in `_strip_html` (perf)
**File**: `src/vision_insight/services/search/http_search_service.py`
**Why**: `re.sub(r"<[^>]+>", "", text)` recompiles the regex on every call.
Pre-compiling to a module-level `_RE_HTML_TAG = re.compile(r"<[^>]+>")` avoids this.

### 3. Move inline `import time as _time` to module level (debt)
**File**: `src/vision_insight/services/evidence/fusion_service.py`
**Why**: `_synthesize_conclusion()` has an inline `import time as _time`.
Move `import time` to the module top-level and use `time.time()` directly.

### 4. Extract `_sanitize_like_pattern` helper in database.py (debt)
**File**: `src/vision_insight/core/database.py`
**Why**: Identical LIKE sanitization code appears twice in `search_analyses()`.
Extract to `_sanitize_like_pattern(value: str) -> str` helper.

## Acceptance Criteria
- `ruff check src/vision_insight/` passes
- `mypy src/vision_insight/` passes (or same as baseline)
- `pytest tests/` — 414+ pass, 0 fail
- No functional changes to behavior

## Scope
Only the specific files listed above. No business logic, API, or UI changes.
