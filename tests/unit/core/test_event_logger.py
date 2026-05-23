"""Tests for structured event logging."""

from __future__ import annotations

import logging

from vision_insight.core import event_logger


def setup_function():
    event_logger.clear_task_events("task-1")
    event_logger.clear_task_events("task-secret")


def test_log_event_stores_sanitized_event():
    event_logger.log_event("task-secret", "api_call", api_key="sk-12345678901234567890")

    events = event_logger.get_task_events("task-secret")

    assert len(events) == 1
    assert events[0]["event"] == "api_call"
    assert events[0]["api_key"] != "sk-12345678901234567890"
    assert "***" in events[0]["api_key"]


def test_log_retry_records_warning_event():
    event_logger.log_retry("task-1", "vlm_request", 2, 3, 1.5, "HTTP 429")

    events = event_logger.get_task_events("task-1")

    assert events[0]["event"] == "vlm_request_retry"
    assert events[0]["level"] == "WARNING"
    assert events[0]["attempt"] == 2
    assert events[0]["delay_s"] == 1.5


def test_log_span_records_end_event():
    with event_logger.log_span("task-1", "ocr", image_bytes=128):
        pass

    events = event_logger.get_task_events("task-1")

    assert [event["event"] for event in events] == ["ocr_start", "ocr_end"]
    assert events[-1]["duration_ms"] >= 0


def test_log_span_records_failure_and_reraises():
    try:
        with event_logger.log_span("task-1", "vlm"):
            raise RuntimeError("boom")
    except RuntimeError:
        pass

    events = event_logger.get_task_events("task-1")

    assert events[-1]["event"] == "vlm_fail"
    assert events[-1]["level"] == "ERROR"
    assert events[-1]["error_type"] == "RuntimeError"


def test_structured_formatter_outputs_json():
    formatter = event_logger._StructuredFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )

    formatted = formatter.format(record)

    assert '"level": "INFO"' in formatted
    assert '"msg": "hello"' in formatted
