"""Request-scoped database performance accounting.

The SQLAlchemy engine is shared by all requests, so these counters live in a
``ContextVar``. Async SQLAlchemy keeps that context through its greenlet bridge,
which lets engine events attribute database work to the active HTTP request
without logging statements or bound values.
"""
from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass


@dataclass
class RequestDatabaseStats:
    query_count: int = 0
    total_duration_ms: float = 0.0
    slowest_duration_ms: float = 0.0
    slowest_operation: str | None = None


_request_database_stats: ContextVar[RequestDatabaseStats | None] = ContextVar(
    "request_database_stats", default=None
)


def begin_request_database_stats() -> Token[RequestDatabaseStats | None]:
    """Start isolated database accounting for the current request context."""
    return _request_database_stats.set(RequestDatabaseStats())


def end_request_database_stats(
    token: Token[RequestDatabaseStats | None],
) -> RequestDatabaseStats:
    """Return the current request's stats and restore the parent context."""
    stats = _request_database_stats.get() or RequestDatabaseStats()
    _request_database_stats.reset(token)
    return stats


def record_database_query(duration_ms: float, operation: str) -> None:
    """Record one SQL execution when it belongs to an HTTP request."""
    stats = _request_database_stats.get()
    if stats is None:
        return

    stats.query_count += 1
    stats.total_duration_ms += duration_ms
    if duration_ms > stats.slowest_duration_ms:
        stats.slowest_duration_ms = duration_ms
        stats.slowest_operation = operation


def sql_operation(statement: str) -> str:
    """Return a bounded metric label for a SQL statement."""
    first_word = statement.lstrip().split(None, 1)
    if not first_word:
        return "other"
    operation = first_word[0].lower()
    return operation if operation in {"select", "insert", "update", "delete"} else "other"
