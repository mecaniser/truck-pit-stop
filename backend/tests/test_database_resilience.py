from __future__ import annotations

import asyncio
import gc
import inspect
import json
import time
import weakref
from dataclasses import FrozenInstanceError, asdict
from uuid import UUID, uuid4

import pytest
import stripe
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError
from sqlalchemy.orm import configure_mappers

from app.core.config import settings
from app.db import session as db_session
from app.services import error_service


SENTINEL = "DB031_SENTINEL_SECRET"


class _ControlledSession:
    def __init__(
        self,
        *,
        fail_at: str | None = None,
        hang_at: str | set[str] | None = None,
        resist_cancel_once_at: set[str] | None = None,
        resist_cancel_count_at: dict[str, int] | None = None,
        release_at: dict[str, asyncio.Event] | None = None,
        fail_after_release_at: set[str] | None = None,
        started: dict[str, asyncio.Event] | None = None,
        close_counter: dict[str, int] | None = None,
    ) -> None:
        self.fail_at = fail_at
        self.hang_at = hang_at
        self.resist_cancel_once_at = resist_cancel_once_at or set()
        self.resist_cancel_count_at = resist_cancel_count_at or {}
        self.release_at = release_at or {}
        self.fail_after_release_at = fail_after_release_at or set()
        self.resisted_cancel_at: set[str] = set()
        self.cancel_count_at: dict[str, int] = {}
        self.started = started or {}
        self.close_counter = close_counter
        self.calls: list[str] = []
        self.added = None
        self.active_steps: set[str] = set()
        self.overlapped_steps = False

    def add(self, value) -> None:
        self.calls.append("add")
        self.added = value
        if self.fail_at == "add":
            raise RuntimeError(f"secret={SENTINEL}")

    async def _step(self, name: str) -> None:
        self.calls.append(name)
        if self.active_steps:
            self.overlapped_steps = True
        if name in self.started:
            self.started[name].set()
        if self.fail_at == name:
            raise RuntimeError(f"secret={SENTINEL}")
        hangs = self.hang_at == name or (
            isinstance(self.hang_at, set) and name in self.hang_at
        )
        if hangs:
            self.active_steps.add(name)
            if name == "close" and self.close_counter is not None:
                self.close_counter["active"] += 1
                self.close_counter["maximum"] = max(
                    self.close_counter["maximum"],
                    self.close_counter["active"],
                )
                try:
                    await self._block(name)
                finally:
                    self.close_counter["active"] -= 1
                    self.active_steps.discard(name)
            else:
                try:
                    await self._block(name)
                finally:
                    self.active_steps.discard(name)
            if name in self.fail_after_release_at:
                raise RuntimeError(f"secret={SENTINEL}")

    async def _block(self, name: str) -> None:
        release = self.release_at.get(name)
        while True:
            try:
                if release is None:
                    await asyncio.Event().wait()
                else:
                    await release.wait()
                    return
            except asyncio.CancelledError:
                cancel_count = self.cancel_count_at.get(name, 0) + 1
                self.cancel_count_at[name] = cancel_count
                resistance_limit = self.resist_cancel_count_at.get(
                    name,
                    1 if name in self.resist_cancel_once_at else 0,
                )
                if (
                    cancel_count <= resistance_limit
                ):
                    self.resisted_cancel_at.add(name)
                    continue
                raise

    async def commit(self) -> None:
        await self._step("commit")

    async def refresh(self, _value) -> None:
        await self._step("refresh")

    async def rollback(self) -> None:
        await self._step("rollback")

    async def close(self) -> None:
        await self._step("close")

    async def invalidate(self) -> None:
        await self._step("invalidate")


class _CaptureLogger:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def warning(self, event: str, **values) -> None:
        self.events.append((event, values))


@pytest.fixture(autouse=True)
def _reset_error_persistence_semaphores():
    configure_mappers()
    error_service._persistence_semaphores.clear()
    yield
    error_service._persistence_semaphores.clear()


async def _persist_test_error() -> object:
    return await error_service.log_error(
        "OperationalError",
        "database unavailable",
        endpoint="/api/v1/repair-orders",
        method="GET",
        status_code=500,
    )


