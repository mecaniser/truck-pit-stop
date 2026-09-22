"""DB-067: native sender contract used by the ELIS receiver fixture tests."""
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.v1.endpoints import admin, conversion_exports
from app.core.paid_invoice_webhook_crypto import encrypt_paid_invoice_webhook_secret
from app.core.webhook_destination import ResolvedWebhookDestination
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.invoice_settlement import InvoiceSettlement
from app.db.models.provider_outbox import ProviderOutboxEvent
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.schemas.repair_order import RepairOrderCreate, RepairOrderUpdate
from app.services import paid_invoice_webhook_service as service

NOW = datetime(2026, 9, 22, 12, tzinfo=timezone.utc)
IDS = [UUID(f"10000000-0000-4000-8000-{n:012d}") for n in range(1, 7)]


def resources():
    tenant = Tenant(id=IDS[0], name="Synthetic Garage", slug="synthetic-garage", paid_invoice_webhook_enabled=True, paid_invoice_webhook_url="https://receiver.example/hook", paid_invoice_webhook_secret_encrypted="placeholder")
    tenant.paid_invoice_webhook_payload_version = 2
    customer = Customer(id=IDS[1], tenant=tenant, tenant_id=tenant.id, first_name="Synthetic", last_name="Customer", email="customer@example.test", phone="+12025550123")
    order = RepairOrder(id=IDS[2], tenant=tenant, tenant_id=tenant.id, customer=customer, vehicle_id=IDS[3], order_number="SYN-0001", status=RepairOrderStatus.PAID)
    order.elis_opportunity_id = IDS[5]
    invoice = Invoice(id=IDS[4], tenant=tenant, tenant_id=tenant.id, repair_order=order, repair_order_id=order.id, invoice_number="SYN-INV-0001", status=InvoiceStatus.PAID, subtotal=Decimal("100"), tax_amount=Decimal("0"), discount_amount=Decimal("0"), total_amount=Decimal("100"), paid_at=NOW, line_items_snapshot={"labor": [{"description": "Synthetic repair", "hours": 1, "total_cost": 100}]})
    return tenant, customer, order, invoice


def native_proof(db, tenant, customer, invoice):
    db.add(InvoiceSettlement(tenant_id=tenant.id, invoice_id=invoice.id, customer_id=customer.id, principal_total=100, legacy_reconciliation_status="native"))


def test_v2_payload_matches_receiver_fixture():
    tenant, customer, order, invoice = resources()
    expected = json.loads((Path(__file__).parent / "fixtures/elis-shop-outcome-v2-paid.json").read_text())
    payload = service.conversion_payload(event_id=UUID(expected["event_id"]), event_type="repair_order.paid", tenant=tenant, invoice=invoice, order=order, customer=customer, occurred_at=NOW)
    assert payload == expected


def test_v1_payload_does_not_gain_v2_fields():
    tenant, customer, order, invoice = resources()
    tenant.paid_invoice_webhook_payload_version = 1
    payload = service.conversion_payload(event_id=uuid4(), event_type="repair_order.paid", tenant=tenant, invoice=invoice, order=order, customer=customer, occurred_at=NOW)
    assert "schema_version" not in payload
    assert "repair_order_uuid" not in payload
    assert "elis_opportunity_id" not in payload["attribution"]


@pytest.mark.parametrize("event_type,delta", [("repair_order.payment_refunded", "-25"), ("repair_order.payment_voided", "-100"), ("repair_order.payment_adjusted", "10")])
def test_v2_corrections_are_deltas_not_replacement_invoice_value(event_type, delta):
    tenant, customer, order, invoice = resources()
    event_id = uuid4()
    payload = service.conversion_payload(event_id=event_id, event_type=event_type, tenant=tenant, invoice=invoice, order=order, customer=customer, occurred_at=NOW, total_amount=Decimal(delta))
    assert payload["amount_semantics"] == "delta"
    assert payload["value_basis"] == "measurement_adjustment"
    assert payload["source_revision"] == str(event_id)
    assert payload["invoice_id"] == str(invoice.id)
    assert payload["total_amount"] == float(delta)


