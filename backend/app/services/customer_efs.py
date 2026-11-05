"""Protected customer EFS claims and explicit shop-attested receipts. No provider IO."""
from contextlib import nullcontext
from dataclasses import dataclass
from decimal import Decimal,DecimalException
import hashlib,hmac,json,re
from uuid import uuid4
from sqlalchemy import select,func
from app.core import efs_crypto as crypto
from app.core.dependencies import identity_user
from app.db.models.efs_instrument import EfsInstrumentSubmission as Claim
from app.db.models.invoice_settlement import InvoicePaymentAttempt as Attempt,InvoiceSettlement as Settlement,InvoicePaymentLedgerEvent as Event
from app.db.models.payment import Payment,PaymentMethod
from app.db.models.user import UserRole
from app.schemas.efs_submission import EfsSummary
from app.services.payment_attempt_resolution import money_staff

SOURCE='customer_efs_v1'
_SEAL=object()
def protected(a):return a.source==SOURCE or bool((a.manual_evidence or {}).get('efs_submission_id'))
def fail(code,message,status=409):
    from app.services.invoice_settlement_service import SettlementDomainError
    raise SettlementDomainError(code,message,status_code=status)
def available():
    try:return crypto.keys()
    except crypto.EfsCryptoUnavailable:fail('efs_unavailable','EFS is unavailable. Contact the shop.',503)
async def readiness(db):
    active,ciphers,_=available()
    stored=(await db.execute(select(Claim.key_version,Claim.fingerprint_key_identity).distinct())).all()
    identity=crypto.key_identity()
    if any(version not in ciphers or not hmac.compare_digest(identity,key_identity) for version,key_identity in stored):fail('efs_unavailable','EFS is unavailable. Contact the shop.',503)
    return active

def key(value,tenant):
    if not isinstance(value,str) or not 8<=len(value.strip())<=200:fail('efs_fields_invalid','Check the payment fields and try again.',422)
    available();return crypto.command_key(value.strip(),tenant)
