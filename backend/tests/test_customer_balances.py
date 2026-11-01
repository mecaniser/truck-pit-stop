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

    assert customer_balances[customer.id] == Decimal("75.00")
    assert vehicle_balances[due_vehicle.id] == Decimal("75.00")
    assert vehicle_balances[credit_vehicle.id] == Decimal("0.00")


async def balance_fixture(db):
    tenant = Tenant(id=uuid4(), name='Fixture', slug=uuid4().hex)
    customer = Customer(id=uuid4(), tenant_id=tenant.id, first_name='Balance', last_name='Fixture', email=uuid4().hex+'@example.com')
    vehicle = Vehicle(id=uuid4(), tenant_id=tenant.id, customer_id=customer.id, make='Volvo', model='VNR')
    db.add_all([tenant, customer, vehicle]); await db.flush()
    return tenant, customer, vehicle


async def add_invoice(db, tenant, customer, vehicle, *, total='103.50', fee='3.50', status=InvoiceStatus.SENT, source=None, ro_source=None):
    ro = RepairOrder(id=uuid4(), tenant_id=tenant.id, customer_id=customer.id, vehicle_id=vehicle.id,
                     order_number=uuid4().hex, status=RepairOrderStatus.INVOICED, source=ro_source)
    db.add(ro); await db.flush()
    invoice = Invoice(id=uuid4(), tenant_id=tenant.id, repair_order_id=ro.id, invoice_number=uuid4().hex,
                      subtotal=Decimal('100'), total_amount=Decimal(total), service_fee_amount=Decimal(fee), status=status, source=source)
    db.add(invoice); await db.flush()
    return invoice


async def add_payment(db, tenant, invoice, amount, status=PaymentStatus.COMPLETED):
    db.add(Payment(id=uuid4(), tenant_id=tenant.id, invoice_id=invoice.id, payment_number=uuid4().hex,
                   amount=Decimal(amount), status=status, method=PaymentMethod.CASH))
    await db.flush()


@pytest.mark.asyncio
async def test_cash_paid_and_ets_are_separate_with_consistent_sort_and_projection(db_session):
    from sqlalchemy import select
    from app.services.customer_balance import customer_balance_totals, vehicle_balance_totals, customer_balance_sort
    from app.api.v1.endpoints.customers import _customer_response_with_read_model
    from app.db.models.customer_read_model import CustomerReadModel
    tenant, customer, vehicle = await balance_fixture(db_session)
    paid = await add_invoice(db_session, tenant, customer, vehicle, status=InvoiceStatus.PAID, ro_source='easy_truck_shop_import')
    await add_payment(db_session, tenant, paid, '100')
    await add_invoice(db_session, tenant, customer, vehicle, total='1089.21', fee='0', source='easy_truck_shop_import')
    native, legacy = await customer_balance_totals(db_session, [customer.id])
    assert native[customer.id] == 0
    assert legacy[customer.id] == Decimal('1089.21')
    v_native, v_legacy = await vehicle_balance_totals(db_session, customer.id, [vehicle.id])
    assert v_native[vehicle.id] == 0
    assert v_legacy[vehicle.id] == Decimal('1089.21')
    sorted_balance = await db_session.scalar(select(customer_balance_sort()).select_from(Customer).where(Customer.id == customer.id))
    assert sorted_balance == 0
    projection = CustomerReadModel(invoice_total=Decimal('1192.71'), payment_total=Decimal('100'), vehicle_count=1)
    response = _customer_response_with_read_model(customer, projection, native, {}, legacy_balances=legacy)
    assert response.balance == 0
    assert response.legacy_ets_balance == Decimal('1089.21')


@pytest.mark.asyncio
@pytest.mark.parametrize('payment_status,expected', [(PaymentStatus.COMPLETED, '75'), (PaymentStatus.PENDING, '100'), (PaymentStatus.FAILED, '100'), (PaymentStatus.REFUNDED, '100')])
async def test_unpaid_principal_ignores_optional_fee_and_uncompleted_payments(db_session, payment_status, expected):
    tenant, customer, vehicle = await balance_fixture(db_session)
    invoice = await add_invoice(db_session, tenant, customer, vehicle)
    await add_payment(db_session, tenant, invoice, '25', payment_status)
    assert (await get_customer_balances(db_session, [customer.id]))[customer.id] == Decimal(expected)


@pytest.mark.asyncio
async def test_valid_settlement_uses_principal_not_gross_card_payment(db_session):
    from app.db.models.invoice_settlement import InvoiceSettlement
    tenant, customer, vehicle = await balance_fixture(db_session)
    invoice = await add_invoice(db_session, tenant, customer, vehicle)
    await add_payment(db_session, tenant, invoice, '51.75')
    db_session.add(InvoiceSettlement(id=uuid4(), tenant_id=tenant.id, invoice_id=invoice.id, customer_id=customer.id,
                                    principal_total=Decimal('100'), confirmed_principal=Decimal('50'), currency='USD', legacy_reconciliation_status='native'))
    await db_session.flush()
    assert (await get_customer_balances(db_session, [customer.id]))[customer.id] == Decimal('50')


