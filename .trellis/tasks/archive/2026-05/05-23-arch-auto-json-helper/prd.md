# PRD: Extract JSON Deserialization Helper

## Category
debt

## Problem
10 instances of `json.loads(str(record.xxx_json or "[]"))` scattered across `routes.py` and `database.py`. This pattern is duplicated, fragile (the `str()` cast handles SQLAlchemy Column types), and error-prone (each call site independently handles defaults).

## What to change
1. Add `_parse_json_field(value, default)` static method to `AnalysisRecord` in `database.py`
2. Replace all 10 call sites in `routes.py` and `database.py` with calls to this helper

## Evidence
- `routes.py` lines 125-130, 415, 661, 672
- `database.py` lines 89-91

## Acceptance criteria
- [ ] `_parse_json_field` method exists on `AnalysisRecord`
- [ ] All 10 call sites use the new helper
- [ ] `ruff check` passes
- [ ] `mypy` passes
- [ ] All existing tests pass
- [ ] No functional changes — identical behavior

## Scope
- `src/vision_insight/core/database.py`
- `src/vision_insight/api/routes.py`

## Statement
No functional changes. Pure extract-refactor to reduce code duplication.