def test_opportunity_reference_is_typed_and_optional():
    assert RepairOrderCreate(customer_id=IDS[1], vehicle_id=IDS[3], elis_opportunity_id=str(IDS[5])).elis_opportunity_id == IDS[5]
    assert RepairOrderUpdate().elis_opportunity_id is None
    with pytest.raises(ValidationError):
        RepairOrderUpdate(elis_opportunity_id="untyped-free-text")


@pytest.mark.asyncio
async def test_paused_delivery_still_captures_once_and_resumes(_db_engine, monkeypatch):
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    async with factory() as db:
        tenant, customer, order, invoice = resources()
        tenant.paid_invoice_webhook_delivery_paused = True
        db.add_all([tenant, customer, order, invoice]); await db.flush()
        native_proof(db, tenant, customer, invoice)
        first = await service.enqueue_paid_invoice_webhook(db, tenant=tenant, invoice=invoice, order=order, customer=customer)
        second = await service.enqueue_paid_invoice_webhook(db, tenant=tenant, invoice=invoice, order=order, customer=customer)
        await db.commit()
        assert first.id == second.id
        assert first.payload["repair_order_uuid"] == str(order.id)
    async def deliver(*_args):
        return "synthetic-receipt", 202
    monkeypatch.setattr(service, "_deliver", deliver)
    paused = await service.process_due_paid_invoice_webhooks(session_factory=factory)
    assert paused["claimed"] == 0
    async with factory() as db:
        tenant = await db.get(Tenant, IDS[0]); tenant.paid_invoice_webhook_delivery_paused = False; await db.commit()
    resumed = await service.process_due_paid_invoice_webhooks(session_factory=factory)
    assert resumed["succeeded"] == 1
    assert (await service.process_due_paid_invoice_webhooks(session_factory=factory))["claimed"] == 0


@pytest.mark.asyncio
async def test_settings_keep_version_and_pause_when_omitted(db_session):
    tenant, customer, order, invoice = resources()
    tenant.paid_invoice_webhook_delivery_paused = True
    user = User(tenant=tenant, email="owner@example.test", hashed_password="x", role=UserRole.GARAGE_OWNER, first_name="Test", last_name="Owner")
    db_session.add_all([tenant, customer, order, invoice, user]); await db_session.commit()
    result = await admin.update_paid_invoice_webhook(admin.PaidInvoiceWebhookUpdateRequest(enabled=True), db=db_session, current_user=user)
    assert result.payload_version == 2
    assert result.delivery_paused is True
    result = await admin.update_paid_invoice_webhook(admin.PaidInvoiceWebhookUpdateRequest(enabled=True, delivery_paused=False, payload_version=1), db=db_session, current_user=user)
    assert result.payload_version == 1
    assert result.delivery_paused is False


def test_settings_reject_unknown_payload_version():
    with pytest.raises(ValidationError):
        admin.PaidInvoiceWebhookUpdateRequest(enabled=False, payload_version=3)


def test_export_opt_in_uses_same_identity_contract():
    tenant, customer, order, invoice = resources()
    payload = conversion_exports._export_item(invoice, order, customer, schema_version=2)
    assert payload["repair_order_uuid"] == str(order.id)
    assert payload["repair_order_id"] == order.order_number
    assert payload["value_basis"] == "invoice_settled"
    assert payload["attribution"]["elis_opportunity_id"] == str(order.elis_opportunity_id)