def _request(
    *,
    path: str = "/api/v1/repair-orders",
    method: str = "GET",
    query_string: bytes = b"",
    headers: list[tuple[bytes, bytes]] | None = None,
    client: tuple[str, int] = ("testclient", 50000),
) -> Request:
    request = Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": headers or [],
            "query_string": query_string,
            "server": ("testserver", 80),
            "client": client,
            "scheme": "http",
        }
    )
    request.state.correlation_id = "test-correlation-id"
    return request


def test_postgres_engine_options_set_connection_budget_and_timeouts():
    options = db_session.build_engine_options("postgresql+asyncpg://user:pass@db/app")

    assert options["pool_pre_ping"] is False
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

    assert options["pool_pre_ping"] is False
    assert "pool_size" not in options
    assert "max_overflow" not in options
    assert "connect_args" not in options


@pytest.mark.asyncio
async def test_error_logging_success_commits_refreshes_and_closes(monkeypatch):
    fake_session = _ControlledSession()
    monkeypatch.setattr(error_service, "AsyncSessionLocal", lambda: fake_session)

    result = await _persist_test_error()

    assert result is fake_session.added
    assert fake_session.calls == ["add", "commit", "refresh", "close"]


@pytest.mark.asyncio
async def test_error_logging_failed_commit_has_unknown_outcome_and_invalidates_once(monkeypatch):
    fake_session = _ControlledSession(fail_at="commit")
    monkeypatch.setattr(error_service, "AsyncSessionLocal", lambda: fake_session)

    result = await _persist_test_error()

    assert result is None
    assert fake_session.calls == ["add", "commit", "invalidate"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("hang_at", "expected_calls"),
    [
        ("commit", ["add", "commit", "invalidate"]),
        ("refresh", ["add", "commit", "refresh", "close"]),
    ],
)
async def test_error_logging_hangs_are_bounded_by_one_absolute_deadline(
    monkeypatch,
    hang_at,
    expected_calls,
):
    fake_session = _ControlledSession(hang_at=hang_at)
    monkeypatch.setattr(error_service, "AsyncSessionLocal", lambda: fake_session)
    monkeypatch.setattr(settings, "ERROR_LOG_PERSIST_TIMEOUT_SECONDS", 0.06)

    started = time.perf_counter()
    result = await _persist_test_error()
    elapsed = time.perf_counter() - started

    assert result is None
    assert fake_session.calls == expected_calls
    assert elapsed < 0.15


@pytest.mark.asyncio
async def test_cancel_resistant_commit_settles_before_cleanup_and_leaves_no_task(
    monkeypatch,
):
    fake_session = _ControlledSession(
        hang_at="commit",
        resist_cancel_once_at={"commit"},
    )
    monkeypatch.setattr(error_service, "AsyncSessionLocal", lambda: fake_session)
    monkeypatch.setattr(settings, "ERROR_LOG_PERSIST_TIMEOUT_SECONDS", 0.08)
    tasks_before = asyncio.all_tasks()

    started = time.perf_counter()
    result = await _persist_test_error()
    elapsed = time.perf_counter() - started
    await asyncio.sleep(0)

    assert result is None
    assert fake_session.calls == ["add", "commit", "invalidate"]
    assert fake_session.resisted_cancel_at == {"commit"}
    assert fake_session.overlapped_steps is False
    assert fake_session.active_steps == set()
    assert asyncio.all_tasks() == tasks_before
    assert elapsed < 0.12
    semaphore = error_service._persistence_semaphore()
    await asyncio.wait_for(semaphore.acquire(), timeout=0.02)
    semaphore.release()

    error_log_ref = weakref.ref(fake_session.added)
    fake_session.added = None
    gc.collect()
    assert error_log_ref() is None


@pytest.mark.asyncio
async def test_hanging_close_is_bounded_and_falls_back_to_invalidate(monkeypatch):
    fake_session = _ControlledSession(hang_at="close")
    monkeypatch.setattr(error_service, "AsyncSessionLocal", lambda: fake_session)
    monkeypatch.setattr(settings, "ERROR_LOG_PERSIST_TIMEOUT_SECONDS", 0.08)
    monkeypatch.setattr(settings, "ERROR_LOG_PERSIST_MAX_CONCURRENCY", 1)
    error_service._persistence_semaphores.clear()

    started = time.perf_counter()
    result = await _persist_test_error()
    elapsed = time.perf_counter() - started

    assert result is None
    assert fake_session.calls == [
        "add",
        "commit",
        "refresh",
        "close",
        "invalidate",
    ]
    assert fake_session.overlapped_steps is False
    assert fake_session.active_steps == set()
    assert elapsed < 0.14
    semaphore = error_service._persistence_semaphore()
    await asyncio.wait_for(semaphore.acquire(), timeout=0.02)
    semaphore.release()
    assert not any(
        task.get_name() == "error-persistence-lifecycle"
        for task in asyncio.all_tasks()
    )


