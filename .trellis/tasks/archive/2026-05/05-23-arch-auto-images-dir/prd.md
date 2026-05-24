# PRD: Align Image Directory Configuration

## Category
debt / config consistency

## Problem
Image storage path is defined in 3 places with inconsistency:
- `config.py`: `upload_dir = Path("data/uploads")` and `cache_dir = Path("data/cache")` (unused for images)
- `routes.py`: `IMAGES_DIR = Path("data/images")` (hardcoded)
- `config.py:ensure_directories()`: `Path("data/images").mkdir(...)` (hardcoded)

The `upload_dir` config setting is unused — images go to `data/images` not `data/uploads`.

## What to Change

### 1. Add `images_dir` to Settings in `config.py`
```python
class Settings(BaseSettings):
    # ... existing fields ...
    images_dir: Path = Path("data/images")  # NEW
```

### 2. Update `ensure_directories()` in `config.py`
Replace hardcoded `Path("data/images").mkdir(...)` with `settings.images_dir.mkdir(...)`.

### 3. Update `routes.py` to use config
Replace `IMAGES_DIR = Path("data/images")` with `IMAGES_DIR = settings.images_dir`.

### 4. Remove unused `upload_dir` and `cache_dir` if confirmed unused
Check if `upload_dir` and `cache_dir` are used anywhere. If not, remove them.

## Acceptance Criteria
- Single source of truth for image directory path
- `ruff check src/` passes
- `mypy src/` passes (if configured)
- All tests pass unchanged
- No functional changes

## Scope
- `src/vision_insight/core/config.py`
- `src/vision_insight/api/routes.py`

## Evidence
- `.trellis/tasks/05-23-arch-auto-scan-r2/research/new-findings-2.md` (P0 #2)