@pytest.mark.asyncio
async def test_v2_wire_body_is_signed_without_transform(monkeypatch):
    tenant, customer, order, invoice = resources()
    monkeypatch.setattr("app.core.config.settings.PAID_INVOICE_WEBHOOK_ENCRYPTION_KEY", Fernet.generate_key().decode())
    tenant.paid_invoice_webhook_secret_encrypted = encrypt_paid_invoice_webhook_secret("synthetic-shared-secret")
    payload = json.loads((Path(__file__).parent / "fixtures/elis-shop-outcome-v2-paid.json").read_text())
    event = ProviderOutboxEvent(id=UUID(payload["event_id"]), tenant_id=tenant.id, event_type="repair_order.paid", aggregate_type="invoice", aggregate_id=invoice.id, payload=payload, idempotency_key=f"repair-order-paid:{invoice.id}")
    sent = {}
    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return None
        async def request(self, method, url, **kwargs):
            sent.update(kwargs)
            return type("Response", (), {"status_code": 202, "headers": {}})()
    async def destination(*_args, **_kwargs):
        return ResolvedWebhookDestination("https://receiver.example/hook", "receiver.example", "receiver.example", ("93.184.216.34",))
    monkeypatch.setattr(service, "resolve_webhook_destination", destination)
    monkeypatch.setattr(service.httpx, "AsyncClient", lambda **kwargs: Client())
    monkeypatch.setattr(service, "_now", lambda: NOW)
    await service._deliver(tenant, event)
    assert sent["content"] == json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    assert service.verify_conversion_signature(secret="synthetic-shared-secret", timestamp=sent["headers"]["X-DieselBridge-Timestamp"], body=sent["content"], signature=sent["headers"]["X-DieselBridge-Signature"], now=NOW)
    assert sent["headers"]["Idempotency-Key"] == f"repair-order-paid:{invoice.id}"


@pytest.mark.asyncio
async def test_pause_after_claim_preserves_pending_work_and_retry_budget(_db_engine, monkeypatch):
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    async with factory() as db:
        tenant, customer, order, invoice = resources()
        db.add_all([tenant, customer, order, invoice]); await db.flush()
        native_proof(db, tenant, customer, invoice)
        event = await service.enqueue_paid_invoice_webhook(db, tenant=tenant, invoice=invoice, order=order, customer=customer)
        await db.commit()
    original_claim = service._claim
    async def claim_then_pause(db, limit):
        result = await original_claim(db, limit)
        tenant = await db.get(Tenant, IDS[0])
        tenant.paid_invoice_webhook_delivery_paused = True
        await db.commit()
        return result
    monkeypatch.setattr(service, "_claim", claim_then_pause)
    result = await service.process_due_paid_invoice_webhooks(session_factory=factory)
    async with factory() as db:
        stored = await db.get(ProviderOutboxEvent, event.id)
        assert stored.status == "pending"
        assert stored.attempt_count == 0
        assert stored.last_attempt_at is None
        assert stored.lock_token is None
        assert result["paused"] == 1


@pytest.mark.asyncio
async def test_v2_export_rejects_corrupt_cross_tenant_join(client, db_session):
    from app.db.models.conversion_api_key import ConversionApiKey
    import hashlib
    tenant, customer, order, invoice = resources()
    other = Tenant(name="Other shop", slug="other-shop")
    db_session.add(other); await db_session.flush()
    order.tenant = other
    key = ConversionApiKey(tenant=tenant, name="test", key_prefix="dbce_test", key_hash=hashlib.sha256(b"dbce_test").hexdigest())
    db_session.add_all([tenant, customer, order, invoice, key]); await db_session.flush()
    native_proof(db_session, tenant, customer, invoice)
    await db_session.commit()
    response = await client.get("/api/v1/conversion-exports/paid-repair-orders", headers={"X-API-Key": "dbce_test"}, params={"paid_from": "2026-09-22T00:00:00Z", "paid_to": "2026-09-23T00:00:00Z", "schema_version": 2})
    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["total"] == 0


def test_retention_preserves_v2_outcome_identity_but_erases_contact():
    from app.services.conversion_pii_retention_service import redact_conversion_payload
    payload = json.loads((Path(__file__).parent / "fixtures/elis-shop-outcome-v2-paid.json").read_text())
    event = ProviderOutboxEvent(payload=payload)
    redact_conversion_payload(event, redacted_at=NOW)
    assert event.payload["repair_order_uuid"] == payload["repair_order_uuid"]
    assert event.payload["source_revision"] == payload["source_revision"]
    assert event.payload["value_basis"] == "invoice_settled"
    assert "customer" not in event.payload
    assert "attribution" not in event.payload
    assert "service_lines" not in event.payload


