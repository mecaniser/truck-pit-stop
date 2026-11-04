"""Exact payment-request resolution. Ledger commands are immutable; no provider search."""
from __future__ import annotations
from collections import defaultdict
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from uuid import UUID
from sqlalchemy import select, or_, func
from app.core.config import settings
from app.core.dependencies import user_has_permission
from app.core.dependencies import identity_user
from app.db.models.user import UserRole
from app.db.models.invoice_settlement import (InvoicePaymentAttempt as Attempt, InvoiceSettlement as Settlement,
    InvoicePaymentLedgerEvent as Event, PaymentRefund, PaymentProviderDispute, PaymentAccountingLink)
from app.schemas.invoice_settlement import ResolutionProjection, ResolutionActions

ZERO=Decimal('0.00')

def error(code,message,status=409,**kw):
    from app.services.invoice_settlement_service import SettlementDomainError
    raise SettlementDomainError(code,message,status_code=status,**kw)

def cash(value):return f'{Decimal(value or 0):.2f}'
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()
def stamp(value):return value.replace(tzinfo=value.tzinfo or timezone.utc) if value else None

def money_staff(actor):
    return bool(actor and actor.role in {UserRole.GARAGE_OWNER,UserRole.GARAGE_ADMIN} and user_has_permission(actor,'payments'))

async def evidence_page(db,attempts):
    """Constant query count, independent of page length; no provider calls or writes."""
    ids=[a.id for a in attempts]
    if not ids:return {}
    tenant=attempts[0].tenant_id
    events=defaultdict(list)
    for row in (await db.scalars(select(Event).where(Event.tenant_id==tenant,Event.attempt_id.in_(ids)).order_by(Event.sequence))).all():events[row.attempt_id].append(row)
    settlements={s.id:s for s in (await db.scalars(select(Settlement).where(Settlement.tenant_id==tenant,Settlement.id.in_([a.settlement_id for a in attempts])))).all()}
    blocked=set((await db.scalars(select(PaymentRefund.source_attempt_id).where(PaymentRefund.tenant_id==tenant,PaymentRefund.source_attempt_id.in_(ids),PaymentRefund.deleted_at.is_(None)))).all())
    blocked.update((await db.scalars(select(PaymentProviderDispute.attempt_id).where(PaymentProviderDispute.tenant_id==tenant,PaymentProviderDispute.attempt_id.in_(ids)))).all())
    blocked.update((await db.scalars(select(PaymentAccountingLink.attempt_id).where(PaymentAccountingLink.tenant_id==tenant,PaymentAccountingLink.attempt_id.in_(ids)))).all())
    return {a.id:dict(events=events[a.id],settlement=settlements.get(a.settlement_id),blocked=a.id in blocked or any(e.event_type in {'provider_receipt_needs_review','efs_received_difference'} for e in events[a.id])) for a in attempts}

def protocol(info):
    return next((e.evidence_snapshot for e in info['events'] if e.event_type=='card_submission_protocol'),None)

def started(info):return any(e.event_type=='card_submission_started' for e in info['events'])

def binding(a,info):
    p=protocol(info) or {}
    result=dict(provider=a.provider,provider_account_id=a.provider_account_id,environment=p.get('environment'),
        configuration_version=a.provider_configuration_version,provider_request_id=p.get('provider_request_id'),
        provider_reference=a.provider_intent_id or a.provider_charge_id,attempted_at=stamp(a.created_at).isoformat(),
        requested_principal=cash(a.principal_amount),provider_charge_amount=cash(a.provider_charge_amount),currency=a.currency)
    result['evidence_context_sha256']=digest(result)
    return result

def eligible_owner(a,actor,audience,customer_id=None):
    if money_staff(actor):return actor.tenant_id==a.tenant_id
    if audience=='guest':return a.subject_type=='guest' and a.customer_id==customer_id
    return bool(actor and actor.role==UserRole.CUSTOMER and actor.tenant_id==a.tenant_id and actor.customer_id==a.customer_id and a.subject_type=='customer' and a.subject_id in {identity_user(actor).id,actor.customer_id})

