"""Request ID middleware for request tracing."""

from __future__ import annotations

import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Context variable to store request ID
request_id_var: ContextVar[str] = ContextVar("request_id", default="unknown")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware that adds a unique request ID to each request.

    The request ID is:
    - Generated if not present in the incoming request
    - Passed through from X-Request-ID header if present
    - Added to response headers
    - Available via context variable for logging
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request and add request ID."""
        # Get or generate request ID
        request_id = request.headers.get("X-Request-ID")
        if not request_id:
            request_id = str(uuid.uuid4())[:16]

        # Set in context variable
        request_id_var.set(request_id)

        # Add to request state for easy access
        request.state.request_id = request_id

        # Process request
        response = await call_next(request)

        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id

        return response


def get_request_id() -> str:
    """Get the current request ID from context.

    Returns:
        Current request ID string.
    """
    return request_id_var.get()


def setup_request_id(app):
    """Setup request ID middleware for the FastAPI app.

    Args:
        app: FastAPI application instance.
    """
    app.add_middleware(RequestIDMiddleware)
