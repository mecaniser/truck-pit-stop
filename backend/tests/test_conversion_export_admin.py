from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException

from app.api.v1.endpoints import admin, conversion_exports
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.provider_outbox import ProviderOutboxEvent, ProviderOutboxStatus
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole


async def _shop(db, slug: str, role=UserRole.GARAGE_OWNER):
    tenant = Tenant(name=slug, slug=slug)
    user = User(
        email=f"{slug}@example.com", hashed_password="x", first_name="Shop", last_name="Admin",
        role=role, tenant=tenant, is_active=True, is_verified=True,
    )
    db.add_all([tenant, user])
    await db.commit()
    return tenant, user


@pytest.mark.asyncio
async def test_admin_can_configure_secret_without_reading_it(db_session, monkeypatch):
    tenant, user = await _shop(db_session, f"webhook-{uuid4().hex}", UserRole.GARAGE_ADMIN)
    monkeypatch.setattr("app.core.config.settings.PAID_INVOICE_WEBHOOK_ENCRYPTION_KEY", Fernet.generate_key().decode())

    async def allow(_url):
        return None

    monkeypatch.setattr(admin, "validate_webhook_destination", allow)
    result = await admin.update_paid_invoice_webhook(
        admin.PaidInvoiceWebhookUpdateRequest(enabled=True, url="https://hooks.example.com/conversions", signing_secret="a-long-signing-secret"),
        db=db_session,
        current_user=user,
    )
    assert result.enabled is True
    assert result.signing_secret_configured is True
    assert not hasattr(result, "signing_secret")
    assert tenant.paid_invoice_webhook_secret_encrypted != "a-long-signing-secret"


@pytest.mark.asyncio
async def test_webhook_settings_reject_unsafe_destination(db_session, monkeypatch):
    _tenant, user = await _shop(db_session, f"unsafe-{uuid4().hex}")

    async def reject(_url):
        from app.core.webhook_destination import WebhookDestinationError
        raise WebhookDestinationError("Webhook destination must resolve only to public addresses")

    monkeypatch.setattr(admin, "validate_webhook_destination", reject)
    with pytest.raises(HTTPException) as exc:
        await admin.update_paid_invoice_webhook(
            admin.PaidInvoiceWebhookUpdateRequest(enabled=False, url="https://hooks.example.com/conversions"),
            db=db_session,
            current_user=user,
        )
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_api_keys_are_returned_once_and_tenant_scoped(db_session):
    _tenant_a, owner_a = await _shop(db_session, f"keys-a-{uuid4().hex}")
    _tenant_b, owner_b = await _shop(db_session, f"keys-b-{uuid4().hex}")
    created = await conversion_exports.create_api_key(
        conversion_exports.ApiKeyCreate(name="CallRail"), db=db_session, user=owner_a,
    )
    assert created.api_key.startswith("dbce_")
    listed = await conversion_exports.list_api_keys(db=db_session, user=owner_a)
    assert listed[0]["key_prefix"] == created.key_prefix
    assert "api_key" not in listed[0]
    assert await conversion_exports.list_api_keys(db=db_session, user=owner_b) == []
    with pytest.raises(HTTPException) as exc:
        await conversion_exports.revoke_api_key(created.id, db=db_session, user=owner_b)
    assert exc.value.status_code == 404
    await conversion_exports.revoke_api_key(created.id, db=db_session, user=owner_a)


async def _invoice_context(db, tenant):
    customer = Customer(tenant=tenant, first_name="Test", last_name="Customer", email="test@example.com")
    order = RepairOrder(
        tenant=tenant, customer=customer, vehicle_id=uuid4(), order_number=f"RO-{uuid4().hex}",
        status=RepairOrderStatus.PAID,
    )
    invoice = Invoice(
        tenant=tenant, repair_order=order, invoice_number=f"INV-{uuid4().hex}", status=InvoiceStatus.PAID,
        subtotal=Decimal("100"), tax_amount=Decimal("0"), discount_amount=Decimal("0"),
        total_amount=Decimal("100"), paid_at=datetime.now(timezone.utc),
    )
    db.add_all([customer, order, invoice])
    await db.commit()
    return customer, order, invoice


