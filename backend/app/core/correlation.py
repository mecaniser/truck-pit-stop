"""Safe correlation identifiers for request tracing and persistence."""
from __future__ import annotations

import re
import uuid
from typing import Any, Optional


CORRELATION_ID_MAX_LENGTH = 64
_SAFE_CORRELATION_ID = re.compile(
    rf"\A[A-Za-z0-9_-]{{1,{CORRELATION_ID_MAX_LENGTH}}}\Z"
)


def normalize_correlation_id(value: Any) -> str:
    """Return a bounded log-safe ID, replacing untrusted or malformed input."""
    if isinstance(value, str) and _SAFE_CORRELATION_ID.fullmatch(value):
        return value
    return str(uuid.uuid4())


def normalize_optional_correlation_id(value: Any) -> Optional[str]:
    """Preserve a missing ID while replacing any unsafe supplied value."""
    if value is None:
        return None
    return normalize_correlation_id(value)


def is_safe_correlation_id(value: Any) -> bool:
    """Expose the validation rule for response and persistence assertions."""
    return isinstance(value, str) and bool(_SAFE_CORRELATION_ID.fullmatch(value))
