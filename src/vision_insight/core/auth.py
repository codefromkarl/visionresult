"""API Key authentication for FastAPI.

This module provides a deep interface for API key authentication:
- Single dependency: `verify_api_key` for route protection
- Centralized key validation logic
- Easy to test with mock keys
"""

import hashlib
import hmac

from fastapi import HTTPException, Security
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
        List of valid API keys.
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

    This is the single entry point for API key authentication.
    Use this as a FastAPI dependency to protect routes.

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


def is_api_key_configured() -> bool:
    """Check if API key authentication is configured.

    Returns:
        True if at least one API key is configured.
    """
    return bool(_get_configured_api_keys())


def invalidate_key_cache() -> None:
    """Invalidate the cached key hashes.

    Call this if settings.api_keys changes at runtime.
    """
    global _valid_key_hashes
    _valid_key_hashes = None
