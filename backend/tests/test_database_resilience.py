from __future__ import annotations

import asyncio
import json

import pytest
from fastapi import Request
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

from app.core.config import settings
from app.db import session as db_session
from app.services import error_service


class _FailingSession:
    def __init__(self) -> None:
        self.added = None
        self.closed = False

    def add(self, value) -> None:
        self.added = value

    async def commit(self) -> None:
        raise RuntimeError("database unavailable")

    async def refresh(self, _value) -> None:
        raise AssertionError("refresh must not run after a failed commit")

    async def close(self) -> None:
        self.closed = True


class _HangingSession:
    def __init__(self) -> None:
        self.closed = False

    def add(self, _value) -> None:
        pass

    async def commit(self) -> None:
        await asyncio.Event().wait()

    async def refresh(self, _value) -> None:
        raise AssertionError("refresh must not run after a timed out commit")

    async def close(self) -> None:
        self.closed = True


def test_postgres_engine_options_set_connection_budget_and_timeouts():
    options = db_session.build_engine_options("postgresql+asyncpg://user:pass@db/app")

    assert options["pool_pre_ping"] is True
    assert options["pool_size"] == settings.DATABASE_POOL_SIZE
    assert options["max_overflow"] == settings.DATABASE_MAX_OVERFLOW
    assert options["pool_timeout"] == settings.DATABASE_POOL_TIMEOUT_SECONDS
    assert options["pool_recycle"] == settings.DATABASE_POOL_RECYCLE_SECONDS
    assert options["connect_args"]["timeout"] == settings.DATABASE_CONNECT_TIMEOUT_SECONDS
    assert options["connect_args"]["server_settings"] == {
        "application_name": "truck-pit-stop-api",
        "statement_timeout": str(settings.DATABASE_STATEMENT_TIMEOUT_MS),
        "lock_timeout": str(settings.DATABASE_LOCK_TIMEOUT_MS),
        "idle_in_transaction_session_timeout": str(settings.DATABASE_IDLE_TRANSACTION_TIMEOUT_MS),
    }


def test_sqlite_engine_options_do_not_override_sqlite_pooling():
    options = db_session.build_engine_options("sqlite+aiosqlite:///:memory:")

    assert options["pool_pre_ping"] is True
    assert "pool_size" not in options
    assert "max_overflow" not in options
    assert "connect_args" not in options


@pytest.mark.asyncio
async def test_error_logging_closes_its_owned_session_after_persistence_failure(monkeypatch):
    fake_session = _FailingSession()
    monkeypatch.setattr(error_service, "AsyncSessionLocal", lambda: fake_session)

    result = await error_service.log_error("OperationalError", "database unavailable")

    assert result is None
    assert fake_session.added is not None
    assert fake_session.closed is True


@pytest.mark.asyncio
async def test_error_logging_times_out_and_closes_its_owned_session(monkeypatch):
    fake_session = _HangingSession()
    monkeypatch.setattr(error_service, "AsyncSessionLocal", lambda: fake_session)
    monkeypatch.setattr(settings, "ERROR_LOG_PERSIST_TIMEOUT_SECONDS", 0.01)

    result = await error_service.log_error("OperationalError", "database unavailable")

    assert result is None
    assert fake_session.closed is True


@pytest.mark.asyncio
async def test_lifespan_disposes_database_engine_when_redis_shutdown_fails(monkeypatch):
    from app import main

    disposed = False

    class _Engine:
        async def dispose(self) -> None:
            nonlocal disposed
            disposed = True

    async def _failing_close_redis() -> None:
        raise RuntimeError("redis shutdown failed")

    monkeypatch.setattr(main, "engine", _Engine())
    monkeypatch.setattr(main, "close_redis", _failing_close_redis)

    with pytest.raises(RuntimeError, match="redis shutdown failed"):
        async with main.lifespan(main.app):
            pass

    assert disposed is True


@pytest.mark.asyncio
async def test_pool_checkout_timeout_returns_retryable_response(monkeypatch):
    from app import main

    def _discard(coroutine):
        coroutine.close()
        return None

    monkeypatch.setattr(main.asyncio, "create_task", _discard)
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/repair-orders",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
        }
    )
    request.state.correlation_id = "test-correlation-id"

    response = await main.sqlalchemy_exception_handler(
        request,
        SQLAlchemyTimeoutError("QueuePool limit reached"),
    )

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "1"
    assert json.loads(response.body) == {
        "detail": "Database temporarily unavailable. Please try again.",
        "error": "Database temporarily unavailable",
        "correlation_id": "test-correlation-id",
    }