@pytest.mark.asyncio
async def test_rollback_hang_is_bounded_and_falls_back_to_invalidate(monkeypatch):
    fake_session = _ControlledSession(
        fail_at="add",
        hang_at="rollback",
    )
    monkeypatch.setattr(error_service, "AsyncSessionLocal", lambda: fake_session)
    monkeypatch.setattr(settings, "ERROR_LOG_PERSIST_TIMEOUT_SECONDS", 0.06)
    monkeypatch.setattr(settings, "ERROR_LOG_PERSIST_MAX_CONCURRENCY", 1)
    error_service._persistence_semaphores.clear()

    started = time.perf_counter()
    result = await _persist_test_error()
    elapsed = time.perf_counter() - started

    assert result is None
    assert fake_session.calls == ["add", "rollback", "invalidate"]
    assert elapsed < 0.15
    semaphore = error_service._persistence_semaphore()
    await asyncio.wait_for(semaphore.acquire(), timeout=0.02)
    semaphore.release()


@pytest.mark.asyncio
async def test_precommit_failure_rolls_back_then_closes(monkeypatch):
    fake_session = _ControlledSession(fail_at="add")
    monkeypatch.setattr(error_service, "AsyncSessionLocal", lambda: fake_session)

    result = await _persist_test_error()

    assert result is None
    assert fake_session.calls == ["add", "rollback", "close"]
    assert fake_session.active_steps == set()
    assert fake_session.overlapped_steps is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fail_at", "hang_at", "expected_calls"),
    [
        (
            None,
            {"close", "invalidate"},
            ["add", "commit", "refresh", "close", "invalidate"],
        ),
        (
            "add",
            {"rollback", "invalidate"},
            ["add", "rollback", "invalidate"],
        ),
        (
            "commit",
            "invalidate",
            ["add", "commit", "invalidate"],
        ),
    ],
)
async def test_cleanup_hangs_receive_independent_bounded_cancellation_waves(
    monkeypatch,
    fail_at,
    hang_at,
    expected_calls,
):
    fake_session = _ControlledSession(fail_at=fail_at, hang_at=hang_at)
    monkeypatch.setattr(error_service, "AsyncSessionLocal", lambda: fake_session)
    monkeypatch.setattr(settings, "ERROR_LOG_PERSIST_TIMEOUT_SECONDS", 0.08)
    monkeypatch.setattr(settings, "ERROR_LOG_PERSIST_MAX_CONCURRENCY", 1)
    error_service._persistence_semaphores.clear()

    started = time.perf_counter()
    result = await _persist_test_error()
    elapsed = time.perf_counter() - started
    await asyncio.sleep(0)

    assert result is None
    assert fake_session.calls == expected_calls
    assert fake_session.active_steps == set()
    assert fake_session.overlapped_steps is False
    assert all(count == 1 for count in fake_session.cancel_count_at.values())
    assert elapsed < 0.15
    semaphore = error_service._persistence_semaphore()
    await asyncio.wait_for(semaphore.acquire(), timeout=0.02)
    semaphore.release()
    assert not any(
        task.get_name() == "error-persistence-lifecycle"
        for task in asyncio.all_tasks()
    )


@pytest.mark.asyncio
async def test_error_logging_semaphore_wait_is_inside_absolute_deadline(monkeypatch):
    semaphore = asyncio.BoundedSemaphore(1)
    await semaphore.acquire()
    session_factory_called = False

    def _unexpected_session():
        nonlocal session_factory_called
        session_factory_called = True
        raise AssertionError("session must not be constructed without a permit")

    monkeypatch.setattr(error_service, "_persistence_semaphore", lambda: semaphore)
    monkeypatch.setattr(error_service, "AsyncSessionLocal", _unexpected_session)
    monkeypatch.setattr(settings, "ERROR_LOG_PERSIST_TIMEOUT_SECONDS", 0.05)

    started = time.perf_counter()
    result = await _persist_test_error()
    elapsed = time.perf_counter() - started

    assert result is None
    assert session_factory_called is False
    assert elapsed < 0.12
    semaphore.release()


