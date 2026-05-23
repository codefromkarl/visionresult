# PRD: Extract Duplicate UUID Generation

## Category: debt

## What to change and why

The pattern `str(uuid.uuid4())[:8]` is repeated 3 times in `src/vision_insight/api/routes.py`
(lines 287, 351, 486) and `str(uuid.uuid4())[:16]` in `src/vision_insight/core/request_id.py` (line 31).

Extract these to shared utility functions in `src/vision_insight/utils/__init__.py` to:
- Remove duplication (3 → 1)
- Centralize ID generation logic for potential future changes (e.g., switch to ULID)

Evidence: `rg -t py -n "str\(uuid" src/`

## Acceptance criteria
- `utils/__init__.py` (or a new `utils/ids.py`) exports `generate_task_id()` and `generate_request_id()`
- All callers in `routes.py` and `request_id.py` use the new utility
- `ruff check src/` passes
- `python3 -m pytest tests/ -x -q` passes

## Scope
- `src/vision_insight/utils/__init__.py` — add utility functions
- `src/vision_insight/api/routes.py` — replace 3 inline UUID calls
- `src/vision_insight/core/request_id.py` — replace 1 inline UUID call

## No functional changes
Same UUID generation behavior, just consolidated.
