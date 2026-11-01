"""Read-only overview balances; historical ETS rows are never current debt.

These operational balances do not attest the account's classification policy.
No payment, settlement or historical source row is repaired by this reader.
"""
from decimal import Decimal

from sqlalchemy import and_, case, func, or_, select

from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.invoice_settlement import InvoiceSettlement
from app.db.models.payment import Payment, PaymentStatus
from app.db.models.repair_order import RepairOrder


def positive(value):
    return case((value > 0, value), else_=0)


def billed_customer_key():
    return func.coalesce(Invoice.billed_customer_id, RepairOrder.customer_id)


def balance_expressions():
    # Match invoice_money_snapshot: the optional card fee and its proportional
    # sales tax are not principal owed before a tender is chosen.
    fee = func.coalesce(Invoice.service_fee_amount, 0)
    base = Invoice.subtotal + func.coalesce(Invoice.shop_supplies_amount, 0)
    fee_tax = func.round(fee * func.coalesce(Invoice.tax_amount, 0) / func.nullif(base + fee, 0), 2)
    principal = positive(Invoice.total_amount - fee - func.coalesce(fee_tax, 0))
    payments = select(func.coalesce(func.sum(Payment.amount), 0)).where(
        Payment.invoice_id == Invoice.id,
        Payment.tenant_id == Invoice.tenant_id,
        Payment.status == PaymentStatus.COMPLETED,
        Payment.deleted_at.is_(None),
    ).correlate(Invoice).scalar_subquery()
    settled = select(InvoiceSettlement.principal_total - InvoiceSettlement.confirmed_principal).where(
        InvoiceSettlement.invoice_id == Invoice.id,
        InvoiceSettlement.tenant_id == Invoice.tenant_id,
        InvoiceSettlement.customer_id == billed_customer_key(),
        InvoiceSettlement.deleted_at.is_(None),
        InvoiceSettlement.currency == 'USD',
        InvoiceSettlement.legacy_reconciliation_status.in_(['native', 'reconciled']),
        InvoiceSettlement.principal_total == principal,
        InvoiceSettlement.confirmed_principal >= 0,
        InvoiceSettlement.confirmed_principal <= InvoiceSettlement.principal_total,
    ).correlate(Invoice, RepairOrder).scalar_subquery()
    # A native replacement may retain an ETS repair order/invoice number.
    historical = or_(Invoice.source == 'easy_truck_shop_import',
                     Invoice.accounting_policy == 'historical_export_hold')
    remainder = case((Invoice.status == InvoiceStatus.PAID, 0),
                     else_=positive(func.coalesce(settled, principal - payments)))
    native = case((historical, 0), (Invoice.status == InvoiceStatus.DRAFT, 0),
                  (Invoice.is_internal.is_(True), 0), (RepairOrder.is_internal.is_(True), 0),
                  (Customer.is_internal_fleet.is_(True), 0), else_=remainder)
    # Preserve the imported recorded balance, not an assertion of collectibility.
    legacy = case((historical, positive(Invoice.total_amount - payments)), else_=0)
    return native, legacy


def balance_query(group_column):
    native, legacy = balance_expressions()
    return select(group_column, func.coalesce(func.sum(native), 0), func.coalesce(func.sum(legacy), 0)).select_from(
        RepairOrder
    ).join(Invoice, and_(Invoice.repair_order_id == RepairOrder.id, Invoice.tenant_id == RepairOrder.tenant_id)).join(
        Customer, and_(Customer.id == billed_customer_key(), Customer.tenant_id == RepairOrder.tenant_id)
    ).where(Invoice.status != InvoiceStatus.CANCELLED, Invoice.deleted_at.is_(None), Invoice.voided_at.is_(None))


async def customer_balance_totals(db, customer_ids):
    if not customer_ids:
        return {}, {}
    rows = (await db.execute(balance_query(billed_customer_key()).where(
        billed_customer_key().in_(customer_ids)
    ).group_by(billed_customer_key()))).all()
    return ({key: Decimal(str(native)).quantize(Decimal("0.01")) for key, native, legacy in rows},
            {key: Decimal(str(legacy)).quantize(Decimal("0.01")) for key, native, legacy in rows})


async def vehicle_balance_totals(db, customer_id, vehicle_ids):
    if not vehicle_ids:
        return {}, {}
    rows = (await db.execute(balance_query(RepairOrder.vehicle_id).where(
        billed_customer_key() == customer_id, RepairOrder.vehicle_id.in_(vehicle_ids)
    ).group_by(RepairOrder.vehicle_id))).all()
    return ({key: Decimal(str(native)).quantize(Decimal("0.01")) for key, native, legacy in rows},
            {key: Decimal(str(legacy)).quantize(Decimal("0.01")) for key, native, legacy in rows})


def customer_balance_sort():
    native, _ = balance_expressions()
    return select(func.coalesce(func.sum(native), 0)).select_from(RepairOrder).join(
        Invoice, and_(Invoice.repair_order_id == RepairOrder.id, Invoice.tenant_id == RepairOrder.tenant_id)
    ).where(billed_customer_key() == Customer.id, RepairOrder.tenant_id == Customer.tenant_id,
            Invoice.status != InvoiceStatus.CANCELLED, Invoice.deleted_at.is_(None), Invoice.voided_at.is_(None)).correlate(Customer).scalar_subquery()
