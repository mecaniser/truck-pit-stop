from decimal import Decimal
from uuid import uuid4

import pytest

from app.api.v1.endpoints.customers import get_customer_balances, get_customer_vehicle_balances
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.payment import Payment, PaymentMethod, PaymentStatus
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.vehicle import Vehicle


@pytest.mark.asyncio
async def test_balances_exclude_cancelled_invoices_and_incomplete_payments(db_session):
    tenant = Tenant(id=uuid4(), name="Balance Garage", slug=f"balance-{uuid4().hex[:8]}")
    customer = Customer(
        id=uuid4(), tenant_id=tenant.id, first_name="Elis", last_name="Logistics",
        company_name="ELIS LOGISTICS LLC", email=f"elis-{uuid4().hex[:6]}@example.com",
    )
    due_vehicle = Vehicle(
        id=uuid4(), tenant_id=tenant.id, customer_id=customer.id,
        make="Volvo", model="VNR", unit_number="603",
    )
    credit_vehicle = Vehicle(
        id=uuid4(), tenant_id=tenant.id, customer_id=customer.id,
        make="Volvo", model="VNR", unit_number="609",
    )
    db_session.add_all([tenant, customer, due_vehicle, credit_vehicle])
    await db_session.flush()

    due_order = RepairOrder(
        id=uuid4(), tenant_id=tenant.id, customer_id=customer.id, vehicle_id=due_vehicle.id,
        order_number=f"RO-{uuid4().hex[:8]}", status=RepairOrderStatus.INVOICED,
    )
    cancelled_order = RepairOrder(
        id=uuid4(), tenant_id=tenant.id, customer_id=customer.id, vehicle_id=due_vehicle.id,
        order_number=f"RO-{uuid4().hex[:8]}", status=RepairOrderStatus.CANCELLED,
    )
    credit_order = RepairOrder(
        id=uuid4(), tenant_id=tenant.id, customer_id=customer.id, vehicle_id=credit_vehicle.id,
        order_number=f"RO-{uuid4().hex[:8]}", status=RepairOrderStatus.INVOICED,
    )
    db_session.add_all([due_order, cancelled_order, credit_order])
    await db_session.flush()

    due_invoice = Invoice(
        id=uuid4(), tenant_id=tenant.id, repair_order_id=due_order.id,
        invoice_number=f"INV-{uuid4().hex[:8]}", status=InvoiceStatus.SENT,
        subtotal=Decimal("100.00"), total_amount=Decimal("100.00"),
    )
    cancelled_invoice = Invoice(
        id=uuid4(), tenant_id=tenant.id, repair_order_id=cancelled_order.id,
        invoice_number=f"INV-{uuid4().hex[:8]}", status=InvoiceStatus.CANCELLED,
        subtotal=Decimal("999.00"), total_amount=Decimal("999.00"),
    )
    credit_invoice = Invoice(
        id=uuid4(), tenant_id=tenant.id, repair_order_id=credit_order.id,
        invoice_number=f"INV-{uuid4().hex[:8]}", status=InvoiceStatus.SENT,
        subtotal=Decimal("40.00"), total_amount=Decimal("40.00"),
    )
    db_session.add_all([due_invoice, cancelled_invoice, credit_invoice])
    await db_session.flush()

    db_session.add_all([
        Payment(
            id=uuid4(), tenant_id=tenant.id, invoice_id=due_invoice.id,
            payment_number=f"PAY-{uuid4().hex[:8]}", amount=Decimal("25.00"),
            method=PaymentMethod.CASH, status=PaymentStatus.COMPLETED,
        ),
        Payment(
            id=uuid4(), tenant_id=tenant.id, invoice_id=due_invoice.id,
            payment_number=f"PAY-{uuid4().hex[:8]}", amount=Decimal("50.00"),
            method=PaymentMethod.CASH, status=PaymentStatus.PENDING,
        ),
        Payment(
            id=uuid4(), tenant_id=tenant.id, invoice_id=cancelled_invoice.id,
            payment_number=f"PAY-{uuid4().hex[:8]}", amount=Decimal("999.00"),
            method=PaymentMethod.CASH, status=PaymentStatus.COMPLETED,
        ),
        Payment(
            id=uuid4(), tenant_id=tenant.id, invoice_id=credit_invoice.id,
            payment_number=f"PAY-{uuid4().hex[:8]}", amount=Decimal("60.00"),
            method=PaymentMethod.CASH, status=PaymentStatus.COMPLETED,
        ),
    ])
    await db_session.flush()

    customer_balances = await get_customer_balances(db_session, [customer.id])
    vehicle_balances = await get_customer_vehicle_balances(
        db_session, customer.id, [due_vehicle.id, credit_vehicle.id]
    )

    assert customer_balances[customer.id] == Decimal("55.00")
    assert vehicle_balances[due_vehicle.id] == Decimal("75.00")
    assert vehicle_balances[credit_vehicle.id] == Decimal("-20.00")
