from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.api.v1.endpoints import platform_payments
from app.core.security import create_access_token
from app.db.models.quickbooks_connection import QuickBooksConnection
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


@pytest.mark.asyncio
async def test_super_admin_can_view_and_reset_quickbooks_controls(client, db_session, monkeypatch):
    monkeypatch.setattr(platform_payments.settings, "QUICKBOOKS_CLIENT_ID", "configured")
    monkeypatch.setattr(platform_payments.settings, "QUICKBOOKS_CLIENT_SECRET", "configured")
    monkeypatch.setattr(platform_payments.settings, "QUICKBOOKS_REDIRECT_URI", "https://app.example.com/callback")
    monkeypatch.setattr(platform_payments.settings, "QUICKBOOKS_TOKEN_ENCRYPTION_KEY", "configured")
    monkeypatch.setattr(platform_payments.settings, "QUICKBOOKS_WEBHOOK_VERIFIER_TOKEN", "configured")
    monkeypatch.setattr(platform_payments.settings, "QUICKBOOKS_ACCOUNTING_ENVIRONMENT", "sandbox")
    monkeypatch.setattr(platform_payments.settings, "QUICKBOOKS_PAYMENTS_ENVIRONMENT", "sandbox")

    tenant = Tenant(name="QuickBooks Garage", slug="quickbooks-control-garage")
    db_session.add(tenant)
    await db_session.flush()
    token_updated_at = datetime.now(timezone.utc) - timedelta(hours=1)
    connection = QuickBooksConnection(
        tenant_id=tenant.id,
        realm_id="913035829570002",
        scopes="com.intuit.quickbooks.accounting com.intuit.quickbooks.payment",
        status="connected",
        encrypted_access_token="encrypted-access",
        encrypted_refresh_token="encrypted-refresh",
        connected_at=token_updated_at,
        last_token_refresh_at=token_updated_at,
    )
    db_session.add(connection)
    await db_session.commit()
    token = await _super_admin_token(db_session)
    headers = {"Authorization": f"Bearer {token}"}

    overview = await client.get("/api/v1/admin/payments-control/quickbooks/overview", headers=headers)
    assert overview.status_code == 200
    merchant = overview.json()["merchants"][0]
    assert merchant["tenant_name"] == "QuickBooks Garage"
    assert merchant["status"] == "active"
    assert merchant["token_health"] == "healthy"
    assert merchant["requirements"] == []
    assert merchant["last_token_refresh_at"] is not None
    assert merchant["accounting_enabled"] is True
    assert merchant["payments_scope_enabled"] is True
    assert merchant["payments_enabled"] is True
    assert merchant["company_id_label"] == "••••0002"
    assert overview.json()["configuration"]["payments_environment"] == "sandbox"

    ledger = await client.get("/api/v1/admin/payments-control/quickbooks/ledger", headers=headers)
    assert ledger.status_code == 200
    assert ledger.json()["entries"] == []
    assert ledger.json()["totals"]["unreconciled"] == 0

    reset = await client.post(
        f"/api/v1/admin/payments-control/tenants/{tenant.id}/reset-quickbooks-connection",
        headers=headers,
    )
    assert reset.status_code == 200
    assert reset.json()["status"] == "not_connected"
    await db_session.refresh(connection)
    assert connection.status == "disconnected"
    assert connection.realm_id is None
    assert connection.encrypted_access_token is None
    assert connection.encrypted_refresh_token is None


def test_quickbooks_routine_access_token_renewal_remains_active():
    token_updated_at = datetime.now(timezone.utc) - timedelta(hours=1)
    tenant = Tenant(name="QuickBooks Garage", slug="quickbooks-routine-renewal")
    connection = QuickBooksConnection(
        tenant=tenant,
        realm_id="913035829570003",
        scopes="com.intuit.quickbooks.accounting com.intuit.quickbooks.payment",
        status="connected",
        encrypted_access_token="encrypted-access",
        encrypted_refresh_token="encrypted-refresh",
        connected_at=token_updated_at,
        access_token_expires_at=token_updated_at + timedelta(minutes=30),
        refresh_token_expires_at=token_updated_at + timedelta(days=90),
        last_token_refresh_at=token_updated_at,
    )
    merchant = platform_payments._quickbooks_merchant_status(
        tenant,
        connection,
        {
            "payments_environment_valid": True,
        },
    )

    assert merchant["token_health"] == "refresh_required"
    assert merchant["status"] == "active"
    assert merchant["requirements"] == []
    assert merchant["payments_enabled"] is True

    connection.last_token_refresh_error = "Intuit rejected token renewal"
    failed_merchant = platform_payments._quickbooks_merchant_status(
        tenant,
        connection,
        {
            "payments_environment_valid": True,
        },
    )
    assert failed_merchant["status"] == "attention"
    assert failed_merchant["requirements"] == ["Resolve the latest token refresh error"]
