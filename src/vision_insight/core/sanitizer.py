"""Log sanitization utilities to prevent sensitive data leakage."""

from __future__ import annotations

import re
from typing import Any

# Patterns for sensitive data
SENSITIVE_PATTERNS = [
    # API keys
    (r'(api[_-]?key|apikey)\s*[=:]\s*["\']?([a-zA-Z0-9_\-]{20,})["\']?', r'\1=***REDACTED***'),
    (r'(sk-[a-zA-Z0-9]{20,})', 'sk-***REDACTED***'),
    (r'(AIza[a-zA-Z0-9_\-]{30,})', 'AIza***REDACTED***'),
    # Bearer tokens
    (r'(Bearer\s+)([a-zA-Z0-9_\-.]{20,})', r'\1***REDACTED***'),
    # Passwords
    (r'(password|passwd|pwd)\s*[=:]\s*["\']?([^\s"\']+)["\']?', r'\1=***REDACTED***'),
    # Database URLs with credentials
    (r'(postgresql|mysql|mongodb)://([^:]+):([^@]+)@', r'\1://\2:***@'),
    # Private keys
    (r'(-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----)', '***REDACTED PRIVATE KEY***'),
    # Credit card numbers (basic pattern)
    (r'\b(\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4})\b', '****-****-****-****'),
    # Email addresses (partial redaction)
    (r'([a-zA-Z0-9._%+-]{2})[a-zA-Z0-9._%+-]*(@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', r'\1***\2'),
]


def sanitize_string(text: str) -> str:
    """Sanitize a string to remove sensitive information.

    Args:
        text: Input string that may contain sensitive data.

    Returns:
        Sanitized string with sensitive data redacted.
    """
    if not text:
        return text

    result = text
    for pattern, replacement in SENSITIVE_PATTERNS:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

    return result


def sanitize_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Sanitize dictionary values to remove sensitive information.

    Args:
        data: Input dictionary.

    Returns:
        Dictionary with sanitized values.
    """
    if not data:
        return data

    sanitized = {}
    sensitive_keys = {
        'api_key', 'apikey', 'api-key', 'secret', 'token',
        'password', 'passwd', 'pwd', 'credentials', 'authorization',
        'private_key', 'privatekey'
    }

    for key, value in data.items():
        # Check if key name indicates sensitive data
        if any(s in key.lower() for s in sensitive_keys):
            if isinstance(value, str) and len(value) > 4:
                sanitized[key] = value[:2] + '***' + value[-2:]
            else:
                sanitized[key] = '***'
        elif isinstance(value, str):
            sanitized[key] = sanitize_string(value)
        elif isinstance(value, dict):
            sanitized[key] = sanitize_dict(value)
        elif isinstance(value, list):
            sanitized[key] = [
                sanitize_dict(item) if isinstance(item, dict)
                else sanitize_string(item) if isinstance(item, str)
                else item
                for item in value
            ]
        else:
            sanitized[key] = value

    return sanitized


def sanitize_log_message(message: str, *args: Any) -> str:
    """Sanitize a log message and its arguments.

    Args:
        message: Log message format string.
        *args: Format arguments.

    Returns:
        Sanitized log message.
    """
    try:
        # Format message with sanitized arguments
        sanitized_args = []
        for arg in args:
            if isinstance(arg, str):
                sanitized_args.append(sanitize_string(arg))
            elif isinstance(arg, dict):
                sanitized_args.append(sanitize_dict(arg))
            else:
                sanitized_args.append(arg)

        formatted = message % tuple(sanitized_args) if sanitized_args else message
        return sanitize_string(formatted)
    except Exception:
        # If formatting fails, just sanitize the message
        return sanitize_string(message)


class SanitizedLogger:
    """Logger wrapper that automatically sanitizes sensitive data."""

    def __init__(self, logger):
        """Initialize with a standard logger.

        Args:
            logger: Standard Python logger instance.
        """
        self._logger = logger

    def _sanitize_message(self, msg: str, args: tuple) -> str:
        """Format and sanitize a logger message with its positional arguments."""
        return sanitize_log_message(msg, *args)

    def debug(self, msg: str, *args: Any, **kwargs: Any):
        """Log debug message with sanitized data."""
        self._logger.debug(self._sanitize_message(msg, args), **kwargs)

    def info(self, msg: str, *args: Any, **kwargs: Any):
        """Log info message with sanitized data."""
        self._logger.info(self._sanitize_message(msg, args), **kwargs)

    def warning(self, msg: str, *args: Any, **kwargs: Any):
        """Log warning message with sanitized data."""
        self._logger.warning(self._sanitize_message(msg, args), **kwargs)

    def error(self, msg: str, *args: Any, **kwargs: Any):
        """Log error message with sanitized data."""
        self._logger.error(self._sanitize_message(msg, args), **kwargs)

    def critical(self, msg: str, *args: Any, **kwargs: Any):
        """Log critical message with sanitized data."""
        self._logger.critical(self._sanitize_message(msg, args), **kwargs)

    def exception(self, msg: str, *args: Any, **kwargs: Any):
        """Log exception with sanitized data."""
        self._logger.exception(self._sanitize_message(msg, args), **kwargs)
