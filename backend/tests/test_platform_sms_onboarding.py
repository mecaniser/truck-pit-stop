"""Platform registration boundary, explicit shop scope and preserved consent routes."""
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select

from app.api.v1.endpoints import platform_sms_onboarding, sms_onboarding
from app.core.dependencies import get_current_active_user, get_db
from app.db.models.messaging_business import MessagingBusiness, SMSConfigurationAudit, TenantSMSBinding
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole

OPERATIONS = [("GET", "", None), ("PUT", "", {"expected_version": 0}),
              ("POST", "/review", {"expected_version": 1}), ("GET", "/review-package", None)]


def app_for(user=None, db=None):
    app = FastAPI()
    app.include_router(platform_sms_onboarding.router, prefix="/admin/tenants/{tenant_id}/sms")
    app.include_router(sms_onboarding.router, prefix="/communications/sms")
    if user is not None:
        app.dependency_overrides[get_current_active_user] = lambda: user
    if db is not None:
        app.dependency_overrides[get_db] = lambda: db
    return app


class NoLookup:
    async def scalar(self, *_args, **_kwargs):
        pytest.fail("Unauthorized registration must not look up a shop")


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [r for r in UserRole if r != UserRole.SUPER_ADMIN])
@pytest.mark.parametrize("method,suffix,body", OPERATIONS)
async def test_non_platform_roles_denied_before_target_lookup(role, method, suffix, body):
    app = app_for(SimpleNamespace(role=role, tenant_id=uuid4()), NoLookup())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        result = await client.request(method, f"/admin/tenants/{uuid4()}/sms/onboarding{suffix}", json=body)
    assert result.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("role", list(UserRole))
@pytest.mark.parametrize("method,suffix,body", OPERATIONS)
async def test_legacy_registration_denied_for_every_role(role, method, suffix, body):
    app = app_for(SimpleNamespace(role=role, tenant_id=uuid4()), NoLookup())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        result = await client.request(method, f"/communications/sms/onboarding{suffix}", json=body)
    assert result.status_code == 403
    assert result.json()["detail"]["code"] == "platform_registration_required"


