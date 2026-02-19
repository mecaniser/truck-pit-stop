from __future__ import annotations

import sys
import os
from pathlib import Path
from typing import Any, Callable

import pytest


# Ensure `app` package resolves from backend/.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Minimal config required to import app settings in test environment.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-with-at-least-32-characters")


class FakePipeline:
    def __init__(self, redis: "FakeRedis") -> None:
        self.redis = redis
        self.ops: list[Callable[[], Any]] = []

    def zremrangebyscore(self, key: str, min_score: int, max_score: int) -> "FakePipeline":
        def _op() -> int:
            zset = self.redis.sorted_sets.setdefault(key, {})
            members_to_remove = [member for member, score in zset.items() if min_score <= score <= max_score]
            for member in members_to_remove:
                zset.pop(member, None)
            return len(members_to_remove)

        self.ops.append(_op)
        return self

    def zadd(self, key: str, mapping: dict[str, int]) -> "FakePipeline":
        def _op() -> int:
            zset = self.redis.sorted_sets.setdefault(key, {})
            added = 0
            for member, score in mapping.items():
                if member not in zset:
                    added += 1
                zset[member] = score
            return added

        self.ops.append(_op)
        return self

    def zcard(self, key: str) -> "FakePipeline":
        def _op() -> int:
            return len(self.redis.sorted_sets.setdefault(key, {}))

        self.ops.append(_op)
        return self

    def expire(self, key: str, ttl: int) -> "FakePipeline":
        def _op() -> bool:
            return True

        self.ops.append(_op)
        return self

    async def execute(self) -> list[Any]:
        return [op() for op in self.ops]


class FakeRedis:
    def __init__(self) -> None:
        self.kv: dict[str, str] = {}
        self.sorted_sets: dict[str, dict[str, int]] = {}

    async def get(self, key: str):
        return self.kv.get(key)

    async def set(self, key: str, value: str, ex: int | None = None, nx: bool = False):
        if nx and key in self.kv:
            return False
        self.kv[key] = value
        return True

    async def setex(self, key: str, ttl: int, value: str):
        self.kv[key] = value
        return True

    async def delete(self, key: str):
        self.kv.pop(key, None)
        return 1

    async def exists(self, key: str):
        return 1 if key in self.kv else 0

    async def incr(self, key: str):
        cur = int(self.kv.get(key, "0"))
        cur += 1
        self.kv[key] = str(cur)
        return cur

    async def ping(self):
        return True

    def pipeline(self) -> FakePipeline:
        return FakePipeline(self)


@pytest.fixture
def fake_redis() -> FakeRedis:
    return FakeRedis()


# ---------------------------------------------------------------------------
# Integration-test fixtures: async client with in-memory SQLite
# ---------------------------------------------------------------------------

pytest.importorskip("aiosqlite")

import httpx
import pytest_asyncio
from sqlalchemy import event, String
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.db.base import Base
import app.db.models  # noqa: F401 — ensure all models are registered
from app.db.session import get_db
from app.core import redis as redis_module


def _render_pg_uuid_as_string(ddl_compiler, column, **kw):
    """Compile postgresql.UUID as CHAR(32) on SQLite."""
    return "CHAR(32)"


