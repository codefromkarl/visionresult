# PRD: Defer directory creation in Settings

## Category
ARCH

## Problem
The `settings = Settings()` followed by `settings.upload_dir.mkdir(...)` at module import time causes side effects on import, making testing harder.

## Evidence
- File: `src/vision_insight/core/config.py:72-73`
- `settings = Settings()` followed by `settings.upload_dir.mkdir(parents=True, exist_ok=True)` at module import time
- This causes side effects on import, making testing harder

## Solution
Defer directory creation to application startup or use a lazy initialization pattern.

## Changes
1. Remove the eager directory creation from module level
2. Add a `ensure_directories()` function that can be called at startup
3. Update `main.py` to call `ensure_directories()` at startup

## Acceptance Criteria
- [ ] Ruff lint passes: `ruff check src/`
- [ ] Tests pass: `pytest tests/unit/ -q`
- [ ] No functional changes to API behavior
- [ ] Directories are created at startup, not import time

## Scope
Only modify `src/vision_insight/core/config.py` and `src/vision_insight/main.py`

## Statement
No functional changes — only import-time side effect removal.