@pytest.mark.asyncio
async def test_cancellation_exactly_at_semaphore_acquisition_releases_permit(monkeypatch):
    class _CancelOnAcquireSemaphore(asyncio.BoundedSemaphore):
        cancel_once = True

        async def acquire(self):
            acquired = await super().acquire()
            if self.cancel_once:
                self.cancel_once = False
                asyncio.get_running_loop().call_soon(asyncio.current_task().cancel)
            return acquired

    semaphore = _CancelOnAcquireSemaphore(1)
    fake_session = _ControlledSession()
    monkeypatch.setattr(error_service, "_persistence_semaphore", lambda: semaphore)
    monkeypatch.setattr(error_service, "AsyncSessionLocal", lambda: fake_session)
    monkeypatch.setattr(settings, "ERROR_LOG_PERSIST_TIMEOUT_SECONDS", 0.08)

    result = await _persist_test_error()
    await asyncio.sleep(0)

    assert result is None
    assert semaphore._value == 1
    assert fake_session.active_steps == set()
    await asyncio.wait_for(semaphore.acquire(), timeout=0.02)
    semaphore.release()


@pytest.mark.asyncio
async def test_error_logging_keeps_concurrency_permit_through_hanging_close(monkeypatch):
    close_counter = {"active": 0, "maximum": 0}
    sessions: list[_ControlledSession] = []

    def _session_factory():
        session = _ControlledSession(
            hang_at="close",
            close_counter=close_counter,
        )
        sessions.append(session)
        return session

    monkeypatch.setattr(error_service, "AsyncSessionLocal", _session_factory)
    monkeypatch.setattr(settings, "ERROR_LOG_PERSIST_TIMEOUT_SECONDS", 0.08)
    monkeypatch.setattr(settings, "ERROR_LOG_PERSIST_MAX_CONCURRENCY", 2)
    error_service._persistence_semaphores.clear()

    started = time.perf_counter()
    results = await asyncio.gather(*(_persist_test_error() for _ in range(5)))
    elapsed = time.perf_counter() - started
    await asyncio.sleep(0)

    assert results == [None] * 5
    assert len(sessions) == 2
    assert sessions
    assert close_counter == {"active": 0, "maximum": 2}
    assert elapsed < 0.18

    semaphore = error_service._persistence_semaphore()
    await asyncio.wait_for(semaphore.acquire(), timeout=0.02)
    await asyncio.wait_for(semaphore.acquire(), timeout=0.02)
    semaphore.release()
    semaphore.release()


@pytest.mark.asyncio
async def test_external_cancel_twice_resistant_commit_reclaims_permit_late(monkeypatch):
    commit_started = asyncio.Event()
    commit_release = asyncio.Event()
    fake_session = _ControlledSession(
        hang_at="commit",
        resist_cancel_count_at={"commit": 2},
        release_at={"commit": commit_release},
        fail_after_release_at={"commit"},
        started={"commit": commit_started},
    )
    monkeypatch.setattr(error_service, "AsyncSessionLocal", lambda: fake_session)
    monkeypatch.setattr(settings, "ERROR_LOG_PERSIST_TIMEOUT_SECONDS", 0.08)
    monkeypatch.setattr(settings, "ERROR_LOG_PERSIST_MAX_CONCURRENCY", 1)
    error_service._persistence_semaphores.clear()

    task = asyncio.create_task(_persist_test_error())
    await asyncio.wait_for(commit_started.wait(), timeout=0.05)
    cancelled_at = time.perf_counter()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    cancellation_elapsed = time.perf_counter() - cancelled_at

    assert fake_session.calls == ["add", "commit"]
    assert fake_session.cancel_count_at == {"commit": 2}
    assert fake_session.active_steps == {"commit"}
    assert fake_session.overlapped_steps is False
    assert 0.04 <= cancellation_elapsed < 0.15
    semaphore = error_service._persistence_semaphore()
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(semaphore.acquire(), timeout=0.01)

    commit_release.set()
    await asyncio.wait_for(semaphore.acquire(), timeout=0.2)
    semaphore.release()
    await asyncio.sleep(0)
    assert fake_session.calls == ["add", "commit", "invalidate"]
    assert fake_session.active_steps == set()
    assert fake_session.overlapped_steps is False
    assert not any(
        pending.get_name() == "error-persistence-lifecycle"
        for pending in asyncio.all_tasks()
    )


