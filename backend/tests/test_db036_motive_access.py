"""Explicit company grants and safe integration read contracts."""

from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.api.v1.endpoints.motive import vehicles
from app.core.dependencies import RequestUserPrincipal
from app.db.models.motive_oauth import MotiveAuthorization, MotiveRemoteVehicle
from app.db.models.user import User, UserRole
from app.db.models.user_customer_link import UserCustomerLink
from app.services import motive_access as access
from app.services import motive_oauth as service
from tests.test_db036_motive_oauth import connect, setup
from tests.test_db036_motive_sandbox import seed

pytestmark = pytest.mark.asyncio


async def customer(db, owner, truck):
    foreign, _, _ = await seed(db, binding=False)
    user = User(
        id=uuid4(),
        tenant_id=foreign.tenant_id,
        email=f"{uuid4()}@example.test",
        hashed_password="fixture",
        first_name="Fleet",
        last_name="Admin",
        role=UserRole.CUSTOMER,
        is_active=True,
        is_verified=True,
    )
    db.add(user)
    await db.flush()
    link = UserCustomerLink(
        user_id=user.id, tenant_id=owner.tenant_id, customer_id=truck.customer_id
    )
    db.add(link)
    await db.commit()
    return RequestUserPrincipal(user, owner.tenant_id, truck.customer_id), link


async def test_customer_requires_explicit_grant_preserves_selected_tenant(
    db_session, monkeypatch
):
    db = db_session
    owner, truck, _ = await setup(db, monkeypatch)
    actor, link = await customer(db, owner, truck)
    assert actor.identity.tenant_id != actor.tenant_id
    assert (await access.companies(db, actor))["items"] == []
    with pytest.raises(HTTPException):
        await service.authorize(db, actor, truck.customer_id)
    assert [
        r["user_id"]
        for r in (await access.candidates(db, owner, truck.customer_id))["items"]
    ] == [actor.id]
    grant = await access.set_grant(db, owner, truck.customer_id, actor.id)
    assert grant["user_id"] == actor.id
    assert (
        await service.authorize(db, actor, truck.customer_id)
    ).id == truck.customer_id
    assert [r["id"] for r in (await access.companies(db, actor))["items"]] == [
        truck.customer_id
    ]
    with pytest.raises(HTTPException):
        await access.set_grant(db, actor, truck.customer_id, actor.id)
    with pytest.raises(HTTPException):
        await access.candidates(db, actor, truck.customer_id)
    wrong = RequestUserPrincipal(actor.identity, actor.tenant_id, uuid4())
    with pytest.raises(HTTPException):
        await service.authorize(db, wrong, truck.customer_id)
    link.deleted_at = service.now()
    await db.commit()
    with pytest.raises(HTTPException):
        await service.authorize(db, actor, truck.customer_id)


async def test_revocation_consumes_pending_oauth_and_immediately_removes_access(
    db_session, monkeypatch
):
    db = db_session
    owner, truck, _ = await setup(db, monkeypatch)
    actor, _ = await customer(db, owner, truck)
    await access.set_grant(db, owner, truck.customer_id, actor.id)
    await service.start(db, actor, truck.customer_id, "customer-session")
    auth = (
        await db.execute(
            select(MotiveAuthorization).where(MotiveAuthorization.user_id == actor.id)
        )
    ).scalar_one()
    assert auth.consumed_at is None
    await access.set_grant(db, owner, truck.customer_id, actor.id, revoke=True)
    await db.refresh(auth)
    assert auth.consumed_at is not None
    assert (await access.companies(db, actor))["items"] == []
    with pytest.raises(HTTPException):
        await service.authorize(db, actor, truck.customer_id)


async def test_grants_reject_unlinked_and_inactive_users(db_session, monkeypatch):
    db = db_session
    owner, truck, _ = await setup(db, monkeypatch)
    actor, link = await customer(db, owner, truck)
    actor.identity.is_active = False
    await db.commit()
    with pytest.raises(HTTPException):
        await access.set_grant(db, owner, truck.customer_id, actor.id)
    actor.identity.is_active = True
    link.customer_id = (await seed(db, binding=False))[2].customer_id
    await db.commit()
    with pytest.raises(HTTPException):
        await access.set_grant(db, owner, truck.customer_id, actor.id)