@pytest.mark.asyncio
async def test_cross_tenant_payment_and_wrong_customer_settlement_cannot_reduce_balance(db_session):
    from app.db.models.invoice_settlement import InvoiceSettlement
    tenant, customer, vehicle = await balance_fixture(db_session)
    other_tenant, other_customer, other_vehicle = await balance_fixture(db_session)
    invoice = await add_invoice(db_session, tenant, customer, vehicle)
    await add_payment(db_session, other_tenant, invoice, '100')
    db_session.add(InvoiceSettlement(id=uuid4(), tenant_id=tenant.id, invoice_id=invoice.id, customer_id=other_customer.id,
                                    principal_total=Decimal('100'), confirmed_principal=Decimal('100'), currency='USD'))
    await db_session.flush()
    assert (await get_customer_balances(db_session, [customer.id]))[customer.id] == Decimal('100')
    assert (await get_customer_vehicle_balances(db_session, other_customer.id, [vehicle.id]))[vehicle.id] == 0


@pytest.mark.asyncio
async def test_fee_tax_matches_canonical_principal(db_session):
    from app.services.invoice_settlement_service import invoice_money_snapshot
    tenant, customer, vehicle = await balance_fixture(db_session)
    invoice = await add_invoice(db_session, tenant, customer, vehicle, total='110.75')
    invoice.tax_amount = Decimal('7.25')
    await db_session.flush()
    assert (await get_customer_balances(db_session, [customer.id]))[customer.id] == invoice_money_snapshot(invoice)[0]


@pytest.mark.asyncio
async def test_bill_to_snapshot_survives_repair_order_reassignment(db_session):
    from app.services.customer_balance import customer_balance_totals
    tenant, original, vehicle = await balance_fixture(db_session)
    replacement = Customer(id=uuid4(), tenant_id=tenant.id, first_name='New', last_name='Owner', email=uuid4().hex+'@example.com')
    db_session.add(replacement); await db_session.flush()
    invoice = await add_invoice(db_session, tenant, replacement, vehicle)
    invoice.billed_customer_id = original.id
    await db_session.flush()
    native, _ = await customer_balance_totals(db_session, [original.id, replacement.id])
    assert native[original.id] == Decimal('100')
    assert native.get(replacement.id, 0) == 0
    assert (await get_customer_vehicle_balances(db_session, original.id, [vehicle.id]))[vehicle.id] == Decimal('100')
    assert (await get_customer_vehicle_balances(db_session, replacement.id, [vehicle.id]))[vehicle.id] == 0


@pytest.mark.asyncio
async def test_draft_internal_deleted_invoices_and_deleted_payments(db_session):
    from datetime import datetime, timezone
    tenant, customer, vehicle = await balance_fixture(db_session)
    await add_invoice(db_session, tenant, customer, vehicle, status=InvoiceStatus.DRAFT)
    internal = await add_invoice(db_session, tenant, customer, vehicle); internal.is_internal = True
    deleted = await add_invoice(db_session, tenant, customer, vehicle); deleted.deleted_at = datetime.now(timezone.utc)
    unpaid = await add_invoice(db_session, tenant, customer, vehicle)
    db_session.add(Payment(id=uuid4(), tenant_id=tenant.id, invoice_id=unpaid.id, payment_number=uuid4().hex,
                           amount=Decimal('100'), status=PaymentStatus.COMPLETED, method=PaymentMethod.CASH,
                           deleted_at=datetime.now(timezone.utc)))
    await db_session.flush()
    assert (await get_customer_balances(db_session, [customer.id]))[customer.id] == Decimal('100')


@pytest.mark.asyncio
async def test_historical_policy_and_voided_invoice_are_not_current_debt(db_session):
    from datetime import datetime, timezone
    from app.services.customer_balance import customer_balance_totals
    tenant, customer, vehicle = await balance_fixture(db_session)
    historical = await add_invoice(db_session, tenant, customer, vehicle)
    historical.accounting_policy = 'historical_export_hold'
    voided = await add_invoice(db_session, tenant, customer, vehicle)
    voided.voided_at = datetime.now(timezone.utc)
    await db_session.flush()
    native, legacy = await customer_balance_totals(db_session, [customer.id])
    assert native[customer.id] == 0
    assert legacy[customer.id] == Decimal('103.50')


@pytest.mark.asyncio
@pytest.mark.parametrize('internal_scope', ['order', 'customer'])
async def test_internal_order_or_house_account_is_not_current_debt(db_session, internal_scope):
    from sqlalchemy import select
    from app.services.customer_balance import customer_balance_sort
    tenant, customer, vehicle = await balance_fixture(db_session)
    invoice = await add_invoice(db_session, tenant, customer, vehicle)
    if internal_scope == 'order':
        order = await db_session.get(RepairOrder, invoice.repair_order_id)
        order.is_internal = True
    else:
        customer.is_internal_fleet = True
    await db_session.flush()
    assert (await get_customer_balances(db_session, [customer.id]))[customer.id] == 0
    assert await db_session.scalar(select(customer_balance_sort()).select_from(Customer).where(Customer.id == customer.id)) == 0