def request_hash(body):return hashlib.sha256(json.dumps(body,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()

def reject_secret(code,*values):
    # ASCII digits separated by punctuation/spacing are still the bearer code.
    pattern=r'[\s-]*'.join(re.escape(c) for c in code)
    if any(isinstance(v,str) and re.search(pattern,v) for v in values):fail('efs_reference_invalid','Use the merchant authorization reference, not the MoneyCode.',422)

@dataclass(frozen=True)
class EfsAdmission:
    tenant_id:object
    invoice_id:object
    customer_id:object
    sidecar_id:object
    last4:str
    seal:object

def valid_admission(proof,tenant,invoice,customer,source):
    return isinstance(proof,EfsAdmission) and proof.seal is _SEAL and (proof.tenant_id,proof.invoice_id,proof.customer_id,source)==(tenant.id,invoice.id,customer,SOURCE)

@dataclass(frozen=True)
class EfsReceiptProof:
    tenant_id:object
    attempt_id:object
    sidecar_id:object
    actor_id:object
    seal:object
    received_amount:object=None
    authorization_reference:str=''
    observation_id:object=None

async def claim_for(db,a,lock=False):
    q=select(Claim).where(Claim.tenant_id==a.tenant_id,Claim.attempt_id==a.id)
    if lock:q=q.with_for_update().execution_options(populate_existing=True)
    row=await db.scalar(q)
    if not row or (row.invoice_id,row.settlement_id,row.customer_id)!=(a.invoice_id,a.settlement_id,a.customer_id):fail('efs_binding_review','This EFS request requires shop review.')
    return row

async def validate_receipt_proof(db,a,actor,proof,received_amount=None,reference=None):
    if not isinstance(proof,EfsReceiptProof) or proof.seal is not _SEAL or not money_staff(actor) or actor.tenant_id!=a.tenant_id:fail('efs_verification_required','Use the EFS verification action for this request.')
    claim=await claim_for(db,a,True)
    if (proof.tenant_id,proof.attempt_id,proof.sidecar_id,proof.actor_id)!=(a.tenant_id,a.id,claim.id,identity_user(actor).id):fail('efs_verification_required','Use the EFS verification action for this request.')
    try:code=crypto.decrypt(claim)
    except crypto.EfsCryptoUnavailable:fail('efs_unavailable','EFS is unavailable. Contact the shop.',503)
    reject_secret(code,reference)
    if proof.received_amount!=received_amount or proof.authorization_reference!=reference:
        fail('efs_verification_required','The received amount must match the reviewed receipt.')
    if proof.observation_id is None and received_amount!=a.principal_amount:
        fail('efs_verification_required','Use the recorded receipt difference review.')
    if proof.observation_id is not None and not await review_admission(db,None,a,proof):
        fail('efs_verification_required','The recorded receipt requires review.')
    return claim

def legacy_code(value):
    if not isinstance(value,str):raise ValueError('Not a recognized legacy EFS code')
    return crypto.normalize(re.sub(r'[\s-]','',value.strip()))

def legacy_candidates(*values):
    candidates=set()
    pending=list(values)
    while pending:
        value=pending.pop()
        if isinstance(value,dict):
            pending.extend(value.keys());pending.extend(value.values());continue
        if isinstance(value,(list,tuple)):
            pending.extend(value);continue
        if not isinstance(value,str):continue
        for match in re.finditer(r'(?=([0-9](?:[\s-]*[0-9]){9}))',value):
            candidate=re.sub(r'[\s-]','',match.group(1))
            if len(candidate)==10:candidates.add(candidate)
    return candidates

async def guard_legacy(db,tenant_id,evidence):
    """Reject a claimed bearer instrument anywhere in legacy financial evidence."""
    if (evidence or {}).get('fleet_provider')!='EFS':return
    candidates=legacy_candidates(evidence or {})
    if not candidates:return
    if not await db.scalar(select(Claim.id).where(Claim.tenant_id==tenant_id).limit(1)):return
    await readiness(db)
    fingerprints=[crypto.fingerprint(code,tenant_id) for code in candidates]
    if await db.scalar(select(Claim.id).where(Claim.tenant_id==tenant_id,Claim.code_fingerprint.in_(fingerprints)).limit(1)):
        fail('efs_code_requires_review','This code requires shop review. Contact the shop.')

async def legacy_claimed(db,tenant_id,code):
    from app.services.fleet_payment_evidence import fleet_reference_fingerprint
    candidate=fleet_reference_fingerprint({'fleet_provider':'EFS','reference_number':code})
    # No secret, unhashed code or unkeyed candidate is ever a SQL parameter.
    rows=(await db.execute(select(Attempt.manual_reference_fingerprint,Attempt.manual_evidence).where(Attempt.tenant_id==tenant_id,Attempt.rail=='fleet_payment',Attempt.source!=SOURCE))).all()
    for fingerprint,evidence in rows:
        if (evidence or {}).get('fleet_provider')!='EFS':continue
        if fingerprint and hmac.compare_digest(candidate,fingerprint):return True
        if any(hmac.compare_digest(code,other) for other in legacy_candidates(evidence or {})):return True
    refs=(await db.scalars(select(Payment.reference_number).where(Payment.tenant_id==tenant_id,Payment.method==PaymentMethod.FLEET_PAYMENT,Payment.payment_provider=='EFS'))).all()
    for reference in refs:
        if any(hmac.compare_digest(code,other) for other in legacy_candidates(reference)):return True
    return False

async def unresolved(db,tenant_id,invoice_id=None,attempt_ids=None):
    query=select(Event).where(Event.tenant_id==tenant_id,Event.event_type.in_(['efs_received_difference','efs_difference_resolved']))
    if invoice_id is not None:query=query.where(Event.invoice_id==invoice_id)
    if attempt_ids is not None:query=query.where(Event.attempt_id.in_(attempt_ids))
    events=(await db.scalars(query)).all();observed=[e for e in events if e.event_type=='efs_received_difference'];resolved=[e for e in events if e.event_type=='efs_difference_resolved']
    from uuid import UUID
    ids=[]
    for row in resolved:
        try:ids.append(UUID(row.evidence_snapshot.get('payment_id')))
        except (ValueError,TypeError,AttributeError):continue
    payments={str(p.id):p for p in (await db.scalars(select(Payment).where(Payment.tenant_id==tenant_id,Payment.id.in_(ids),Payment.deleted_at.is_(None)))).all()} if ids else {}
    attempts={a.id:a for a in (await db.scalars(select(Attempt).where(Attempt.tenant_id==tenant_id,Attempt.id.in_([e.attempt_id for e in observed])))).all()} if observed else {}
    pending=[]
    for event in observed:
        settled=False;a=attempts.get(event.attempt_id);evidence=event.evidence_snapshot or {}
        for resolution in resolved:
            result=resolution.evidence_snapshot or {};payment=payments.get(result.get('payment_id'))
            try:actual=Decimal(evidence.get('actual_received_amount','NaN'))
            except Exception:actual=Decimal('NaN')
            if (a and payment and result.get('observation_id')==str(event.id) and resolution.attempt_id==event.attempt_id and resolution.invoice_id==event.invoice_id and resolution.settlement_id==event.settlement_id
                and a.payment_id==payment.id and payment.invoice_payment_attempt_id==a.id and payment.invoice_id==a.invoice_id==event.invoice_id and a.state in {'confirmed','refunded','reversed'}
                and payment.reference_number==evidence.get('authorization_reference')==a.provider_reference and actual.is_finite() and actual==a.received_amount
                and str(a.applied_principal_amount)==result.get('applied_principal_amount') and str(a.unapplied_amount)==result.get('unapplied_amount') and result.get('submission_id')==evidence.get('submission_id')):
                settled=True;break
        if not settled:pending.append(event)
    return pending

async def has_review(db,tenant_id,invoice_id):return bool(await unresolved(db,tenant_id,invoice_id))

async def review_admission(db,invoice,a,proof):
    if not isinstance(proof,EfsReceiptProof) or proof.seal is not _SEAL or not proof.observation_id:return False
    row=await db.scalar(select(Event).where(Event.id==proof.observation_id,Event.tenant_id==a.tenant_id,Event.invoice_id==a.invoice_id,Event.attempt_id==a.id,Event.settlement_id==a.settlement_id,Event.event_type=='efs_received_difference'))
    if not row:return False
    evidence=row.evidence_snapshot or {}
    try:amount=Decimal(evidence.get('actual_received_amount','NaN'))
    except Exception:return False
    return evidence.get('merchant_authorized') is True and evidence.get('submission_id')==str(proof.sidecar_id) and amount.is_finite() and amount>0 and amount==proof.received_amount and evidence.get('authorization_reference')==proof.authorization_reference

async def summaries(db,attempts,*,actor=None,audience='customer',customer_id=None):
    ids=[a.id for a in attempts if protected(a)]
    if not ids:return {}
    with getattr(db,'no_autoflush',nullcontext()):
        tenant=attempts[0].tenant_id
        claims={r.attempt_id:r for r in (await db.scalars(select(Claim).where(Claim.tenant_id==tenant,Claim.attempt_id.in_(ids)))).all()}
        events=(await db.scalars(select(Event).where(Event.tenant_id==tenant,Event.attempt_id.in_(ids),Event.event_type.in_(['efs_received_difference','attempt_cancelled','efs_rejected'])))).all()
        kinds={identity:{e.event_type for e in events if e.attempt_id==identity} for identity in ids}
        observations=await unresolved(db,tenant,attempt_ids=ids)
        result={}
        try:
            _,ciphers,_=crypto.keys();key_identity=crypto.key_identity()
        except crypto.EfsCryptoUnavailable:
            ciphers={};key_identity=None
        from app.services.payment_attempt_resolution import eligible_owner
        for a in attempts:
            if a.id not in ids:continue
            row=claims.get(a.id);differences=[e for e in observations if e.attempt_id==a.id];review=not row or bool(differences)
            status='review_required' if review else 'received' if a.state in {'confirmed','refunded','reversed'} else 'cancelled' if 'attempt_cancelled' in kinds[a.id] else 'rejected' if 'efs_rejected' in kinds[a.id] or a.state in {'failed','expired'} else 'awaiting_verification'
            staff=money_staff(actor) and actor.tenant_id==a.tenant_id
            pending=a.state=='pending' and not review and a.received_amount is None
            secret_ready=bool(row and row.key_version in ciphers and row.fingerprint_key_identity==key_identity)
            can_cancel=pending and secret_ready and eligible_owner(a,actor,audience,customer_id)
            difference=None
            if staff and row and len(differences)==1:
                observed=differences[0];data=observed.evidence_snapshot or {}
                try:
                    from app.schemas.efs_submission import exact_money
                    actual=exact_money(Decimal(data['actual_received_amount']))
                    if data.get('merchant_authorized') is True and data.get('submission_id')==str(row.id):difference=dict(observation_id=str(observed.id),requested_amount=f'{a.principal_amount:.2f}',actual_received_amount=f'{actual:.2f}',currency='USD',authorization_reference=data.get('authorization_reference'))
                except (ValueError,KeyError,TypeError,DecimalException):pass
            result[a.id]=EfsSummary(code_last4=row.last4 if row else '',status=status,can_cancel=can_cancel,can_reveal=staff and secret_ready,can_verify=staff and secret_ready and a.state in {'pending','failed','expired'} and not review,can_reject=staff and pending and secret_ready,can_resolve_received_difference=staff and secret_ready and difference is not None and a.received_amount is None,difference_review=difference)
        return result

async def authorize_submission(db,invoice,tenant,customer_id,actor,body):
    if actor is not None:
        from app.core.dependencies import RequestUserPrincipal
        from app.db.models.user import User
        from app.db.models.user_customer_link import UserCustomerLink
        original_customer=customer_id
        current=await db.scalar(select(User).where(User.id==identity_user(actor).id,User.is_active.is_(True),User.deleted_at.is_(None)).with_for_update().execution_options(populate_existing=True))
        if not current or current.role!=UserRole.CUSTOMER:fail('invoice_not_found','Invoice not found.',404)
        if isinstance(actor,RequestUserPrincipal):
            member=await db.scalar(select(UserCustomerLink).where(UserCustomerLink.user_id==current.id,UserCustomerLink.tenant_id==tenant.id,UserCustomerLink.customer_id==original_customer,UserCustomerLink.deleted_at.is_(None)).with_for_update().execution_options(populate_existing=True))
            if not member:fail('invoice_not_found','Invoice not found.',404)
        elif current.tenant_id!=tenant.id or current.customer_id!=original_customer:fail('invoice_not_found','Invoice not found.',404)
        from app.api.v1.endpoints.invoice_settlements import invoice_for_principal
        refreshed,_,actual=await invoice_for_principal(db,invoice.id,actor)
        if actual!=original_customer:fail('invoice_not_found','Invoice not found.',404)
        return refreshed
    from app.api.v1.endpoints.invoice_access import _load_db048_guest_context
    refreshed,_,actual,_=await _load_db048_guest_context(db,body.token.get_secret_value())
    if refreshed.id!=invoice.id or actual.id!=customer_id:fail('invoice_not_found','Invoice not found.',404)
    return refreshed

async def submit(db,*,invoice,tenant,customer_id,actor,body,idempotency_key):
    from app.services.financial_transaction_lock import lock_tenant_financials
    from app.services.invoice_settlement_service import create_attempt,append_ledger_event
    await lock_tenant_financials(db,tenant.id)
    invoice=await authorize_submission(db,invoice,tenant,customer_id,actor,body)
    if actor is not None and actor.role!=UserRole.CUSTOMER:fail('invoice_not_found','Invoice not found.',404)
    if db.bind.dialect.name=='postgresql':
        from sqlalchemy import text
        await db.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':749852018326118})
        if (await db.scalar(text('SHOW transaction_isolation'))) != 'read committed':fail('efs_unavailable','EFS is unavailable. Contact the shop.',503)
    await readiness(db)
    if not body.submitted_for_verification:fail('efs_confirmation_required','Review the code and amount before submitting.',422)
    code=crypto.normalize(body.code.get_secret_value());fingerprint=crypto.fingerprint(code,tenant.id)
    command=key(idempotency_key,tenant.id)
    data=dict(fingerprint=fingerprint,amount=str(body.amount.quantize(Decimal('.01'))),version=body.expected_settlement_version,invoice_id=str(invoice.id),customer_id=str(customer_id),actor_id=str(identity_user(actor).id) if actor else None,subject='customer' if actor else 'guest',provider='EFS')
    hashed=request_hash(data)
    existing=await db.scalar(select(Attempt).where(Attempt.tenant_id==tenant.id,Attempt.idempotency_key==command))
    if existing:
        claim=await claim_for(db,existing)
        if existing.invoice_id!=invoice.id or existing.customer_id!=customer_id or claim.submission_request_sha256!=hashed:fail('idempotency_conflict','This command belongs to a different request.')
        return existing,await db.get(Settlement,existing.settlement_id)
    if await db.scalar(select(Claim.id).where(Claim.tenant_id==tenant.id,Claim.code_fingerprint==fingerprint).limit(1)) or await legacy_claimed(db,tenant.id,code):fail('efs_code_requires_review','This code requires shop review. Use a different code or contact the shop.')
    sidecar_id=uuid4();admission=EfsAdmission(tenant.id,invoice.id,customer_id,sidecar_id,code[-4:],_SEAL)
    created=await create_attempt(db,invoice=invoice,tenant=tenant,customer_id=customer_id,actor=actor,amount=body.amount,rail='fleet_payment',expected_settlement_version=body.expected_settlement_version,idempotency_key=command,source=SOURCE,subject_type='customer' if actor else 'guest',subject_id=identity_user(actor).id if actor else customer_id,sender_evidence={'source':SOURCE,'fleet_provider':'EFS','code_last4':code[-4:],'efs_submission_id':str(sidecar_id)},efs_admission=admission)
    active,_,_=available()
    row=Claim(id=sidecar_id,tenant_id=tenant.id,invoice_id=invoice.id,settlement_id=created.settlement.id,attempt_id=created.attempt.id,customer_id=customer_id,provider='EFS',key_version=active,code_fingerprint=fingerprint,fingerprint_key_identity=crypto.key_identity(),last4=code[-4:],submission_request_sha256=hashed)
    row.secret_ciphertext=crypto.encrypt(code,row);db.add(row);await db.flush()
    await append_ledger_event(db,settlement=created.settlement,attempt=created.attempt,event_type='efs_submitted',idempotency_key=command+':submitted',actor=actor,evidence={'provider':'EFS','code_last4':row.last4,'submission_id':str(row.id)})
    await notify(db,tenant,created.attempt,row)
    await db.flush();return created.attempt,created.settlement

async def notify(db,tenant,a,claim):
    from app.core.config import settings
    from app.services.pending_zelle_staff_notification_service import enqueue_staff_sms
    if not settings.SMS_AUTOMATION_OUTBOX_ENABLED or not tenant.sms_enabled or not tenant.messaging_enabled:return
    await enqueue_staff_sms(db,tenant_id=tenant.id,domain_event_id=f'invoice:{a.invoice_id}:efs-submission:{a.id}',template_name='pending_efs_staff_submit_sms',body=f'EFS ending {claim.last4} was submitted for ${a.principal_amount:.2f}. Review the payment request and verify merchant authorization before recording receipt.',skip_unconsented=True)

async def staff_context(db,attempt_id,actor):
    from app.services.payment_attempt_resolution import locked_context
    if not money_staff(actor):fail('invoice_not_found','Invoice not found.',404)
    a,s,invoice=await locked_context(db,attempt_id,actor=actor)
    if not protected(a):fail('invoice_not_found','Invoice not found.',404)
    row=await claim_for(db,a,True)
    return a,s,invoice,row

async def reveal(db,attempt_id,actor,body):
    from app.services.invoice_settlement_service import append_ledger_event
    a,s,invoice,row=await staff_context(db,attempt_id,actor)
    if a.version!=body.expected_attempt_version:fail('stale_attempt_version','The payment request changed. Refresh before continuing.')
    try:code=crypto.decrypt(row)
    except crypto.EfsCryptoUnavailable:fail('efs_unavailable','EFS is unavailable. Contact the shop.',503)
    reject_secret(code,body.reason)
    if len(body.reason.strip())<3:fail('efs_reason_required','Enter a reason for viewing the code.',422)
    await append_ledger_event(db,settlement=s,attempt=a,event_type='efs_code_revealed',idempotency_key='efs-reveal:'+str(uuid4()),actor=actor,evidence={'purpose':'merchant_authorization','reason':body.reason.strip(),'submission_id':str(row.id)})
    await db.flush();return {'code':code,'last4':row.last4}

async def verify(db,attempt_id,actor,body,idempotency_key,step_up_context=None):
    from app.services.invoice_settlement_service import append_ledger_event,confirm_attempt
    from app.services.payment_attempt_resolution import _release
    a,s,invoice,row=await staff_context(db,attempt_id,actor)
    command=key(idempotency_key,a.tenant_id)+':verify'
    try:code=crypto.decrypt(row)
    except crypto.EfsCryptoUnavailable:fail('efs_unavailable','EFS is unavailable. Contact the shop.',503)
    reject_secret(code,body.reason,body.authorization_reference,idempotency_key)
    if len(body.reason.strip())<3:fail('efs_reason_required','Enter a verification reason.',422)
    hashed=request_hash({'body':body.model_dump(mode='json'),'attempt_id':str(a.id),'actor_id':str(identity_user(actor).id)})
    previous=await db.scalar(select(Event).where(Event.tenant_id==a.tenant_id,Event.idempotency_key==command))
    if previous:
        if previous.attempt_id!=a.id or previous.evidence_snapshot.get('request_sha256')!=hashed:fail('idempotency_conflict','This verification command has changed.')
        return a,s
    if a.version!=body.expected_attempt_version:fail('stale_attempt_version','The payment request changed. Refresh before continuing.')
    if s.version!=body.expected_settlement_version:fail('stale_settlement_version','The invoice balance changed. Refresh before continuing.')
    invoice_review=await has_review(db,a.tenant_id,a.invoice_id)
    if body.action=='resolve_received_difference':
        return await resolve_difference(db,a,s,invoice,row,actor,body,command,hashed,step_up_context)
    if invoice_review:fail('efs_review_required','The received EFS amount needs shop review before another payment.')
    if a.state not in {'pending','failed','expired'} or a.received_amount is not None:fail('efs_transition_conflict','This EFS request was already received.')
    audit={'request_sha256':hashed,'action':body.action,'reason':body.reason.strip(),'submission_id':str(row.id)}
    if body.action=='reject':
        await _release(db,a,s,actor=actor,event_type='efs_rejected',key=command,evidence=audit)
    else:
        if body.merchant_authorized is not True or body.received_amount is None or not body.authorization_reference or not body.authorization_reference.strip():fail('efs_authorization_required','Record actual merchant authorization and received amount.',422)
        if await legacy_claimed(db,a.tenant_id,code):fail('efs_code_requires_review','This instrument requires shop review before recording another receipt.')
        audit.update(authorization_reference=body.authorization_reference.strip(),merchant_authorized=True,actual_received_amount=str(body.received_amount))
        if body.received_amount!=a.principal_amount or invoice_review:
            a.version+=1;s.version+=1
            await append_ledger_event(db,settlement=s,attempt=a,event_type='efs_received_difference',idempotency_key=command,actor=actor,evidence={**audit,'resulting_attempt_version':a.version,'resulting_settlement_version':s.version})
        else:
            proof=EfsReceiptProof(a.tenant_id,a.id,row.id,identity_user(actor).id,_SEAL,body.received_amount,body.authorization_reference.strip())
            result=await confirm_attempt(db,attempt_id=a.id,tenant=await tenant_for(db,a.tenant_id),actor=actor,expected_attempt_version=a.version,idempotency_key=command+':receipt',received_principal=body.received_amount,reference=body.authorization_reference.strip(),efs_proof=proof)
            a,s=result.attempt,result.settlement
            await append_ledger_event(db,settlement=s,attempt=a,event_type='efs_verified',idempotency_key=command,actor=actor,evidence={**audit,'resulting_attempt_version':a.version,'resulting_settlement_version':s.version})
    await db.flush();return a,s

async def tenant_for(db,tenant_id):
    from app.db.models.tenant import Tenant
    return await db.get(Tenant,tenant_id)

async def resolve_difference(db,a,s,invoice,claim,actor,body,command,hashed,step_up_context):
    from app.core.payment_step_up import authorize_step_up,PaymentStepUpScope,payment_step_up_mutation_result
    from app.services.invoice_settlement_service import confirm_attempt,append_ledger_event
    from app.schemas.efs_submission import exact_money
    if step_up_context is None:fail('payment_step_up_required','Verify your identity before recording this receipt.',403)
    if a.state not in {'pending','failed','expired'} or a.received_amount is not None or a.payment_id is not None:fail('efs_transition_conflict','This EFS receipt was already recorded.')
    observations=await unresolved(db,a.tenant_id,a.invoice_id)
    own=[e for e in observations if e.attempt_id==a.id]
    if len(own)!=1 or own[0].id!=body.observation_id:fail('efs_observation_conflict','The recorded receipt needs further shop review.')
    observation=await db.scalar(select(Event).where(Event.id==body.observation_id,Event.tenant_id==a.tenant_id).with_for_update().execution_options(populate_existing=True))
    data=observation.evidence_snapshot or {}
    if (observation.invoice_id,observation.settlement_id,observation.attempt_id,observation.customer_id)!=(a.invoice_id,a.settlement_id,a.id,a.customer_id) or data.get('submission_id')!=str(claim.id) or data.get('merchant_authorized') is not True:fail('efs_observation_conflict','The receipt observation does not match this request.')
    try:actual=exact_money(Decimal(data['actual_received_amount']));reference=data['authorization_reference'].strip()
    except (ValueError,KeyError,TypeError,AttributeError,DecimalException):fail('efs_observation_conflict','The recorded receipt needs further shop review.')
    try:code=crypto.decrypt(claim)
    except crypto.EfsCryptoUnavailable:fail('efs_unavailable','EFS is unavailable. Contact the shop.',503)
    reject_secret(code,reference,body.reason)
    if await legacy_claimed(db,a.tenant_id,code):fail('efs_code_requires_review','This instrument requires shop review before recording another receipt.')
    if not reference or len(body.reason.strip())<3:fail('efs_observation_conflict','The recorded receipt needs further shop review.')
    grant=await authorize_step_up(db,context=step_up_context,required_scope=PaymentStepUpScope.EFS_RECEIVED_DIFFERENCE,consume=True)
    proof=EfsReceiptProof(a.tenant_id,a.id,claim.id,identity_user(actor).id,_SEAL,actual,reference,observation.id)
    result=await confirm_attempt(db,attempt_id=a.id,tenant=await tenant_for(db,a.tenant_id),actor=actor,expected_attempt_version=a.version,idempotency_key=command+':receipt',received_principal=actual,reference=reference,efs_proof=proof)
    a,s=result.attempt,result.settlement
    await append_ledger_event(db,settlement=s,attempt=a,event_type='efs_difference_resolved',idempotency_key=command,actor=actor,evidence={'request_sha256':hashed,'observation_id':str(observation.id),'submission_id':str(claim.id),'payment_id':str(result.payment.id),'actual_received_amount':str(a.received_amount),'applied_principal_amount':str(a.applied_principal_amount),'unapplied_amount':str(a.unapplied_amount),'reason':body.reason.strip(),'resulting_attempt_version':a.version,'resulting_settlement_version':s.version})
    db.add(payment_step_up_mutation_result(context=step_up_context,scope=PaymentStepUpScope.EFS_RECEIVED_DIFFERENCE,grant=grant,succeeded=True,metadata={'action':'efs.resolve_received_difference','attempt_id':str(a.id),'observation_id':str(observation.id)}))
    await db.flush();return a,s

async def require_efs_feature_ready(db,tenant,invoice_id,*,lock=False):
    """Manual merchant receipt readiness is independent from card authorization."""
    from app.services.invoice_settlement_service import provider_readiness
    from app.core.config import settings
    from uuid import UUID
    try:
        allowed={UUID(value.strip()) for value in settings.EFS_CUSTOMER_ENABLED_TENANT_IDS.split(',') if value.strip()}
    except (ValueError,TypeError,AttributeError):allowed=set()
    if tenant.id not in allowed:fail('efs_unavailable','EFS is unavailable for this shop.',503)
    state=await provider_readiness(db,tenant,invoice_id=invoice_id,lock_ancestry=lock)
    if not state.split_payment_global_gate or not state.split_payment_tenant_gate:fail('split_payments_disabled','Partial payments are not enabled for this shop.')
    card_only={'stripe_connect_platform_approval_missing','stripe_connect_onboarding_incomplete','quickbooks_payments_platform_approval_missing','quickbooks_payments_onboarding_incomplete','quickbooks_payments_provider_identity_missing','provider_not_selected','account_mappings_incomplete'}
    config=state.configuration
    mappings=bool(config and config.check_deposit_account and config.sales_tax_liability_account and config.checking_account)
    if not config or config.writer_strategy!='dieselbridge' or not state.qbo_accounting_ready or not mappings or any(reason not in card_only for reason in state.reasons):
        fail('efs_unavailable','EFS is unavailable for this invoice. Contact the shop.',503)
    return state

async def submit_capability(db,invoice,settlement,tenant,*,actor=None,audience='customer'):
    if audience not in {'customer','guest'}:return False,None
    from app.services.invoice_settlement_service import SettlementDomainError,allocatable_balance
    from app.services.invoice_accounting_policy import require_standard_payment
    try:
        with getattr(db,'no_autoflush',nullcontext()):
            await readiness(db)
            await require_efs_feature_ready(db,tenant,invoice.id)
            if settlement.invoice_id!=invoice.id or settlement.tenant_id!=tenant.id or allocatable_balance(settlement)<=0 or settlement.unapplied_credit>0 or settlement.refund_pending>0:
                return False,'No additional EFS payment is available for this invoice.'
            lane=EfsAdmission(tenant.id,invoice.id,settlement.customer_id,None,'',_SEAL)
            await require_standard_payment(db,invoice,new_entry=True,efs_proof=lane)
        return True,None
    except (SettlementDomainError,crypto.EfsCryptoUnavailable):
        return False,'EFS is unavailable for this invoice. Contact the shop.'

async def unapplied_review(db,tenant_id,invoice_id):
    return bool(await db.scalar(select(Attempt.id).join(Settlement,Settlement.id==Attempt.settlement_id).where(Attempt.tenant_id==tenant_id,Attempt.invoice_id==invoice_id,Attempt.source==SOURCE,Attempt.unapplied_amount>0,Settlement.tenant_id==tenant_id,(Settlement.unapplied_credit>0)|(Settlement.refund_pending>0)).limit(1)))

def manual_payment_lane(proof,invoice,attempt=None):
    if isinstance(proof,EfsAdmission):
        return proof.seal is _SEAL and proof.tenant_id==invoice.tenant_id and proof.invoice_id==invoice.id
    return isinstance(proof,EfsReceiptProof) and proof.seal is _SEAL and attempt is not None and proof.tenant_id==invoice.tenant_id and proof.attempt_id==attempt.id and attempt.invoice_id==invoice.id


async def guard_disposition_text(db,attempt,*values):
    """Keep the protected bearer out of later refund/credit audit fields."""
    if attempt is None or not protected(attempt):return
    try:code=crypto.decrypt(await claim_for(db,attempt))
    except crypto.EfsCryptoUnavailable:fail('efs_unavailable','EFS is unavailable. Contact the shop.',503)
    reject_secret(code,*values)
