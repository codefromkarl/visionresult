"""Tests for request ID middleware."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from starlette.responses import Response

from vision_insight.core.request_id import RequestIDMiddleware, get_request_id


@pytest.mark.asyncio
async def test_request_id_middleware_uses_incoming_header():
    middleware = RequestIDMiddleware(app=None)
    request = SimpleNamespace(
        headers={"X-Request-ID": "req-123"},
        state=SimpleNamespace(),
    )

    async def call_next(req):
        assert req.state.request_id == "req-123"
        assert get_request_id() == "req-123"
        return Response("ok")

    response = await middleware.dispatch(request, call_next)

    assert response.headers["X-Request-ID"] == "req-123"


@pytest.mark.asyncio
async def test_request_id_middleware_generates_id_when_missing():
    middleware = RequestIDMiddleware(app=None)
    request = SimpleNamespace(headers={}, state=SimpleNamespace())

    async def call_next(req):
        assert len(req.state.request_id) == 16
        return Response("ok")

    response = await middleware.dispatch(request, call_next)

    assert len(response.headers["X-Request-ID"]) == 16
