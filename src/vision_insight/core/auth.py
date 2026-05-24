"""API Key authentication middleware."""

import hashlib
import hmac

from fastapi import FastAPI, HTTPException, Request, Security
from fastapi.security import APIKeyHeader, APIKeyQuery

from vision_insight.core.config import settings

# API Key configuration
API_KEY_HEADER = "X-API-Key"
API_KEY_QUERY = "api_key"

# Security schemes
api_key_header = APIKeyHeader(name=API_KEY_HEADER, auto_error=False)
api_key_query = APIKeyQuery(name=API_KEY_QUERY, auto_error=False)


def _get_configured_api_keys() -> list[str]:
    """Get list of valid API keys from configuration.

    Returns:
        List of valid API key hashes.
    """
    # Get API keys from environment or config
    raw_keys = settings.api_keys
    if not raw_keys:
        return []

    # Split by comma if multiple keys
    if isinstance(raw_keys, str):
        keys = [k.strip() for k in raw_keys.split(",") if k.strip()]
    else:
        keys = [raw_keys]

    return keys


def _hash_api_key(key: str) -> str:
    """Hash API key for secure comparison.

    Args:
        key: Raw API key.

    Returns:
        Hashed key string.
    """
    return hashlib.sha256(key.encode()).hexdigest()


# Cached hashes — computed once on first use, avoids rehashing on every request
_valid_key_hashes: list[str] | None = None


def _get_valid_key_hashes() -> list[str]:
    """Get pre-computed hashes of configured API keys (cached).

    Returns:
        List of SHA-256 hashes for all configured API keys.
    """
    global _valid_key_hashes
    if _valid_key_hashes is None:
        keys = _get_configured_api_keys()
        _valid_key_hashes = [_hash_api_key(k) for k in keys]
    return _valid_key_hashes


def _validate_api_key(api_key: str) -> bool:
    """Validate an API key against configured keys.

    Args:
        api_key: Raw API key to validate.

    Returns:
        True if the key is valid (or no keys are configured).
    """
    valid_keys = _get_configured_api_keys()
    if not valid_keys:
        return True
    hashed_key = _hash_api_key(api_key)
    valid_hashes = _get_valid_key_hashes()
    return any(hmac.compare_digest(hashed_key, vh) for vh in valid_hashes)


def verify_api_key(
    api_key_header: str | None = Security(api_key_header),
    api_key_query: str | None = Security(api_key_query),
) -> str:
    """Verify API key from header or query parameter.

    Args:
        api_key_header: API key from X-API-Key header.
        api_key_query: API key from query parameter.

    Returns:
        Verified API key.

    Raises:
        HTTPException: If API key is invalid or missing.
    """
    # Get API key from header or query
    api_key = api_key_header or api_key_query

    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="API key required. Provide via X-API-Key header or api_key query parameter",
        )

    # Get configured keys
    valid_keys = _get_configured_api_keys()

    # If no keys configured, allow access (development mode)
    if not valid_keys:
        return api_key

    if not _validate_api_key(api_key):
        raise HTTPException(
            status_code=403,
            detail="Invalid API key",
        )

    return api_key


def setup_api_key_auth(app: FastAPI, enabled: bool = True) -> None:
    """Setup API key authentication for the FastAPI app.

    Args:
        app: FastAPI application instance.
        enabled: Whether to enable API key authentication.
    """
    if not enabled:
        return

    # Store auth state in app
    app.state.api_key_auth_enabled = True

    # Add middleware to check API key for protected routes
    @app.middleware("http")
    async def check_api_key_middleware(request: Request, call_next):
        """Middleware to check API key for protected endpoints."""
        # Skip auth for health checks, docs, and static files
        path = request.url.path
        skip_paths = {"/health", "/favicon.ico", "/docs", "/redoc", "/openapi.json"}
        if path in skip_paths or path.startswith("/static"):
            return await call_next(request)

        # Skip auth for frontend serving
        if path == "/" or not path.startswith("/api/"):
            return await call_next(request)

        # Check API key
        api_key = request.headers.get(API_KEY_HEADER) or request.query_params.get(API_KEY_QUERY)

        if not api_key:
            from starlette.responses import JSONResponse

            return JSONResponse(
                status_code=401,
                content={"detail": "API key required"},
            )

        if not _validate_api_key(api_key):
            from starlette.responses import JSONResponse

            return JSONResponse(
                status_code=403,
                content={"detail": "Invalid API key"},
            )

        # Process request
        response = await call_next(request)
        return response
