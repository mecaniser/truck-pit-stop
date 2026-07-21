from __future__ import annotations

from decimal import Decimal

import pytest

from app.api.v1.endpoints import platform_payments
from app.core.security import create_access_token
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole


async def _super_admin_token(db_session):
    user = User(
        email="payment-controls-admin@example.com",
        hashed_password="not-used",
        first_name="Platform",
        last_name="Admin",
        role=UserRole.SUPER_ADMIN,
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.commit()
    return create_access_token({"sub": str(user.id)})


@pytest.mark.asyncio
async def test_super_admin_can_view_controls_and_set_forward_only_fee(client, db_session, monkeypatch):
    tenant = Tenant(name="Payments Garage", slug="payments-garage")
    db_session.add(tenant)
    await db_session.commit()
    token = await _super_admin_token(db_session)
    monkeypatch.setattr(
        platform_payments,
        "_merchant_status",
        lambda record: {
            "tenant_id": str(record.id),
            "tenant_name": record.name,
            "owner_email": None,
            "account_id": None,
            "status": "not_started",
            "charges_enabled": False,
            "payouts_enabled": False,
            "requirements": [],
            "platform_fee_percent": None,
            "uses_default_fee": True,
            "last_webhook_at": None,
            "last_webhook_event": None,
            "last_webhook_error": None,
        },
    )
    headers = {"Authorization": f"Bearer {token}"}

    overview = await client.get("/api/v1/admin/payments-control/overview", headers=headers)
    assert overview.status_code == 200
    assert overview.json()["merchants"][0]["tenant_name"] == "Payments Garage"
    assert "secret_key_configured" in overview.json()["configuration"]

    update = await client.patch(
        f"/api/v1/admin/payments-control/tenants/{tenant.id}/fee",
        headers=headers,
        json={"percent": "2.25"},
    )
    assert update.status_code == 200
    assert update.json()["platform_fee_percent"] == "2.250"
    assert update.json()["effective_for"] == "new PaymentIntents only"

    await db_session.refresh(tenant)
    assert tenant.stripe_platform_fee_percent == Decimal("2.250")


@pytest.mark.asyncio
async def test_super_admin_can_reset_a_stale_stripe_connection(client, db_session):
    tenant = Tenant(
        name="Stale Stripe Garage",
        slug="stale-stripe-garage",
        stripe_account_id="acct_no_longer_available",
        stripe_connection_type="stripe_hosted",
        stripe_onboarding_complete=True,
        stripe_last_webhook_event="account.updated",
    )
    db_session.add(tenant)
    await db_session.commit()
    token = await _super_admin_token(db_session)

    response = await client.post(
        f"/api/v1/admin/payments-control/tenants/{tenant.id}/reset-stripe-connection",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "not_started"
    await db_session.refresh(tenant)
    assert tenant.stripe_account_id is None
    assert tenant.stripe_connection_type is None
    assert tenant.stripe_onboarding_complete is False
    assert tenant.stripe_last_webhook_event is None
