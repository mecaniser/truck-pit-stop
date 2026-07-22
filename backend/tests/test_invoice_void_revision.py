from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.v1.endpoints.invoices import (
    InvoiceVoidRequest,
    auto_create_invoice_for_order,
    void_invoice,
)
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.repair_order_history import RepairOrderHistoryEvent
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle


async def _seed_invoice(db_session, *, pending_zelle: bool = False):
    tenant = Tenant(
        id=uuid4(),
        name="Revision Garage",
        slug=f"revision-{uuid4().hex[:8]}",
        labor_rate=Decimal("100.00"),
        sales_tax_rate=Decimal("0.00"),
        shop_supplies_rate=Decimal("0.00"),
        service_fee_rate=Decimal("0.00"),
    )
    customer = Customer(
        id=uuid4(),
        tenant_id=tenant.id,
        first_name="Alex",
        last_name="Fleet",
        email="alex@example.test",
    )
    vehicle = Vehicle(
        id=uuid4(),
        tenant_id=tenant.id,
        customer_id=customer.id,
        year=2022,
        make="Freightliner",
        model="Cascadia",
    )
    manager = User(
        id=uuid4(),
        tenant_id=tenant.id,
        email="manager@example.test",
        hashed_password="x",
        first_name="Morgan",
        last_name="Manager",
        role=UserRole.GARAGE_ADMIN,
        is_active=True,
        is_verified=True,
    )
    order = RepairOrder(
        id=uuid4(),
        tenant_id=tenant.id,
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        order_number=f"RO-{uuid4().hex[:8]}",
        status=RepairOrderStatus.INVOICED,
        total_parts_cost=Decimal("0.00"),
        total_labor_cost=Decimal("40.00"),
        total_cost=Decimal("40.00"),
        pricing_locked_at=datetime.now(timezone.utc),
        pricing_lock_reason="invoice_finalized",
    )
    invoice = Invoice(
        id=uuid4(),
        tenant_id=tenant.id,
        repair_order_id=order.id,
        invoice_number=f"INV-{uuid4().hex[:8]}",
        status=InvoiceStatus.SENT,
        subtotal=Decimal("40.00"),
        shop_supplies_amount=Decimal("0.00"),
        service_fee_amount=Decimal("0.00"),
        tax_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("40.00"),
        zelle_pending_submitted_at=datetime.now(timezone.utc) if pending_zelle else None,
    )
    db_session.add_all([tenant, customer, vehicle, manager, order, invoice])
    await db_session.commit()
    return tenant, order, invoice, manager


@pytest.mark.asyncio
async def test_void_preserves_invoice_and_replacement_supersedes_it(db_session, monkeypatch):
    tenant, order, invoice, manager = await _seed_invoice(db_session)

    async def no_op(**_kwargs):
        return None

    monkeypatch.setattr(
        "app.api.v1.endpoints.invoices.broadcast_repair_order_update",
        no_op,
    )

    response = await void_invoice(
        invoice_id=invoice.id,
        body=InvoiceVoidRequest(reason="Labor entry needs correction"),
        db=db_session,
        current_user=manager,
    )

    assert response.status == InvoiceStatus.CANCELLED.value
    stored_invoice = await db_session.get(Invoice, invoice.id)
    stored_order = await db_session.get(RepairOrder, order.id)
    assert stored_invoice is not None
    assert stored_invoice.status == InvoiceStatus.CANCELLED
    assert stored_invoice.voided_by_user_id == manager.id
    assert stored_invoice.void_reason == "Labor entry needs correction"
    assert stored_invoice.voided_at is not None
    assert stored_order.status == RepairOrderStatus.PENDING_REVIEW
    assert stored_order.pricing_locked_at is None
    assert stored_order.pricing_lock_reason is None

    history = (await db_session.execute(
        select(RepairOrderHistoryEvent).where(
            RepairOrderHistoryEvent.repair_order_id == order.id,
            RepairOrderHistoryEvent.event_type == "invoice_voided",
        )
    )).scalar_one()
    assert invoice.invoice_number in history.detail
    assert "Labor entry needs correction" in history.detail

    loaded_order = (await db_session.execute(
        select(RepairOrder)
        .where(RepairOrder.id == order.id)
        .options(selectinload(RepairOrder.customer), selectinload(RepairOrder.vehicle))
    )).scalar_one()
    replacement = await auto_create_invoice_for_order(
        db=db_session,
        order=loaded_order,
        tenant=tenant,
        created_by_user_id=manager.id,
        notify=False,
    )

    assert replacement is not None
    assert replacement.id != invoice.id
    assert replacement.supersedes_invoice_id == invoice.id
    invoices = (await db_session.execute(
        select(Invoice).where(Invoice.repair_order_id == order.id)
    )).scalars().all()
    assert len(invoices) == 2
    assert sum(item.status != InvoiceStatus.CANCELLED for item in invoices) == 1


@pytest.mark.asyncio
async def test_void_is_blocked_while_zelle_confirmation_is_pending(db_session):
    _, order, invoice, manager = await _seed_invoice(db_session, pending_zelle=True)

    with pytest.raises(HTTPException) as exc:
        await void_invoice(
            invoice_id=invoice.id,
            body=InvoiceVoidRequest(reason="Need to revise pricing"),
            db=db_session,
            current_user=manager,
        )

    assert exc.value.status_code == 409
    assert "Zelle" in exc.value.detail
    assert (await db_session.get(Invoice, invoice.id)).status == InvoiceStatus.SENT
    assert (await db_session.get(RepairOrder, order.id)).status == RepairOrderStatus.INVOICED


@pytest.mark.asyncio
async def test_void_requires_manager_role(db_session):
    _, order, invoice, manager = await _seed_invoice(db_session)
    manager.role = UserRole.RECEPTIONIST

    with pytest.raises(HTTPException) as exc:
        await void_invoice(
            invoice_id=invoice.id,
            body=InvoiceVoidRequest(reason="Need to revise pricing"),
            db=db_session,
            current_user=manager,
        )

    assert exc.value.status_code == 403
    assert (await db_session.get(Invoice, invoice.id)).status == InvoiceStatus.SENT
    assert (await db_session.get(RepairOrder, order.id)).status == RepairOrderStatus.INVOICED


@pytest.mark.asyncio
async def test_paid_invoice_requires_refund_or_credit_instead_of_void(db_session):
    _, order, invoice, manager = await _seed_invoice(db_session)
    invoice.status = InvoiceStatus.PAID
    invoice.paid_at = datetime.now(timezone.utc)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await void_invoice(
            invoice_id=invoice.id,
            body=InvoiceVoidRequest(reason="Need to revise pricing"),
            db=db_session,
            current_user=manager,
        )

    assert exc.value.status_code == 409
    assert "refund or credit note" in exc.value.detail
    assert (await db_session.get(Invoice, invoice.id)).status == InvoiceStatus.PAID
    assert (await db_session.get(RepairOrder, order.id)).status == RepairOrderStatus.INVOICED
