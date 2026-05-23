# PRD: Type Annotations Cleanup

## Category
arch — Architecture standardization

## What to Change

### 1. EvidenceService.fuse() return type
- **File**: `src/vision_insight/services/__init__.py:84`
- Change `-> list:` to `-> list[FusedConclusion]:`
- Add `FusedConclusion` to imports

### 2. Fix `request: Request = None` default parameter
- **File**: `src/vision_insight/api/routes.py:298`
- Change `request: Request = None,` to `request: Request | None = None,`

### 3. ReportService.generate_structured_report() return type
- **File**: `src/vision_insight/services/__init__.py:98`
- Change `-> dict:` to `-> dict[str, Any]:`
- Add `Any` to imports

### 4. get_database_stats() return type
- **File**: `src/vision_insight/core/database.py:288`
- Change `-> dict:` to `-> dict[str, int]:`

### 5. get_image_metadata() return type
- **File**: `src/vision_insight/utils/image.py:124`
- Change `-> dict:` to `-> dict[str, Any]:`
- `Any` is already imported

## Why

These type annotations weaken the Interface contracts:
- Bare `list` and `dict` provide no type information to callers or type checkers
- `request: Request = None` is a type error (should be `Request | None`)
- Consistent type annotations improve IDE support and catch bugs at compile time

## Acceptance Criteria

- [ ] `ruff check src/vision_insight/` passes
- [ ] `mypy src/vision_insight/ --ignore-missing-imports` passes
- [ ] `pytest tests/` passes (414 tests)
- [ ] No functional changes to behavior

## Scope

Only these files:
1. `src/vision_insight/services/__init__.py`
2. `src/vision_insight/api/routes.py`
3. `src/vision_insight/core/database.py`
4. `src/vision_insight/utils/image.py`

## Explicit Statement

No functional changes. Only type annotations are modified.