@pytest.mark.asyncio
async def test_opportunity_reference_cannot_be_changed_after_invoicing(db_session):
    from fastapi import HTTPException
    from app.api.v1.endpoints.repair_orders import update_repair_order
    tenant, customer, order, invoice = resources()
    user = User(tenant=tenant, email="staff@example.test", hashed_password="x", role=UserRole.GARAGE_OWNER, first_name="Test", last_name="Staff")
    db_session.add_all([tenant, customer, order, invoice, user]); await db_session.commit()
    with pytest.raises(HTTPException) as exc:
        await update_repair_order(order.id, RepairOrderUpdate(elis_opportunity_id=uuid4()), db=db_session, current_user=user)
    assert exc.value.status_code == 409
    assert order.elis_opportunity_id == IDS[5]


@pytest.mark.asyncio
@pytest.mark.parametrize("resource", ["order", "customer", "invoice"])
async def test_enqueue_rejects_cross_tenant_resources(db_session, resource):
    tenant, customer, order, invoice = resources()
    {"order": order, "customer": customer, "invoice": invoice}[resource].tenant_id = uuid4()
    with pytest.raises(ValueError, match="same shop"):
        await service.enqueue_paid_invoice_webhook(db_session, tenant=tenant, invoice=invoice, order=order, customer=customer)


@pytest.mark.asyncio
async def test_enqueue_rejects_invoice_from_different_repair_order(db_session):
    tenant, customer, order, invoice = resources()
    invoice.repair_order_id = uuid4()
    with pytest.raises(ValueError, match="does not belong"):
        await service.enqueue_paid_invoice_webhook(db_session, tenant=tenant, invoice=invoice, order=order, customer=customer)