@pytest.mark.asyncio
@pytest.mark.parametrize("prefix", ["/communications/sms", f"/admin/tenants/{uuid4()}/sms"])
async def test_unauthenticated_registration_denied(prefix):
    app = app_for(db=NoLookup())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(prefix + "/onboarding")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_explicit_target_data_version_audit_and_provider_boundaries(db_session, monkeypatch):
    from app.services import messaging_service
    from app.core.config import settings
    monkeypatch.setattr(messaging_service, "_get_twilio_client", lambda: pytest.fail("No provider transport"))
    for key in ("SMS_TENANT_ROUTING_ENABLED", "SMS_AUTOMATION_OUTBOX_ENABLED", "SMS_RECOVERY_ENABLED"):
        monkeypatch.setattr(settings, key, False)
    a = Tenant(id=uuid4(), name="Shop A", slug=f"a-{uuid4()}", is_active=False, messaging_enabled=False)
    b = Tenant(id=uuid4(), name="Shop B", slug=f"b-{uuid4()}")
    deleted = Tenant(id=uuid4(), name="Deleted", slug=f"d-{uuid4()}", deleted_at=datetime.now(timezone.utc))
    actor = User(id=uuid4(), tenant_id=None, email=f"platform-{uuid4()}@example.test", first_name="Platform", last_name="Test", role=UserRole.SUPER_ADMIN, hashed_password="disabled", is_active=True)
    db_session.add_all([a, b, deleted, actor]); await db_session.flush()
    old_a = MessagingBusiness(tenant_id=a.id, legal_name="Retained draft A", sample_messages=[], version=3, status="draft")
    old_b = MessagingBusiness(tenant_id=b.id, legal_name="Untouched B", sample_messages=[], version=9, status="draft")
    db_session.add_all([old_a, old_b]); await db_session.commit()
    app = app_for(actor, db_session)
    path = f"/admin/tenants/{a.id}/sms/onboarding"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        initial = await client.get(path)
        assert initial.status_code == 200
        assert initial.json()["fields"]["legal_name"] == "Retained draft A"
        assert initial.json()["submission_enabled"] is False
        for target in (uuid4(), deleted.id):
            assert (await client.get(f"/admin/tenants/{target}/sms/onboarding")).status_code == 404
        for forbidden in ("tenant_id", "status", "enabled", "credential_ref", "account_sid"):
            assert (await client.put(path, json={"expected_version": 3, forbidden: str(b.id)})).status_code == 422
        body = {"expected_version": 3, "legal_name": "Shop A LLC", "trade_name": "Shop A", "website_url": "https://shop.example", "support_email": "help@shop.example", "consent_source_url": "https://shop.example/consent", "privacy_url": "https://shop.example/privacy", "terms_url": "https://shop.example/terms", "representative_name": "Owner", "representative_email": "owner@shop.example", "message_description": "Repair updates", "sample_messages": ["Repair is ready. Reply STOP to opt out."]}
        saved = await client.put(path, json=body)
        assert saved.status_code == 200 and saved.json()["version"] == 4
        stale = await client.put(path, json=body)
        assert stale.status_code == 409 and stale.json()["detail"]["code"] == "version_conflict"
        review = await client.post(path + "/review", json={"expected_version": 4})
        assert review.status_code == 200 and review.json()["status"] == "ready_for_review"
        package = await client.get(path + "/review-package")
        assert package.json()["review_only"] is True and package.json()["version"] == 5
        old_a.status = "approved"; await db_session.commit()
        for method, suffix, data in [("PUT", "", {"expected_version": 5}), ("POST", "/review", {"expected_version": 5})]:
            locked = await client.request(method, path + suffix, json=data)
            assert locked.status_code == 409 and locked.json()["detail"]["code"] == "registration_locked"
    await db_session.refresh(old_b)
    assert (old_b.legal_name, old_b.version, old_b.status) == ("Untouched B", 9, "draft")
    audits = (await db_session.scalars(select(SMSConfigurationAudit))).all()
    assert [(row.tenant_id, row.actor_id, row.action, row.business_version) for row in audits] == [(a.id, actor.id, "draft_saved", 4), (a.id, actor.id, "review_requested", 5)]
    assert (await db_session.scalars(select(TenantSMSBinding))).all() == []
    assert not a.sms_enabled and not b.sms_enabled
    assert all(not getattr(settings, key) for key in ("SMS_TENANT_ROUTING_ENABLED", "SMS_AUTOMATION_OUTBOX_ENABLED", "SMS_RECOVERY_ENABLED"))


@pytest.mark.asyncio
async def test_consent_routes_remain_tenant_scoped(db_session):
    from app.db.models.customer import Customer
    a = Tenant(id=uuid4(), name="Consent A", slug=f"a-{uuid4()}", messaging_enabled=True)
    b = Tenant(id=uuid4(), name="Consent B", slug=f"b-{uuid4()}", messaging_enabled=True)
    actor = User(id=uuid4(), tenant_id=a.id, email=f"owner-{uuid4()}@example.test", first_name="Owner", last_name="A", role=UserRole.GARAGE_OWNER, hashed_password="disabled", is_active=True)
    db_session.add_all([a, b]); await db_session.flush()
    customer = Customer(id=uuid4(), tenant_id=a.id, first_name="Local", last_name="Contact", email="local@example.test", phone="+15005550111")
    foreign = Customer(id=uuid4(), tenant_id=b.id, first_name="Foreign", last_name="Contact", email="foreign@example.test", phone="+15005550112")
    db_session.add_all([actor, customer, foreign]); await db_session.commit()
    app = app_for(actor, db_session)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/communications/sms/consents", params={"customer_id": str(customer.id)})).status_code == 200
        body = {"customer_id": str(customer.id), "status": "granted", "source": "signed_service_form", "disclosure_version": "v1", "collected_at": "2020-01-01T00:00:00Z"}
        assert (await client.post("/communications/sms/consents", json=body)).status_code == 200
        body["customer_id"] = str(foreign.id)
        assert (await client.post("/communications/sms/consents", json=body)).status_code == 404
        assert (await client.get("/communications/sms/consents", params={"customer_id": str(foreign.id)})).status_code == 404