def projection(a,info,*,actor=None,audience='customer',customer_id=None):
    s=info.get('settlement');events=info['events'];p=protocol(info);staff=money_staff(actor)
    actions=ResolutionActions();owner=eligible_owner(a,actor,audience,customer_id)
    blocked=info['blocked'] or a.received_amount is not None or a.payment_id is not None
    cancelled=next((e for e in reversed(events) if e.event_type=='attempt_cancelled'),None)
    review=next((e for e in reversed(events) if e.event_type in {'review_requested','provider_receipt_needs_review'}),None)
    resolved=next((e for e in reversed(events) if e.event_type in {'attempt_cancelled','attempt_terminal_released'}),None)
    pending=a.state=='pending';known=bool(a.provider_intent_id or a.provider_charge_id)
    local_card=bool(p and not started(info) and not known and not a.provider_reference and not blocked)
    missing=[k for k in ('provider_account_id','environment','configuration_version') if not binding(a,info).get(k)] if a.rail=='card' else []
    if a.state in {'confirmed','refunded','reversed'}:status='received'
    elif cancelled:status='cancelled'
    elif a.state in {'failed','expired'}:status='failed'
    elif a.rail=='zelle':status='transfer_reported' if (a.manual_evidence or {}).get('transfer_sent_confirmed') is True else 'verification_pending'
    elif a.rail=='card':status='checkout_started' if local_card else 'verification_pending'
    else:status='review_required'
    if any(e.event_type in {'provider_receipt_needs_review','efs_received_difference'} for e in events):status='review_required'
    if pending and (review or info['blocked'] or (a.rail=='card' and not local_card and not known)):status='review_required'
    reason=None
    if pending and owner:
        actions.request_review=a.rail in {'zelle','card'}
        actions.cancel_unsent=not blocked and (a.rail=='zelle' or (a.rail=='card' and (local_card or (a.provider=='stripe_connect' and known))))
        actions.check_provider_status=a.rail=='card' and known
        actions.release_with_terminal_evidence=staff and a.rail=='card' and not blocked and not missing
    actions.record_late_receipt=staff and a.rail=='zelle' and a.state in {'failed','expired'} and not blocked
    legacy_review=bool(resolved and resolved.evidence_snapshot.get('legacy_projection_review_required'))
    if legacy_review:reason=dict(code='legacy_projection_review_required',message='The shop must review this transfer before another payment.')
    if status=='review_required':reason=dict(code='provider_review_required',message='The shop must review this payment before you try again.')
    if a.rail not in {'zelle','card'} and not info.get('efs'):reason=dict(code='unsupported_resolution_rail',message='This payment request requires shop review.');actions=ResolutionActions()
    notice=None
    if status=='cancelled':notice=dict(kind='request_cancelled',message='Payment request canceled. No payment was recorded. You can try again.',resolved_at=stamp(cancelled.occurred_at).isoformat())
    if legacy_review and notice:notice['message']='Payment request canceled. The shop must review this transfer before another payment.'
    if resolved and status=='failed':notice=dict(kind='reviewed_release',message='The shop verified that this payment did not complete. You can try again.',resolved_at=stamp(resolved.occurred_at).isoformat())
    elif status=='received' and cancelled:notice=dict(kind='late_receipt',message='Payment was received after the request was canceled. The current balance includes the receipt.',resolved_at=stamp(a.confirmed_at).isoformat() if a.confirmed_at else None)
    efs=info.get('efs')
    if efs is not None:
        status={'awaiting_verification':'verification_pending','received':'received','rejected':'failed','cancelled':'cancelled','review_required':'review_required'}[efs.status]
        actions=ResolutionActions(cancel_unsent=efs.can_cancel)
        reason=dict(code='efs_review_required',message='The shop must review this EFS payment.') if efs.status=='review_required' else None
        if efs.status in {'cancelled','rejected'}:
            notice=dict(kind='efs_request_closed',message='To try again, use a different code or contact the shop.',resolved_at=stamp(a.failed_at).isoformat() if a.failed_at else None)
    return ResolutionProjection(attempt_id=a.id,invoice_id=a.invoice_id,attempt_version=a.version,settlement_version=s.version if s else 1,
        rail=a.rail,requested_principal=cash(a.principal_amount),currency=a.currency,attempt_state=a.state,checkout_status=status,
        reservation_amount=cash(a.principal_amount if pending else ZERO),can_retry=a.state in {'failed','expired'} and not blocked and not legacy_review and (bool(efs and efs.status in {'cancelled','rejected'}) or bool(resolved or any(e.event_type=='terminal_no_charge_verified' for e in events))),
        actions=actions,block_reason=reason,resolution_notice=notice,review_status='resolved' if resolved else 'requested' if review else 'evidence_required' if status=='review_required' else 'none')

async def project_many(db,attempts,*,actor=None,audience='customer',customer_id=None):
    with getattr(db,'no_autoflush',nullcontext()):
        infos=await evidence_page(db,attempts)
        from app.services.customer_efs import summaries
        efss=await summaries(db,attempts,actor=actor,audience=audience,customer_id=customer_id)
        for identity,value in efss.items():infos[identity]['efs']=value
        return {a.id:projection(a,infos[a.id],actor=actor,audience=audience,customer_id=customer_id) for a in attempts}