@pytest.mark.asyncio
async def test_twice_resistant_late_confirmed_commit_closes_and_reclaims_permit(
    monkeypatch,
):
    commit_started = asyncio.Event()
    commit_release = asyncio.Event()
    fake_session = _ControlledSession(
        hang_at="commit",
        resist_cancel_count_at={"commit": 2},
        release_at={"commit": commit_release},
        started={"commit": commit_started},
    )
    monkeypatch.setattr(error_service, "AsyncSessionLocal", lambda: fake_session)
    monkeypatch.setattr(settings, "ERROR_LOG_PERSIST_TIMEOUT_SECONDS", 0.08)
    monkeypatch.setattr(settings, "ERROR_LOG_PERSIST_MAX_CONCURRENCY", 1)
    error_service._persistence_semaphores.clear()

    result = await _persist_test_error()

    assert result is None
    assert commit_started.is_set()
    assert fake_session.calls == ["add", "commit"]
    assert fake_session.cancel_count_at == {"commit": 2}
    assert fake_session.active_steps == {"commit"}
    semaphore = error_service._persistence_semaphore()
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(semaphore.acquire(), timeout=0.01)

    commit_release.set()
    await asyncio.wait_for(semaphore.acquire(), timeout=0.2)
    semaphore.release()
    await asyncio.sleep(0)

    assert fake_session.calls == ["add", "commit", "close"]
    assert fake_session.active_steps == set()
    assert fake_session.overlapped_steps is False
    assert not any(
        pending.get_name() == "error-persistence-lifecycle"
        for pending in asyncio.all_tasks()
    )


def test_error_snapshot_is_bounded_redacted_and_fails_closed():
    user_id = uuid4()
    tenant_id = uuid4()
    envelope = error_service.build_error_persistence_envelope(
        error_type=f"OperationalError token={SENTINEL}" + ("x" * 400),
        message=f"password={SENTINEL} " + ("m" * 20_000),
        category=error_service.ErrorCategory.DATABASE,
        severity=error_service.ErrorSeverity.ERROR,
        correlation_id="unsafe correlation value",
        endpoint=(
            f"https://example.test/api/v1/quotes/token/{SENTINEL}/approve"
            f"?access_token={SENTINEL}"
        ),
        method="get",
        status_code=500,
        user_id=str(user_id),
        tenant_id=str(tenant_id),
        stack_trace=f"Bearer {SENTINEL} " + ("s" * 60_000),
        client_ip=f"token={SENTINEL}",
    )
    serialized = json.dumps(asdict(envelope), default=str)

    assert SENTINEL not in serialized
    assert len(envelope.error_type) <= error_service.ERROR_TYPE_MAX_LENGTH
    assert len(envelope.message) <= error_service.ERROR_MESSAGE_MAX_LENGTH
    assert len(envelope.stack_trace or "") <= error_service.ERROR_STACK_MAX_LENGTH
    assert envelope.endpoint == "/api/v1/quotes/token/:token/approve"
    assert envelope.method == "GET"
    assert envelope.status_code == 500
    assert envelope.user_id == user_id
    assert envelope.tenant_id == tenant_id
    assert envelope.client_ip is None

    class _Explosive:
        def __str__(self) -> str:
            raise RuntimeError(f"password={SENTINEL}")

    fallback = error_service.build_error_persistence_envelope(
        error_type=_Explosive(),
        message=_Explosive(),
        category=error_service.ErrorCategory.UNHANDLED,
        severity=error_service.ErrorSeverity.ERROR,
        correlation_id="safe-correlation",
        endpoint=_Explosive(),
        method="GET",
        status_code=500,
    )
    assert fallback == error_service.fallback_error_persistence_envelope(
        correlation_id="safe-correlation",
        status_code=500,
    )
    assert SENTINEL not in json.dumps(asdict(fallback), default=str)


def test_request_context_materializes_as_bounded_redacted_json_primitives():
    source = {
        "payment_intent_id": "pi_safe",
        "amount": 1250.5,
        "attempt": 2,
        "retryable": False,
        "optional": None,
        "password": SENTINEL,
        "url": f"https://example.test/hook?token={SENTINEL}",
        f"credential={SENTINEL}": "safe",
        "nested": ["safe", f"Bearer {SENTINEL}", True, None],
    }

    materialized = error_service.sanitize_context(source)
    serialized = json.dumps(
        materialized,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )

    def _assert_primitive_tree(value):
        if type(value) is dict:
            assert all(type(key) is str for key in value)
            for item in value.values():
                _assert_primitive_tree(item)
            return
        if type(value) is list:
            for item in value:
                _assert_primitive_tree(item)
            return
        assert value is None or type(value) in (str, int, float, bool)

    assert materialized is not None
    _assert_primitive_tree(materialized)
    assert materialized["password"] == "[REDACTED]"
    assert SENTINEL not in serialized
    assert len(serialized.encode("utf-8")) <= (
        error_service.ERROR_CONTEXT_MAX_SERIALIZED_BYTES
    )


