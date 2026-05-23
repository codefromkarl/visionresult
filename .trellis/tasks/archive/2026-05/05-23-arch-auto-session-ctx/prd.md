# PRD: Add session context manager

## Category
ARCH/DEBT

## Problem
The `database.py` file uses manual `session = get_session(); try: ... finally: session.close()` pattern 7 times. This is error-prone and could be improved with a context manager.

## Evidence
- File: `src/vision_insight/core/database.py`
- Lines 130-137, 140-146, 150-161, 165-178, 210-235, 240-263, 270-288
- Each function repeats the same try/finally pattern

## Solution
Add a `get_session_ctx()` context manager that automatically handles session lifecycle.

## Changes
1. Add `get_session_ctx()` context manager function
2. Migrate all callers to use the new context manager
3. Keep backward compatibility for existing code

## Acceptance Criteria
- [ ] Ruff lint passes: `ruff check src/`
- [ ] Tests pass: `pytest tests/unit/ -q`
- [ ] No functional changes to API behavior
- [ ] All session operations use context manager

## Scope
Only modify `src/vision_insight/core/database.py`

## Statement
No functional changes — only code quality improvement.
