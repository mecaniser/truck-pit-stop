from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
import base64
import hashlib
import hmac
import json
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError
from sqlalchemy import select

from app.api.v1.endpoints import quickbooks
from app.core.quickbooks_crypto import decrypt_quickbooks_token
from app.core.security import create_access_token
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.provider_outbox import ProviderOutboxEvent, ProviderOutboxStatus
from app.db.models.quickbooks_connection import QuickBooksConnection, QuickBooksOAuthState
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle
from app.services.quickbooks_sync_service import QUICKBOOKS_INVOICE_SYNC_EVENT
from app.services.quickbooks_service import QuickBooksTokenSet
from app.services.quickbooks_payments_service import payments_base_url


async def _owner_with_token(db_session, *, suffix: str = "one"):
    tenant = Tenant(name=f"QuickBooks Garage {suffix}", slug=f"quickbooks-{suffix}")
    user = User(
        email=f"owner-{suffix}@example.com",
        hashed_password="not-used-in-this-test",
        first_name="QuickBooks",
        last_name="Owner",
        role=UserRole.GARAGE_OWNER,
        tenant=tenant,
        is_active=True,
        is_verified=True,
    )
    db_session.add_all([tenant, user])
    await db_session.commit()
    return tenant, user, create_access_token({"sub": str(user.id)})