def test_request_context_fails_closed_for_hostile_cyclic_deep_or_large_graphs():
    class _Hostile:
        def __str__(self):
            raise AssertionError("hostile context must never be stringified")

        def __repr__(self):
            raise AssertionError("hostile context must never be represented")

    cyclic = {}
    cyclic["self"] = cyclic

    deep = {}
    cursor = deep
    for _ in range(error_service.ERROR_CONTEXT_MAX_DEPTH + 1):
        child = {}
        cursor["child"] = child
        cursor = child

    too_many = {
        f"item-{index}": index
        for index in range(error_service.ERROR_CONTEXT_MAX_ITEMS + 1)
    }
    too_large = {
        "items": [
            "x" * error_service.ERROR_CONTEXT_MAX_STRING_LENGTH
            for _ in range(error_service.ERROR_CONTEXT_MAX_ITEMS)
        ]
    }

    for unsafe in (
        {"user": _Hostile()},
        cyclic,
        deep,
        too_many,
        too_large,
        {"nonfinite": float("nan")},
        {"tuple": ("not", "json")},
    ):
        assert error_service.sanitize_context(unsafe) is None


@pytest.mark.asyncio
async def test_safe_stripe_scalar_context_survives_owned_persistence(monkeypatch):
    fake_session = _ControlledSession()
    monkeypatch.setattr(error_service, "AsyncSessionLocal", lambda: fake_session)
    context = {
        "payment_intent_id": "pi_safe",
        "invoice_id": "invoice-safe",
        "tenant_id": "tenant-safe",
        "error_code": "declined",
        "decline_code": None,
        "amount": 1250.5,
    }

    result = await error_service.log_error(
        "PaymentFailed_declined",
        "Payment failed",
        request_context=context,
    )

    assert result is fake_session.added
    assert fake_session.added.request_context == context
    assert json.loads(
        json.dumps(fake_session.added.request_context, allow_nan=False)
    ) == context


@pytest.mark.asyncio
async def test_request_context_source_graph_is_collectable_while_commit_is_in_flight(
    monkeypatch,
):
    class _SourceUser:
        def __str__(self):
            raise AssertionError("source user must never be stringified")

        def __repr__(self):
            raise AssertionError("source user must never be represented")

    class _SourceError(Exception):
        def __str__(self):
            raise AssertionError("source exception must never be stringified")

        def __repr__(self):
            raise AssertionError("source exception must never be represented")

    commit_started = asyncio.Event()
    commit_release = asyncio.Event()
    fake_session = _ControlledSession(
        hang_at="commit",
        release_at={"commit": commit_release},
        started={"commit": commit_started},
    )
    monkeypatch.setattr(error_service, "AsyncSessionLocal", lambda: fake_session)
    monkeypatch.setattr(settings, "ERROR_LOG_PERSIST_TIMEOUT_SECONDS", 1.0)

    user = _SourceUser()
    user.secret = SENTINEL
    request = _request(
        path=f"/api/v1/quotes/token/{SENTINEL}/approve",
        query_string=f"access_token={SENTINEL}".encode(),
    )
    request.state.user = user
    exc = _SourceError(f"password={SENTINEL}")
    source = {"nested": [request, user, exc], "secret": SENTINEL}
    source["cycle"] = source
    request_ref = weakref.ref(request)
    user_ref = weakref.ref(user)
    exc_ref = weakref.ref(exc)

    task = asyncio.create_task(
        error_service.log_error(
            "OperationalError",
            "safe failure",
            request_context=source,
        )
    )
    await asyncio.wait_for(commit_started.wait(), timeout=0.1)
    assert fake_session.added.request_context is None
    assert task.done() is False

    del source
    del request
    del user
    del exc
    gc.collect()

    assert request_ref() is None
    assert user_ref() is None
    assert exc_ref() is None
    assert json.dumps(fake_session.added.request_context, allow_nan=False) == "null"

    commit_release.set()
    result = await asyncio.wait_for(task, timeout=0.2)
    assert result is fake_session.added
    assert fake_session.calls == ["add", "commit", "refresh", "close"]