@pytest.mark.asyncio
async def test_delivery_history_and_replay_are_tenant_scoped(db_session):
    tenant_a, owner_a = await _shop(db_session, f"history-a-{uuid4().hex}")
    tenant_b, owner_b = await _shop(db_session, f"history-b-{uuid4().hex}")
    event_a = ProviderOutboxEvent(
        tenant_id=tenant_a.id, event_type="repair_order.paid", aggregate_type="invoice", aggregate_id=uuid4(),
        payload={}, idempotency_key=f"a-{uuid4()}", status=ProviderOutboxStatus.DEAD.value,
        available_at=datetime.now(timezone.utc),
    )
    event_b = ProviderOutboxEvent(
        tenant_id=tenant_b.id, event_type="repair_order.paid", aggregate_type="invoice", aggregate_id=uuid4(),
        payload={}, idempotency_key=f"b-{uuid4()}", status=ProviderOutboxStatus.DEAD.value,
        available_at=datetime.now(timezone.utc),
    )
    db_session.add_all([event_a, event_b])
    await db_session.commit()
    history = await conversion_exports.delivery_history(skip=0, limit=50, db=db_session, user=owner_a)
    assert [row["event_id"] for row in history] == [event_a.id]
    with pytest.raises(HTTPException) as exc:
        await conversion_exports.replay_delivery(event_b.id, db=db_session, user=owner_a)
    assert exc.value.status_code == 404
    replayed = await conversion_exports.replay_delivery(event_a.id, db=db_session, user=owner_a)
    assert replayed["status"] == ProviderOutboxStatus.PENDING.value
    with pytest.raises(HTTPException) as exc:
        await conversion_exports.replay_delivery(event_a.id, db=db_session, user=owner_a)
    assert exc.value.status_code == 409
    assert owner_b.tenant_id == tenant_b.id


@pytest.mark.asyncio
async def test_correction_validation_idempotency_and_tenant_boundary(db_session):
    tenant_a, owner_a = await _shop(db_session, f"correction-a-{uuid4().hex}")
    _tenant_b, owner_b = await _shop(db_session, f"correction-b-{uuid4().hex}")
    tenant_a.paid_invoice_webhook_enabled = True
    tenant_a.paid_invoice_webhook_url = "https://hooks.example.com/conversions"
    tenant_a.paid_invoice_webhook_secret_encrypted = "encrypted"
    _customer, _order, invoice = await _invoice_context(db_session, tenant_a)

    with pytest.raises(HTTPException) as exc:
        await conversion_exports.create_correction(
            invoice.id, conversion_exports.CorrectionRequest(event_type="repair_order.payment_refunded", total_amount=Decimal("10")),
            idempotency_key="refund-001", db=db_session, user=owner_a,
        )
    assert exc.value.status_code == 422
    with pytest.raises(HTTPException) as exc:
        await conversion_exports.create_correction(
            invoice.id, conversion_exports.CorrectionRequest(event_type="repair_order.payment_voided", total_amount=Decimal("-10")),
            idempotency_key="void-0001", db=db_session, user=owner_a,
        )
    assert exc.value.status_code == 422
    with pytest.raises(HTTPException) as exc:
        await conversion_exports.create_correction(
            invoice.id, conversion_exports.CorrectionRequest(event_type="repair_order.payment_adjusted", total_amount=Decimal("5")),
            idempotency_key="adjust-01", db=db_session, user=owner_b,
        )
    assert exc.value.status_code == 404

    body = conversion_exports.CorrectionRequest(event_type="repair_order.payment_refunded", total_amount=Decimal("-25"))
    first = await conversion_exports.create_correction(invoice.id, body, idempotency_key="refund-002", db=db_session, user=owner_a)
    second = await conversion_exports.create_correction(invoice.id, body, idempotency_key="refund-002", db=db_session, user=owner_a)
    assert second == first
    with pytest.raises(HTTPException) as exc:
        await conversion_exports.create_correction(
            invoice.id, conversion_exports.CorrectionRequest(event_type="repair_order.payment_refunded", total_amount=Decimal("-20")),
            idempotency_key="refund-002", db=db_session, user=owner_a,
        )
    assert exc.value.status_code == 409
