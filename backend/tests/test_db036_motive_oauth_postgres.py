"""Real PostgreSQL races and database company boundaries in disposable schemas."""

import asyncio
import os
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import create_engine, select, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models.motive_oauth import MotiveConnection, MotiveRemoteVehicle
from app.services import motive_oauth as s
from tests.test_db036_motive_oauth import Provider, connect, setup

NATIVE_UUID_BIND = PG_UUID.bind_processor
NATIVE_UUID_RESULT = PG_UUID.result_processor
pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def oauth_pg(monkeypatch):
    dsn = os.environ.get("DB036_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("Disposable local DB036_TEST_DATABASE_URL required")
    url = make_url(dsn)
    assert url.host in {"127.0.0.1", "localhost"} and url.database == "db036_test"
    monkeypatch.setattr(PG_UUID, "bind_processor", NATIVE_UUID_BIND)
    monkeypatch.setattr(PG_UUID, "result_processor", NATIVE_UUID_RESULT)
    schema = "db036_oauth_" + uuid4().hex
    admin = create_engine(url.set(drivername="postgresql+psycopg2"))
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    sync = create_engine(
        url.set(drivername="postgresql+psycopg2"),
        connect_args={"options": f"-csearch_path={schema}"},
    )
    with sync.begin() as conn:
        Base.metadata.create_all(conn)
    engine = create_async_engine(
        url.set(drivername="postgresql+asyncpg"),
        connect_args={"server_settings": {"search_path": schema}},
    )
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()
        sync.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


async def test_oauth_postgres_refresh_singleflight_lock_and_disconnect(
    oauth_pg, monkeypatch
):
    factory = oauth_pg
    async with factory() as db:
        actor, truck, _ = await setup(db, monkeypatch)
        row = await connect(db, actor, truck)
        row.token_expires_at = s.now()
        await db.commit()
        tenant_id, company_id = row.tenant_id, row.fleet_customer_id
    entered = asyncio.Event()
    release = asyncio.Event()

    class Slow(Provider):
        async def tokens(self, **kwargs):
            entered.set()
            await release.wait()
            return await super().tokens(**kwargs)

    client = Slow()

    async def first():
        async with factory() as db:
            row = await s.connection(db, tenant_id, company_id, True)
            return await s.sync(db, row, client)

    task = asyncio.create_task(first())
    await asyncio.wait_for(entered.wait(), 5)
    try:
        async with factory() as db:
            with pytest.raises(HTTPException) as exc:
                from app.db.models.user import User

                current = await db.get(User, actor.id)
                await s.disconnect(db, current, company_id)
            assert exc.value.status_code == 409
    finally:
        release.set()
        await task
    assert client.calls == 1
    async with factory() as db:
        from app.db.models.user import User

        current = await db.get(User, actor.id)
        await s.disconnect(db, current, company_id)
        row = await s.connection(db, tenant_id, company_id)
        assert row.encrypted_tokens is None and row.status == "disconnected"


async def test_oauth_postgres_state_replay_one_provider_exchange(oauth_pg, monkeypatch):
    from urllib.parse import parse_qs, urlsplit

    from app.db.models.user import User

    factory = oauth_pg
    async with factory() as db:
        actor, truck, _ = await setup(db, monkeypatch)
        started = await s.start(db, actor, truck.customer_id, "session-1")
        state = parse_qs(urlsplit(started["authorization_url"]).query)["state"][0]
        user_id = actor.id
    provider = Provider()

    async def exchange():
        async with factory() as db:
            actor = await db.get(User, user_id)
            try:
                return await s.callback(
                    db, actor, "session-1", state, "code", client=provider
                )
            except HTTPException as exc:
                return exc.status_code

    results = await asyncio.gather(exchange(), exchange())
    assert len([r for r in results if isinstance(r, dict)]) == 1
    assert 400 in results and provider.calls == 1


async def test_oauth_postgres_cross_tenant_fk(oauth_pg, monkeypatch):
    factory = oauth_pg
    async with factory() as db:
        actor, truck, _ = await setup(db, monkeypatch)
        row = await connect(db, actor, truck)
        row_id = row.id
    async with factory() as db:
        db.add(
            MotiveRemoteVehicle(
                tenant_id=uuid4(),
                connection_id=row_id,
                provider_vehicle_id="123",
                discovered_at=s.now(),
            )
        )
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()
    async with factory() as db:
        assert (
            await db.execute(select(MotiveConnection))
        ).scalar_one().tenant_id == actor.tenant_id


async def test_oauth_postgres_callback_disconnect_race(oauth_pg, monkeypatch):
    from urllib.parse import parse_qs, urlsplit

    from app.db.models.user import User

    factory = oauth_pg
    async with factory() as db:
        actor, truck, _ = await setup(db, monkeypatch)
        result = await s.start(db, actor, truck.customer_id, "session-1")
        state = parse_qs(urlsplit(result["authorization_url"]).query)["state"][0]
        user_id, company_id, tenant_id = actor.id, truck.customer_id, actor.tenant_id
    entered, release = asyncio.Event(), asyncio.Event()

    class Slow(Provider):
        async def tokens(self, **kwargs):
            entered.set()
            await release.wait()
            return await super().tokens(**kwargs)

    async def exchange():
        async with factory() as db:
            actor = await db.get(User, user_id)
            with pytest.raises(HTTPException) as exc:
                await s.callback(db, actor, "session-1", state, "code", client=Slow())
            assert exc.value.status_code == 409

    task = asyncio.create_task(exchange())
    await asyncio.wait_for(entered.wait(), 5)
    try:
        async with factory() as db:
            actor = await db.get(User, user_id)
            await s.disconnect(db, actor, company_id)
    finally:
        release.set()
        await task
    async with factory() as db:
        row = await s.connection(db, tenant_id, company_id)
        assert row.encrypted_tokens is None and row.status == "disconnected"
