"""Read actual receipts separately from non-sale collection documents."""
from decimal import Decimal, InvalidOperation
from sqlalchemy import select,and_
from app.db.models.invoice import Invoice
from app.db.models.source_debt_handoff import SourceDebtHandoff

async def collection_economics(db,invoice_ids):
    if not invoice_ids:return {}
    rows=(await db.execute(select(SourceDebtHandoff,Invoice).join(Invoice,and_(Invoice.id==SourceDebtHandoff.source_dbn_invoice_id,Invoice.tenant_id==SourceDebtHandoff.tenant_id)).where(SourceDebtHandoff.native_invoice_id.in_(invoice_ids)))).all()
    result={}
    for handoff,original in rows:
        result[handoff.native_invoice_id]=None
        snapshot=original.line_items_snapshot or {}
        try:
            if not snapshot.get('labor') and not snapshot.get('parts'):continue
            def number(value):
                if value is None or isinstance(value,bool):raise ValueError('unknown economic amount')
                parsed=Decimal(str(value))
                if not parsed.is_finite() or parsed<0:raise ValueError('invalid economic amount')
                return parsed
            labor=sum((number(row['total_cost']) for row in snapshot.get('labor',[])),Decimal(0))
            parts=sum((number(row['total_price']) for row in snapshot.get('parts',[])),Decimal(0))
            try:
                parts_cost=Decimal(0)
                for row in snapshot.get('parts',[]):
                    quantity=number(row['quantity'])
                    if quantity<=0 and number(row['total_price'])>0:raise ValueError('invalid part quantity')
                    parts_cost+=number(row['unit_cost'])*quantity
            except (KeyError,TypeError,ValueError,InvalidOperation):
                parts_cost=None
            fees=number(original.shop_supplies_amount)+number(original.service_fee_amount)
            tax=number(original.tax_amount);discount=number(original.discount_amount);total=number(original.total_amount)
            values=(labor,parts,fees,tax,discount,total)
            if any(not v.is_finite() or v<0 for v in values) or total<=0 or total!=handoff.original_issued_total or labor+parts+fees+tax-discount!=total:continue
            result[handoff.native_invoice_id]=dict(total=total,labor=labor,parts=parts,parts_cost=parts_cost,fees=fees,tax=tax)
        except (KeyError,TypeError,ValueError,InvalidOperation):continue
    return result

def confirmed_collection_receipt_clause():
    from sqlalchemy import or_
    from app.db.models.payment import Payment
    from app.db.models.invoice_settlement import InvoicePaymentAttempt
    from app.db.models.source_debt_handoff import SourceReceiptLink
    attempt=select(InvoicePaymentAttempt.id).where(InvoicePaymentAttempt.id==Payment.invoice_payment_attempt_id,
        InvoicePaymentAttempt.tenant_id==Payment.tenant_id,InvoicePaymentAttempt.invoice_id==Invoice.id,
        InvoicePaymentAttempt.customer_id==Invoice.billed_customer_id,InvoicePaymentAttempt.payment_id==Payment.id,InvoicePaymentAttempt.confirmed_at.is_not(None)).correlate(Payment,Invoice).exists()
    external=select(SourceReceiptLink.id).where(SourceReceiptLink.native_payment_id==Payment.id,
        SourceReceiptLink.tenant_id==Payment.tenant_id,SourceReceiptLink.handoff_id==Invoice.source_debt_handoff_id,
        SourceReceiptLink.origin=='ets_external',SourceReceiptLink.amount>0).correlate(Payment,Invoice).exists()
    return select(SourceDebtHandoff.id).where(SourceDebtHandoff.id==Invoice.source_debt_handoff_id,
        SourceDebtHandoff.native_invoice_id==Invoice.id,SourceDebtHandoff.tenant_id==Payment.tenant_id,
        SourceDebtHandoff.customer_id==Invoice.billed_customer_id,Invoice.source=='ets_collection_handoff',or_(attempt,external)).correlate(Payment,Invoice).exists()

async def collection_receipt_components(db,payments):
    from app.db.models.payment import Payment
    from app.db.models.invoice_settlement import InvoicePaymentAttempt
    from app.db.models.source_debt_handoff import SourceReceiptLink
    ids=[payment.id for payment in payments]
    if not ids:return {}
    result={}
    attempts=(await db.execute(select(Payment,InvoicePaymentAttempt).join(InvoicePaymentAttempt,and_(InvoicePaymentAttempt.id==Payment.invoice_payment_attempt_id,InvoicePaymentAttempt.invoice_id==Payment.invoice_id,InvoicePaymentAttempt.tenant_id==Payment.tenant_id)).where(Payment.id.in_(ids),InvoicePaymentAttempt.confirmed_at.is_not(None)))).all()
    for payment,attempt in attempts:
        principal=Decimal(str(attempt.applied_principal_amount or 0));fee=Decimal(str(attempt.applied_card_fee_amount or 0));tax=Decimal(str(attempt.applied_card_fee_tax_amount or 0));unapplied=Decimal(str(attempt.unapplied_amount or 0))
        if all(v.is_finite() and v>=0 for v in (principal,fee,tax,unapplied)) and principal==payment.amount and principal+fee+tax+unapplied==confirmed_receipt_gross(attempt):
            result[payment.id]=dict(principal=principal,fee=fee,fee_tax=tax,unapplied=unapplied,gross=confirmed_receipt_gross(attempt))
    links=(await db.execute(select(Payment,SourceReceiptLink).join(SourceReceiptLink,and_(SourceReceiptLink.native_payment_id==Payment.id,SourceReceiptLink.tenant_id==Payment.tenant_id)).where(Payment.id.in_(ids),SourceReceiptLink.origin=='ets_external'))).all()
    for payment,link in links:
        if link.amount==payment.amount:result[payment.id]=dict(principal=link.amount,fee=Decimal(0),fee_tax=Decimal(0),unapplied=Decimal(0),gross=payment.amount)
    return result

def receipt_gross_expression():
    from sqlalchemy import case,func
    from app.db.models.payment import Payment
    from app.db.models.invoice_settlement import InvoicePaymentAttempt
    gross=select(case((InvoicePaymentAttempt.rail=="card",InvoicePaymentAttempt.provider_charge_amount),else_=InvoicePaymentAttempt.received_amount)).where(InvoicePaymentAttempt.id==Payment.invoice_payment_attempt_id,
        InvoicePaymentAttempt.tenant_id==Payment.tenant_id,InvoicePaymentAttempt.invoice_id==Invoice.id,
        InvoicePaymentAttempt.confirmed_at.is_not(None)).correlate(Payment,Invoice).scalar_subquery()
    return case((Invoice.accounting_policy=='source_collection_hold',func.coalesce(gross,Payment.amount)),else_=Payment.amount)


def confirmed_receipt_gross(attempt):
    """Card provider capture is immutable; verified manual received amount can exceed quote."""
    return attempt.provider_charge_amount if attempt.rail=='card' else attempt.received_amount
