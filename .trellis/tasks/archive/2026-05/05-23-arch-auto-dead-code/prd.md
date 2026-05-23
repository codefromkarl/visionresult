# arch-auto: remove dead code

## Category
debt

## What to change and why

Remove unused code identified during architecture audit. Evidence: `research/synthesis.md` P0-1 through P0-4.

### Changes:

1. **core/sanitizer.py**: Remove `sanitize_log_message()` function (lines 91–114) and `SanitizedLogger` class (lines 119–168). These are never used in production code — only in their own test file.

2. **3 OCR service files**: Remove empty `if TYPE_CHECKING: pass` blocks:
   - `services/ocr/baidu_service.py` (lines 15, 23–24)
   - `services/ocr/paddle_service.py` (lines 6, 11–12)
   - `services/ocr/tesseract_service.py` (lines 7, 14–15)

3. **core/auth.py**: Remove `generate_api_key()` function (lines 100–106). Never called in production or CLI.

4. **utils/image.py**: Remove 4 unused async wrapper functions that have no production callers:
   - `get_image_metadata_async()` (line 240)
   - `compress_image_async()` (line 252)
   - `assess_sharpness_async()` (line 270)
   - `is_blurry_async()` (line 282)

5. **Test updates**: Remove corresponding dead test functions:
   - `tests/unit/core/test_sanitizer.py`: Remove `test_sanitize_log_message_formats_and_redacts_args` and `test_sanitized_logger_redacts_messages` (and the `SanitizedLogger`/`sanitize_log_message` imports)
   - `tests/unit/core/test_auth.py`: Remove `test_generate_api_key_is_urlsafe_and_unique`
   - `tests/unit/test_image_utils.py`: Remove test functions for the 4 removed async wrappers (if any exist)

## Acceptance criteria
- `ruff check src/ tests/` passes
- All existing tests pass (minus removed dead tests)
- No functional changes

## Scope
Only these specific files:
- `src/vision_insight/core/sanitizer.py`
- `src/vision_insight/core/auth.py`
- `src/vision_insight/services/ocr/baidu_service.py`
- `src/vision_insight/services/ocr/paddle_service.py`
- `src/vision_insight/services/ocr/tesseract_service.py`
- `src/vision_insight/utils/image.py`
- `tests/unit/core/test_sanitizer.py`
- `tests/unit/core/test_auth.py`
- `tests/unit/test_image_utils.py`

## No functional changes
This is purely dead code removal. No behavior, API, or feature changes.
