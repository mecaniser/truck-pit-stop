"""Privacy-limited, read-only settlement evidence for the scoped fleet manifest."""
from datetime import timezone
from decimal import Decimal
import hashlib,json


def _digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()

ZERO=Decimal('0.00')
RAILS={'cash','card','zelle','check','ach','fleet_payment'}
STATES={'pending','confirmed','failed','expired','refunded','reversed'}
MAX_PAYMENTS=1000
SETTLEMENT_STATES={'paid','unpaid','partially_paid','payment_pending','partially_paid_pending','overpayment_resolution'}


def money(value):
    number=Decimal(str(value if value is not None else 0))
    if not number.is_finite() or number<0 or number>=Decimal('100000000') or number!=number.quantize(Decimal('.01')):
        raise ValueError('Invalid source settlement money')
    return number.quantize(Decimal('.01'))


def stamp(value):
    if value is None:return None
    return (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)).isoformat()


def project_settlement(invoice,settlement,attempts):
    if settlement is None:return None
    if len(attempts)>MAX_PAYMENTS:raise ValueError('Settlement payment snapshot exceeds limit')
    if settlement.state not in SETTLEMENT_STATES:raise ValueError('Unsupported source settlement state')
    reasons=[]
    def review(reason):
        if reason not in reasons:reasons.append(reason)
    if (settlement.invoice_id!=invoice.id or settlement.tenant_id!=invoice.tenant_id):
        raise ValueError('Settlement scope mismatch')
    fields={'principal_total':'principal_total','max_card_fee':'max_card_fee','max_card_fee_tax':'max_card_fee_tax',
        'confirmed_principal':'confirmed_principal','pending_principal':'active_pending_principal',
        'unapplied_credit':'unapplied_credit','refund_pending':'refund_pending'}
    values={name:money(getattr(settlement,source)) for name,source in fields.items()}
    if values['principal_total']+values['max_card_fee']+values['max_card_fee_tax']!=money(invoice.total_amount):review('invoice_settlement_amount_mismatch')
    if values['max_card_fee']!=money(invoice.service_fee_amount):review('invoice_settlement_fee_mismatch')
    if values['unapplied_credit'] or values['refund_pending']:review('source_credit_or_refund_requires_review')
    if values['confirmed_principal']+values['pending_principal']>values['principal_total']:review('source_principal_overallocated')
    payments=[];confirmed=ZERO;pending=ZERO;fees=ZERO;fee_tax=ZERO;seen=set()
    for attempt in sorted(attempts,key=lambda a:str(a.id)):
        if (attempt.tenant_id!=invoice.tenant_id or attempt.invoice_id!=invoice.id or attempt.settlement_id!=settlement.id or attempt.customer_id!=settlement.customer_id):
            review('source_payment_scope_mismatch');continue
        if str(attempt.id) in seen:review('duplicate_source_payment');continue
        seen.add(str(attempt.id))
        if attempt.rail not in RAILS or attempt.state not in STATES:raise ValueError('Unsupported source payment state')
        if getattr(attempt,'deleted_at',None):review('source_deleted_payment_requires_review')
        if attempt.state in ('refunded','reversed'):review('source_payment_reversal_requires_review')
        received=money(attempt.received_amount) if attempt.received_amount is not None else None
        applied=money(attempt.applied_principal_amount);fee=money(attempt.applied_card_fee_amount);tax=money(attempt.applied_card_fee_tax_amount);unapplied=money(attempt.unapplied_amount)
        if unapplied:review('source_credit_or_refund_requires_review')
        if attempt.rail!='card' and (fee or tax):review('noncard_payment_has_card_fee')
        if attempt.state=='confirmed':
            confirmed+=applied;fees+=fee;fee_tax+=tax
            if received is None or received<=ZERO:review('source_received_amount_missing')
        elif attempt.state in ('pending','failed','expired') and (received is not None or applied or fee or tax):review('unconfirmed_payment_has_applied_money')
        if attempt.state=='pending':pending+=money(attempt.principal_amount)
        # DB-048 received_amount is principal-only. Provider gross is separately
        # preserved for card attempts; never silently call principal the total paid.
        gross=(money(attempt.provider_charge_amount) if attempt.rail=='card' else received) if attempt.state in ('confirmed','refunded','reversed') else None
        if gross is not None and gross!=applied+fee+tax+unapplied:review('source_payment_gross_mismatch')
        if received is not None and received<applied:review('source_received_principal_mismatch')
        value={'attempt_id':str(attempt.id),'rail':attempt.rail,'state':attempt.state,
            'principal_amount':format(money(attempt.principal_amount),'.2f'),
            'received_amount':format(received,'.2f') if received is not None else None,
            'gross_received_amount':format(gross,'.2f') if gross is not None else None,
            'applied_principal_amount':format(applied,'.2f'),'applied_card_fee_amount':format(fee,'.2f'),
            'applied_card_fee_tax_amount':format(tax,'.2f'),'unapplied_amount':format(unapplied,'.2f'),
            'confirmed_at':stamp(attempt.confirmed_at),'actual_paid_date':None,'paid_date_basis':'unknown'}
        value['revision']=_digest(value);payments.append(value)
    if confirmed!=values['confirmed_principal']:review('source_confirmed_principal_mismatch')
    if pending!=values['pending_principal']:review('source_pending_principal_mismatch')
    if settlement.state=='paid' and confirmed!=values['principal_total']:review('source_paid_state_mismatch')
    if settlement.state=='unpaid' and confirmed>ZERO:review('source_paid_state_mismatch')
    if fees>values['max_card_fee'] or fee_tax>values['max_card_fee_tax']:review('source_card_fee_overallocated')
    value={'settlement_id':str(settlement.id),'status':'review_required' if reasons else 'available',
        'review_reasons':reasons,'source_state':settlement.state,
        **{k:format(v,'.2f') for k,v in values.items()},'payments':payments}
    value['revision']=_digest(value)
    return value
