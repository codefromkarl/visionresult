# PRD: Fix sanitize_dict to fully redact secrets

## Category
security

## Problem
The `sanitize_dict` function in `core/sanitizer.py` partially reveals secrets by exposing the first 2 and last 2 characters:
```python
sanitized[key] = value[:2] + '***' + value[-2:]
```

For a key like `api_key = "sk-abc123def456ghi789"`, this outputs `sk-***89`. This defeats the purpose of redaction — an attacker with log access can narrow down the key space.

## What to Change
Modify `sanitize_dict()` in `src/vision_insight/core/sanitizer.py` to fully redact all values under sensitive keys. Only the key name should be visible.

## Acceptance Criteria
1. All values under sensitive keys (api_key, secret, token, password, etc.) are fully redacted to `"***"`
2. Existing tests pass
3. No functional changes to other parts of the system

## Scope
Only modify: `src/vision_insight/core/sanitizer.py`

## Evidence
- File: `src/vision_insight/core/sanitizer.py` lines 82-85
- Current behavior leaks partial secrets

## Statement
No functional changes — this is a security hardening fix only.
