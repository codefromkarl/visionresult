# arch-auto: remaining P0 deepening — round 2

## Category
debt / perf

## What to change and why

Based on research in `research/remaining-p0-findings.md`, implement these P0 fixes:

### 1. Remove dead `context_parts` expression (debt)
- **File**: `src/vision_insight/api/routes.py` line 676
- Remove `"\n".join(context_parts)` — result is discarded, dead code.

### 2. Fix deprecated `datetime.utcnow()` (debt)
- **File**: `src/vision_insight/api/health.py` lines 137, 168
- Replace `datetime.utcnow()` with `datetime.now(UTC)` and add import.

### 3. Fix SQLAlchemy raw SQL string (perf/debt)
- **File**: `src/vision_insight/api/health.py` line 47
- Use `text("SELECT 1")` instead of bare string.

### 4. Remove import-time mkdir in database.py (debt)
- **File**: `src/vision_insight/core/database.py` line 20
- Remove `DB_PATH.parent.mkdir(parents=True, exist_ok=True)` — already handled by `ensure_directories()`.

### 5. Remove import-time mkdir in routes.py (debt)
- **File**: `src/vision_insight/api/routes.py` line 62
- Remove `IMAGES_DIR.mkdir(parents=True, exist_ok=True)` — directory creation handled at save time.

### 6. Move datetime import to module level (perf)
- **File**: `src/vision_insight/pipeline/graph.py` line 158
- Move `from datetime import datetime as dt` to top of file.

### 7. Extract shared image format detection (debt)
- **Files**: `utils/image.py` (new function), `routes.py`, `zhipu_service.py`
- Add `detect_image_format(image_bytes: bytes) -> str` to `utils/image.py`.
- Use it in `routes.py` validation and `zhipu_service.py`.

## Acceptance criteria
- All existing tests pass (`python3 -m pytest tests/ -x`)
- Ruff lint clean (`ruff check src/`)
- No functional changes to API behavior
- No new imports of external packages

## Scope
Only the specific files mentioned above. No changes to business logic, API contracts, or test assertions.
