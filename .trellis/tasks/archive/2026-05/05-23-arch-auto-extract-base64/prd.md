# PRD: Extract duplicate base64 image encoding

## Category
debt

## Context
The pattern `base64.b64encode(image_bytes).decode("utf-8")` is repeated in 4 locations across VLM and OCR services. This is a simple utility function that should be extracted to reduce duplication.

## What to Change
1. Add `encode_image_base64(image_bytes: bytes) -> str` to `src/vision_insight/utils/image.py`
2. Update the following files to use the new utility:
   - `src/vision_insight/services/vlm/api_service.py:88,180`
   - `src/vision_insight/services/vlm/zhipu_service.py:80`
   - `src/vision_insight/services/ocr/baidu_service.py:149`

## Why
- Reduces code duplication (DRY principle)
- Single place to update if encoding logic needs to change
- Improves code readability

## Acceptance Criteria
1. `ruff check src/vision_insight/` passes
2. `pytest tests/` passes
3. No functional changes to behavior
4. All 4 locations now use the shared utility

## Scope
Only the files listed above. No other changes.

## Risk Assessment
None — pure extraction refactor with no behavior change.

## Evidence
- `rg -n 'base64\.b64encode' src/vision_insight/` shows 4 locations
