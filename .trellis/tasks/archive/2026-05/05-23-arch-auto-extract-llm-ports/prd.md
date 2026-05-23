# PRD: Extract LLM port adapters

## Category
ARCH

## Problem
`ZhipuLLMPort` and `EmptyLLMPort` are defined inline inside `create_evidence_service()` in `service_registry.py`. This gives the factory method low Locality — understanding the evidence service wiring requires reading a 60-line method with inline class definitions.

## Evidence
- File: `src/vision_insight/core/service_registry.py:180-230`
- Both adapters are defined inline inside `create_evidence_service()`
- This makes the code harder to understand and test

## Solution
Extract `ZhipuLLMPort` and `EmptyLLMPort` to `services/evidence/llm_ports.py`

## Changes
1. Create `src/vision_insight/services/evidence/llm_ports.py`
2. Move `ZhipuLLMPort` and `EmptyLLMPort` to the new file
3. Update imports in `service_registry.py`

## Acceptance Criteria
- [ ] Ruff lint passes: `ruff check src/`
- [ ] Tests pass: `pytest tests/unit/ -q`
- [ ] No functional changes to API behavior
- [ ] LLM ports are reusable and testable

## Scope
Only modify `src/vision_insight/core/service_registry.py` and create `src/vision_insight/services/evidence/llm_ports.py`

## Statement
No functional changes — only code organization improvement.