async def append_protocol(db,a,s,actor):
    from app.services.invoice_settlement_service import append_ledger_event
    environment=settings.QUICKBOOKS_PAYMENTS_ENVIRONMENT if a.provider=='quickbooks_payments' else ('production' if str(settings.STRIPE_SECRET_KEY or '').startswith('sk_live_') else 'sandbox')
    await append_ledger_event(db,settlement=s,attempt=a,event_type='card_submission_protocol',idempotency_key=f'attempt:{a.id}:protocol:v1',actor=actor,
        evidence=dict(version=1,provider=a.provider,provider_account_id=a.provider_account_id,configuration_version=a.provider_configuration_version,environment=environment,
            provider_request_id=f'db048-attempt-{a.id}' if a.provider=='quickbooks_payments' else a.idempotency_key))

async def mark_submission_started(db,a,actor=None):
    from app.services.invoice_settlement_service import append_ledger_event,locked_accessible_invoice_for_attempt
    await locked_accessible_invoice_for_attempt(db,a)
    await db.refresh(a,with_for_update=True)
    if a.state!='pending':error('attempt_transition_conflict','This payment request is no longer payable.')
    info=(await evidence_page(db,[a]))[a.id]
    p=protocol(info)
    if not p or p.get('version')!=1:
        error('provider_review_required','The historical submission outcome is unknown. Ask the shop to review this exact request.')
    environment=settings.QUICKBOOKS_PAYMENTS_ENVIRONMENT if a.provider=='quickbooks_payments' else ('production' if str(settings.STRIPE_SECRET_KEY or '').startswith('sk_live_') else 'sandbox')
    expected_request=f'db048-attempt-{a.id}' if a.provider=='quickbooks_payments' else a.idempotency_key
    if any(p.get(key)!=value for key,value in dict(provider=a.provider,provider_account_id=a.provider_account_id,configuration_version=a.provider_configuration_version,environment=environment,provider_request_id=expected_request).items()):
        error('provider_review_required','The original submission binding is unavailable.')
    if started(info):
        error('provider_outcome_unknown','This request may already have been submitted. Check its existing provider status or ask the shop to review it.')
    if p and not started(info):
        s=info['settlement']
        await append_ledger_event(db,settlement=s,attempt=a,event_type='card_submission_started',idempotency_key=f'attempt:{a.id}:submission:v1',actor=actor,evidence=p)
    # Historic requests remain possibly submitted; never manufacture a V1 protocol.
    await db.commit()
    from app.services.financial_transaction_lock import lock_tenant_financials
    await lock_tenant_financials(db,a.tenant_id)
    await db.refresh(a,with_for_update=True)
    if a.state!='pending':error('attempt_transition_conflict','This payment request changed before submission.')

@dataclass(frozen=True)
class TerminalNoChargeProof:
    tenant_id: UUID
    attempt_id: UUID
    provider: str
    reference: str
    proof_kind: str

async def authorize_failure(db,a,proof=None):
    """All internal/card release callers must supply a bound verified result."""
    if a.rail!='card':return
    references={value for value in (a.provider_intent_id,a.provider_charge_id) if value}
    if a.provider=='quickbooks_payments':references.add(f'db048-attempt-{a.id}')
    if (not isinstance(proof,TerminalNoChargeProof) or (proof.tenant_id,proof.attempt_id,proof.provider)!=(a.tenant_id,a.id,a.provider)
        or a.received_amount is not None or a.payment_id is not None
        or proof.reference not in references):
        error('provider_review_required','A card request cannot be released without terminal provider proof.')

