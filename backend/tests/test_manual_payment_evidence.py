from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.api.v1.endpoints import payments
from app.api.v1.endpoints.payments import ManualPaymentRequest
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.payment import Payment, PaymentMethod
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle


async def _seed_manual_payment(db_session):
    tenant = Tenant(id=uuid4(), name="Settlement Garage", slug=f"settlement-{uuid4().hex[:8]}")
    customer = Customer(
        id=uuid4(),
        tenant_id=tenant.id,
        first_name="Taylor",
        last_name="Carrier",
        email="billing@example.test",
    )
    vehicle = Vehicle(
        id=uuid4(),
        tenant_id=tenant.id,
        customer_id=customer.id,
        make="Kenworth",
        model="T680",
        year=2023,
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
        total_parts_cost=Decimal("100.00"),
        total_labor_cost=Decimal("0.00"),
        total_cost=Decimal("100.00"),
    )
    invoice = Invoice(
        id=uuid4(),
        tenant_id=tenant.id,
        repair_order_id=order.id,
        invoice_number=f"INV-{uuid4().hex[:8]}",
        status=InvoiceStatus.SENT,
        subtotal=Decimal("100.00"),
        shop_supplies_amount=Decimal("0.00"),
        service_fee_amount=Decimal("3.00"),
        tax_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("103.00"),
    )
    db_session.add_all([tenant, customer, vehicle, manager, order, invoice])
    await db_session.commit()
    return invoice, order, manager


def _stub_payment_side_effects(monkeypatch):
    async def no_op(**_kwargs):
        return None

    async def payment_number(_db, _tenant_id):
        return f"PMT-{uuid4().hex[:8]}"

    monkeypatch.setattr(payments, "allocate_next_payment_number", payment_number)
    monkeypatch.setattr(payments, "broadcast_payment_received", no_op)
    monkeypatch.setattr(payments, "broadcast_repair_order_update", no_op)
    monkeypatch.setattr(payments, "send_invoice_payment_confirmation_email", no_op)
    monkeypatch.setattr(payments, "record_payment", lambda **_kwargs: None)


@pytest.mark.asyncio
async def test_ach_requires_reference_before_invoice_is_marked_paid(db_session):
    invoice, order, manager = await _seed_manual_payment(db_session)

    with pytest.raises(HTTPException) as exc:
        await payments.record_manual_payment(
            body=ManualPaymentRequest(invoice_id=invoice.id, method="ach"),
            db=db_session,
            current_user=manager,
        )

    assert exc.value.status_code == 422
    assert "bank trace" in exc.value.detail
    assert (await db_session.get(Invoice, invoice.id)).status == InvoiceStatus.SENT
    assert (await db_session.get(RepairOrder, order.id)).status == RepairOrderStatus.INVOICED


@pytest.mark.asyncio
async def test_ach_confirmation_persists_bank_reference(db_session, monkeypatch):
    invoice, order, manager = await _seed_manual_payment(db_session)
    _stub_payment_side_effects(monkeypatch)

    await payments.record_manual_payment(
        body=ManualPaymentRequest(
            invoice_id=invoice.id,
            method="ach",
            reference_number="ACH-TRACE-8472",
            notes="Verified in operating account",
        ),
        db=db_session,
        current_user=manager,
    )

    payment = (await db_session.execute(select(Payment).where(Payment.invoice_id == invoice.id))).scalar_one()
    assert payment.method == PaymentMethod.ACH
    assert payment.reference_number == "ACH-TRACE-8472"
    assert payment.notes == "Verified in operating account"
    assert payment.amount == Decimal("100.00")
    assert (await db_session.get(Invoice, invoice.id)).status == InvoiceStatus.PAID
    assert (await db_session.get(RepairOrder, order.id)).status == RepairOrderStatus.PAID


@pytest.mark.asyncio
async def test_fleet_payment_requires_and_persists_authorization_evidence(db_session, monkeypatch):
    invoice, _, manager = await _seed_manual_payment(db_session)

    with pytest.raises(HTTPException) as exc:
        await payments.record_manual_payment(
            body=ManualPaymentRequest(
                invoice_id=invoice.id,
                method="fleet_payment",
                payment_provider="EFS",
                reference_number="EFS-99221",
            ),
            db=db_session,
            current_user=manager,
        )
    assert exc.value.status_code == 422
    assert "authorization" in exc.value.detail.lower()

    _stub_payment_side_effects(monkeypatch)
    await payments.record_manual_payment(
        body=ManualPaymentRequest(
            invoice_id=invoice.id,
            method="fleet_payment",
            payment_provider="EFS",
            reference_number="EFS-99221",
            authorization_number="AUTH-44109",
        ),
        db=db_session,
        current_user=manager,
    )

    payment = (await db_session.execute(select(Payment).where(Payment.invoice_id == invoice.id))).scalar_one()
    assert payment.method == PaymentMethod.FLEET_PAYMENT
    assert payment.payment_provider == "EFS"
    assert payment.reference_number == "EFS-99221"
    assert payment.authorization_number == "AUTH-44109"
