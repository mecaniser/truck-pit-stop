"""Gross receipt credit allocation; no second receipt or customer-fee credit."""
import hashlib
import json

from sqlalchemy import select

from app.db.models.customer import Customer
from app.db.models.invoice import Invoice
from app.db.models.invoice_settlement import (
    CustomerCreditEntry, InvoiceSettlement, PaymentOverpayment, PaymentRefund,
)
from app.db.models.repair_order import RepairOrder


def _r():
    from app.services import db048_accounting_reconciliation
    return db048_accounting_reconciliation


async def gross_credit_allocations(db, *, attempt, tenant, connection, ensure_invoices=True):
    """Rebuild all live applications from this receipt's immutable credit tree."""
    r = _r()
    origins = (await db.execute(select(CustomerCreditEntry).join(
        PaymentOverpayment, CustomerCreditEntry.origin_overpayment_id == PaymentOverpayment.id,
    ).where(
        CustomerCreditEntry.tenant_id == tenant.id,
        CustomerCreditEntry.customer_id == attempt.customer_id,
        CustomerCreditEntry.entry_type == "issued",
        PaymentOverpayment.tenant_id == tenant.id,
        PaymentOverpayment.customer_id == attempt.customer_id,
        PaymentOverpayment.source_attempt_id == attempt.id,
    ).order_by(CustomerCreditEntry.id))).scalars().all()
    amounts = {}
    for origin in origins:
        applications = (await db.execute(select(CustomerCreditEntry).where(
            CustomerCreditEntry.tenant_id == tenant.id,
            CustomerCreditEntry.customer_id == attempt.customer_id,
            CustomerCreditEntry.entry_type == "applied",
            CustomerCreditEntry.source_entry_id == origin.id,
        ).order_by(CustomerCreditEntry.id))).scalars().all()
        if sum((r.money(a.amount) for a in applications), r.ZERO) > r.money(origin.amount):
            raise r.DB048ReconciliationError("Gross credit exceeds its consented origin")
        for application in applications:
            reversals = (await db.execute(select(CustomerCreditEntry).where(
                CustomerCreditEntry.tenant_id == tenant.id,
                CustomerCreditEntry.customer_id == attempt.customer_id,
                CustomerCreditEntry.entry_type == "reversed",
                CustomerCreditEntry.source_entry_id == application.id,
            ))).scalars().all()
            reversed_amount = sum((r.money(row.amount) for row in reversals), r.ZERO)
            recovered = r.ZERO
            for reversal in reversals:
                recoveries = (await db.execute(select(CustomerCreditEntry).where(
                    CustomerCreditEntry.tenant_id == tenant.id,
                    CustomerCreditEntry.customer_id == attempt.customer_id,
                    CustomerCreditEntry.entry_type == "applied",
                    CustomerCreditEntry.source_entry_id == reversal.id,
                ))).scalars().all()
                recovery = sum((r.money(row.amount) for row in recoveries), r.ZERO)
                if recovery > r.money(reversal.amount):
                    raise r.DB048ReconciliationError("Gross credit recovery exceeds reversal")
                recovered += recovery
            if reversed_amount > r.money(application.amount):
                raise r.DB048ReconciliationError("Gross credit reversal exceeds application")
            active = r.money(application.amount) - reversed_amount + recovered
            if active > 0:
                key = application.target_invoice_id
                amounts[key] = amounts.get(key, r.ZERO) + active
    result = {}
    for invoice_id in sorted(amounts, key=str):
        invoice = await db.scalar(select(Invoice).where(
            Invoice.id == invoice_id, Invoice.tenant_id == tenant.id))
        order = await db.scalar(select(RepairOrder).where(
            RepairOrder.id == (invoice.repair_order_id if invoice else None),
            RepairOrder.tenant_id == tenant.id, RepairOrder.customer_id == attempt.customer_id))
        customer = await db.scalar(select(Customer).where(
            Customer.id == attempt.customer_id, Customer.tenant_id == tenant.id))
        settlement = await db.scalar(select(InvoiceSettlement).where(
            InvoiceSettlement.invoice_id == invoice_id, InvoiceSettlement.tenant_id == tenant.id,
            InvoiceSettlement.customer_id == attempt.customer_id).with_for_update())
        if not invoice or not order or not customer or not settlement:
            raise r.DB048ReconciliationError("Gross credit target identity does not match")
        if settlement.qbo_realm_snapshot != connection.realm_id:
            raise r.DB048ReconciliationError("Gross credit target realm does not match")
        if ensure_invoices:
            customer_id, qbo_invoice_id = await r._ensure_db048_qbo_invoice(
                connection=connection, invoice=invoice, customer=customer,
                principal_total=settlement.principal_total, tenant_name=tenant.name)
        else:
            customer_id, qbo_invoice_id = customer.quickbooks_customer_id, invoice.quickbooks_invoice_id
            if not customer_id or not qbo_invoice_id:
                raise r.DB048ReconciliationError("Gross credit target is not synchronized yet")
        if str(customer.quickbooks_customer_id or "") != str(customer_id):
            raise r.DB048ReconciliationError("Gross credit customer identity does not match")
        result[qbo_invoice_id] = r.money(result.get(qbo_invoice_id, r.ZERO) + amounts[invoice_id])
    return result