async def locked_context(db,attempt_id,*,actor=None,guest_invoice=None,guest_customer_id=None):
    from app.services.financial_transaction_lock import lock_tenant_financials
    from app.services.invoice_settlement_service import locked_accessible_invoice_for_attempt
    tenant_id=guest_invoice.tenant_id if guest_invoice else actor.tenant_id
    await lock_tenant_financials(db,tenant_id)
    if actor is not None:
        from app.db.models.user import User
        from app.db.models.user_customer_link import UserCustomerLink
        from app.core.dependencies import RequestUserPrincipal
        customer_actor=actor.role==UserRole.CUSTOMER
        requested_customer_id=actor.customer_id if customer_actor else None
        if not customer_actor and not money_staff(actor):error('invoice_not_found','Invoice not found.',404)
        current=await db.scalar(select(User).where(User.id==identity_user(actor).id,User.is_active.is_(True),User.deleted_at.is_(None)).with_for_update().execution_options(populate_existing=True))
        if not current:error('invoice_not_found','Invoice not found.',404)
        if customer_actor:
            if current.role!=UserRole.CUSTOMER:error('invoice_not_found','Invoice not found.',404)
            if isinstance(actor,RequestUserPrincipal):
                link=await db.scalar(select(UserCustomerLink).where(UserCustomerLink.user_id==current.id,UserCustomerLink.tenant_id==tenant_id,UserCustomerLink.customer_id==requested_customer_id,UserCustomerLink.deleted_at.is_(None)).with_for_update().execution_options(populate_existing=True))
                if not link:error('invoice_not_found','Invoice not found.',404)
            elif current.tenant_id!=tenant_id or current.customer_id!=requested_customer_id:error('invoice_not_found','Invoice not found.',404)
        elif current.tenant_id!=tenant_id or not money_staff(current):error('invoice_not_found','Invoice not found.',404)
    a=await db.scalar(select(Attempt).where(Attempt.id==attempt_id,Attempt.tenant_id==tenant_id,Attempt.deleted_at.is_(None)))
    if not a:error('invoice_not_found','Invoice not found.',404)
    if guest_invoice:
        if a.invoice_id!=guest_invoice.id or a.customer_id!=guest_customer_id or a.subject_type!='guest':error('invoice_not_found','Invoice not found.',404)
    else:
        from app.api.v1.endpoints.invoice_settlements import invoice_for_principal
        if actor.role!=UserRole.CUSTOMER and not money_staff(actor):error('invoice_not_found','Invoice not found.',404)
        invoice,_,customer_id=await invoice_for_principal(db,a.invoice_id,actor)
        if a.customer_id!=customer_id:error('invoice_not_found','Invoice not found.',404)
    invoice=await locked_accessible_invoice_for_attempt(db,a)
    s=await db.scalar(select(Settlement).where(Settlement.id==a.settlement_id,Settlement.tenant_id==tenant_id).with_for_update().execution_options(populate_existing=True))
    a=await db.scalar(select(Attempt).where(Attempt.id==a.id,Attempt.tenant_id==tenant_id).with_for_update().execution_options(populate_existing=True))
    if not s or s.invoice_id!=a.invoice_id or s.customer_id!=a.customer_id:error('provider_review_required','The payment request binding requires review.')
    return a,s,invoice

async def staff_detail(db,a,*,actor):
    if not money_staff(actor):error('invoice_not_found','Invoice not found.',404)
    with getattr(db,'no_autoflush',nullcontext()):
        info=(await evidence_page(db,[a]))[a.id];b=binding(a,info)
        from app.services.customer_efs import summaries
        info['efs']=(await summaries(db,[a],actor=actor,audience='staff')).get(a.id)
        missing=[key for key in ('provider_account_id','environment','configuration_version') if not b.get(key)]
        return dict(resolution=projection(a,info,actor=actor,audience='staff'),binding=b,
            evidence_requirements=dict(can_submit_terminal_evidence=a.state=='pending' and a.rail=='card' and not info['blocked'] and not missing,requires_provider_case=True,requires_document=False,
                allowed_kinds=['provider_terminal_no_charge','provider_cancelled'],missing_binding_fields=missing,message='Obtain terminal confirmation for this exact request from the provider. Absence of a transaction is not proof.'),
            history=[dict(event_id=str(e.id),action=(e.evidence_snapshot or {}).get('action',e.event_type),occurred_at=e.occurred_at,actor_display=e.actor_name_snapshot,reason=(e.evidence_snapshot or {}).get('reason'),proof_kind=(e.evidence_snapshot or {}).get('proof_kind'),evidence_reference=(e.evidence_snapshot or {}).get('evidence_reference'),provider_case_reference=(e.evidence_snapshot or {}).get('provider_case_reference')) for e in info['events'] if e.event_type in {'resolution_command','review_requested','attempt_cancelled','attempt_terminal_released'}])

