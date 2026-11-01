"""Shared ETS billing is display context, never another invoice or receivable."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace as NS
from uuid import uuid4

import pytest
from sqlalchemy import event, select

from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.payment import Payment, PaymentMethod, PaymentStatus
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.user import UserRole
from app.db.models.vehicle import Vehicle
from app.services import imported_billing as billing
from app.services.ets_source_evidence import _digest
from test_db139_imported_billing import snapshot_fixture


async def seed(db, monkeypatch, paid="534.41", owner_suffix=False):
    tenant = Tenant(id=uuid4(), name="Synthetic ETS shop", slug=uuid4().hex)
    customer = Customer(id=uuid4(), tenant_id=tenant.id, first_name="Fixture", last_name="Customer", email="fixture@example.test")
    vehicle = Vehicle(id=uuid4(), tenant_id=tenant.id, customer_id=customer.id, make="Fixture", model="Truck")
    orders = [RepairOrder(id=uuid4(), tenant_id=tenant.id, customer_id=customer.id,
        vehicle_id=vehicle.id, order_number="ETS-7001-8002" + suffix, source=billing.SOURCE,
        status=RepairOrderStatus.COMPLETED) for suffix in ("", "-2", "-3")]
    owner = orders[1 if owner_suffix else 0]
    inv = Invoice(id=uuid4(), tenant_id=tenant.id, repair_order_id=owner.id,
        invoice_number="ETSINV-9001", source=billing.SOURCE,
        status=InvoiceStatus.PAID if paid == "534.41" else InvoiceStatus.SENT,
        subtotal=Decimal("534.41"), tax_amount=0, total_amount=Decimal("534.41"))
    db.add_all([tenant, customer, vehicle, *orders, inv])
    if Decimal(paid):
        db.add(Payment(id=uuid4(), tenant_id=tenant.id, invoice_id=inv.id, source=billing.SOURCE,
            payment_number="ETSPAY-1", amount=Decimal(paid), method=PaymentMethod.CASH, status=PaymentStatus.COMPLETED))
    await db.flush()
    _, _, envelope = snapshot_fixture(invoice_status="10" if paid == "534.41" else "5",
        balance={"amount":str(Decimal("534.41") - Decimal(paid)), "currency":"USD"})
    facts = envelope["observations"][0]["evidence"]
    if Decimal(paid):
        facts["payment_lines"][0]["amount"]["amount"] = paid
    else:
        facts["payment_lines"] = []
    envelope["observations"][0]["sha256"] = _digest(facts)
    async def evidence(_db, tenant_id, invoice_ids):
        if inv.id in invoice_ids:
            assert tenant_id == tenant.id
            return {inv.id: envelope}
        return {}
    monkeypatch.setattr(billing, "_source_evidence", evidence)
    monkeypatch.setattr(billing, "trusted_shop_binding", lambda _: ("shop1", None))
    return orders, inv, envelope


@pytest.mark.asyncio
@pytest.mark.parametrize("paid,status", [("534.41", "paid"), ("100.01", "partially_paid"), ("0.00", "unpaid")])
@pytest.mark.parametrize("owner_suffix", [False, True])
async def test_shared_status_offpage_owner_and_no_financial_writes(db_session, monkeypatch, paid, status, owner_suffix):
    orders, inv, _ = await seed(db_session, monkeypatch, paid, owner_suffix)
    before = [(i.id, i.repair_order_id, i.total_amount, i.status) for i in (await db_session.scalars(select(Invoice))).all()]
    payments_before = [(p.id, p.amount, p.status) for p in (await db_session.scalars(select(Payment))).all()]
    statements = []
    def record(_conn, _cursor, statement, *_):
        statements.append(statement)
    event.listen(db_session.bind.sync_engine, "before_cursor_execute", record)
    try:
        # Only the final operation is on this page; its owner must still resolve.
        actor = NS(tenant_id=orders[0].tenant_id, role=UserRole.GARAGE_OWNER)
        await billing.attach_imported_invoice_totals(db_session, [orders[2]], actor)
        assert len(statements) <= 4
        for order in orders:
            result = await billing.load_imported_billing(db_session, order)
            assert result.payment_status == status
            assert result.invoice_id == inv.id and result.shared_invoice
            assert result.invoice_repair_order_id == inv.repair_order_id
            assert result.recorded_remaining_amount == Decimal("534.41") - Decimal(paid)
            assert result.recorded_completed_amount == Decimal(paid)
        assert orders[2].imported_billing == result
        assert all(statement.lstrip().startswith("SELECT") for statement in statements)
    finally:
        event.remove(db_session.bind.sync_engine, "before_cursor_execute", record)
    assert before == [(i.id, i.repair_order_id, i.total_amount, i.status) for i in (await db_session.scalars(select(Invoice))).all()]
    assert payments_before == [(p.id, p.amount, p.status) for p in (await db_session.scalars(select(Payment))).all()]


@pytest.mark.asyncio
@pytest.mark.parametrize("conflict", ["deleted_order", "native_order", "duplicate_invoice", "deleted_invoice", "native_invoice", "bill_to"])
async def test_conflicting_group_holds_every_member(db_session, monkeypatch, conflict):
    orders, inv, _ = await seed(db_session, monkeypatch)
    if conflict == "deleted_order": orders[2].deleted_at = datetime.now(timezone.utc)
    if conflict == "native_order": orders[2].source = None
    if conflict == "deleted_invoice": inv.deleted_at = datetime.now(timezone.utc)
    if conflict == "native_invoice": inv.source = None
    if conflict == "bill_to": inv.billed_customer_id = uuid4()
    if conflict == "duplicate_invoice":
        db_session.add(Invoice(id=uuid4(), tenant_id=inv.tenant_id, repair_order_id=orders[2].id,
            invoice_number="ETSINV-9002", source=billing.SOURCE, status=InvoiceStatus.PAID,
            subtotal=534, tax_amount=0, total_amount=534))
    await db_session.flush()
    for order in orders[:2]:
        result = await billing.load_imported_billing(db_session, order)
        assert result.payment_status == "unverified"
        assert result.total_amount is None and result.recorded_remaining_amount is None
        assert result.invoice_id is None and result.review_reasons


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["stale", "missing", "refund"])
async def test_shared_context_preserves_evidence_holds(db_session, monkeypatch, state):
    orders, inv, envelope = await seed(db_session, monkeypatch)
    if state == "stale":
        row = envelope["observations"][0]
        row["evidence"]["observed_at_source"] = (datetime.now(timezone.utc)-timedelta(hours=25)).isoformat()
        row["sha256"] = _digest(row["evidence"])
    if state == "missing":
        async def empty(*_): return {}
        monkeypatch.setattr(billing, "_source_evidence", empty)
    if state == "refund":
        payment = (await db_session.scalars(select(Payment))).one()
        payment.status = PaymentStatus.REFUNDED
        await db_session.flush()
    result = await billing.load_imported_billing(db_session, orders[2])
    assert result.shared_invoice and result.invoice_id == inv.id
    assert result.payment_status == "unverified" and result.recorded_remaining_amount is None


@pytest.mark.asyncio
@pytest.mark.parametrize("number", ["ETS-7001-80020", "ETS-7001-8002x", "ETS-7001-8002-2-extra", "ETS-7001-8003"])
async def test_prefix_or_customer_collision_does_not_borrow(db_session, monkeypatch, number):
    orders, inv, _ = await seed(db_session, monkeypatch)
    outsider = RepairOrder(id=uuid4(), tenant_id=inv.tenant_id, customer_id=orders[0].customer_id,
        vehicle_id=orders[0].vehicle_id, order_number=number, source=billing.SOURCE,
        status=RepairOrderStatus.COMPLETED)
    db_session.add(outsider)
    await db_session.flush()
    result = await billing.load_imported_billing(db_session, outsider)
    assert result.invoice_id is None and result.payment_status == "unverified"
    assert (await billing.load_imported_billing(db_session, orders[2])).payment_status == "paid"


@pytest.mark.asyncio
async def test_foreign_tenant_same_job_cannot_supply_invoice(db_session, monkeypatch):
    orders, inv, _ = await seed(db_session, monkeypatch)
    foreign = Tenant(id=uuid4(), name="Other fixture shop", slug=uuid4().hex)
    db_session.add(foreign)
    outsider = RepairOrder(id=uuid4(), tenant_id=foreign.id, customer_id=orders[0].customer_id,
        vehicle_id=orders[0].vehicle_id, order_number="ETS-7001-8002-4", source=billing.SOURCE,
        status=RepairOrderStatus.COMPLETED)
    db_session.add(outsider)
    await db_session.flush()
    result = await billing.load_imported_billing(db_session, outsider)
    assert result.invoice_id is None and result.payment_status == "unverified"
    assert (await billing.load_imported_billing(db_session, orders[2])).payment_status == "paid"


@pytest.mark.asyncio
async def test_real_paginated_endpoint_serializes_shared_context(db_session, monkeypatch):
    import json
    from app.api.v1.endpoints.repair_orders import list_repair_orders, get_imported_billing
    orders, inv, _ = await seed(db_session, monkeypatch, "100.01", True)
    actor = NS(id=uuid4(), tenant_id=inv.tenant_id, role=UserRole.GARAGE_OWNER)
    response = await list_repair_orders(customer_id=None, vehicle_id=None, status=None,
        search=None, deleted=False, overdue=False, skip=0, limit=1, paginated=True,
        db=db_session, current_user=actor)
    payload = json.loads(response.body)
    assert payload["total"] == 3
    row = payload["items"][0]
    assert row["imported_billing"]["invoice_id"] == str(inv.id)
    assert row["imported_billing"]["payment_status"] == "partially_paid"
    assert row["imported_billing"]["recorded_remaining_amount"] == "434.40"
    assert row["imported_billing"]["shared_invoice"] is True
    detail = await get_imported_billing(orders[2].id, db_session, actor)
    assert detail.model_dump(mode="json") == row["imported_billing"]


@pytest.mark.asyncio
@pytest.mark.parametrize("owner_suffix", [False, True])
@pytest.mark.parametrize("identity", ["vehicle_id", "customer_id"])
async def test_identity_conflict_preserves_only_direct_partial_invoice_owner(db_session, monkeypatch, owner_suffix, identity):
    orders, inv, _ = await seed(db_session, monkeypatch, "100.01", owner_suffix)
    owner = next(order for order in orders if order.id == inv.repair_order_id)
    setattr(orders[2], identity, uuid4())
    await db_session.flush()
    actor = NS(tenant_id=inv.tenant_id, role=UserRole.GARAGE_OWNER)
    await billing.attach_imported_invoice_totals(db_session, orders, actor)
    for order in orders:
        result = await billing.load_imported_billing(db_session, order)
        assert result == order.imported_billing
        assert not result.shared_invoice and result.review_required
        assert "shared_job_identity_conflict" in result.review_reasons
        if order.id == owner.id:
            assert result.invoice_id == inv.id
            assert result.invoice_repair_order_id == owner.id
            assert result.payment_status == "partially_paid"
            assert result.recorded_remaining_amount == Decimal("434.40")
        else:
            # Even the sibling whose identity agrees with owner cannot borrow.
            assert result.invoice_id is None and result.total_amount is None
            assert result.payment_status == "unverified"
            assert result.recorded_remaining_amount is None


@pytest.mark.asyncio
@pytest.mark.parametrize("conflict", ["duplicate", "deleted", "mixed", "refund", "stale", "bill_to", "native_order", "deleted_order"])
async def test_direct_owner_preservation_never_bypasses_other_holds(db_session, monkeypatch, conflict):
    orders, inv, envelope = await seed(db_session, monkeypatch, "100.01")
    orders[2].vehicle_id = uuid4()
    if conflict in {"duplicate", "deleted", "mixed"}:
        db_session.add(Invoice(id=uuid4(), tenant_id=inv.tenant_id, repair_order_id=orders[2].id,
            invoice_number="ETSINV-9002", source=None if conflict == "mixed" else billing.SOURCE,
            status=InvoiceStatus.PAID if conflict == "duplicate" else InvoiceStatus.CANCELLED,
            deleted_at=datetime.now(timezone.utc) if conflict == "deleted" else None,
            subtotal=100, tax_amount=0, total_amount=100))
    if conflict == "refund":
        payment = (await db_session.scalars(select(Payment))).one()
        payment.status = PaymentStatus.REFUNDED
    if conflict == "stale":
        row = envelope["observations"][0]
        row["evidence"]["observed_at_source"] = (datetime.now(timezone.utc)-timedelta(hours=25)).isoformat()
        row["sha256"] = _digest(row["evidence"])
    if conflict == "bill_to": inv.billed_customer_id = uuid4()
    if conflict == "native_order": orders[2].source = None
    if conflict == "deleted_order": orders[2].deleted_at = datetime.now(timezone.utc)
    await db_session.flush()
    for order in orders[:2]:
        result = await billing.load_imported_billing(db_session, order)
        assert result.payment_status == "unverified" and result.recorded_remaining_amount is None
        assert not result.shared_invoice
        if conflict not in {"refund", "stale"} or order.id != inv.repair_order_id:
            assert result.invoice_id is None and result.total_amount is None


@pytest.mark.asyncio
@pytest.mark.parametrize("identity", ["customer_id", "vehicle_id"])
async def test_direct_owner_requires_its_own_nonnull_identity(db_session, monkeypatch, identity):
    orders, inv, _ = await seed(db_session, monkeypatch, "100.01")
    # Exercise historical malformed identity without writing a database-invalid row.
    with db_session.no_autoflush:
        setattr(orders[0], identity, None)
        result = await billing.load_imported_billing(db_session, orders[0])
    assert result.invoice_id is None and result.total_amount is None
    assert result.payment_status == "unverified"
    assert result.review_reasons == ["source_identity_unavailable"]