@pytest.mark.asyncio
async def test_error_persistence_fallback_log_is_fixed_and_credential_free(monkeypatch):
    fake_session = _ControlledSession(fail_at="commit")
    capture_logger = _CaptureLogger()
    monkeypatch.setattr(error_service, "AsyncSessionLocal", lambda: fake_session)
    monkeypatch.setattr(error_service, "logger", capture_logger)

    result = await error_service.log_error(
        "OperationalError",
        f"password={SENTINEL}",
    )

    assert result is None
    assert capture_logger.events == [
        ("error_log_persistence_failed", {"phase": "commit"})
    ]
    assert SENTINEL not in repr(capture_logger.events)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler_name", "payload"),
    [
        (
            "_handle_payment_failed",
            {
                "id": "pi_test",
                "metadata": {},
                "last_payment_error": {"code": "declined", "message": "declined"},
            },
        ),
        (
            "_handle_charge_failed",
            {
                "id": "ch_test",
                "payment_intent": "pi_test",
                "failure_code": "declined",
                "failure_message": "declined",
            },
        ),
        (
            "_handle_dispute_created",
            {
                "id": "dp_test",
                "charge": "ch_test",
                "amount": 1000,
                "reason": "fraudulent",
                "status": "needs_response",
            },
        ),
    ],
)
async def test_stripe_failure_handlers_use_dedicated_error_session(
    monkeypatch,
    handler_name,
    payload,
):
    from app.api.v1.endpoints import stripe_webhooks

    captured: list[dict] = []

    async def _capture_error(**kwargs):
        captured.append(kwargs)

    monkeypatch.setattr(stripe_webhooks.error_service, "log_error", _capture_error)
    handler = getattr(stripe_webhooks, handler_name)

    await handler(object(), payload)

    assert "db" not in inspect.signature(error_service.log_error).parameters
    assert len(captured) == 1
    assert "db" not in captured[0]


@pytest.mark.asyncio
async def test_background_snapshot_retains_no_request_exception_or_user(monkeypatch):
    from app import main

    class _User:
        pass

    class _RetainedError(Exception):
        pass

    user = _User()
    user.id = uuid4()
    user.tenant_id = uuid4()
    request = _request(
        path=f"/api/v1/quotes/token/{SENTINEL}/approve",
        query_string=f"access_token={SENTINEL}".encode(),
        headers=[
            (b"authorization", f"Bearer {SENTINEL}".encode()),
            (b"cookie", f"session={SENTINEL}".encode()),
            (b"user-agent", SENTINEL.encode()),
        ],
    )
    request.state.user = user
    exc = _RetainedError(f"password={SENTINEL}")
    request_ref = weakref.ref(request)
    user_ref = weakref.ref(user)
    exc_ref = weakref.ref(exc)

    response = await main.global_exception_handler(request, exc)
    background = response.background

    assert background is not None
    assert background.func is main._log_error_async
    assert background.func.__closure__ is None
    assert background.kwargs == {}
    assert len(background.args) == 1
    envelope = background.args[0]
    assert isinstance(envelope, error_service.ErrorPersistenceEnvelope)
    assert not any(
        isinstance(value, (Request, BaseException))
        for value in (*background.args, *background.kwargs.values())
    )
    assert envelope.endpoint == "/api/v1/quotes/token/:token/approve"
    assert envelope.user_id == user.id
    assert envelope.tenant_id == user.tenant_id
    assert envelope.client_ip == "testclient"
    assert all(
        value is None or isinstance(value, (str, int, UUID))
        for value in asdict(envelope).values()
    )
    assert SENTINEL not in json.dumps(asdict(envelope), default=str)
    with pytest.raises(FrozenInstanceError):
        envelope.message = "changed"

    del request
    del user
    del exc
    gc.collect()

    assert request_ref() is None
    assert user_ref() is None
    assert exc_ref() is None