async def sync_gross_credit_application(db, envelope, settlement):
    from app.services.db048_qbo_gross_accounting import _payment_state, _attempt_changes, _assert_open_period
    r = _r()
    attempt = envelope.source_attempt
    settlement = await db.scalar(select(InvoiceSettlement).where(
        InvoiceSettlement.id == settlement.id, InvoiceSettlement.tenant_id == envelope.tenant.id,
        InvoiceSettlement.invoice_id == attempt.invoice_id,
        InvoiceSettlement.customer_id == attempt.customer_id).with_for_update())
    source_invoice = await db.scalar(select(Invoice).where(
        Invoice.id == attempt.invoice_id, Invoice.tenant_id == envelope.tenant.id))
    customer = await db.scalar(select(Customer).where(
        Customer.id == attempt.customer_id, Customer.tenant_id == envelope.tenant.id))
    payment_id = envelope.source_accounting_link.provider_deposit_id
    if (not settlement or settlement.qbo_realm_snapshot != envelope.connection.realm_id
            or not source_invoice or not source_invoice.quickbooks_invoice_id
            or not customer or not customer.quickbooks_customer_id
            or not payment_id or payment_id != envelope.source_payment.quickbooks_payment_id
            or envelope.source_accounting_link.owning_writer != "dieselbridge"
            or envelope.source_accounting_link.qbo_realm_snapshot != envelope.connection.realm_id):
        raise r.DB048ReconciliationError("Gross credit source identity does not match")
    current = (await r._request(envelope.connection, "GET", f"payment/{payment_id}")).get("Payment") or {}
    reference = r.db048_qbo_payment_reference(attempt=attempt, payment=envelope.source_payment)
    mapping_key = {"stripe_connect": "stripe_clearing_account", "quickbooks_payments": "qbp_clearing_account"}.get(
        attempt.provider, "check_deposit_account" if attempt.rail == "check" else "zelle_ach_account")
    deposit_account = await r._resolve_qbo_account_reference(envelope.connection,
        (envelope.source_accounting_link.account_mapping_snapshot or {}).get(mapping_key))
    def validate_identity(entity):
        if (str(entity.get("Id")) != str(payment_id)
                or str((entity.get("CustomerRef") or {}).get("value")) != str(customer.quickbooks_customer_id)
                or str(entity.get("PaymentRefNum")) != reference
                or str((entity.get("DepositToAccountRef") or {}).get("value")) != str(deposit_account)
                or ((entity.get("CurrencyRef") or {}).get("value") or "USD") != "USD"
                or (entity.get("ExchangeRate") is not None and str(entity["ExchangeRate"]) not in {"1", "1.0", "1.00"})
                or not r._qbo_payment_note_matches(entity.get("PrivateNote"), attempt=attempt,
                    payment=envelope.source_payment, invoice=source_invoice, payment_id=str(payment_id))):
            raise r.DB048ReconciliationError("Gross credit source collides with an unrelated receipt")
    validate_identity(current)
    original_gross = r.money(attempt.provider_charge_amount)
    original_allocation = sum(map(r.money, (attempt.applied_principal_amount,
        attempt.applied_card_fee_amount, attempt.applied_card_fee_tax_amount)), r.ZERO)
    changes = await _attempt_changes(db, attempt, envelope.connection.realm_id)
    gross = original_gross + sum((c["gross"] for c in changes), r.ZERO)
    canonical_allocation = original_allocation + sum(
        (c["principal"] + c["fee"] + c["tax"] for c in changes), r.ZERO)
    if canonical_allocation < 0 or gross < canonical_allocation:
        raise r.DB048ReconciliationError("Gross credit source financial state is inconsistent")
    allocations = await gross_credit_allocations(db, attempt=attempt, tenant=envelope.tenant,
                                                connection=envelope.connection)
    invoice_id = str(source_invoice.quickbooks_invoice_id)
    if canonical_allocation:
        allocations[invoice_id] = allocations.get(invoice_id, r.ZERO) + canonical_allocation
    allocated = sum(allocations.values(), r.ZERO)
    refunds = (await db.execute(select(PaymentRefund).where(
        PaymentRefund.tenant_id == envelope.tenant.id,
        PaymentRefund.source_attempt_id == attempt.id,
        PaymentRefund.state.in_(["succeeded", "pending", "manual_action_required", "failed"]),
    ))).scalars().all()
    reserved_refunds = sum((r.money(refund.amount) for refund in refunds), r.ZERO)
    if allocated + reserved_refunds > gross:
        raise r.DB048ReconciliationError("Gross credit consumes more than actual excess")
    desired = {"total": str(r.money(gross)),
               "lines": [(key, str(r.money(value))) for key, value in sorted(allocations.items())],
               "unapplied": str(r.money(gross - allocated))}
    original = {"total": str(original_gross),
                "lines": [(invoice_id, str(original_allocation))] if original_allocation else [],
                "unapplied": str(r.money(original_gross - original_allocation))}
    snapshots = dict(settlement.accounting_projection_snapshot or {})
    states = dict(snapshots.get("payments") or {})
    previous = states.get(str(attempt.id))
    canonical = lambda value: json.dumps(value, sort_keys=True)
    revision = hashlib.sha256(canonical(desired).encode()).hexdigest()
    for retry in range(3):
        validate_identity(current)
        actual = canonical(_payment_state(current))
        if actual == canonical(desired):
            break
        if actual not in {canonical(original), canonical(previous)}:
            raise r.DB048ReconciliationError("Gross credit source allocations changed outside this ledger")
        await _assert_open_period(envelope.connection, current)
        payload = r._qbo_payment_update_payload(current, total_amount=gross,
            lines=[{"Amount": float(value), "LinkedTxn": [{"TxnId": key, "TxnType": "Invoice"}]}
                   for key, value in sorted(allocations.items())], note=current["PrivateNote"])
        try:
            await r._request(envelope.connection, "POST", "payment?operation=update", json=payload,
                params={"requestid": r._qbo_request_id("grosscredit", f"{attempt.id}:{revision}")})
        except r.QuickBooksAccountingError as exc:
            if exc.status_code != 400 or "5010" not in str(exc) or retry == 2:
                raise
        current = (await r._request(envelope.connection, "GET", f"payment/{payment_id}")).get("Payment") or {}
    else:
        raise r.DB048ReconciliationError("Gross credit update exhausted bounded retries")
    validate_identity(current)
    if canonical(_payment_state(current)) != canonical(desired):
        raise r.DB048ReconciliationError("Gross credit readback does not match")
    # Target ensures may have updated this same source invoice snapshot.
    snapshots = dict(settlement.accounting_projection_snapshot or {})
    states = dict(snapshots.get("payments") or {})
    states[str(attempt.id)] = desired
    snapshots["payments"] = states
    settlement.accounting_projection_snapshot = snapshots
    await db.flush()
    return str(payment_id)