async def _release(db,a,s,*,actor,event_type,key,evidence):
    from app.services.invoice_settlement_service import append_ledger_event,settlement_state,money,current_zelle_attempt_matches
    if a.state!='pending' or a.received_amount is not None or a.payment_id is not None:error('attempt_resolution_not_allowed','This request cannot be released.')
    info=(await evidence_page(db,[a]))[a.id]
    if info['blocked']:error('provider_review_required','Financial activity requires shop review.')
    reserved=await db.scalar(select(func.coalesce(func.sum(Attempt.principal_amount),0)).where(Attempt.tenant_id==a.tenant_id,Attempt.settlement_id==s.id,Attempt.state=='pending',Attempt.deleted_at.is_(None)))
    if money(s.active_pending_principal)!=money(reserved) or money(s.active_pending_principal)<money(a.principal_amount):error('provider_review_required','The reserved amount requires reconciliation.')
    if a.rail=='zelle':
        from app.db.models.invoice import Invoice
        invoice=await db.get(Invoice,a.invoice_id)
        if invoice.zelle_pending_submitted_at:
            others=await db.scalar(select(Attempt.id).where(Attempt.tenant_id==a.tenant_id,Attempt.invoice_id==a.invoice_id,Attempt.id!=a.id,Attempt.rail=='zelle',Attempt.state=='pending',Attempt.deleted_at.is_(None)).limit(1))
            if current_zelle_attempt_matches(invoice=invoice,settlement=s,attempt=a) and not others:
                invoice.zelle_pending_submitted_at=None
                invoice.zelle_pending_sender_email=None;invoice.zelle_pending_sender_phone=None;invoice.zelle_pending_notes=None
            else:evidence={**evidence,'legacy_projection_review_required':True}
    prior=s.state;s.active_pending_principal=money(s.active_pending_principal)-money(a.principal_amount)
    s.version+=1;a.version+=1;a.state='failed';a.failure_code='request_cancelled' if event_type=='attempt_cancelled' else 'reviewed_terminal_release';a.failed_at=datetime.now(timezone.utc)
    s.state=settlement_state(s)
    await append_ledger_event(db,settlement=s,attempt=a,event_type=event_type,idempotency_key=key,actor=actor,prior_state=prior,new_state=s.state,pending_delta=-money(a.principal_amount),evidence={**evidence,'resulting_attempt_version':a.version,'resulting_settlement_version':s.version})
    await db.flush()

async def _provider_result(db,a,*,cancel=False,reference=None):
    """No create/search/refund. Only the exact bound provider object is inspected."""
    from app.db.models.quickbooks_connection import QuickBooksConnection
    from app.db.models.invoice_settlement import TenantPaymentProviderConfiguration
    info=(await evidence_page(db,[a]))[a.id];p=protocol(info)
    if not p:error('provider_review_required','Historical provider environment requires support review.')
    current_environment=settings.QUICKBOOKS_PAYMENTS_ENVIRONMENT if a.provider=='quickbooks_payments' else ('production' if str(settings.STRIPE_SECRET_KEY or '').startswith('sk_live_') else 'sandbox')
    if p.get('environment')!=current_environment:error('provider_review_required','The original provider environment is unavailable.')
    if a.provider=='stripe_connect':
        import stripe
        from app.services.stripe_payment_finalization import validate_db048_stripe_payment_intent
        identity=reference or a.provider_intent_id
        if not identity:error('provider_outcome_unknown','The provider reference is unknown. Ask the shop to review it.')
        try:
            raw=stripe.PaymentIntent.retrieve(identity,stripe_account=a.provider_account_id)
            if raw.get('livemode') is not (p['environment']=='production'):error('provider_review_required','Provider environment requires review.')
            checked=await validate_db048_stripe_payment_intent(db=db,payment_intent=raw,trusted_provider_account_id=a.provider_account_id,attempt=a,allowed_statuses={'succeeded','canceled','requires_payment_method','requires_confirmation','requires_action','processing','requires_capture'})
            if cancel and checked.status in {'requires_payment_method','requires_confirmation','requires_action'} and type(raw.get('amount_received')) is int and raw.get('amount_received')==0 and type(raw.get('amount_capturable')) is int and raw.get('amount_capturable')==0:
                stripe.PaymentIntent.cancel(identity,stripe_account=a.provider_account_id,idempotency_key=f'db048-resolution-cancel-{a.id}')
                raw=stripe.PaymentIntent.retrieve(identity,stripe_account=a.provider_account_id)
                if raw.get('livemode') is not (p['environment']=='production'):error('provider_review_required','Provider environment requires review.')
                checked=await validate_db048_stripe_payment_intent(db=db,payment_intent=raw,trusted_provider_account_id=a.provider_account_id,attempt=a,allowed_statuses={'succeeded','canceled','processing','requires_payment_method','requires_confirmation','requires_action','requires_capture'})
            if checked.status=='succeeded':return 'received',checked.latest_charge_id,identity
            if checked.status=='canceled' and type(raw.get('amount_received')) is int and raw.get('amount_received')==0 and type(raw.get('amount_capturable')) is int and raw.get('amount_capturable')==0:return 'terminal',None,identity
            return 'pending',None,identity
        except stripe.error.StripeError:return 'pending',None,identity
    if a.provider=='quickbooks_payments':
        from app.services.quickbooks_payments_service import get_charge,is_successful_charge,QuickBooksPaymentError
        identity=reference or a.provider_charge_id
        if not identity:error('provider_outcome_unknown','The provider reference is unknown. Ask the shop to review it.')
        cfg=await db.scalar(select(TenantPaymentProviderConfiguration).where(TenantPaymentProviderConfiguration.tenant_id==a.tenant_id,TenantPaymentProviderConfiguration.version==a.provider_configuration_version))
        connection=await db.scalar(select(QuickBooksConnection).where(QuickBooksConnection.tenant_id==a.tenant_id,QuickBooksConnection.deleted_at.is_(None),QuickBooksConnection.status=='connected'))
        if not cfg or not connection or connection.realm_id!=cfg.qbo_realm_snapshot or a.provider_account_id!=cfg.provider_account_snapshot:error('provider_review_required','The original merchant binding is unavailable.')
        # An unbound supplied reference cannot prove request provenance merely by amount.
        if identity!=a.provider_charge_id:error('provider_review_required','A support case must establish exact request provenance before this reference can be used.')
        try:charge=await get_charge(connection=connection,charge_id=identity)
        except QuickBooksPaymentError:return 'pending',None,identity
        if str(charge.id)!=identity or Decimal(charge.amount)!=Decimal(a.provider_charge_amount) or (charge.raw or {}).get('currency')!='USD':error('provider_review_required','Provider payment binding requires review.')
        if is_successful_charge(charge):return 'received',charge.id,identity
        if charge.status.casefold() in {'failed','declined','cancelled','canceled','voided'}:return 'terminal',None,identity
        return 'pending',None,identity
    error('attempt_resolution_not_allowed','This payment provider does not support status checking.')

