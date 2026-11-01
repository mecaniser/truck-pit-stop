"""Historical deduplication artifacts are recognized only by the display reader."""
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from uuid import uuid4
from types import SimpleNamespace as NS

import pytest
from sqlalchemy import event, select
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.payment import Payment, PaymentMethod, PaymentStatus
from app.db.models.user import UserRole
from app.services import imported_billing as billing
from app.services.ets_source_evidence import _digest
from test_db139_shared_billing import seed


async def retired_fixture(db, monkeypatch, paid="534.41"):
    orders, inv, envelope = await seed(db, monkeypatch, paid)
    now = datetime.now(timezone.utc)
    copy = Invoice(id=uuid4(), tenant_id=inv.tenant_id, repair_order_id=orders[1].id,
        invoice_number=inv.invoice_number + "-" + orders[1].order_number,
        source=billing.SOURCE, status=InvoiceStatus.CANCELLED,
        subtotal=inv.subtotal, tax_amount=0, total_amount=inv.total_amount,
        deleted_at=now, updated_at=now, void_reason=billing._LEGACY_VOID_REASON)
    payment = Payment(id=uuid4(), tenant_id=inv.tenant_id, invoice_id=copy.id,
        payment_number="RETIRED-1", amount=Decimal("534.41"), method=PaymentMethod.CASH,
        source=billing.SOURCE, status=PaymentStatus.FAILED, deleted_at=now, updated_at=now)
    db.add_all([copy, payment]); await db.flush()
    return orders, inv, copy, payment, envelope


@pytest.mark.asyncio
@pytest.mark.parametrize("paid,status", [("534.41", "paid"), ("100.01", "partially_paid"), ("0.00", "unpaid")])
async def test_verified_retired_copies_share_without_writes(db_session, monkeypatch, paid, status):
    orders, inv, copy, payment, _ = await retired_fixture(db_session, monkeypatch, paid)
    before = (copy.status, copy.deleted_at, payment.status, payment.amount)
    statements = []
    def record(_conn, _cursor, statement, *_): statements.append(statement)
    event.listen(db_session.bind.sync_engine, "before_cursor_execute", record)
    try:
        await billing.attach_imported_invoice_totals(db_session, [orders[2]], NS(tenant_id=inv.tenant_id,role=UserRole.GARAGE_OWNER))
        assert len(statements) <= 5
        result = await billing.load_imported_billing(db_session, orders[1])
        assert result == orders[2].imported_billing
        assert result.payment_status == status and result.shared_invoice
        assert result.invoice_id == inv.id and result.invoice_repair_order_id == orders[0].id
        assert result.recorded_remaining_amount == Decimal("534.41")-Decimal(paid)
        assert all(s.lstrip().startswith("SELECT") for s in statements)
    finally: event.remove(db_session.bind.sync_engine, "before_cursor_execute", record)
    assert before == (copy.status, copy.deleted_at, payment.status, payment.amount)
    assert billing.supported_invoice([inv, copy])[1] == "deleted_invoice_evidence"


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["reason", "name", "total", "billto", "native_copy", "not_cancelled",
    "copy_source_evidence", "copy_provider", "copy_revision", "copy_actor", "internal",
    "copy_time", "payment_time", "payment_live", "payment_native", "payment_refund", "payment_provider",
    "payment_zero", "payment_negative", "payment_attempt", "vehicle", "customer", "deleted_order",
    "native_order", "stale", "source_bad_payment", "canonical_deleted_payment", "source_missing"])
