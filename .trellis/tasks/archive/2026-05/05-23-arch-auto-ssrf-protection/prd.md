# PRD: Add SSRF protection for URL download

## Category
security

## Problem
The `/analyze/url` endpoint accepts an arbitrary URL and fetches it with `httpx.AsyncClient.get(request.image_url)`. There is no validation of the URL target:
- An attacker could pass `http://169.254.169.254/latest/meta-data/` (AWS metadata)
- Or `http://localhost:6379/` (internal Redis)
- Or `file:///etc/passwd` (file protocol)

This is a classic SSRF (Server-Side Request Forgery) vulnerability.

## What to Change
Add URL validation before downloading:
1. Only allow `http://` and `https://` schemes
2. Block private IP ranges (10.x, 172.16-31.x, 192.168.x, 127.x, 169.254.x)
3. Block localhost
4. Add timeout to prevent hanging connections

## Acceptance Criteria
1. URLs with non-HTTP(S) schemes are rejected
2. URLs pointing to private/internal IPs are rejected
3. URLs pointing to localhost are rejected
4. Valid public URLs still work
5. All existing tests pass

## Scope
Only modify: `src/vision_insight/api/routes.py`

## Evidence
- File: `src/vision_insight/api/routes.py` lines 365-375
- Current implementation has no URL validation

## Statement
No functional changes — this is security hardening only.
