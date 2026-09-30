# ruff: noqa: F811 - pytest fixture injection
"""Durable full-scope receipts and credential races on disposable PostgreSQL."""
import asyncio

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.core import motive_crypto
from app.db.models.motive_oauth import MotiveConnection, MotiveWebhookReceipt
from app.db.models.user import User
from app.services import motive_ingestion as ingest
from app.services import motive_oauth as oauth
from tests.test_db036_motive_full import SECRET, FullProvider, prepared, signed
from tests.test_db036_motive_oauth_postgres import oauth_pg  # noqa: F401

pytestmark = pytest.mark.asyncio


async def test_postgres_concurrent_signed_receipt_is_durable(oauth_pg, monkeypatch):
    factory = oauth_pg
    async with factory() as db:
        actor, truck, row, _, _ = await prepared(db, monkeypatch)
        await ingest.configure_webhook(db, actor, truck.customer_id, SECRET)
        route, generation = row.webhook_id, row.webhook_generation
    body, signature = signed({"action": "vehicle_location_received", "id": "synthetic", "vehicle_id": 123})
    async def deliver():
        async with factory() as db:
            try:
                return await ingest.ingest_webhook(db, route, generation, body, signature)
            except HTTPException as exc:
                assert exc.status_code == 503
                return {"status": "retry"}
    results = await asyncio.gather(deliver(), deliver())
    assert any(r["status"] == "accepted" for r in results)
    async with factory() as db:
        assert (await ingest.ingest_webhook(db, route, generation, body, signature))["status"] == "duplicate"
        assert await db.scalar(select(func.count()).select_from(MotiveWebhookReceipt)) == 1


async def test_postgres_revoked_actor_rotation_survives_denial(oauth_pg, monkeypatch):
    factory = oauth_pg
    async with factory() as db:
        actor, _, row, _, _ = await prepared(db, monkeypatch)
        row.token_expires_at = oauth.now()
        user_id, connection_id = actor.id, row.id
        await db.commit()
    class RevokingProvider(FullProvider):
        async def tokens(self, **kwargs):
            return {"access_token": "rotated-access", "refresh_token": "rotated-refresh", "expires_in": 7200}
        async def inventory(self, token):
            async with factory() as other:
                actor = await other.get(User, user_id)
                actor.is_active = False
                await other.commit()
            return await super().inventory(token)
    async with factory() as db:
        actor = await db.get(User, user_id)
        row = (await db.execute(select(MotiveConnection).where(MotiveConnection.id == connection_id).with_for_update())).scalar_one()
        with pytest.raises(HTTPException) as exc:
            await oauth.sync(db, row, RevokingProvider(), actor=actor)
        assert exc.value.status_code == 403
        await db.rollback()
    async with factory() as db:
        row = await db.get(MotiveConnection, connection_id)
        assert motive_crypto.decrypt(row.encrypted_tokens, row.id, row.tenant_id, row.fleet_customer_id)["refresh_token"] == "rotated-refresh"