async def test_metrics_zero_virtual_distinction_and_expired_membership(
    db_session, monkeypatch
):
    db = db_session
    owner, truck, membership = await setup(db, monkeypatch)
    row = await connect(db, owner, truck)
    stamp = service.now()
    remote = MotiveRemoteVehicle(
        tenant_id=owner.tenant_id,
        connection_id=row.id,
        provider_vehicle_id="123",
        vehicle_id=truck.id,
        mapped_at=stamp - timedelta(hours=1),
        discovered_at=stamp,
        provider_status="active",
        metrics_observed_at=stamp,
        metrics_received_at=stamp,
        true_odometer_miles=0,
        virtual_odometer_miles=45,
        true_engine_hours=None,
        virtual_engine_hours=2,
    )
    db.add(remote)
    await db.commit()
    result = (await vehicles(truck.customer_id, db, owner))["items"][0]
    assert result["metrics"]["odometer_miles"] == 0
    assert result["metrics"]["engine_hours"] is None
    assert result["metrics"]["virtual_engine_hours"] == 2
    remote.metrics_observed_at = stamp - timedelta(days=31)
    await db.commit()
    assert (await vehicles(truck.customer_id, db, owner))["items"][0]["metrics"] is None
    remote.metrics_observed_at = stamp
    membership.effective_to = stamp
    await db.commit()
    result = (await vehicles(truck.customer_id, db, owner))["items"][0]
    assert result["metrics"] is None
    assert result["faults"] == []


async def test_webhook_http_limits_and_durable_failure(monkeypatch):
    import httpx
    from fastapi import FastAPI
    from sqlalchemy.exc import OperationalError

    from app.api.v1.endpoints import motive_webhooks as endpoint
    from app.core.dependencies import get_db

    class DB:
        rollbacks = 0

        async def rollback(self):
            self.rollbacks += 1

    db = DB()
    app = FastAPI()
    app.include_router(endpoint.router, prefix="/webhooks/motive")
    app.dependency_overrides[get_db] = lambda: db
    bodies = []

    async def accept(*args):
        bodies.append(args[3])

    monkeypatch.setattr(endpoint, "ingest_webhook", accept)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://app.example.test"
    ) as client:
        url = f"/webhooks/motive/{uuid4()}/1"
        response = await client.post(
            url, content=b"signed-test", headers={"X-KT-Webhook-Signature": "signature"}
        )
        assert response.status_code == 200
        assert bodies == [b"signed-test"]
        response = await client.post(url, content=b"x" * (endpoint.MAX_BODY + 1))
        assert response.status_code == 413
        assert len(bodies) == 1

        async def fail(*args):
            raise OperationalError("fixture", {}, Exception("sensitive-value"))

        monkeypatch.setattr(endpoint, "ingest_webhook", fail)
        response = await client.post(url, content=b"signed-test")
        assert response.status_code == 503
        assert "sensitive-value" not in response.text
        assert db.rollbacks == 1


async def test_webhook_rotation_uses_configured_origin_and_never_idempotency_cache(
    db_session, monkeypatch
):
    from app.api.v1.endpoints.motive import CompanyRequest, rotate_webhook, webhook
    from app.core.config import settings
    from app.middleware import idempotency

    db = db_session
    owner, truck, _ = await setup(db, monkeypatch)
    await connect(db, owner, truck)
    monkeypatch.setattr(settings, "PUBLIC_API_BASE_URL", "https://api.example.test")
    rotated = await rotate_webhook(
        CompanyRequest(fleet_customer_id=truck.customer_id), db, owner
    )
    assert rotated["url"].startswith("https://api.example.test/api/v1/webhooks/motive/")
    assert len(rotated["shared_secret"]) >= 32
    status = await webhook(truck.customer_id, db, owner)
    assert "shared_secret" not in status
    assert not idempotency.IdempotencyMiddleware._should_apply(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/fleet/motive/webhook/rotate",
        }
    )
    monkeypatch.setattr(settings, "PUBLIC_API_BASE_URL", "http://unsafe.example.test")
    with pytest.raises(HTTPException) as failure:
        await rotate_webhook(
            CompanyRequest(fleet_customer_id=truck.customer_id), db, owner
        )
    assert failure.value.status_code == 503
