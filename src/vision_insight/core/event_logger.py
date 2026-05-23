"""Structured event logger for tracing the full analysis request chain.

Every log entry includes task_id so the entire lifecycle of a request
can be reconstructed by grepping for that ID.

Events are stored in memory per task_id and can be queried via API.
Events are also broadcast via SSE queues for real-time display.

Usage:
    from vision_insight.core.event_logger import log_event

    log_event("task_id", "vlm_call_start", provider="gemini", timeout=60)
    log_event("task_id", "vlm_call_end", status="timeout", duration_ms=60123, attempt=1)
"""

import asyncio
import json
import logging
import os
import threading
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from vision_insight.core.request_id import get_request_id
from vision_insight.core.sanitizer import sanitize_dict, sanitize_string

# ---------------------------------------------------------------------------
# In-memory event store per task_id
# ---------------------------------------------------------------------------

_event_store: dict[str, list[dict[str, Any]]] = {}
_store_lock = threading.Lock()

_MAX_EVENTS_PER_TASK = 200
_MAX_TASKS = 50

# ---------------------------------------------------------------------------
# SSE broadcast queues per task_id
# ---------------------------------------------------------------------------

_sse_queues: dict[str, list[asyncio.Queue]] = {}
_sse_lock = threading.Lock()


def register_sse_queue(task_id: str) -> asyncio.Queue:
    """Register a new SSE queue for a task_id. Returns the queue."""
    q: asyncio.Queue = asyncio.Queue()
    with _sse_lock:
        if task_id not in _sse_queues:
            _sse_queues[task_id] = []
        _sse_queues[task_id].append(q)
    return q


def unregister_sse_queue(task_id: str, q: asyncio.Queue) -> None:
    """Remove an SSE queue for a task_id."""
    with _sse_lock:
        if task_id in _sse_queues:
            try:
                _sse_queues[task_id].remove(q)
            except ValueError:
                pass
            if not _sse_queues[task_id]:
                del _sse_queues[task_id]


def _broadcast_event(task_id: str, event_data: dict[str, Any]) -> None:
    """Broadcast event to all SSE queues for a task_id."""
    with _sse_lock:
        queues = _sse_queues.get(task_id, [])
    for q in queues:
        try:
            q.put_nowait(event_data)
        except asyncio.QueueFull:
            pass  # Drop if queue is full


# ---------------------------------------------------------------------------
# In-memory store
# ---------------------------------------------------------------------------

def _store_event(task_id: str, event: str, level: str, data: dict[str, Any]) -> dict[str, Any]:
    """Store event in memory for API retrieval. Returns the event dict.

    Sanitizes sensitive data before storage.
    """
    # Sanitize data to prevent sensitive information leakage
    sanitized_data = sanitize_dict(data)

    # Get request ID for tracing
    request_id = get_request_id()

    event_obj = {
        "ts": datetime.now(UTC).isoformat(),
        "level": level,
        "event": event,
        "request_id": request_id,
        **sanitized_data,
    }

    with _store_lock:
        if task_id not in _event_store:
            if len(_event_store) >= _MAX_TASKS:
                oldest = min(_event_store.keys(), key=lambda k: _event_store[k][0].get("ts", ""))
                del _event_store[oldest]
            _event_store[task_id] = []

        events = _event_store[task_id]
        if len(events) < _MAX_EVENTS_PER_TASK:
            events.append(event_obj)

    return event_obj


def get_task_events(task_id: str) -> list[dict[str, Any]]:
    """Retrieve stored events for a task_id."""
    with _store_lock:
        return list(_event_store.get(task_id, []))


def clear_task_events(task_id: str) -> None:
    """Remove stored events for a task_id."""
    with _store_lock:
        _event_store.pop(task_id, None)


# ---------------------------------------------------------------------------
# JSON formatter for structured logs
# ---------------------------------------------------------------------------

class _StructuredFormatter(logging.Formatter):
    """Emit one JSON object per line — easy to grep/jq."""

    def format(self, record: logging.LogRecord) -> str:
        base: dict[str, Any] = {
            "ts": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "level": record.levelname,
            "msg": record.getMessage(),
        }
        for key in ("task_id", "event", "data"):
            val = getattr(record, key, None)
            if val is not None:
                base[key] = val
        return json.dumps(base, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_logger = logging.getLogger("vision_insight.event")
_initialized = False


def _ensure_configured() -> None:
    """Attach a file handler the first time log_event is called."""
    global _initialized
    if _initialized:
        return
    _initialized = True

    stderr_handler = logging.StreamHandler()
    stderr_handler.setFormatter(_StructuredFormatter())
    _logger.addHandler(stderr_handler)
    _logger.setLevel(logging.DEBUG)

    log_file = os.environ.get("VIA_LOG_FILE", "")
    if log_file:
        os.makedirs(os.path.dirname(log_file) or ".", exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(_StructuredFormatter())
        _logger.addHandler(file_handler)


_LEVEL_NAMES = {
    logging.DEBUG: "DEBUG",
    logging.INFO: "INFO",
    logging.WARNING: "WARNING",
    logging.ERROR: "ERROR",
    logging.CRITICAL: "CRITICAL",
}


def log_event(
    task_id: str,
    event: str,
    level: int = logging.INFO,
    **data: Any,
) -> None:
    """Emit a structured event log.

    Args:
        task_id: The analysis task ID (8-char hex).
        event: Event name, e.g. "request_received", "vlm_timeout".
        level: Python log level.
        **data: Arbitrary key-value pairs attached to the event.
    """
    _ensure_configured()

    # Store in memory and get the event dict (sanitized)
    event_obj = _store_event(task_id, event, _LEVEL_NAMES.get(level, "INFO"), data)

    # Broadcast to SSE queues
    _broadcast_event(task_id, {"type": "event", "data": event_obj})

    # Build a readable message for file/stderr log (sanitized)
    parts = [f"{k}={v}" for k, v in event_obj.items() if k not in ("ts", "level", "event")]
    msg = f"[{task_id}] {event}"
    if parts:
        msg += " | " + " ".join(parts)
    # Sanitize the final message
    sanitized_msg = sanitize_string(msg)
    _logger.log(
        level,
        sanitized_msg,
        extra={"task_id": task_id, "event": event, "data": sanitize_dict(data)},
    )


@contextmanager
def log_span(
    task_id: str,
    event: str,
    **extra: Any,
):
    """Context manager that logs start/end of a span with duration_ms."""
    log_event(task_id, f"{event}_start", **extra)
    t0 = time.monotonic()
    try:
        yield
    except Exception as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        log_event(
            task_id,
            f"{event}_fail",
            level=logging.ERROR,
            duration_ms=duration_ms,
            error=str(exc),
            error_type=type(exc).__name__,
            **extra,
        )
        raise
    else:
        duration_ms = int((time.monotonic() - t0) * 1000)
        log_event(task_id, f"{event}_end", duration_ms=duration_ms, **extra)


def log_retry(
    task_id: str,
    event: str,
    attempt: int,
    max_retries: int,
    delay: float,
    error: str,
) -> None:
    """Log a retry attempt."""
    log_event(
        task_id,
        f"{event}_retry",
        level=logging.WARNING,
        attempt=attempt,
        max_retries=max_retries,
        delay_s=delay,
        error=error,
    )
