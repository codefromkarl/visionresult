# PRD: Remove Dead Code

**Category**: debt  
**Priority**: P0

## Problem

Several dead code patterns exist:

1. **F-1.5**: `if TYPE_CHECKING: pass` blocks in 3 OCR service files — no-op guards with no types imported
2. **F-1.6**: Unused backward-compatible prompt aliases (`SCENE_ANALYSIS_PROMPT`, `OBJECT_DETECTION_PROMPT`) in 2 VLM files — defined but never referenced
3. **F-3.5**: `SanitizedLogger` class in `sanitizer.py` — never instantiated anywhere

## Solution

1. Remove `if TYPE_CHECKING: pass` from `tesseract_service.py`, `baidu_service.py`, `paddle_service.py` (also remove unused `from typing import TYPE_CHECKING` import)
2. Remove `SCENE_ANALYSIS_PROMPT = SCENE_ANALYSIS_PROMPT_EN/ZH` and `OBJECT_DETECTION_PROMPT = OBJECT_DETECTION_PROMPT_EN/ZH` alias lines from `api_service.py` and `zhipu_service.py`
3. Remove `SanitizedLogger` class (lines 119-160) from `sanitizer.py`

## Evidence

- Research: `.trellis/tasks/05-23-arch-auto-explore-2/research/findings.md` (F-1.5, F-1.6, F-3.5)

## Scope

Only these files:
- `src/vision_insight/services/ocr/tesseract_service.py`
- `src/vision_insight/services/ocr/baidu_service.py`
- `src/vision_insight/services/ocr/paddle_service.py`
- `src/vision_insight/services/vlm/api_service.py`
- `src/vision_insight/services/vlm/zhipu_service.py`
- `src/vision_insight/core/sanitizer.py`

## Acceptance Criteria

- No functional changes
- All existing tests pass
- Lint / typecheck clean

## Explicit Statement

**No functional changes.** Pure dead code removal.