async def execute(db,attempt_id,command,key,*,actor=None,guest_invoice=None,guest_customer_id=None,step_up_context=None):
    from app.services.invoice_settlement_service import append_ledger_event,confirm_attempt,SettlementDomainError
    from app.db.models.tenant import Tenant
    if not key or not 8<=len(key.strip())<=200:error('idempotency_key_invalid','Use an Idempotency-Key between 8 and 200 characters.',422)
    key=key.strip();event_key='resolution:'+key
    a,s,invoice=await locked_context(db,attempt_id,actor=actor,guest_invoice=guest_invoice,guest_customer_id=guest_customer_id)
    audience='guest' if guest_invoice else 'staff' if money_staff(actor) else 'customer'
    from app.services.customer_efs import protected,claim_for,reject_secret
    if protected(a):
        from app.core import efs_crypto
        from app.services.customer_efs import key as efs_command_key
        try:code=efs_crypto.decrypt(await claim_for(db,a,True))
        except efs_crypto.EfsCryptoUnavailable:error('efs_unavailable','EFS is unavailable. Contact the shop.',503)
        reject_secret(code,command.reason,command.reason_code)
        key=efs_command_key(key,a.tenant_id);event_key='resolution:'+key
        if command.action!='cancel_unsent' or not command.reason or len(command.reason.strip())<3:error('efs_cancel_confirmation_required','Confirm this request cancellation and enter a reason.',422)
    body=command.model_dump(mode='json',exclude={'token'})
    request_hash=digest(dict(command=body,attempt_id=str(a.id),invoice_id=str(invoice.id),tenant_id=str(a.tenant_id),customer_id=str(a.customer_id),actor_id=str(identity_user(actor).id) if actor else None,subject=audience))
    previous=await db.scalar(select(Event).where(Event.tenant_id==a.tenant_id,Event.idempotency_key==event_key))
    if previous:
        if previous.attempt_id!=a.id or previous.evidence_snapshot.get('request_sha256')!=request_hash:error('idempotency_conflict','This key belongs to a different resolution command.')
        return a,s
    if a.version!=command.expected_attempt_version:error('stale_attempt_version','The payment request changed. Refresh before continuing.',current_version=a.version)
    if s.version!=command.expected_settlement_version:error('stale_settlement_version','The invoice balance changed. Refresh before continuing.',current_version=s.version)
    info=(await evidence_page(db,[a]))[a.id]
    from app.services.customer_efs import summaries
    info['efs']=(await summaries(db,[a],actor=actor,audience=audience,customer_id=guest_customer_id)).get(a.id)
    dto=projection(a,info,actor=actor,audience=audience,customer_id=guest_customer_id)
    if a.state!='pending':error('attempt_resolution_not_allowed','This request was already resolved. Refresh its current status.')
    allowed=getattr(dto.actions,command.action)
    if not allowed:error('attempt_resolution_not_allowed','This action is not available for this payment request.')
    private=dict(action=command.action,request_sha256=request_hash,reason_code=command.reason_code,reason=(command.reason or '').strip(),expected_attempt_version=command.expected_attempt_version,expected_settlement_version=command.expected_settlement_version,resulting_attempt_version=a.version,resulting_settlement_version=s.version,binding=binding(a,info))
    if command.action=='cancel_unsent' and a.rail=='zelle':
        if command.transfer_not_sent_confirmed is not True:error('transfer_not_sent_confirmation_required','Confirm that the transfer was not sent.',422)
        if money_staff(actor) and not (command.reason or '').strip():error('resolution_reason_required','Explain why this request was not sent.',422)
    if command.action=='release_with_terminal_evidence':
        if not money_staff(actor) or not command.evidence or not (command.reason or '').strip():error('terminal_evidence_required','A reason and complete terminal provider evidence are required.',422)
        b=binding(a,info);ev=command.evidence.model_dump(mode='json')
        if any(ev.get(k)!=b.get(k) for k in ('provider','provider_account_id','environment','configuration_version','provider_request_id','evidence_context_sha256')) or stamp(command.evidence.attempted_at)!=stamp(a.created_at):error('evidence_binding_changed','Refresh the exact provider context before reviewing evidence.')
        if command.evidence.evidence_sha256 or command.evidence.evidence_reference.startswith(('http:','https:','file:','upload:')):error('terminal_evidence_document_unavailable','Use a documented provider support-case reference; uploaded-file proof is not available in this workflow.',422)
        start,end=stamp(command.evidence.review_window_start),stamp(command.evidence.review_window_end)
        if start>stamp(a.created_at) or end<stamp(a.created_at) or end>datetime.now(timezone.utc) or start>end:error('terminal_evidence_window_invalid','The provider review window must cover this exact attempt.',422)
        from app.core.payment_step_up import authorize_step_up,PaymentStepUpScope,payment_step_up_mutation_result
        if step_up_context is None:error('payment_step_up_required','Verify your identity before releasing this payment request.',403)
        grant=await authorize_step_up(db,context=step_up_context,required_scope=PaymentStepUpScope.ATTEMPTS_RESOLVE,consume=False)
        private.update(proof_kind=command.evidence.kind,evidence_reference=command.evidence.evidence_reference,provider_case_reference=command.evidence.provider_case_reference,terminal_evidence=ev)
    await append_ledger_event(db,settlement=s,attempt=a,event_type='resolution_command',idempotency_key=event_key,actor=actor,evidence=private)
    await db.flush()
    if command.action=='request_review':
        a.version+=1;s.version+=1
        await append_ledger_event(db,settlement=s,attempt=a,event_type='review_requested',idempotency_key=event_key+':review',actor=actor,evidence={**private,'resulting_attempt_version':a.version,'resulting_settlement_version':s.version})
    elif command.action=='cancel_unsent' and (a.rail=='zelle' or protected(a) or (protocol(info) and not started(info) and not a.provider_intent_id and not a.provider_charge_id)):
        await _release(db,a,s,actor=actor,event_type='attempt_cancelled',key=event_key+':cancel',evidence=private)
    else:
        # The command is durable before external reads/cancellation. Replays never repeat IO.
        await db.commit()
        try:
            outcome,charge_id,reference=await _provider_result(db,a,cancel=command.action=='cancel_unsent',reference=command.evidence.provider_reference if command.evidence else None) if (a.provider_intent_id or a.provider_charge_id or (command.evidence and command.evidence.provider_reference)) else ('manual',None,None)
        except SettlementDomainError as provider_error:
            if command.action=='release_with_terminal_evidence' or provider_error.code not in {'provider_review_required','provider_outcome_unknown','provider_payment_mismatch'}:raise
            outcome,charge_id,reference='pending',None,None
        if outcome=='received':
            # A trusted provider receipt remains a fact when the initiating
            # user's authority changes while the provider read is in flight.
            # Reconcile as system, commit the fact, then reauthorize disclosure.
            from app.services.financial_transaction_lock import lock_tenant_financials
            original_tenant_id=a.tenant_id
            await lock_tenant_financials(db,original_tenant_id)
            a=await db.scalar(select(Attempt).where(Attempt.id==attempt_id,Attempt.tenant_id==original_tenant_id,Attempt.deleted_at.is_(None)).with_for_update().execution_options(populate_existing=True))
            if not a:error('invoice_not_found','Invoice not found.',404)
            s=await db.scalar(select(Settlement).where(Settlement.id==a.settlement_id,Settlement.tenant_id==a.tenant_id).with_for_update().execution_options(populate_existing=True))
            tenant=await db.get(Tenant,a.tenant_id)
            try:
                async with db.begin_nested():
                    result=await confirm_attempt(db,attempt_id=a.id,tenant=tenant,actor=None,expected_attempt_version=a.version,idempotency_key=event_key+':receipt',received_principal=a.principal_amount,provider_charge_id=charge_id,provider_event_id=event_key,verified_provider_fact=True)
            except SettlementDomainError as admission_error:
                a=await db.scalar(select(Attempt).where(Attempt.id==attempt_id,Attempt.tenant_id==original_tenant_id).with_for_update().execution_options(populate_existing=True))
                s=await db.scalar(select(Settlement).where(Settlement.id==a.settlement_id,Settlement.tenant_id==original_tenant_id).with_for_update().execution_options(populate_existing=True))
                # Inaccessible documents are never resurrected. Retain the
                # independently verified observation for explicit reconciliation.
                await append_ledger_event(db,settlement=s,attempt=a,event_type='provider_receipt_needs_review',idempotency_key=event_key+':receipt-review',actor=None,evidence={**private,'proof_kind':'provider_verified_receipt','provider_reference':reference,'provider_charge_id':charge_id,'admission_code':admission_error.code,'resulting_attempt_version':a.version,'resulting_settlement_version':s.version})
            else:
                a,s=result.attempt,result.settlement
                await append_ledger_event(db,settlement=s,attempt=a,event_type='resolution_completed',idempotency_key=event_key+':received',actor=None,evidence={**private,'proof_kind':'provider_verified_receipt','provider_reference':reference,'provider_charge_id':charge_id,'resulting_attempt_version':a.version,'resulting_settlement_version':s.version})
            await db.commit()
            if guest_invoice is not None and hasattr(command,'token'):
                from app.api.v1.endpoints.invoice_access import _load_db048_guest_context
                fresh_invoice,_,fresh_customer,_=await _load_db048_guest_context(db,command.token)
                if fresh_invoice.id!=guest_invoice.id or fresh_customer.id!=guest_customer_id:error('invoice_not_found','Invoice not found.',404)
                guest_invoice=fresh_invoice
            a,s,invoice=await locked_context(db,attempt_id,actor=actor,guest_invoice=guest_invoice,guest_customer_id=guest_customer_id)
            return a,s
        if guest_invoice is not None and hasattr(command,'token'):
            from app.api.v1.endpoints.invoice_access import _load_db048_guest_context
            fresh_invoice,_,fresh_customer,_=await _load_db048_guest_context(db,command.token)
            if fresh_invoice.id!=guest_invoice.id or fresh_customer.id!=guest_customer_id:error('invoice_not_found','Invoice not found.',404)
            guest_invoice=fresh_invoice
        a,s,invoice=await locked_context(db,attempt_id,actor=actor,guest_invoice=guest_invoice,guest_customer_id=guest_customer_id)
        if a.state!='pending':error('attempt_resolution_not_allowed','The payment request changed while its provider status was checked.')
        if outcome=='terminal' or (outcome=='manual' and command.action=='release_with_terminal_evidence'):
            if a.version!=command.expected_attempt_version or s.version!=command.expected_settlement_version:
                error('attempt_resolution_not_allowed','The payment request changed during provider review. Refresh before proceeding.')
            if command.action=='release_with_terminal_evidence':
                from app.core.payment_step_up import authorize_step_up,PaymentStepUpScope,payment_step_up_mutation_result
                grant=await authorize_step_up(db,context=step_up_context,required_scope=PaymentStepUpScope.ATTEMPTS_RESOLVE,consume=True)
                db.add(payment_step_up_mutation_result(context=step_up_context,scope=PaymentStepUpScope.ATTEMPTS_RESOLVE,grant=grant,succeeded=True,metadata={'action':'payment_attempt.resolve','attempt_id':str(a.id)}))
            await _release(db,a,s,actor=actor,event_type='attempt_cancelled' if command.action=='cancel_unsent' else 'attempt_terminal_released',key=event_key+':release',evidence={**private,'proof_kind':private.get('proof_kind','provider_terminal_no_charge'),'provider_reference':reference})
        else:
            a.version+=1;s.version+=1
            await append_ledger_event(db,settlement=s,attempt=a,event_type='review_requested',idempotency_key=event_key+':pending',actor=actor,evidence={**private,'proof_kind':'provider_outcome_unknown','resulting_attempt_version':a.version,'resulting_settlement_version':s.version})
    await db.flush()
    return a,s
