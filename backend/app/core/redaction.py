"""Defense-in-depth redaction for logs and persisted error context.

Authentication material must not survive merely because it was nested inside a
structured event, embedded in a URL, or passed through a stdlib logging tuple
(as Uvicorn access logs do).  Keep this module dependency-light so it can be
used by logging setup, middleware, and error persistence alike.
"""
from __future__ import annotations

import logging
import re
import traceback
from collections.abc import Mapping
from typing import Any


REDACTED = "[REDACTED]"

_SENSITIVE_KEY_PARTS = (
    "access_token",
    "refresh_token",
    "authorization",
    "password",
    "passwd",
    "secret",
    "api_key",
    "apikey",
    "cookie",
    "session",
    "credential",
    "jwt",
    "token",
)

_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?ix)"
    r"(?P<prefix>"
    r"[\"']?(?:access[_-]?token|refresh[_-]?token|authorization|password|passwd|"
    r"secret|api[_-]?key|apikey|cookie|session|credential|jwt|token)[\"']?"
    r"\s*(?:=|:|%3d)\s*[\"']?"
    r")"
    r"(?P<value>[^&\s,;\)\]\}\"']+)"
)
_BEARER_VALUE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_MAGIC_LINK_PATH_VALUE = re.compile(
    r"(?P<prefix>/(?:api/v1/quotes/token|quote)/)[^/?#\s]+"
)


def _sensitive_key(key: Any) -> bool:
    if not isinstance(key, str):
        return False
    normalized = key.strip().lower().replace("-", "_")
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def sanitize_request_path(value: str) -> str:
    """Replace public quote credentials embedded in paths with a placeholder.

    The concrete path must continue through ASGI for routing, but it is a
    credential whenever it reaches a human-readable or persisted diagnostic
    surface.  This also accepts a full URL or exception message containing the
    path and preserves any route suffix (for example ``/approve``).
    """
    return _MAGIC_LINK_PATH_VALUE.sub(
        lambda match: f"{match.group('prefix')}:token",
        value,
    )


def redact_text(value: str) -> str:
    """Redact credential-shaped values embedded in arbitrary text or URLs."""
    redacted = sanitize_request_path(value)
    redacted = _BEARER_VALUE.sub(f"Bearer {REDACTED}", redacted)
    return _SENSITIVE_ASSIGNMENT.sub(
        lambda match: f"{match.group('prefix')}{REDACTED}",
        redacted,
    )


def redact_sensitive(value: Any) -> Any:
    """Recursively redact structured values while preserving container types."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, bytes):
        return redact_text(value.decode("latin1"))
    if isinstance(value, bytearray):
        return redact_text(bytes(value).decode("latin1"))
    if isinstance(value, Mapping):
        return {
            key: REDACTED if _sensitive_key(key) else redact_sensitive(item)
            for key, item in value.items()
        }
    if isinstance(value, tuple):
        return tuple(redact_sensitive(item) for item in value)
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, set):
        return {redact_sensitive(item) for item in value}
    return value


def redact_structlog_event(_logger: Any, _method_name: str, event_dict: dict) -> dict:
    """Structlog processor that redacts before console/JSON rendering."""
    return redact_sensitive(event_dict)


class SensitiveDataFilter(logging.Filter):
    """Sanitize stdlib records, including Uvicorn's positional URL argument."""

    _dieselbridge_sensitive_filter = True

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_sensitive(record.msg)
        if record.args:
            record.args = redact_sensitive(record.args)
        if record.stack_info:
            record.stack_info = redact_text(record.stack_info)
        if record.exc_info:
            record.exc_text = redact_text(
                "".join(traceback.format_exception(*record.exc_info))
            )
        elif record.exc_text:
            record.exc_text = redact_text(record.exc_text)
        return True


def install_sensitive_data_filters() -> None:
    """Attach a single redaction filter to app and ASGI logging surfaces."""
    loggers = [
        logging.getLogger(),
        logging.getLogger("uvicorn"),
        logging.getLogger("uvicorn.error"),
        logging.getLogger("uvicorn.access"),
    ]
    for target in loggers:
        if not any(
            getattr(item, "_dieselbridge_sensitive_filter", False)
            for item in target.filters
        ):
            target.addFilter(SensitiveDataFilter())
        for handler in target.handlers:
            if not any(
                getattr(item, "_dieselbridge_sensitive_filter", False)
                for item in handler.filters
            ):
                handler.addFilter(SensitiveDataFilter())