async def test_uncertain_artifact_keeps_original_hold(db_session, monkeypatch, case):
    orders, inv, copy, payment, env = await retired_fixture(db_session, monkeypatch)
    if case == "reason": copy.void_reason = "Customer cancelled"
    elif case == "name": copy.invoice_number = "ETSINV-other"
    elif case == "total": copy.total_amount += 1
    elif case == "billto": copy.billed_customer_id = uuid4()
    elif case == "native_copy": copy.source = None
    elif case == "not_cancelled": copy.status = InvoiceStatus.PAID
    elif case == "copy_source_evidence":
        async def with_copy(*_): return {inv.id: env, copy.id: {"unexpected": True}}
        monkeypatch.setattr(billing, "_source_evidence", with_copy)
    elif case == "copy_provider": copy.quickbooks_invoice_id = "external"
    elif case == "copy_revision": copy.supersedes_invoice_id = inv.id
    elif case == "copy_actor": copy.created_by_user_id = uuid4()
    elif case == "internal": copy.is_internal = True
    elif case == "copy_time": copy.updated_at += timedelta(seconds=1)
    elif case == "payment_time": payment.deleted_at += timedelta(seconds=1)
    elif case == "payment_live": payment.deleted_at = None
    elif case == "payment_native": payment.source = None
    elif case == "payment_refund": payment.quickbooks_refund_id = "refund"
    elif case == "payment_provider": payment.payment_provider = "quickbooks"
    elif case == "payment_zero": payment.amount = Decimal("0")
    elif case == "payment_negative": payment.amount = Decimal("-1")
    elif case == "payment_attempt": payment.invoice_payment_attempt_id = uuid4()
    elif case == "vehicle": orders[1].vehicle_id = uuid4()
    elif case == "customer": orders[1].customer_id = uuid4()
    elif case == "deleted_order": orders[1].deleted_at = datetime.now(timezone.utc)
    elif case == "native_order": orders[1].source = None
    elif case == "canonical_deleted_payment":
        canonical_payment = (await db_session.scalars(select(Payment).where(Payment.invoice_id == inv.id))).one()
        canonical_payment.deleted_at = datetime.now(timezone.utc)
    elif case == "source_missing":
        async def missing(*_): return {}
        monkeypatch.setattr(billing, "_source_evidence", missing)
    else:
        facts = env["observations"][0]["evidence"]
        if case == "stale": facts["observed_at_source"] = (datetime.now(timezone.utc)-timedelta(days=2)).isoformat()
        elif case == "source_bad_payment": facts["payment_lines"][0]["payment"]["canceled"]=True
        env["observations"][0]["sha256"] = _digest(facts)
    # Disable autoflush: corrupted cross-tenant/FK fixtures model hostile evidence,
    # rather than writing impossible foreign keys into the fixture database.
    with db_session.no_autoflush:
        result = await billing.load_imported_billing(db_session, orders[2])
    assert result.total_amount is None and result.payment_status == "unverified"


@pytest.mark.asyncio
@pytest.mark.parametrize("blocked", [True, False])
async def test_native_financial_reference_blocks_retirement(db_session, monkeypatch, blocked):
    orders, inv, copy, payment, _ = await retired_fixture(db_session, monkeypatch)
    async def refs(_db, tenant, ids):
        assert tenant == inv.tenant_id and ids == [copy.id]
        return {copy.id} if blocked else {uuid4()}
    monkeypatch.setattr(billing, "_retired_reference_ids", refs)
    result = await billing.load_imported_billing(db_session, orders[2])
    assert (result.total_amount is None) == blocked


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["reverse_revision", "settlement", "accounting_payment", "accounting_invoice", "foreign_accounting"])
async def test_real_financial_references_and_tenant_isolation(db_session, monkeypatch, kind):
    from app.db.models.invoice_settlement import InvoiceSettlement, PaymentAccountingLink
    orders, inv, copy, payment, _ = await retired_fixture(db_session, monkeypatch)
    if kind == "reverse_revision":
        inv.supersedes_invoice_id = copy.id
    elif kind == "settlement":
        db_session.add(InvoiceSettlement(id=uuid4(), tenant_id=inv.tenant_id,
            invoice_id=copy.id, customer_id=orders[0].customer_id, principal_total=copy.total_amount))
    else:
        db_session.add(PaymentAccountingLink(id=uuid4(),
            tenant_id=uuid4() if kind == "foreign_accounting" else inv.tenant_id,
            invoice_id=None, financial_object_type="payment", financial_object_id=(copy.id if kind == "accounting_invoice" else payment.id),
            owning_writer="dieselbridge"))
    await db_session.flush()
    result = await billing.load_imported_billing(db_session, orders[2])
    assert (result.total_amount is None) == (kind != "foreign_accounting")


@pytest.mark.asyncio
async def test_copy_on_owner_and_extra_active_invoice_stay_held(db_session, monkeypatch):
    orders, inv, copy, _, _ = await retired_fixture(db_session, monkeypatch)
    copy.repair_order_id = inv.repair_order_id
    copy.invoice_number = inv.invoice_number + "-" + orders[0].order_number
    with db_session.no_autoflush:
        assert (await billing.load_imported_billing(db_session, orders[2])).total_amount is None
    copy.repair_order_id = orders[1].id
    copy.invoice_number = inv.invoice_number + "-" + orders[1].order_number
    db_session.add(Invoice(id=uuid4(), tenant_id=inv.tenant_id, repair_order_id=orders[2].id,
        invoice_number="ETSINV-second",source=billing.SOURCE,status=InvoiceStatus.PAID,
        subtotal=1,tax_amount=0,total_amount=1))
    await db_session.flush()
    assert (await billing.load_imported_billing(db_session, orders[2])).total_amount is None
