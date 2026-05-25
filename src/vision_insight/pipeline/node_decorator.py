"""Pipeline node decorator to eliminate boilerplate.

This module provides a deep interface for pipeline nodes:
- Single decorator: `@pipeline_node(name)`
- Handles progress notification, step tracking, logging, and error handling
- Easy to use: just decorate your node function
"""

import logging
from collections.abc import Callable
from datetime import datetime as dt
from functools import wraps
from typing import Any, TypeVar

from vision_insight.core.event_logger import log_event

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

# These will be set by graph.py after it defines them
_PipelineState = None
_ProgressCallback = None
_STAGE_PROGRESS = None


def _set_imports(pipeline_state, progress_callback, stage_progress):
    """Set the imports from graph.py to avoid circular imports."""
    global _PipelineState, _ProgressCallback, _STAGE_PROGRESS
    _PipelineState = pipeline_state
    _ProgressCallback = progress_callback
    _STAGE_PROGRESS = stage_progress


def _notify_progress(state: dict, stage: str) -> None:
    """Send progress notification if callback is provided."""
    callback = state.get("progress_callback")
    if callback and _STAGE_PROGRESS:
        progress = _STAGE_PROGRESS.get(stage, 0)
        try:
            callback(stage, progress)
        except Exception:
            pass  # Don't let callback errors break the pipeline


def _start_pipeline_step(state: dict, stage_name: str) -> dict:
    """Record the start of a pipeline step if verbose mode is enabled."""
    if not state.get("verbose"):
        return {}

    return {
        "stage_name": stage_name,
        "status": "running",
        "start_time": dt.now().isoformat(),
        "input_summary": "",
        "output_summary": "",
        "key_findings": [],
        "error_message": None,
        "input_data": {},
        "output_data": {},
    }


def _end_pipeline_step(
    state: dict,
    step_info: dict,
    status: str = "success",
    output_summary: str = "",
    key_findings: list[str] | None = None,
    error_message: str | None = None,
    output_data: dict[Any, Any] | None = None,
) -> None:
    """Complete a pipeline step recording."""
    if not step_info or not state.get("verbose"):
        return

    step_info["end_time"] = dt.now().isoformat()
    step_info["status"] = status
    if output_summary:
        step_info["output_summary"] = output_summary
    if key_findings:
        step_info["key_findings"] = key_findings
    if error_message:
        step_info["error_message"] = error_message
    if output_data:
        step_info["output_data"] = output_data
    # Calculate duration
    start = dt.fromisoformat(step_info["start_time"])
    end = dt.fromisoformat(step_info["end_time"])
    step_info["duration_ms"] = int((end - start).total_seconds() * 1000)
    # Append to trace
    if "pipeline_trace" in state:
        state["pipeline_trace"].setdefault("steps", []).append(step_info)


def pipeline_node(name: str) -> Callable[[F], F]:
    """Decorator to wrap a pipeline node with standard scaffolding.

    This eliminates the boilerplate of:
    - Progress notification
    - Step tracking
    - Logging
    - Error handling

    Usage:
        @pipeline_node("ocr")
        async def ocr_node(state: dict) -> dict[str, Any]:
            report = state["report"]
            # ... unique logic ...
            return {"report": report}

    The decorated function should:
    1. Accept a PipelineState dict
    2. Return a dict with the updated "report"
    3. Raise exceptions on failure (they'll be caught and logged)

    The decorator will:
    1. Call _notify_progress(state, name)
    2. Create step_info for verbose tracking
    3. Log node_start event
    4. Execute the function
    5. Log node_end event (or node_fail on exception)
    6. Update step_info with results
    """

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(state: dict) -> dict[str, Any]:
            report = state["report"]
            task_id = report.id

            # Progress notification
            _notify_progress(state, name)

            # Step tracking
            step_info = _start_pipeline_step(state, name)

            # Log start
            log_event(task_id, "node_start", node=name)

            try:
                # Execute the actual node logic
                result = await func(state)

                # Log success
                log_event(task_id, "node_end", node=name)

                return result

            except Exception as exc:
                # Log failure
                log_event(task_id, "node_fail", node=name, error=str(exc))
                logger.warning("%s node failed: %s", name, exc)

                # Update step_info
                _end_pipeline_step(
                    state, step_info, status="failed", error_message=str(exc)
                )

                # Re-raise to let caller handle
                raise

        return wrapper  # type: ignore

    return decorator


def pipeline_node_with_insight(name: str, icon: str, title: str, tool: str) -> Callable[[F], F]:
    """Decorator for pipeline nodes that also log insight events.

    This extends pipeline_node with automatic insight logging.

    Usage:
        @pipeline_node_with_insight("ocr", "📝", "OCR 文字识别", "OCR Service")
        async def ocr_node(state: dict) -> dict[str, Any]:
            report = state["report"]
            # ... unique logic ...
            # Return insight results in the state
            state["insight_results"] = [
                {"label": "识别文字", "value": texts[:10]},
                {"label": "平均置信度", "value": f"{avg_conf:.1%}"},
            ]
            return {"report": report}
    """

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(state: dict) -> dict[str, Any]:
            report = state["report"]
            task_id = report.id

            # Progress notification
            _notify_progress(state, name)

            # Step tracking
            step_info = _start_pipeline_step(state, name)

            # Log start
            log_event(task_id, "node_start", node=name)

            try:
                # Execute the actual node logic
                result = await func(state)

                # Log insight if results were provided
                insight_results = state.pop("insight_results", None)
                if insight_results:
                    log_event(
                        task_id,
                        "insight",
                        node=name,
                        icon=icon,
                        title=title,
                        tool=tool,
                        results=insight_results,
                    )

                # Log success
                log_event(task_id, "node_end", node=name)

                return result

            except Exception as exc:
                # Log failure
                log_event(task_id, "node_fail", node=name, error=str(exc))
                logger.warning("%s node failed: %s", name, exc)

                # Update step_info
                _end_pipeline_step(
                    state, step_info, status="failed", error_message=str(exc)
                )

                # Re-raise to let caller handle
                raise

        return wrapper  # type: ignore

    return decorator