def test_testclient_host_keeps_valid_snapshot_instead_of_fallback(monkeypatch):
    from app import main

    captured: list[error_service.ErrorPersistenceEnvelope] = []

    async def _capture(envelope):
        captured.append(envelope)

    monkeypatch.setattr(main, "_log_error_async", _capture)
    test_app = FastAPI()
    test_app.add_exception_handler(Exception, main.global_exception_handler)

    @test_app.get("/boom")
    async def _boom():
        raise RuntimeError("safe failure")

    with TestClient(test_app, raise_server_exceptions=False) as client:
        response = client.get("/boom")

    assert response.status_code == 500
    assert captured and len(captured) == 1
    assert captured[0].error_type == "RuntimeError"
    assert captured[0].message == "safe failure"
    assert captured[0].endpoint == "/boom"
    assert captured[0].client_ip == "testclient"


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

    persistence_finished = asyncio.Event()

    captured: list[error_service.ErrorPersistenceEnvelope] = []

    async def _capture_persistence(envelope):
        captured.append(envelope)
        persistence_finished.set()

    monkeypatch.setattr(main, "_log_error_async", _capture_persistence)
    request = _request()

    response = await main.sqlalchemy_exception_handler(
        request,
        SQLAlchemyTimeoutError("QueuePool limit reached"),
    )

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "1"
    assert persistence_finished.is_set() is False
    assert response.background is not None
    await response.background()
    assert persistence_finished.is_set() is True
    assert captured[0].client_ip == "testclient"
    assert response.body == (
        b'{"detail":"Database temporarily unavailable. Please try again.",'
        b'"error":"Database temporarily unavailable",'
        b'"correlation_id":"test-correlation-id"}'
    )


@pytest.mark.asyncio
async def test_exception_handler_response_status_body_and_headers_are_unchanged(monkeypatch):
    from app import main

    captured: list[error_service.ErrorPersistenceEnvelope] = []

    async def _capture_persistence(envelope):
        captured.append(envelope)

    monkeypatch.setattr(main, "_log_error_async", _capture_persistence)

    not_found = await main.http_exception_handler(
        _request(),
        HTTPException(
            status_code=404,
            detail="missing",
            headers={"X-Reason": "kept"},
        ),
    )
    assert not_found.status_code == 404
    assert not_found.body == (
        b'{"detail":"missing","error":"missing",'
        b'"correlation_id":"test-correlation-id"}'
    )
    assert not_found.headers["X-Reason"] == "kept"
    assert not_found.background is None

    server_error = await main.http_exception_handler(
        _request(),
        HTTPException(
            status_code=500,
            detail=f"password={SENTINEL}",
            headers={"X-Reason": "kept"},
        ),
    )
    assert server_error.status_code == 500
    assert server_error.body == (
        b'{"detail":"Internal server error","error":"Internal server error",'
        b'"correlation_id":"test-correlation-id"}'
    )
    assert server_error.headers["X-Reason"] == "kept"
    assert server_error.background is not None
    await server_error.background()

    stripe_error = await main.stripe_exception_handler(
        _request(method="POST"),
        stripe.error.APIConnectionError("provider unavailable"),
    )
    assert stripe_error.status_code == 503
    assert stripe_error.body == (
        b'{"detail":"Unable to connect to payment service. Please try again.",'
        b'"error":"Payment error","correlation_id":"test-correlation-id",'
        b'"message":"Unable to connect to payment service. Please try again.",'
        b'"code":null}'
    )
    assert stripe_error.background is not None
    await stripe_error.background()

    unhandled = await main.global_exception_handler(
        _request(),
        RuntimeError("safe failure"),
    )
    assert unhandled.status_code == 500
    assert unhandled.body == (
        b'{"detail":"Internal server error","error":"Internal server error",'
        b'"correlation_id":"test-correlation-id",'
        b'"message":"An unexpected error occurred. Reference: '
        b'test-correlation-id"}'
    )
    assert unhandled.background is not None
    await unhandled.background()

    class _ExplosiveError(Exception):
        def __str__(self) -> str:
            raise RuntimeError(f"password={SENTINEL}")

    snapshot_failure = await main.global_exception_handler(
        _request(),
        _ExplosiveError(),
    )
    assert snapshot_failure.status_code == 500
    assert snapshot_failure.body == unhandled.body
    assert snapshot_failure.background is not None
    await snapshot_failure.background()

    assert [envelope.error_type for envelope in captured] == [
        "HTTPException",
        "APIConnectionError",
        "RuntimeError",
        "ErrorSnapshotFailure",
    ]
    assert SENTINEL not in json.dumps(
        [asdict(envelope) for envelope in captured],
        default=str,
    )