async def _super_admin_token(db_session):
    user = User(
        email="quickbooks-platform-admin@example.com",
        hashed_password="not-used-in-this-test",
        first_name="Platform",
        last_name="Admin",
        role=UserRole.SUPER_ADMIN,
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.commit()
    return create_access_token({"sub": str(user.id)})


def _configure_quickbooks(monkeypatch):
    monkeypatch.setattr(quickbooks.settings, "QUICKBOOKS_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(quickbooks.settings, "QUICKBOOKS_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setattr(quickbooks.settings, "QUICKBOOKS_REDIRECT_URI", "https://app.example.com/api/v1/quickbooks/oauth/callback")
    monkeypatch.setattr(quickbooks.settings, "QUICKBOOKS_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())


def test_quickbooks_payment_charge_request_accepts_only_an_opaque_token(monkeypatch):
    request = quickbooks.QuickBooksChargeRequest(
        invoice_id=uuid4(),
        token="opaque-intuit-token",
        idempotency_key="quickbooks-payment-request-001",
    )
    assert request.token == "opaque-intuit-token"

    with pytest.raises(ValidationError):
        quickbooks.QuickBooksChargeRequest(
            invoice_id=uuid4(),
            token="opaque-intuit-token",
            idempotency_key="quickbooks-payment-request-002",
            card={"number": "4111111111111111"},
        )

    monkeypatch.setattr(quickbooks.settings, "QUICKBOOKS_PAYMENTS_ENVIRONMENT", "sandbox")
    assert payments_base_url() == "https://sandbox.api.intuit.com"


@pytest.mark.asyncio
async def test_quickbooks_connect_callback_encrypts_tokens_and_rejects_state_replay(client, db_session, monkeypatch):
    _configure_quickbooks(monkeypatch)
    tenant, _user, token = await _owner_with_token(db_session)
    headers = {"Authorization": f"Bearer {token}"}

    start = await client.post("/api/v1/quickbooks/connect", headers=headers)

    assert start.status_code == 200
    authorization_url = start.json()["url"]
    query = parse_qs(urlparse(authorization_url).query)
    state_value = query["state"][0]
    assert query["scope"] == [
        "com.intuit.quickbooks.accounting com.intuit.quickbooks.payment"
    ]

    state_record = (
        await db_session.execute(
            select(QuickBooksOAuthState).where(
                QuickBooksOAuthState.state_hash == sha256(state_value.encode()).hexdigest()
            )
        )
    ).scalar_one()
    assert state_record.tenant_id == tenant.id
    assert state_record.state_hash != state_value
    assert state_record.consumed_at is None

    async def fake_exchange(_code: str) -> QuickBooksTokenSet:
        return QuickBooksTokenSet(
            access_token="intuit-access-token",
            refresh_token="intuit-refresh-token",
            expires_in=3600,
            refresh_token_expires_in=8_640_000,
        )

    monkeypatch.setattr(quickbooks, "exchange_authorization_code", fake_exchange)
    callback = await client.get(
        "/api/v1/quickbooks/oauth/callback",
        params={"state": state_value, "code": "authorization-code", "realmId": "913035829570001"},
    )

    assert callback.status_code == 303
    assert callback.headers["location"].endswith("/dashboard/settings?quickbooks=connected")
    connection = (
        await db_session.execute(
            select(QuickBooksConnection).where(QuickBooksConnection.tenant_id == tenant.id)
        )
    ).scalar_one()
    assert connection.status == "connected"
    assert connection.realm_id == "913035829570001"
    assert connection.encrypted_access_token != "intuit-access-token"
    assert connection.encrypted_refresh_token != "intuit-refresh-token"
    assert decrypt_quickbooks_token(connection.encrypted_access_token) == "intuit-access-token"
    assert decrypt_quickbooks_token(connection.encrypted_refresh_token) == "intuit-refresh-token"

    replay = await client.get(
        "/api/v1/quickbooks/oauth/callback",
        params={"state": state_value, "code": "authorization-code", "realmId": "913035829570001"},
    )
    assert replay.status_code == 400


@pytest.mark.asyncio
async def test_quickbooks_callback_resets_accounting_links_when_company_changes(
    client,
    db_session,
    monkeypatch,
):
    _configure_quickbooks(monkeypatch)
    tenant, _user, token = await _owner_with_token(db_session, suffix="realm-switch")
    headers = {"Authorization": f"Bearer {token}"}
    customer = Customer(
        id=uuid4(),
        tenant_id=tenant.id,
        first_name="Diesel",
        last_name="Bridge",
        email="diesel@example.test",
        quickbooks_customer_id="old-customer",
    )
    vehicle = Vehicle(
        id=uuid4(),
        tenant_id=tenant.id,
        customer_id=customer.id,
        year=2024,
        make="Freightliner",
        model="Cascadia",
    )
    order = RepairOrder(
        id=uuid4(),
        tenant_id=tenant.id,
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        order_number=f"RO-{uuid4().hex[:8]}",
        status=RepairOrderStatus.INVOICED,
        total_parts_cost=Decimal("0.00"),
        total_labor_cost=Decimal("100.00"),
        total_cost=Decimal("100.00"),
    )
    invoice = Invoice(
        id=uuid4(),
        tenant_id=tenant.id,
        repair_order_id=order.id,
        invoice_number=f"INV-{uuid4().hex[:8]}",
        status=InvoiceStatus.SENT,
        subtotal=Decimal("100.00"),
        tax_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("100.00"),
        quickbooks_invoice_id="old-invoice",
        quickbooks_sync_status="synced",
        quickbooks_synced_at=datetime.now(timezone.utc),
    )
    event = ProviderOutboxEvent(
        tenant_id=tenant.id,
        event_type=QUICKBOOKS_INVOICE_SYNC_EVENT,
        aggregate_type="quickbooks_invoice",
        aggregate_id=invoice.id,
        payload={"invoice_id": str(invoice.id), "operation": "sync"},
        idempotency_key=f"quickbooks-invoice:{invoice.id}:sync:v1",
        status=ProviderOutboxStatus.SUCCEEDED.value,
        attempt_count=5,
        available_at=datetime.now(timezone.utc),
        locked_at=datetime.now(timezone.utc) - timedelta(minutes=2),
        locked_until=datetime.now(timezone.utc) + timedelta(minutes=10),
        lock_token="old-claim-token",
        last_attempt_at=datetime.now(timezone.utc) - timedelta(minutes=2),
        completed_at=datetime.now(timezone.utc),
        last_error="old failure",
    )
    connection = QuickBooksConnection(
        tenant_id=tenant.id,
        realm_id="111111111111111",
        scopes="com.intuit.quickbooks.accounting",
        status="connected",
        encrypted_access_token="old-access",
        encrypted_refresh_token="old-refresh",
    )
    db_session.add_all([customer, vehicle, order, invoice, event, connection])
    await db_session.commit()

    async def fake_exchange(_code: str) -> QuickBooksTokenSet:
        return QuickBooksTokenSet(
            access_token="new-access",
            refresh_token="new-refresh",
            expires_in=3600,
            refresh_token_expires_in=8_640_000,
        )

    monkeypatch.setattr(quickbooks, "exchange_authorization_code", fake_exchange)
    start = await client.post("/api/v1/quickbooks/connect", headers=headers)
    state_value = parse_qs(urlparse(start.json()["url"]).query)["state"][0]
    callback = await client.get(
        "/api/v1/quickbooks/oauth/callback",
        params={"state": state_value, "code": "authorization-code", "realmId": "222222222222222"},
    )

    assert callback.status_code == 303
    await db_session.refresh(customer)
    await db_session.refresh(invoice)
    await db_session.refresh(event)
    assert customer.quickbooks_customer_id is None
    assert invoice.quickbooks_invoice_id is None
    assert invoice.quickbooks_sync_status == "pending"
    assert invoice.quickbooks_sync_error is None
    assert event.status == ProviderOutboxStatus.PENDING.value
    assert event.attempt_count == 0
    assert event.locked_at is None
    assert event.locked_until is None
    assert event.lock_token is None
    assert event.completed_at is None
    assert event.last_error is None


@pytest.mark.asyncio
async def test_quickbooks_callback_deduplicates_existing_sync_events_and_recovers_stale_processing(
    client,
    db_session,
    monkeypatch,
):
    _configure_quickbooks(monkeypatch)
    tenant, _user, token = await _owner_with_token(
        db_session,
        suffix="existing-outbox",
    )
    headers = {"Authorization": f"Bearer {token}"}
    customer = Customer(
        id=uuid4(),
        tenant_id=tenant.id,
        first_name="Outbox",
        last_name="Customer",
        email="outbox@example.test",
    )
    vehicle = Vehicle(
        id=uuid4(),
        tenant_id=tenant.id,
        customer_id=customer.id,
        year=2024,
        make="Kenworth",
        model="T680",
    )
    stale_order = RepairOrder(
        id=uuid4(),
        tenant_id=tenant.id,
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        order_number=f"RO-{uuid4().hex[:8]}",
        status=RepairOrderStatus.INVOICED,
        total_parts_cost=Decimal("0.00"),
        total_labor_cost=Decimal("100.00"),
        total_cost=Decimal("100.00"),
    )
    active_order = RepairOrder(
        id=uuid4(),
        tenant_id=tenant.id,
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        order_number=f"RO-{uuid4().hex[:8]}",
        status=RepairOrderStatus.INVOICED,
        total_parts_cost=Decimal("0.00"),
        total_labor_cost=Decimal("75.00"),
        total_cost=Decimal("75.00"),
    )
    stale_invoice = Invoice(
        id=uuid4(),
        tenant_id=tenant.id,
        repair_order_id=stale_order.id,
        invoice_number=f"INV-{uuid4().hex[:8]}",
        status=InvoiceStatus.SENT,
        subtotal=Decimal("100.00"),
        tax_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("100.00"),
    )
    active_invoice = Invoice(
        id=uuid4(),
        tenant_id=tenant.id,
        repair_order_id=active_order.id,
        invoice_number=f"INV-{uuid4().hex[:8]}",
        status=InvoiceStatus.SENT,
        subtotal=Decimal("75.00"),
        tax_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("75.00"),
    )
    stale_event = ProviderOutboxEvent(
        tenant_id=tenant.id,
        event_type=QUICKBOOKS_INVOICE_SYNC_EVENT,
        aggregate_type="quickbooks_invoice",
        aggregate_id=stale_invoice.id,
        payload={"invoice_id": str(stale_invoice.id), "operation": "sync"},
        idempotency_key=f"quickbooks-invoice:{stale_invoice.id}:sync:v1",
        status=ProviderOutboxStatus.PROCESSING.value,
        attempt_count=1,
        available_at=datetime.now(timezone.utc) - timedelta(days=30),
        updated_at=datetime.now(timezone.utc) - timedelta(days=30),
    )
    active_event = ProviderOutboxEvent(
        tenant_id=tenant.id,
        event_type=QUICKBOOKS_INVOICE_SYNC_EVENT,
        aggregate_type="quickbooks_invoice",
        aggregate_id=active_invoice.id,
        payload={"invoice_id": str(active_invoice.id), "operation": "sync"},
        idempotency_key=f"quickbooks-invoice:{active_invoice.id}:sync:v1",
        status=ProviderOutboxStatus.PROCESSING.value,
        attempt_count=1,
        available_at=datetime.now(timezone.utc) - timedelta(hours=2),
        updated_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    db_session.add_all([
        customer,
        vehicle,
        stale_order,
        active_order,
        stale_invoice,
        active_invoice,
        stale_event,
        active_event,
    ])
    await db_session.commit()

    async def fake_exchange(_code: str) -> QuickBooksTokenSet:
        return QuickBooksTokenSet(
            access_token="new-access",
            refresh_token="new-refresh",
            expires_in=3600,
            refresh_token_expires_in=8_640_000,
        )

    monkeypatch.setattr(quickbooks, "exchange_authorization_code", fake_exchange)
    start = await client.post("/api/v1/quickbooks/connect", headers=headers)
    state_value = parse_qs(urlparse(start.json()["url"]).query)["state"][0]
    callback = await client.get(
        "/api/v1/quickbooks/oauth/callback",
        params={
            "state": state_value,
            "code": "authorization-code",
            "realmId": "913035829570777",
        },
    )

    assert callback.status_code == 303
    assert callback.headers["location"].endswith(
        "/dashboard/settings?quickbooks=connected"
    )
    await db_session.refresh(stale_event)
    await db_session.refresh(active_event)
    events = (await db_session.execute(
        select(ProviderOutboxEvent).where(
            ProviderOutboxEvent.tenant_id == tenant.id,
            ProviderOutboxEvent.event_type == QUICKBOOKS_INVOICE_SYNC_EVENT,
        )
    )).scalars().all()
    assert len(events) == 2
    events_by_invoice = {event.aggregate_id: event for event in events}
    assert (
        events_by_invoice[stale_invoice.id].status
        == ProviderOutboxStatus.PENDING.value
    )
    assert events_by_invoice[stale_invoice.id].locked_until is None
    assert (
        events_by_invoice[active_invoice.id].status
        == ProviderOutboxStatus.PROCESSING.value
    )


@pytest.mark.asyncio
async def test_quickbooks_connection_status_is_tenant_scoped_and_disconnect_forgets_tokens(client, db_session, monkeypatch):
    _configure_quickbooks(monkeypatch)
    tenant, _user, token = await _owner_with_token(db_session, suffix="primary")
    _other_tenant, _other_user, other_token = await _owner_with_token(db_session, suffix="other")
    encrypted_access = Fernet(quickbooks.settings.QUICKBOOKS_TOKEN_ENCRYPTION_KEY.encode()).encrypt(b"access").decode()
    encrypted_refresh = Fernet(quickbooks.settings.QUICKBOOKS_TOKEN_ENCRYPTION_KEY.encode()).encrypt(b"refresh").decode()
    connection = QuickBooksConnection(
        tenant_id=tenant.id,
        realm_id="913035829570002",
        scopes="com.intuit.quickbooks.accounting com.intuit.quickbooks.payment",
        status="connected",
        encrypted_access_token=encrypted_access,
        encrypted_refresh_token=encrypted_refresh,
    )
    db_session.add(connection)
    await db_session.commit()

    other_status = await client.get(
        "/api/v1/quickbooks/status",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert other_status.status_code == 200
    assert other_status.json()["is_connected"] is False
    assert other_status.json()["realm_id"] is None

    healthy_status = await client.get(
        "/api/v1/quickbooks/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert healthy_status.status_code == 200
    assert healthy_status.json()["token_health"] == "healthy"

    disconnect_response = await client.post(
        "/api/v1/quickbooks/disconnect",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert disconnect_response.status_code == 200
    assert disconnect_response.json()["is_connected"] is False

    await db_session.refresh(connection)
    assert connection.status == "disconnected"
    assert connection.realm_id is None
    assert connection.encrypted_access_token is None
    assert connection.encrypted_refresh_token is None


@pytest.mark.asyncio
async def test_quickbooks_webhook_verifies_signature_and_records_tenant_health(client, db_session, monkeypatch):
    _configure_quickbooks(monkeypatch)
    verifier = "quickbooks-webhook-verifier"
    monkeypatch.setattr(quickbooks.settings, "QUICKBOOKS_WEBHOOK_VERIFIER_TOKEN", verifier)
    tenant, _user, _token = await _owner_with_token(db_session, suffix="webhook")
    connection = QuickBooksConnection(
        tenant_id=tenant.id,
        realm_id="913035829570099",
        scopes="com.intuit.quickbooks.accounting com.intuit.quickbooks.payment",
        status="connected",
    )
    db_session.add(connection)
    await db_session.commit()

    payload = json.dumps([{
        "id": "event-1",
        "type": "qbo.invoice.updated.v1",
        "intuitaccountid": "913035829570099",
    }]).encode()
    signature = base64.b64encode(hmac.new(verifier.encode(), payload, hashlib.sha256).digest()).decode()
    response = await client.post(
        "/api/v1/quickbooks/webhook",
        content=payload,
        headers={"intuit-signature": signature, "content-type": "application/json"},
    )
    assert response.status_code == 200
    await db_session.refresh(connection)
    assert connection.last_webhook_event == "qbo.invoice.updated.v1"
    assert connection.last_webhook_at is not None

    invalid = await client.post(
        "/api/v1/quickbooks/webhook",
        content=payload,
        headers={"intuit-signature": "not-valid", "content-type": "application/json"},
    )
    assert invalid.status_code == 400


@pytest.mark.asyncio
async def test_quickbooks_connect_requires_deployment_credentials(client, db_session, monkeypatch):
    monkeypatch.setattr(quickbooks.settings, "QUICKBOOKS_CLIENT_ID", "")
    monkeypatch.setattr(quickbooks.settings, "QUICKBOOKS_CLIENT_SECRET", "")
    monkeypatch.setattr(quickbooks.settings, "QUICKBOOKS_REDIRECT_URI", "")
    monkeypatch.setattr(quickbooks.settings, "QUICKBOOKS_TOKEN_ENCRYPTION_KEY", "")
    _tenant, _user, token = await _owner_with_token(db_session, suffix="unconfigured")

    response = await client.post(
        "/api/v1/quickbooks/connect",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 503
    # The global production error policy deliberately avoids exposing which
    # provider credential is missing to browser clients.
    assert response.json()["detail"] == "Internal server error"


@pytest.mark.asyncio
async def test_quickbooks_platform_readiness_is_super_admin_only_and_secret_free(client, db_session, monkeypatch):
    _configure_quickbooks(monkeypatch)
    monkeypatch.setattr(quickbooks.settings, "QUICKBOOKS_WEBHOOK_VERIFIER_TOKEN", "")
    super_admin_token = await _super_admin_token(db_session)
    _tenant, _owner, owner_token = await _owner_with_token(db_session, suffix="platform-access")

    response = await client.get(
        "/api/v1/admin/platform/quickbooks-status",
        headers={"Authorization": f"Bearer {super_admin_token}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "platform_ready": True,
        "callback_url": "https://app.example.com/api/v1/quickbooks/oauth/callback",
        "webhook_ready": False,
        "webhook_url": "http://localhost:8000/api/v1/quickbooks/webhook",
        "scopes": [
            "com.intuit.quickbooks.accounting",
            "com.intuit.quickbooks.payment",
        ],
    }
    assert "test-client-secret" not in response.text
    assert "QUICKBOOKS_TOKEN_ENCRYPTION_KEY" not in response.text

    denied = await client.get(
        "/api/v1/admin/platform/quickbooks-status",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert denied.status_code == 403