@pytest.mark.asyncio
async def test_v2_export_csv_and_json_share_stable_identity(client, db_session):
    from app.db.models.conversion_api_key import ConversionApiKey
    import hashlib
    import csv
    import io
    tenant, customer, order, invoice = resources()
    key = ConversionApiKey(tenant=tenant, name="test", key_prefix="dbce_csv", key_hash=hashlib.sha256(b"dbce_csv").hexdigest())
    db_session.add_all([tenant, customer, order, invoice, key]); await db_session.flush()
    native_proof(db_session, tenant, customer, invoice)
    await db_session.commit()
    params = {"paid_from": "2026-09-22T00:00:00Z", "paid_to": "2026-09-23T00:00:00Z", "schema_version": 2}
    response = await client.get("/api/v1/conversion-exports/paid-repair-orders", headers={"X-API-Key": "dbce_csv"}, params=params)
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["repair_order_uuid"] == str(order.id)
    params["format"] = "csv"
    response = await client.get("/api/v1/conversion-exports/paid-repair-orders", headers={"X-API-Key": "dbce_csv"}, params=params)
    assert response.status_code == 200
    row = list(csv.DictReader(io.StringIO(response.text)))[0]
    assert row["repair_order_uuid"] == item["repair_order_uuid"]
    assert row["value_basis"] == item["value_basis"]
    assert json.loads(row["attribution"])["elis_opportunity_id"] == str(order.elis_opportunity_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("proof", ["imported_invoice", "imported_order", "missing", "wrong_tenant", "wrong_customer", "legacy"])
async def test_v2_requires_native_invoice_creation_authority(db_session, proof):
    from app.db.models.invoice_settlement import InvoiceSettlement
    tenant, customer, order, invoice = resources()
    if proof == "imported_invoice": invoice.source = "easy_truck_shop_import"
    if proof == "imported_order": order.source = "easy_truck_shop_import"
    db_session.add_all([tenant, customer, order, invoice]); await db_session.flush()
    if proof != "missing":
        db_session.add(InvoiceSettlement(tenant_id=uuid4() if proof == "wrong_tenant" else tenant.id, invoice_id=invoice.id, customer_id=uuid4() if proof == "wrong_customer" else customer.id, principal_total=100, legacy_reconciliation_status="reconciled" if proof == "legacy" else "native"))
        await db_session.flush()
    event = await service.enqueue_paid_invoice_webhook(db_session, tenant=tenant, invoice=invoice, order=order, customer=customer)
    assert event is None


@pytest.mark.asyncio
async def test_v2_export_counts_excluded_source_snapshots(client, db_session):
    from app.db.models.conversion_api_key import ConversionApiKey
    import hashlib
    tenant, customer, order, invoice = resources()
    invoice.source = "easy_truck_shop_import"
    key = ConversionApiKey(tenant=tenant, name="test", key_prefix="dbce_import", key_hash=hashlib.sha256(b"dbce_import").hexdigest())
    db_session.add_all([tenant, customer, order, invoice, key]); await db_session.commit()
    response = await client.get("/api/v1/conversion-exports/paid-repair-orders", headers={"X-API-Key": "dbce_import"}, params={"paid_from": "2026-09-22T00:00:00Z", "paid_to": "2026-09-23T00:00:00Z", "schema_version": 2})
    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["coverage"] == {"paid_invoice_count": 1, "eligible_native_count": 0, "excluded_native_authority_count": 1}


@pytest.mark.asyncio
async def test_opportunity_reference_stays_locked_after_status_regression(db_session):
    from fastapi import HTTPException
    from app.api.v1.endpoints.repair_orders import update_repair_order
    tenant, customer, order, invoice = resources()
    user = User(tenant=tenant, email="locked@example.test", hashed_password="x", role=UserRole.GARAGE_OWNER, first_name="Test", last_name="Staff")
    db_session.add_all([tenant, customer, order, invoice, user]); await db_session.commit()
    await update_repair_order(order.id, RepairOrderUpdate(status=RepairOrderStatus.COMPLETED), db=db_session, current_user=user)
    with pytest.raises(HTTPException) as exc:
        await update_repair_order(order.id, RepairOrderUpdate(elis_opportunity_id=uuid4()), db=db_session, current_user=user)
    assert exc.value.status_code == 409
    assert invoice.status == InvoiceStatus.PAID
    assert order.elis_opportunity_id == IDS[5]


@pytest.mark.asyncio
async def test_native_cash_confirmation_captures_once_in_same_transaction(db_session, monkeypatch):
    from tests.test_db048_cash import context, pay
    from sqlalchemy import func
    from app.db.models.payment import Payment
    ctx = await context(db_session, monkeypatch)
    tenant, owner, customer, invoice, settlement = ctx
    tenant.paid_invoice_webhook_enabled = True
    tenant.paid_invoice_webhook_payload_version = 2
    tenant.paid_invoice_webhook_url = "https://receiver.example/hook"
    tenant.paid_invoice_webhook_secret_encrypted = "configured"
    await db_session.commit()
    payment_id, _ = await pay(db_session, ctx)
    event = (await db_session.execute(select(ProviderOutboxEvent).where(ProviderOutboxEvent.tenant_id == tenant.id, ProviderOutboxEvent.event_type == "repair_order.paid"))).scalar_one_or_none()
    assert event is not None
    assert event.payload["repair_order_uuid"] == str(invoice.repair_order_id)
    assert event.payload["value_basis"] == "invoice_settled"
    await db_session.rollback()
    assert await db_session.scalar(select(func.count()).select_from(Payment)) == 0
    assert await db_session.scalar(select(func.count()).select_from(ProviderOutboxEvent)) == 0
    for entity in ctx:
        await db_session.refresh(entity)
    await db_session.refresh(invoice, attribute_names=["repair_order"])
    await db_session.refresh(invoice.repair_order, attribute_names=["customer"])
    payment_id, _ = await pay(db_session, ctx)
    await db_session.commit()
    replayed_id, _ = await pay(db_session, ctx)
    assert replayed_id == payment_id
    assert await db_session.scalar(select(func.count()).select_from(ProviderOutboxEvent)) == 1
