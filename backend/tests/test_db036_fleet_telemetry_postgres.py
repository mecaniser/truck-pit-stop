# ruff: noqa: F811
"""Database replay serialization and authenticated principal isolation."""

import asyncio
from types import SimpleNamespace

import pytest
from app.db.models.tenant import Tenant
from app.db.models.user import User
from app.services import fleet_telemetry as s
from fastapi import HTTPException
from sqlalchemy import update
from tests.test_db036_fleet_telemetry import body, prepared
from tests.test_db036_motive_oauth_postgres import oauth_pg  # noqa: F401

pytestmark = pytest.mark.asyncio


async def test_concurrent_replay(oauth_pg, monkeypatch):
    async with oauth_pg() as db:
        actor, v, _m = await prepared(db, monkeypatch)
        principal = SimpleNamespace(id=actor.id, tenant_id=actor.tenant_id)
        vid = v.id
        request = body(v, speed_mph=0)

    async def capture():
        async with oauth_pg() as db:
            row, created = await s.capture(db, principal, vid, request)
            await db.commit()
            return row.id, created

    a, b = await asyncio.gather(capture(), capture())
    assert a[0] == b[0] and {a[1], b[1]} == {True, False}


async def test_reloaded_user_cannot_change_authenticated_tenant(oauth_pg, monkeypatch):
    async with oauth_pg() as db:
        actor, v, _m = await prepared(db, monkeypatch)
        other = Tenant(name="Other synthetic", slug="other-synthetic")
        db.add(other)
        await db.commit()
        original = actor.tenant_id
        async with oauth_pg() as writer:
            await writer.execute(
                update(User).where(User.id == actor.id).values(tenant_id=other.id)
            )
            await writer.commit()
        assert actor.tenant_id == original
        with pytest.raises(HTTPException) as exc:
            await s.capture(db, actor, v.id, body(v, speed_mph=0))
        assert exc.value.status_code == 403
