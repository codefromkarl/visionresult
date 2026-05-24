# PRD: Make parse_json_field Public

## Category
debt / architecture standardization

## Problem
`AnalysisRecord._parse_json_field` is a private method (prefixed with `_`) but is accessed from outside the class in `routes.py` (7 locations). This violates encapsulation conventions and triggers SLF001 lint warning.

## What to Change

### 1. Rename method in `database.py`
Change `_parse_json_field` to `parse_json_field` (remove underscore prefix).

### 2. Update all references
- `database.py`: 3 internal calls (`self._parse_json_field` → `self.parse_json_field`)
- `routes.py`: 7 external calls (`AnalysisRecord._parse_json_field` → `AnalysisRecord.parse_json_field`)

## Acceptance Criteria
- `ruff check src/` passes (no SLF001 warnings for this method)
- `pytest tests/ -x` passes
- No functional changes

## Scope
- `src/vision_insight/core/database.py`
- `src/vision_insight/api/routes.py`