@pytest_asyncio.fixture
async def _db_engine():
    """Create a fresh in-memory SQLite engine and tables."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    # Make postgresql-specific types renderable on SQLite
    from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
    if not hasattr(SQLiteTypeCompiler, "visit_UUID"):
        SQLiteTypeCompiler.visit_UUID = lambda self, type_, **kw: "CHAR(32)"
    if not hasattr(SQLiteTypeCompiler, "visit_JSONB"):
        SQLiteTypeCompiler.visit_JSONB = lambda self, type_, **kw: "TEXT"
    if not hasattr(SQLiteTypeCompiler, "visit_JSON"):
        SQLiteTypeCompiler.visit_JSON = lambda self, type_, **kw: "TEXT"

    # Patch PG UUID to not call .hex on string values (SQLite compat)
    _orig_bp = PG_UUID.bind_processor

    def _patched_bind_processor(self, dialect):
        if dialect.name == "sqlite":
            def process(value):
                if value is None:
                    return value
                return str(value).replace("-", "")
            return process
        return _orig_bp(self, dialect)

    PG_UUID.bind_processor = _patched_bind_processor

    # Also patch result processor so reads back as UUID when as_uuid=True
    _orig_rp = PG_UUID.result_processor

    def _patched_result_processor(self, dialect, coltype):
        if dialect.name == "sqlite" and self.as_uuid:
            import uuid as _uuid
            def process(value):
                if value is None:
                    return value
                if isinstance(value, _uuid.UUID):
                    return value
                return _uuid.UUID(str(value))
            return process
        return _orig_rp(self, dialect)

    PG_UUID.result_processor = _patched_result_processor

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(_db_engine):
    """Yield a fresh async session for direct DB setup in tests."""
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(_db_engine, monkeypatch):
    """
    Async httpx client talking to the FastAPI app with:
    - Isolated in-memory SQLite DB
    - FakeRedis for all redis functions
    - Rate limiter disabled
    - Email/SMS sending mocked
    """
    from app.main import app

    factory = async_sessionmaker(_db_engine, expire_on_commit=False)

    async def _override_get_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db

    # Patch Redis functions used by auth
    _fake = FakeRedis()

    async def _fake_get_redis():
        return _fake

    monkeypatch.setattr(redis_module, "get_redis", _fake_get_redis)
    monkeypatch.setattr(redis_module, "redis_client", _fake)

    # Patch get_redis in all middleware modules that import it directly
    import app.middleware.throttling as throttling_mod
    import app.middleware.idempotency as idempotency_mod
    monkeypatch.setattr(throttling_mod, "get_redis", _fake_get_redis)
    monkeypatch.setattr(idempotency_mod, "get_redis", _fake_get_redis)

    # Stub token-version / blacklist helpers to use the fake KV store
    async def _get_tv(user_id: str) -> int:
        v = await _fake.get(f"token_version:{user_id}")
        return int(v) if v else 0

    async def _is_bl(jti: str) -> bool:
        return (await _fake.get(f"token_blacklist:{jti}")) is not None

    async def _bl(jti: str, ttl: int):
        await _fake.setex(f"token_blacklist:{jti}", ttl, "1")

    async def _incr_tv(user_id: str) -> int:
        key = f"token_version:{user_id}"
        cur = await _fake.get(key)
        nxt = (int(cur) if cur else 0) + 1
        await _fake.set(key, str(nxt))
        return nxt

    async def _store_pw_reset(email, token, expires_in=3600):
        await _fake.setex(f"password_reset:{token}", expires_in, email)

    async def _get_email_reset(token):
        return await _fake.get(f"password_reset:{token}")

    async def _del_pw_reset(token):
        await _fake.delete(f"password_reset:{token}")

    monkeypatch.setattr(redis_module, "get_token_version", _get_tv)
    monkeypatch.setattr(redis_module, "is_token_blacklisted", _is_bl)
    monkeypatch.setattr(redis_module, "blacklist_token", _bl)
    monkeypatch.setattr(redis_module, "increment_token_version", _incr_tv)
    monkeypatch.setattr(redis_module, "store_password_reset_token", _store_pw_reset)
    monkeypatch.setattr(redis_module, "get_email_from_reset_token", _get_email_reset)
    monkeypatch.setattr(redis_module, "delete_password_reset_token", _del_pw_reset)

    # Disable rate limiter — set enabled=False directly (official slowapi toggle)
    import app.core.rate_limit as rl_module
    rl_module.limiter.enabled = False

    # Mock email sending
    import app.services.email_service as email_mod
    import resend

    monkeypatch.setattr(resend.Emails, "send", lambda params: {"id": "mock"})

    # Mock metrics (no-op)
    import app.core.metrics as metrics_mod
    monkeypatch.setattr(metrics_mod, "record_login", lambda **kw: None)
    monkeypatch.setattr(metrics_mod, "record_logout", lambda **kw: None)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()
