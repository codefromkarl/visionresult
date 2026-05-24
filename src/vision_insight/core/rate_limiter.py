"""Rate limiting middleware for API endpoints."""

import time
from collections import defaultdict

from fastapi import FastAPI, HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory rate limiter using sliding window algorithm.

    Tracks requests per IP address and enforces limits.
    """

    _MAX_TRACKED_IPS = 10_000  # Cap memory usage under DDoS

    def __init__(
        self,
        app,
        requests_per_minute: int = 60,
        requests_per_hour: int = 1000,
        cleanup_interval: int = 300,
    ):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        self.cleanup_interval = cleanup_interval

        # Store: {ip: [(timestamp, endpoint), ...]}
        self._requests: dict[str, list[tuple[float, str]]] = defaultdict(list)
        self._last_cleanup = time.time()

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request, considering proxy headers."""
        # Check for proxy headers
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # Take the first IP (client IP)
            return forwarded.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()

        # Fallback to direct connection
        if request.client:
            return request.client.host

        return "unknown"

    def _cleanup_old_entries(self) -> None:
        """Remove entries older than 1 hour and cap total tracked IPs."""
        now = time.time()
        if now - self._last_cleanup < self.cleanup_interval:
            return

        cutoff = now - 3600  # 1 hour ago
        for ip in list(self._requests.keys()):
            self._requests[ip] = [(ts, ep) for ts, ep in self._requests[ip] if ts > cutoff]
            if not self._requests[ip]:
                del self._requests[ip]

        # Evict oldest IPs if we exceed the cap
        if len(self._requests) > self._MAX_TRACKED_IPS:
            # Sort by most recent request timestamp, keep newest
            sorted_ips = sorted(
                self._requests.keys(),
                key=lambda ip: self._requests[ip][-1][0] if self._requests[ip] else 0,
            )
            # Remove oldest entries until we're under the limit
            excess = len(self._requests) - self._MAX_TRACKED_IPS
            for ip in sorted_ips[:excess]:
                del self._requests[ip]

        self._last_cleanup = now

    def _check_rate_limit(self, client_ip: str, endpoint: str) -> None:
        """Check if request exceeds rate limits.

        Args:
            client_ip: Client IP address.
            endpoint: Request endpoint path.

        Raises:
            HTTPException: If rate limit is exceeded.
        """
        now = time.time()
        self._cleanup_old_entries()

        # Get request history for this IP
        requests = self._requests[client_ip]

        # Count requests in last minute
        minute_ago = now - 60
        recent_minute = sum(1 for ts, _ in requests if ts > minute_ago)

        # Count requests in last hour
        hour_ago = now - 3600
        recent_hour = sum(1 for ts, _ in requests if ts > hour_ago)

        # Check limits
        if recent_minute >= self.requests_per_minute:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: {self.requests_per_minute} requests per minute",
                headers={"Retry-After": "60"},
            )

        if recent_hour >= self.requests_per_hour:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: {self.requests_per_hour} requests per hour",
                headers={"Retry-After": "3600"},
            )

        # Record this request
        self._requests[client_ip].append((now, endpoint))

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request through rate limiter."""
        # Skip rate limiting for health checks and static files
        path = request.url.path
        if path in ("/health", "/favicon.ico") or path.startswith("/static"):
            return await call_next(request)

        # Get client IP
        client_ip = self._get_client_ip(request)

        # Check rate limit
        self._check_rate_limit(client_ip, path)

        # Process request
        response = await call_next(request)

        # Add rate limit headers
        now = time.time()
        requests = self._requests.get(client_ip, [])
        minute_ago = now - 60
        recent_count = sum(1 for ts, _ in requests if ts > minute_ago)

        response.headers["X-RateLimit-Limit"] = str(self.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(
            max(0, self.requests_per_minute - recent_count)
        )
        response.headers["X-RateLimit-Reset"] = str(int(now + 60))

        return response


def setup_rate_limiting(
    app: FastAPI,
    requests_per_minute: int = 60,
    requests_per_hour: int = 1000,
) -> None:
    """Setup rate limiting middleware for the FastAPI app.

    Args:
        app: FastAPI application instance.
        requests_per_minute: Maximum requests per minute per IP.
        requests_per_hour: Maximum requests per hour per IP.
    """
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=requests_per_minute,
        requests_per_hour=requests_per_hour,
    )
